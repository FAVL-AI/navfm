"""The Yahboom Navigation State experience: runtime, panel, and replay.

Architecture, and why it is split this way
------------------------------------------

Three layers, each testable without the one above it:

``navstate.py``      the START / CURRENT / GOAL contract. No Isaac imports, so
                     the sealing rules run in CI on CPU.
``YahboomRuntime``   everything that touches the simulator: robot, camera, TF,
                     control, capture, record. **Fully headless-capable** and
                     driven by ordinary method calls, so the entire operator
                     workflow -- capture start, seal goal, reset, run, record,
                     replay -- can be exercised with no window and no human.
``YahboomNavigationStatePanel``
                     an ``omni.ui`` view over the runtime. It reads state and
                     calls runtime methods. It holds no state of its own.

The split exists because a UI that owns state cannot be tested, and an operator
interface that only works when someone is watching cannot be regression-tested
at all. Every acceptance criterion for this feature is therefore expressible as
a headless call sequence; the panel is the part a human uses, not the part the
guarantees live in.

Two rules the layering enforces
-------------------------------

**Viewing is not acting.** ``view_state()`` changes what the panel displays and
touches the simulator not at all. Moving the robot requires ``reset_to_start()``
or a control command, which are separate methods with separate buttons. An
inspection click that teleports the experiment is a defect that looks like a
feature until someone loses a run to it.

**The goal pose never reaches the policy.** ViNT receives the front RGB history
and the sealed goal *image*. The goal *pose* is read only by
``distance_to_goal()`` for logging and evaluation. This is enforced in
``navstate.GoalState`` by giving the two things separate accessors.

Headless versus windowed
------------------------

Everything works headless except keyboard teleoperation: ``carb.input`` receives
no events without a window, and this module says so rather than silently doing
nothing when you press W. Programmatic driving (``drive(vx, vy, w)``) is the
headless equivalent and is what the self-test uses.
"""

from __future__ import annotations

import contextlib
import json
import math
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from navfm.isaac.navstate import (
    EpisodeRecorder,
    EpisodeReplay,
    GoalSealedError,
    NavigationEpisode,
    Pose2D,
    StateSnapshot,
    TransformRecord,
    sha256_file,
)

__all__ = [
    "ControlMode",
    "PanelMode",
    "YahboomNavigationStatePanel",
    "YahboomRuntime",
    "mecanum_wheel_velocities",
]

ROBOT_PRIM = "/World/YahboomM3Pro"
CAMERA_PRIM = f"{ROBOT_PRIM}/camera_link/front_rgb_camera"

#: Provisional simulation geometry. See the calibration ledger -- none is a
#: caliper measurement, and the wheel radius in particular was X3-contaminated
#: upstream before correction.
WHEEL_RADIUS_M = 0.040
HALF_WHEELBASE_M = 0.0775
HALF_TRACK_M = 0.085

METRIC_WAYPOINT_SPACING = 0.12
EXECUTED_WAYPOINT_INDEX = 2
CONTROL_HZ = 4.0


class PanelMode:
    LIVE = "LIVE"
    REPLAY = "REPLAY"


class ControlMode:
    STOPPED = "STOPPED"
    MANUAL = "MANUAL"
    VINT = "ViNT"


def mecanum_wheel_velocities(
    vx: float, vy: float, wz: float, *, radius: float = WHEEL_RADIUS_M,
    half_wheelbase: float = HALF_WHEELBASE_M, half_track: float = HALF_TRACK_M,
) -> tuple[float, float, float, float]:
    """Body twist -> (fl, fr, rl, rr) wheel angular velocities, rad/s.

    Isaac ships ``HolonomicController`` for exactly this, and it is NOT used
    here for a specific reason: in this install (isaacsim.robot.wheeled_robots
    4.0.24) its constructor writes ``self.max_wheel_speed = (max_wheel_speed,)``
    -- a stray trailing comma making a 1-tuple, which is then compared against a
    float in its own saturation branch. Rather than depend on that and hope the
    branch is never taken, the arithmetic is here, in eight lines, tested.

    Pure arithmetic, deliberately outside the runtime so it is testable without
    a simulator. ``radius`` divides, so it converts wheel rotation into ground
    distance: a wrong value rescales every command silently, which is exactly
    the X3 contamination this project already found once.
    """
    if radius <= 0:
        raise ValueError(f"wheel radius must be positive; got {radius!r}")
    k = half_wheelbase + half_track
    return (
        (vx - vy - k * wz) / radius,
        (vx + vy + k * wz) / radius,
        (vx + vy - k * wz) / radius,
        (vx - vy + k * wz) / radius,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class YahboomRuntime:
    """Simulator-facing state and actions. Headless-capable; the panel is optional.

    Isaac imports are deferred into methods so this module can be imported, and
    partially unit-tested, in an environment without Isaac Sim.
    """

    def __init__(
        self,
        *,
        robot_prim: str = ROBOT_PRIM,
        camera_prim: str = CAMERA_PRIM,
        out_root: str | Path | None = None,
        scene: str = "",
    ) -> None:
        self.robot_prim = robot_prim
        self.camera_prim = camera_prim
        self.scene = scene
        self.out_root = Path(out_root) if out_root else Path.home() / "navfm-data" / "simulation_development"
        self.out_root.mkdir(parents=True, exist_ok=True)

        self.panel_mode = PanelMode.LIVE
        self.control_mode = ControlMode.STOPPED
        self.viewing = "CURRENT"

        self.episode = NavigationEpisode("episode_0001", scene=scene, robot="yahboom_m3_pro")
        self.recorder: EpisodeRecorder | None = None
        self.replay: EpisodeReplay | None = None
        self.replay_frame = 0

        # Bound by attach(). Typed Any because their real types live in Isaac,
        # which is not importable in the environment where this is type-checked.
        self._sim: Any = None
        self._robot: Any = None
        self._rgb_annotator: Any = None
        self._dof_names: list[str] = []
        self._wheel_dofs: list[int] = []
        self._commanded = (0.0, 0.0, 0.0)
        self._last_pose: Pose2D | None = None
        self._achieved = (0.0, 0.0, 0.0)
        self._frame = 0
        self._vint: Any = None
        self._vint_cfg: dict[str, Any] = {}
        self._obs_history: list[Any] = []
        self._episode_dir: Path | None = None

    # ---------------------------------------------------------------- setup
    def attach(self, simulation_context: Any, articulation: Any, rgb_annotator: Any) -> None:
        """Bind to a live stage. Kept separate from __init__ so the runtime can
        be constructed and inspected before Isaac exists."""
        self._sim = simulation_context
        self._robot = articulation
        self._rgb_annotator = rgb_annotator
        self._dof_names = list(getattr(articulation, "dof_names", None) or [])
        self._wheel_dofs = [i for i, n in enumerate(self._dof_names) if "wheel" in n.lower()]
        self._configure_wheel_drives()

    def _configure_wheel_drives(self) -> None:
        """Velocity control needs a velocity drive.

        A URDF whose joints declare no dynamics imports with zero stiffness AND
        zero damping. A velocity target is then accepted, logged, and produces no
        torque: the robot stands still while the record says 0.45 m/s. That
        produced a perfectly well-formed 40-frame trajectory of a stationary
        robot once already. kp=0 (no position servo), kd high (track velocity).
        """
        import numpy as np

        if self._robot is None or not self._dof_names:
            return
        n = len(self._dof_names)
        kps = np.zeros((1, n), dtype=np.float32)
        kds = np.zeros((1, n), dtype=np.float32)
        for i in self._wheel_dofs:
            kds[0, i] = 1.0e4
        with contextlib.suppress(Exception):  # version drift; not fatal
            self._robot.set_gains(kps=kps, kds=kds)

    # ----------------------------------------------------------------- read
    def pose(self) -> Pose2D:
        import numpy as np

        pos, quat = self._robot.get_world_poses()
        p = np.asarray(pos[0], dtype=np.float64)
        w, x, y, z = (float(v) for v in np.asarray(quat[0], dtype=np.float64))
        yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
        return Pose2D(float(p[0]), float(p[1]), yaw)

    def rgb(self):
        """One frame from the robot-mounted top-arm camera. Never a world camera."""
        import numpy as np

        arr = np.asarray(self._rgb_annotator.get_data())
        if arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[:, :, :3]
        return arr.astype(np.uint8)

    def transforms(self) -> tuple[TransformRecord, ...]:
        """The runtime hierarchy, read from the stage.

        Not a hand-written list: a hand-written list stays correct only until the
        asset changes, and then describes a robot that no longer exists.
        """
        from isaacsim.core.utils import stage as stage_utils
        from pxr import UsdGeom, UsdPhysics

        stage = stage_utils.get_current_stage()
        out: list[TransformRecord] = []
        joint_parent: dict[str, str] = {}
        joint_kind: dict[str, str] = {}
        for prim in stage.Traverse():
            if not str(prim.GetPath()).startswith(self.robot_prim):
                continue
            if "Joint" in str(prim.GetTypeName()):
                try:
                    j = UsdPhysics.Joint(prim)
                    b0 = j.GetBody0Rel().GetTargets()
                    b1 = j.GetBody1Rel().GetTargets()
                    if b0 and b1:
                        child, parent = Path(str(b1[0])).name, Path(str(b0[0])).name
                        joint_parent[child] = parent
                        joint_kind[child] = str(prim.GetTypeName())
                except Exception:
                    continue
        for prim in stage.Traverse():
            path = str(prim.GetPath())
            if not path.startswith(self.robot_prim) or "Joint" in str(prim.GetTypeName()):
                continue
            xf = UsdGeom.Xformable(prim)
            if not xf:
                continue
            name = prim.GetName()
            m = xf.ComputeLocalToWorldTransform(0)
            t = m.ExtractTranslation()
            r = m.ExtractRotation().Decompose((1, 0, 0), (0, 1, 0), (0, 0, 1))
            kind = joint_kind.get(name, "")
            out.append(
                TransformRecord(
                    frame=name,
                    parent=joint_parent.get(name, "World" if name == Path(self.robot_prim).name else "?"),
                    translation=(float(t[0]), float(t[1]), float(t[2])),
                    rotation_rpy=(math.radians(r[0]), math.radians(r[1]), math.radians(r[2])),
                    is_static="Revolute" not in kind and "Prismatic" not in kind,
                    source=kind or "usd xform",
                )
            )
        return tuple(sorted(out, key=lambda x: x.frame))

    def camera_report(self) -> dict[str, Any]:
        """Camera validity from MEASURED geometry, never from a link's name.

        A prim called ``top_arm_mount`` sitting at chassis height passed an
        earlier version of this check. Height is the evidence; the name is not.
        """
        from isaacsim.core.utils import stage as stage_utils
        from pxr import UsdGeom

        stage = stage_utils.get_current_stage()
        cam = stage.GetPrimAtPath(self.camera_prim)
        base = stage.GetPrimAtPath(f"{self.robot_prim}/base_link")
        if not cam or not base:
            return {"valid": False, "reason": "camera or base_link prim missing"}
        cw = UsdGeom.Xformable(cam).ComputeLocalToWorldTransform(0).ExtractTranslation()
        bw = UsdGeom.Xformable(base).ComputeLocalToWorldTransform(0).ExtractTranslation()
        above = float(cw[2]) - float(bw[2])
        return {
            "prim": self.camera_prim,
            "mount": "yahboom_top_arm",
            "world_height_m": float(cw[2]),
            "height_above_base_link_m": above,
            "above_chassis": above > 0.15,
            "valid": above > 0.15,
            "calibration_status": "PROVISIONAL_SIMULATION",
            "note": "validity is measured from the transform, not inferred from the parent's name",
        }

    # --------------------------------------------------------------- action
    def drive(self, vx: float, vy: float, wz: float) -> None:
        """Command a body twist. The programmatic equivalent of pressing WASD."""
        import numpy as np

        from navfm.control import M3PRO_LIMITS

        vx, vy, wz = M3PRO_LIMITS.clamp(vx, vy, wz)
        self._commanded = (vx, vy, wz)
        fl, fr, rl, rr = mecanum_wheel_velocities(vx, vy, wz)
        cmd = np.zeros(len(self._dof_names), dtype=np.float32)
        for i, n in enumerate(self._dof_names):
            low = n.lower()
            for key, val in (("fl", fl), ("fr", fr), ("rl", rl), ("rr", rr)):
                if low.startswith(key):
                    cmd[i] = val
        self._robot.set_joint_velocity_targets(cmd[None, :])

    def stop(self) -> None:
        self.drive(0.0, 0.0, 0.0)

    def step(self, n: int = 1, *, render: bool = True) -> None:
        for _ in range(n):
            self._sim.step(render=render)

    def teleport(self, pose: Pose2D, *, settle_steps: int = 20) -> None:
        """Explicitly move the robot. Never called by a view action."""
        import numpy as np

        self.stop()
        q = np.array([[math.cos(pose.yaw / 2), 0.0, 0.0, math.sin(pose.yaw / 2)]], dtype=np.float32)
        self._robot.set_world_poses(np.array([[pose.x, pose.y, 0.05]], dtype=np.float32), q)
        self._robot.set_joint_velocities(np.zeros((1, len(self._dof_names)), dtype=np.float32))
        self.step(settle_steps)

    # -------------------------------------------------------------- capture
    def _snapshot(self, label: str, image_dir: Path | None = None) -> StateSnapshot:
        img_path = img_sha = None
        if image_dir is not None:
            from PIL import Image as PILImage

            image_dir.mkdir(parents=True, exist_ok=True)
            p = image_dir / f"{label.lower()}.jpg"
            PILImage.fromarray(self.rgb()).save(p, quality=95)
            img_path, img_sha = str(p), sha256_file(p)
        return StateSnapshot(
            label=label, pose=self.pose(), image_path=img_path, image_sha256=img_sha,
            transforms=self.transforms(), timestamp_utc=_now(),
        )

    def episode_dir(self) -> Path:
        if self._episode_dir is None:
            self._episode_dir = self.out_root / self.episode.episode_id
            self._episode_dir.mkdir(parents=True, exist_ok=True)
        return self._episode_dir

    def capture_start(self) -> StateSnapshot:
        ok, why = self.episode.can_capture_start()
        if not ok:
            raise GoalSealedError(why)
        return self.episode.capture_start(self._snapshot("START", self.episode_dir() / "raw"))

    def capture_goal(self) -> Any:
        ok, why = self.episode.can_seal_goal()
        if not ok:
            raise GoalSealedError(why)
        return self.episode.seal_goal(self._snapshot("GOAL", self.episode_dir() / "raw"))

    def reset_to_start(self) -> Pose2D:
        """An explicit control action, deliberately not reachable from VIEW START."""
        ok, why = self.episode.can_reset_to_start()
        if not ok:
            raise GoalSealedError(why)
        assert self.episode.start is not None
        self.teleport(self.episode.start.pose)
        return self.pose()

    def view_state(self, which: str) -> str:
        """DISPLAY ONLY. Touches nothing in the simulator, by construction."""
        if which not in ("START", "CURRENT", "GOAL"):
            raise ValueError(f"unknown state {which!r}")
        self.viewing = which
        return self.viewing

    # ------------------------------------------------------------ recording
    def start_recording(self) -> None:
        self.episode.require_ready()
        self.recorder = EpisodeRecorder(self.episode, self.episode_dir())
        self._frame = 0

    def stop_recording(self) -> Path | None:
        if self.recorder is None:
            return None
        path = self.recorder.finalise()
        self.recorder = None
        return path

    def tick(self) -> StateSnapshot:
        """Advance CURRENT by one control step and record it if recording."""
        from PIL import Image as PILImage

        pose = self.pose()
        img_path = img_sha = None
        if self.recorder is not None:
            p = self.episode_dir() / f"{self._frame}.jpg"
            PILImage.fromarray(self.rgb()).save(p, quality=95)
            img_path, img_sha = str(p), sha256_file(p)

        if self._last_pose is not None:
            dt = 1.0 / CONTROL_HZ
            self._achieved = (
                math.hypot(pose.x - self._last_pose.x, pose.y - self._last_pose.y) / dt,
                0.0,
                self._last_pose.heading_error_to(pose) / dt,
            )
        self._last_pose = pose

        snap = StateSnapshot(
            label="CURRENT", pose=pose, image_path=img_path, image_sha256=img_sha,
            transforms=self.transforms(), timestamp_utc=_now(),
        )
        snap = self.episode.update_current(snap)
        if self.recorder is not None:
            self.recorder.record_step(
                snap, control_mode=self.control_mode,
                commanded=self._commanded, achieved=self._achieved,
                policy_output=getattr(self, "_last_policy_output", None),
            )
            self._frame += 1
        return snap

    # ----------------------------------------------------------------- ViNT
    def load_vint(self, checkpoint: str | Path) -> None:
        """CPU deliberately: a PyTorch CUDA context beside Isaac's RTX renderer
        segfaults this build reproducibly, at the first inference."""
        import torch

        from navfm import upstream
        from navfm.models.loader import extract_state_dict, load_checkpoint

        self._vint_cfg = upstream.model_config("vint")
        model = upstream.build_model("vint")
        model.load_state_dict(
            extract_state_dict(load_checkpoint(checkpoint, trust_checkpoint=True)), strict=True
        )
        torch.set_num_threads(8)
        self._vint = model.to("cpu").eval()

    def vint_step(self) -> tuple[float, float, float]:
        """One closed-loop step. Sees images only -- never the goal pose."""
        import torch
        from PIL import Image as PILImage
        from vint_train.data.data_utils import resize_and_aspect_crop

        from navfm.control import (
            M3PRO_LIMITS,
            BaseKinematics,
            PDConfig,
            unnormalise_waypoint,
            waypoint_to_twist,
        )

        self.episode.require_ready()
        assert self.episode.goal is not None
        goal_path = self.episode.goal.policy_observation()  # image only, by design
        if goal_path is None:
            raise GoalSealedError("sealed goal carries no image")

        w, h = self._vint_cfg["image_size"]
        ctx = self._vint_cfg["context_size"]
        frame = self.rgb()
        if not self._obs_history:
            self._obs_history = [frame] * (ctx + 1)
        self._obs_history = [*self._obs_history, frame][-(ctx + 1):]

        obs = torch.cat([resize_and_aspect_crop(PILImage.fromarray(f), (w, h))
                         for f in self._obs_history], dim=0).unsqueeze(0)
        goal = resize_and_aspect_crop(PILImage.open(goal_path).convert("RGB"), (w, h)).unsqueeze(0)
        with torch.no_grad():
            dist, action = self._vint(obs, goal)
        wp_norm = action[0, EXECUTED_WAYPOINT_INDEX].cpu().numpy()
        wp_m = unnormalise_waypoint(wp_norm, metric_waypoint_spacing=METRIC_WAYPOINT_SPACING)
        wp_seq = [float(v) for v in wp_m]
        vx, vy, wz = waypoint_to_twist(
            wp_seq, M3PRO_LIMITS, PDConfig(dt=1.0 / CONTROL_HZ), kinematics=BaseKinematics.HOLONOMIC
        )
        self._last_policy_output = {
            "vint_dist": float(dist[0, 0]),
            "waypoint_normalised": [float(v) for v in wp_norm],
            "waypoint_metres": [float(v) for v in wp_m],
        }
        self.drive(vx, vy, wz)
        return vx, vy, wz

    # --------------------------------------------------------------- replay
    def load_replay(self, manifest: str | Path) -> EpisodeReplay:
        self.replay = EpisodeReplay(manifest)
        self.replay_frame = 0
        self.panel_mode = PanelMode.REPLAY
        return self.replay

    def replay_at(self, frame: int) -> dict[str, Any]:
        if self.replay is None:
            raise RuntimeError("no recording loaded")
        self.replay_frame = max(0, min(int(frame), len(self.replay) - 1))
        return self.replay.at(self.replay_frame)

    # --------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:
        pose = self.pose() if self._robot is not None else None
        ok_run, why_run = self.episode.can_run()
        return {
            "panel_mode": self.panel_mode,
            "control_mode": self.control_mode,
            "viewing": self.viewing,
            "x": pose.x if pose else None,
            "y": pose.y if pose else None,
            "yaw": pose.yaw if pose else None,
            "commanded_vx_vy_w": list(self._commanded),
            "achieved_vx_vy_w": list(self._achieved),
            "frame": self._frame,
            "recording": self.recorder is not None,
            "goal_sealed": self.episode.is_sealed,
            "start_captured": self.episode.start is not None,
            "can_run": ok_run,
            "can_run_reason": why_run,
            "distance_to_goal_m": self.episode.distance_to_goal(),
            "episode_id": self.episode.episode_id,
        }

    # ------------------------------------------------------------- export
    def export_option1(self) -> Path:
        """Model-ready trajectory beside the research provenance, never inside it."""
        import pickle

        import numpy as np

        d = self.episode_dir()
        hist = self.episode.history
        pos = np.array([[s.pose.x, s.pose.y] for s in hist], dtype=np.float64)
        yaw = np.unwrap(np.array([s.pose.yaw for s in hist], dtype=np.float64))
        with open(d / "traj_data.pkl", "wb") as fh:
            pickle.dump({"position": pos, "yaw": yaw}, fh)
        cam = self.camera_report()
        (d / "raw").mkdir(exist_ok=True)
        (d / "raw" / "metadata.json").write_text(
            json.dumps(
                {
                    "stage": "SIMULATION_DEVELOPMENT", "admission_status": "NOT_ADMITTED",
                    "training_allowed": False, "final_evaluation_allowed": False,
                    "source": "ISAAC_SIM", "source_policy": self.control_mode,
                    "robot": "Yahboom ROSMASTER M3 Pro digital twin",
                    "camera": cam, "scene": self.scene,
                    "goal_image_sha256": self.episode.goal.image_sha256 if self.episode.goal else None,
                    "frames": len(hist),
                },
                indent=2,
            )
            + "\n"
        )
        return d


class YahboomNavigationStatePanel:
    """The dockable panel. A view: it reads runtime state and calls runtime methods.

    Holds no state of its own, so nothing can be true in the UI and false in the
    simulator. Every callback is a direct method call that returns immediately --
    stepping physics from a UI callback would block the editor and make the panel
    feel broken while the simulation ran.
    """

    WINDOW_TITLE = "Yahboom Navigation State"

    def __init__(self, runtime: YahboomRuntime) -> None:
        self.runtime = runtime
        self._window: Any = None
        self._labels: dict[str, Any] = {}
        self._image_provider = None
        self._image_widget = None
        self._keyboard_sub = None
        self._keyboard = None
        self._pressed: set[str] = set()
        self.available = False

    # ------------------------------------------------------------------ ui
    def build(self) -> bool:
        """Build the window. Returns False headless rather than raising."""
        try:
            import omni.ui as ui
        except Exception:
            return False

        self._window = ui.Window(self.WINDOW_TITLE, width=420, height=760)
        # dockPreference is accepted but INERT in Kit 107 -- omni/ui/_ui.pyi:11397
        # says so outright ("In Kit Next it's unused"). deferred_dock_in is what
        # actually docks, and it works even before the target window exists.
        with contextlib.suppress(Exception):
            self._window.deferred_dock_in("Viewport", ui.DockPolicy.CURRENT_WINDOW_IS_ACTIVE)
        with self._window.frame, ui.VStack(spacing=6, height=0):
            self._section_modes(ui)
            ui.Line()
            self._section_state(ui)
            ui.Line()
            self._section_camera(ui)
            ui.Line()
            self._section_capture(ui)
            ui.Line()
            self._section_recording(ui)
            ui.Line()
            self._section_tf(ui)
        self.available = True
        return True

    def _section_modes(self, ui: Any) -> None:
        ui.Label("MODE", height=18)
        with ui.HStack(height=26, spacing=4):
            ui.Button("LIVE", clicked_fn=lambda: self._set_panel_mode(PanelMode.LIVE))
            ui.Button("REPLAY", clicked_fn=lambda: self._set_panel_mode(PanelMode.REPLAY))
        with ui.HStack(height=26, spacing=4):
            ui.Button("STOPPED", clicked_fn=lambda: self._set_control(ControlMode.STOPPED))
            ui.Button("MANUAL", clicked_fn=lambda: self._set_control(ControlMode.MANUAL))
            ui.Button("ViNT", clicked_fn=lambda: self._set_control(ControlMode.VINT))
        self._labels["mode"] = ui.Label("", height=18)

    def _section_state(self, ui: Any) -> None:
        ui.Label("VIEW  (display only -- never moves the robot)", height=18)
        with ui.HStack(height=26, spacing=4):
            ui.Button("START", clicked_fn=lambda: self._view("START"))
            ui.Button("CURRENT", clicked_fn=lambda: self._view("CURRENT"))
            ui.Button("GOAL", clicked_fn=lambda: self._view("GOAL"))
        for key in ("pose", "vel", "goal", "frame"):
            self._labels[key] = ui.Label("", height=18)

    def _section_camera(self, ui: Any) -> None:
        ui.Label("TOP-ARM FRONT RGB  (the navigation observation)", height=18)
        try:
            self._image_provider = ui.ByteImageProvider()
            self._image_widget = ui.ImageWithProvider(self._image_provider, height=180)
        except Exception:
            self._image_provider = None
        self._labels["camera"] = ui.Label("", height=18, word_wrap=True)

    def _section_capture(self, ui: Any) -> None:
        ui.Label("EPISODE", height=18)
        with ui.HStack(height=26, spacing=4):
            ui.Button("CAPTURE START", clicked_fn=self._capture_start)
            ui.Button("CAPTURE GOAL", clicked_fn=self._capture_goal)
        with ui.HStack(height=26, spacing=4):
            ui.Button("RESET ROBOT TO START", clicked_fn=self._reset_to_start)
        self._labels["episode"] = ui.Label("", height=18, word_wrap=True)

    def _section_recording(self, ui: Any) -> None:
        ui.Label("RECORDING", height=18)
        with ui.HStack(height=26, spacing=4):
            ui.Button("START RECORDING", clicked_fn=self._start_recording)
            ui.Button("STOP RECORDING", clicked_fn=self._stop_recording)
        self._labels["recording"] = ui.Label("", height=18, word_wrap=True)

    def _section_tf(self, ui: Any) -> None:
        ui.Label("TRANSFORM TREE", height=18)
        with ui.ScrollingFrame(height=180):
            self._labels["tf"] = ui.Label("", word_wrap=True)

    # ----------------------------------------------------------- callbacks
    def _set_panel_mode(self, mode: str) -> None:
        self.runtime.panel_mode = mode

    def _set_control(self, mode: str) -> None:
        self.runtime.control_mode = mode
        if mode == ControlMode.STOPPED:
            try:
                self.runtime.stop()
            except Exception as exc:
                self._say("episode", f"stop failed: {exc}")

    def _view(self, which: str) -> None:
        """Display only. Deliberately cannot reach teleport()."""
        self.runtime.view_state(which)

    def _capture_start(self) -> None:
        try:
            s = self.runtime.capture_start()
            self._say("episode", f"START captured at ({s.pose.x:.2f}, {s.pose.y:.2f})")
        except GoalSealedError as exc:
            self._say("episode", f"refused: {exc}")

    def _capture_goal(self) -> None:
        try:
            g = self.runtime.capture_goal()
            self._say("episode", f"GOAL SEALED  digest {(g.image_sha256 or '')[:16]}")
        except GoalSealedError as exc:
            self._say("episode", f"refused: {exc}")

    def _reset_to_start(self) -> None:
        try:
            p = self.runtime.reset_to_start()
            self._say("episode", f"reset to ({p.x:.2f}, {p.y:.2f}, {math.degrees(p.yaw):.1f} deg)")
        except GoalSealedError as exc:
            self._say("episode", f"refused: {exc}")

    def _start_recording(self) -> None:
        try:
            self.runtime.start_recording()
            self._say("recording", "recording")
        except GoalSealedError as exc:
            self._say("recording", f"refused: {exc}")

    def _stop_recording(self) -> None:
        path = self.runtime.stop_recording()
        self._say("recording", f"saved {path}" if path else "not recording")

    # ------------------------------------------------------------ keyboard
    def attach_keyboard(self) -> bool:
        """WASDQE teleoperation. Windowed sessions only.

        ``carb.input`` delivers nothing without a window, so this returns False
        headless rather than installing a handler that silently never fires --
        a key that does nothing is worse than a key that is documented as absent.
        """
        try:
            import carb.input
            import omni.appwindow
        except Exception:
            return False
        try:
            self._keyboard = omni.appwindow.get_default_app_window().get_keyboard()
            self._keyboard_sub = carb.input.acquire_input_interface().subscribe_to_keyboard_events(
                self._keyboard, self._on_keyboard_event
            )
        except Exception:
            return False
        return True

    def _on_keyboard_event(self, event: Any, *_: Any) -> bool:
        import carb.input

        name = getattr(event.input, "name", str(event.input))
        if event.type == carb.input.KeyboardEventType.KEY_PRESS:
            self._pressed.add(name)
        elif event.type == carb.input.KeyboardEventType.KEY_RELEASE:
            self._pressed.discard(name)
        if name == "SPACE":
            self._pressed.clear()
        return True

    def keyboard_twist(self, *, v: float = 0.35, vy: float = 0.25, w: float = 0.9) -> tuple[float, float, float]:
        """Held keys -> body twist. Pure, so it is unit-testable without a window."""
        p = self._pressed
        return (
            (v if "W" in p else 0.0) - (v if "S" in p else 0.0),
            (vy if "Q" in p else 0.0) - (vy if "E" in p else 0.0),
            (w if "A" in p else 0.0) - (w if "D" in p else 0.0),
        )

    # --------------------------------------------------------------- update
    def _say(self, key: str, text: str) -> None:
        lab = self._labels.get(key)
        if lab is not None:
            lab.text = text

    def update(self) -> None:
        """Refresh the view. Never steps physics -- the caller owns the loop."""
        if not self.available:
            return
        try:
            st = self.runtime.status()
        except Exception as exc:
            self._say("mode", f"runtime unavailable: {exc}")
            return
        self._say("mode", f"{st['panel_mode']} | {st['control_mode']} | viewing {st['viewing']}")
        if st["x"] is not None:
            self._say("pose", f"x {st['x']:+.3f}   y {st['y']:+.3f}   yaw {math.degrees(st['yaw']):+.1f} deg")
        c, a = st["commanded_vx_vy_w"], st["achieved_vx_vy_w"]
        self._say("vel", f"cmd {c[0]:+.2f}/{c[1]:+.2f}/{c[2]:+.2f}   achieved {a[0]:+.2f}/{a[1]:+.2f}/{a[2]:+.2f}")
        d = st["distance_to_goal_m"]
        self._say(
            "goal",
            f"start {'yes' if st['start_captured'] else 'no'} | goal "
            f"{'SEALED' if st['goal_sealed'] else 'not sealed'}"
            + (f" | {d:.2f} m away" if d is not None else ""),
        )
        self._say("frame", f"frame {st['frame']} | {'RECORDING' if st['recording'] else 'idle'}")
        try:
            cam = self.runtime.camera_report()
            self._say(
                "camera",
                f"{cam.get('mount')} @ {cam.get('world_height_m', 0):.3f} m "
                f"({cam.get('height_above_base_link_m', 0):.3f} above base) "
                f"{'OK' if cam.get('valid') else 'INVALID -- not above chassis'}",
            )
        except Exception:
            pass
        self._push_image()
        self._push_tf()

    def _push_image(self) -> None:
        if self._image_provider is None:
            return
        try:
            import numpy as np

            rgb = self.runtime.rgb()
            rgba = np.dstack([rgb, np.full(rgb.shape[:2], 255, dtype=np.uint8)])
            h, w = rgba.shape[:2]
            # sizes is [WIDTH, HEIGHT] -- the opposite order to numpy's (H, W, 4).
            # set_data_array takes the uint8 array directly and avoids a
            # per-frame .tolist() over ~300k ints; set_data is deprecated in this
            # build and its own .so says so.
            flat = np.ascontiguousarray(rgba).reshape(-1)
            if hasattr(self._image_provider, "set_data_array"):
                self._image_provider.set_data_array(flat, [w, h])
            else:
                self._image_provider.set_bytes_data(flat.tolist(), [w, h])
        except Exception:
            pass

    def _push_tf(self) -> None:
        try:
            rows = self.runtime.transforms()
        except Exception:
            return
        lines = [
            f"{t.frame:<22} <- {t.parent:<16} "
            f"({t.translation[0]:+.3f},{t.translation[1]:+.3f},{t.translation[2]:+.3f}) "
            f"{'fixed' if t.is_static else 'moving'}"
            for t in rows
        ]
        self._say("tf", "\n".join(lines) if lines else "(no frames)")

    def destroy(self) -> None:
        if self._keyboard_sub is not None:
            try:
                import carb.input

                # unsubscribe_TO, not unsubscribe_from -- the latter does not
                # exist here and AttributeErrors. It needs BOTH the keyboard
                # device and the int handle.
                carb.input.acquire_input_interface().unsubscribe_to_keyboard_events(
                    self._keyboard, self._keyboard_sub
                )
            except Exception:
                pass
            self._keyboard_sub = None
        if self._window is not None:
            self._window.destroy()
            self._window = None
        self.available = False


def run_operator_workflow(
    runtime: YahboomRuntime,
    *,
    start_pose: Pose2D,
    goal_pose: Pose2D,
    steps: int = 40,
    on_step: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """The full workflow, headless: drive, capture, seal, reset, run, record.

    This is the acceptance test. Running it without a window is the point -- an
    operator interface whose guarantees only hold when someone is watching
    cannot be regression-tested.
    """
    runtime.teleport(start_pose)
    runtime.capture_start()
    runtime.teleport(goal_pose)
    runtime.capture_goal()
    runtime.teleport(start_pose)
    runtime.reset_to_start()
    runtime.start_recording()
    runtime.control_mode = ControlMode.VINT
    for i in range(steps):
        runtime.vint_step()
        runtime.step(int(60 / CONTROL_HZ))
        runtime.tick()
        if on_step:
            on_step(i)
    runtime.stop()
    manifest = runtime.stop_recording()
    out = runtime.export_option1()
    return {"manifest": str(manifest), "trajectory_dir": str(out), "status": runtime.status()}
