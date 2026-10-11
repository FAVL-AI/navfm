"""ROSMASTER M3 PRO in Isaac Sim: base, camera rig, pose readout.

Two mecanum-specific decisions, both deliberate:

**1. The base is velocity-driven, not wheel-driven.** URDF has no
representation of mecanum rollers, and modelling 40 free-spinning rollers in
PhysX is both slow and numerically fragile at the contact patch. Since the data
we are collecting is ``(image, SE(2) pose)`` and the label pipeline only ever
reads the base pose, wheel-level fidelity buys nothing and costs stability. We
therefore command body-frame velocity on the articulation root and spin the
visual wheels kinematically. If a later experiment needs wheel slip, swap in
``isaacsim.robot.wheeled_robots`` ``HolonomicController`` -- the interface here
is the same.

**2. The camera is rigidly mounted, not on the arm.** The physical M3 PRO
carries its Orbbec DaBai DCW2 on the DOFBOT-PRO arm, so its extrinsics are a
function of six joint angles. A navigation dataset needs a *fixed* forward
camera -- the GNM format has no place to store a time-varying camera transform,
and the models assume a static viewpoint. We therefore lock the arm to a stowed
pose and treat the resulting camera transform as fixed, and we record it in the
trajectory metadata so it can be reproduced on hardware.

Camera intrinsics default to the DaBai DCW2 in its 4:3 mode (H-FOV 64 deg,
V-FOV 55 deg), not the 16:9 mode (86 x 55), because the GNM preprocessing
centre-crops to 4:3 -- capturing 16:9 would throw away a quarter of the width
and leave sim and real with different effective fields of view.
"""

from __future__ import annotations

import contextlib
import dataclasses
import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from ..control import M3PRO_LIMITS, BaseLimits

__all__ = ["M3PRO", "CameraRig", "RobotConfig", "SimRobot"]


@dataclasses.dataclass(frozen=True)
class CameraRig:
    """Forward-facing RGB camera extrinsics and intrinsics.

    ``x_offset``/``height`` mirror ``camera_metrics`` in the reference
    ``data_config.yaml`` and must match the physical mount for sim2real.
    Both are PROVISIONAL for the M3 PRO -- Yahboom publishes neither. Measure
    them from ``yahboomcar_description`` or the CAD bundle and update here.
    """

    x_offset: float = 0.16
    y_offset: float = 0.0
    height: float = 0.28
    pitch_deg: float = 0.0
    #: Horizontal FOV in the 4:3 capture mode.
    horizontal_fov_deg: float = 64.0
    resolution: tuple[int, int] = (640, 480)

    @property
    def focal_length_px(self) -> float:
        w = self.resolution[0]
        return 0.5 * w / math.tan(math.radians(self.horizontal_fov_deg) / 2.0)

    def camera_matrix(self) -> dict[str, float]:
        w, h = self.resolution
        f = self.focal_length_px
        return {"fx": f, "fy": f, "cx": w / 2.0, "cy": h / 2.0}

    def usd_focal_length(self, horizontal_aperture: float = 20.955) -> float:
        """Convert FOV to the USD camera's focal length, in stage units."""
        return horizontal_aperture / (2.0 * math.tan(math.radians(self.horizontal_fov_deg) / 2.0))


@dataclasses.dataclass(frozen=True)
class RobotConfig:
    name: str
    usd_path: str | None
    urdf_path: str | None
    limits: BaseLimits
    camera: CameraRig
    #: Radius of the circumscribed footprint, for collision checks in planning.
    footprint_radius: float = 0.24
    spawn_height: float = 0.06
    holonomic: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["camera"]["focal_length_px"] = self.camera.focal_length_px
        return d


#: PROVISIONAL geometry -- see docs/HARDWARE.md. ``footprint_radius`` is derived
#: from the 80 mm mecanum wheels plus a typical ROSMASTER chassis; Yahboom does
#: not publish wheelbase, track width, chassis dimensions or mass.
M3PRO = RobotConfig(
    name="m3pro",
    usd_path=None,  # set by --robot-usd once yahboomcar_description is converted
    urdf_path=None,
    limits=M3PRO_LIMITS,
    camera=CameraRig(),
    footprint_radius=0.24,
    holonomic=True,
)


class SimRobot:
    """Thin wrapper over an Isaac Sim articulation, exposing exactly what the
    collector needs: set body velocity, read ground-truth SE(2) pose, read RGB.

    Isaac imports are deferred so this module can be imported (and its config
    objects unit-tested) without Isaac Sim installed.
    """

    def __init__(
        self,
        app: Any,
        config: RobotConfig,
        *,
        prim_path: str = "/World/Robot",
        camera_prim: str = "Camera_front",
        camera_parent_link: str = "base_link",
    ) -> None:
        self.app = app
        self.config = config
        self.prim_path = prim_path
        # The camera hangs off the articulation's base LINK, not off the robot
        # root. The root is a plain xform that the reference was added under and
        # that physics never touches; the links beneath it are what move. A
        # camera parented to the root therefore stays where it was authored while
        # the robot drives away -- world-fixed in effect, whatever it is called.
        # G7 measured exactly that on 2026-09-09: the robot moved 2.236 m and the
        # camera moved 0.000 m, and every frame the collector wrote would have
        # been from a static viewpoint that never turned with the base.
        self.camera_parent_path = f"{prim_path}/{camera_parent_link}"
        self.camera_path = f"{self.camera_parent_path}/{camera_prim}"
        self._articulation: Any = None
        self._camera: Any = None
        self._is_v6 = False

    # -- construction ----------------------------------------------------

    def spawn(
        self, position: Sequence[float] | np.ndarray = (0.0, 0.0, 0.0), yaw: float = 0.0
    ) -> None:
        if not self.config.usd_path:
            raise ValueError(
                "RobotConfig.usd_path is unset. Convert yahboomcar_description to USD first:\n"
                "  python -m navfm.isaac.urdf_import --urdf .../yahboomcar.urdf "
                "--out assets/m3pro.usd --holonomic"
            )
        import isaacsim.core.experimental.utils.stage as stage_utils

        stage_utils.add_reference_to_stage(self.config.usd_path, path=self.prim_path)
        self._attach()
        # An articulation is not addressable the instant its prim appears: the
        # physics tensor entity is created by the simulation, so teleport() --
        # which sets velocities -- asserts on 5.1 unless the timeline has
        # advanced at least one frame since the reference was added. Stepping
        # here rather than in every caller keeps spawn() a complete operation.
        self._settle()
        self.teleport(position, yaw)

    def _settle(self, frames: int = 3) -> None:
        """Advance the sim until the articulation's physics entity is valid."""
        app = getattr(self, "app", None)
        if app is None:
            return
        for _ in range(frames):
            with contextlib.suppress(Exception):
                app.update()
        valid = getattr(self._articulation, "is_physics_tensor_entity_valid", None)
        if callable(valid):
            for _ in range(frames):
                if valid():
                    return
                with contextlib.suppress(Exception):
                    app.update()

    def _attach(self) -> None:
        # 5.1 is the PRIMARY branch, so it is tried FIRST. Preferring the 6.0
        # experimental namespace here was wrong in a way that could not show up
        # until a real run: `isaacsim.core.experimental.prims` imports fine on
        # 5.1, so the fallback always won and the primary path was never used.
        # The two APIs differ -- 5.x set_velocities takes one (N, 6) array,
        # experimental takes linear and angular separately -- so the wrong choice
        # surfaces as a shape error deep inside a velocity command.
        try:
            from isaacsim.core.prims import Articulation

            self._articulation = Articulation(self.prim_path)
            self._is_v6 = False
        except ImportError:  # 6.0 experimental
            from isaacsim.core.experimental.prims import Articulation

            self._articulation = Articulation(self.prim_path)
            self._is_v6 = True

    def attach_camera(self) -> None:
        """Create the forward RGB sensor at the configured extrinsics."""
        cam = self.config.camera
        translation = [[cam.x_offset, cam.y_offset, cam.height]]
        try:
            from isaacsim.sensors.experimental.rtx import (
                CameraSensor,
                RtxCamera,
            )

            rtx = RtxCamera(
                self.camera_path,
                tick_rate=0.0,  # autotrigger: render on every stepped frame
                translations=translation,
            )
            self._camera = CameraSensor(rtx, resolution=cam.resolution, annotators=["rgb"])
            self._is_v6 = True
        except ImportError:  # Isaac Sim 5.x
            from isaacsim.sensors.camera import Camera

            self._camera = Camera(
                prim_path=self.camera_path,
                resolution=cam.resolution,
                translation=np.array(translation[0]),
            )
            self._camera.initialize()
            self._camera.add_motion_vectors_to_frame()
            self._is_v6 = False

    # -- state -----------------------------------------------------------

    def pose(self) -> tuple[np.ndarray, float]:
        """Ground-truth ``((x, y), yaw)`` in the world frame.

        Reads the articulation root pose, which is the exact quantity we want in
        ``traj_data.pkl``. Note this is *ground truth*, not wheel odometry. That
        is the right choice for training labels -- the reference datasets used
        filtered odometry and its drift is a known source of label noise -- but
        it does mean a sim-trained policy never sees odometry drift. Enable
        ``--odometry-noise`` in the collector to inject a calibrated drift model
        if you want that robustness.
        """
        from ..kinematics import yaw_from_quat_wxyz

        positions, orientations = self._articulation.get_world_poses()
        pos = np.asarray(positions).reshape(-1, 3)[0]
        quat = np.asarray(orientations).reshape(-1, 4)[0]  # wxyz
        return pos[:2].astype(np.float64), float(yaw_from_quat_wxyz(quat))

    def rgb(self) -> np.ndarray:
        """Latest RGB frame as ``H x W x 3`` uint8.

        Only valid immediately after ``IsaacApp.step()``, which blocks on
        render completion. Calling it at any other point risks pairing an image
        with a pose from a different instant.
        """
        if self._is_v6:
            data, _info = self._camera.get_data("rgb")
            arr = np.asarray(data)
        else:
            arr = np.asarray(self._camera.get_rgba())
        if arr.ndim == 4:
            arr = arr[0]
        if arr.shape[-1] == 4:
            arr = arr[..., :3]
        return np.ascontiguousarray(arr.astype(np.uint8))

    # -- actuation -------------------------------------------------------

    def teleport(self, position: Sequence[float] | np.ndarray, yaw: float) -> None:
        pos = np.asarray(position, dtype=np.float64).reshape(-1)
        if pos.shape[0] == 2:
            pos = np.array([pos[0], pos[1], self.config.spawn_height])
        half = 0.5 * float(yaw)
        quat = np.array([math.cos(half), 0.0, 0.0, math.sin(half)])  # wxyz about +z
        self._articulation.set_world_poses(
            positions=pos.reshape(1, 3), orientations=quat.reshape(1, 4)
        )
        self.set_body_velocity(0.0, 0.0, 0.0)

    def set_body_velocity(self, vx: float, vy: float, wz: float) -> None:
        """Command body-frame velocity, converting to the world frame for PhysX."""
        _pos, yaw = self.pose()
        vx, vy, wz = self.config.limits.clamp(vx, vy, wz)
        c, s = math.cos(yaw), math.sin(yaw)
        world = np.array([[c * vx - s * vy, s * vx + c * vy, 0.0]])
        angular = np.array([[0.0, 0.0, wz]])
        if self._is_v6:
            # 6.0 experimental takes linear and angular as separate (N, 3) arrays.
            self._articulation.set_velocities(world, angular)
        else:
            # 5.x takes a single (N, 6) array.
            self._articulation.set_velocities(np.concatenate([world, angular], axis=1))
