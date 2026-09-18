"""RGB-only ViNT in the hospital scene. An engineering demonstration, not a run.

This exists to make one sentence visible: the robot sees the hospital through
its camera, compares that view with a goal image, and ViNT predicts where to
move next. It is not the experiment, it produces no scientific sample, and
nothing it writes goes near the evidence tree.

Three things are deliberately absent rather than approximated. There is no
safety layer, because no HOCBF implementation exists in this repository and an
animated "safe" indicator over a policy that has none would be a lie told in
pictures. There is no CONTINUE/STOP verdict, because no stopping policy exists
either; ViNT's temporal distance is a genuine model output and is shown as
that, without a threshold nobody has chosen. And no depth, TOF or simulator
ground truth reaches the network -- pose is read for the overlay and the trace
and never enters the policy.

The robot asset is the superseded engineering twin, the one carrying the
F-TWIN-1 squared collider extents. It is used because the production asset does
not exist yet, and it is labelled on every frame and in the record so no
screenshot can later be mistaken for the validated twin.

Waypoint un-normalisation is the part that quietly ruins a demo like this: ViNT
predicts in units of the metric waypoint spacing, and feeding the raw
prediction to a controller expecting metres rescales every command by about
eight without raising anything. The conversion is imported from the tested
path rather than rewritten here.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "third_party" / "visualnav-transformer" / "train"))

HOSPITAL_USD = Path(
    "/home/favl/robotics/FleetSafe-VLA/assets/mirror/hospital_v1/hospital.usd")
ROBOT_USD = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd"
CKPT = REPO / "checkpoints/vint.pth"

METRIC_WAYPOINT_SPACING = 0.12
EXECUTED_WAYPOINT_INDEX = 2
CONTROL_HZ = 4.0

BANNER = "ENGINEERING DEMO - NOT SCIENTIFIC EVIDENCE - n=0"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(Path.home() / "navfm-demo"))
    ap.add_argument("--steps", type=int, default=40,
                    help="40 steps at 4 Hz is about ten seconds of motion")
    ap.add_argument("--start", type=float, nargs=3, default=[0.0, 0.0, 0.0])
    ap.add_argument("--goal", type=float, nargs=3, default=[2.0, 0.0, 0.0])
    args = ap.parse_args()

    out = Path(args.out) / datetime.now(UTC).strftime("demo_%Y%m%dT%H%M%SZ")
    (out / "frames").mkdir(parents=True, exist_ok=True)

    record: dict[str, object] = {
        "RUN_CLASS": "ENGINEERING_DEMO_ONLY",
        "SCIENTIFIC_ARM_A_N": 0,
        "ARM_A_ATTEMPT_003": "NOT_STARTED",
        "ARM_B": "NOT_STARTED",
        "NOT_SCIENTIFIC_EVIDENCE": (
            "this run produces no sample, no metric and no benchmark result. It "
            "may be used to explain and to debug, and for nothing else"),
        "started_at": datetime.now(UTC).isoformat(),
        "NAVIGATION_INPUT": "RGB_ONLY",
        "SAFETY_LAYER": "NOT_ACTIVE_IN_THIS_DEMO",
        "safety_note": ("no HOCBF or runtime-assurance implementation exists in "
                        "this repository, so none is shown"),
        "STOPPING_LAYER": "NOT_ACTIVE_IN_DEMO",
        "stopping_note": ("no stopping policy is implemented. ViNT's temporal "
                          "distance is a genuine model output and is displayed as "
                          "that, with no CONTINUE/STOP verdict attached"),
        "ROBOT_ASSET": "SUPERSEDED_ENGINEERING_ASSET",
        "SCIENTIFIC_USE": "PROHIBITED",
        "robot_asset_note": ("the superseded twin, carrying the F-TWIN-1 squared "
                             "collider extents. The production asset is not built"),
        "PHYSICAL_CAMERA_EXTRINSIC": "NOT_MEASURED",
    }

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True, "renderer": "RaytracedLighting"})

    import numpy as np
    import omni.replicator.core as rep
    import torch
    from isaacsim.core.api import SimulationContext
    from isaacsim.core.prims import Articulation
    from isaacsim.core.utils import stage as stage_utils
    from PIL import Image as PILImage
    from PIL import ImageDraw
    from pxr import Gf, UsdGeom

    import navfm.upstream as upstream
    from navfm.control import (
        M3PRO_LIMITS,
        BaseKinematics,
        PDConfig,
        unnormalise_waypoint,
        waypoint_to_twist,
    )
    from navfm.models.loader import extract_state_dict, load_checkpoint

    stage_utils.open_stage(str(HOSPITAL_USD))
    stage_utils.add_reference_to_stage(str(ROBOT_USD), "/World/YahboomM3Pro")
    record["scene_usd"] = str(HOSPITAL_USD)
    record["scene_usd_sha256"] = sha256_file(HOSPITAL_USD)
    record["robot_usd"] = str(ROBOT_USD.relative_to(REPO))
    record["robot_usd_sha256"] = sha256_file(ROBOT_USD)

    sim = SimulationContext(physics_dt=1.0 / 60.0, rendering_dt=1.0 / 60.0,
                            stage_units_in_meters=1.0)
    sim.initialize_physics()

    robot = Articulation("/World/YahboomM3Pro")
    robot.initialize()
    dof_names = list(robot.dof_names or [])
    wheel_dofs = [i for i, n in enumerate(dof_names) if "wheel" in n.lower()]
    # A URDF whose joints declare no dynamics imports with zero stiffness and
    # zero damping, so a velocity target is accepted, logged, and produces no
    # torque. The robot stands still while the trace reads 0.45 m/s.
    kps = np.zeros((1, len(dof_names)), dtype=np.float32)
    kds = np.zeros((1, len(dof_names)), dtype=np.float32)
    for i in wheel_dofs:
        kds[0, i] = 1.0e4
    robot.set_gains(kps=kps, kds=kds)
    with contextlib.suppress(Exception):
        robot.switch_control_mode("velocity")
    record["dof_count"] = len(dof_names)
    record["wheel_dof_count"] = len(wheel_dofs)

    cam_path = "/World/YahboomM3Pro/camera_link/front_rgb_camera"
    render_product = rep.create.render_product(cam_path, (320, 240))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach([render_product])
    record["camera_prim"] = cam_path

    def step(n: int) -> None:
        for _ in range(n):
            sim.step(render=True)

    def grab() -> np.ndarray:
        return np.asarray(rgb.get_data())[..., :3].copy()

    def teleport(x: float, y: float, yaw: float) -> None:
        prim = stage_utils.get_current_stage().GetPrimAtPath("/World/YahboomM3Pro")
        xf = UsdGeom.Xformable(prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(x, y, 0.0))
        xf.AddRotateZOp().Set(np.degrees(yaw))

    def base_pose() -> tuple[float, float, float]:
        pos, quat = robot.get_world_poses()
        x, y = float(pos[0][0]), float(pos[0][1])
        w, qx, qy, qz = (float(v) for v in quat[0])
        yaw = float(np.arctan2(2 * (w * qz + qx * qy),
                               1 - 2 * (qy * qy + qz * qz)))
        return x, y, yaw

    def set_twist(vx: float, vy: float, w: float) -> None:
        """Mecanum body twist to wheel angular velocities.

        Wheels are matched by DOF name prefix rather than by index, because the
        importer's DOF order is not the wheel order and a positional mapping
        would drive the machine sideways while every log looked correct. Same
        geometry and same matching as the tested pilot.
        """
        radius, half_length, half_width = 0.040, 0.0775, 0.085
        k = half_length + half_width
        order = {
            "fl": (vx - vy - k * w) / radius,
            "fr": (vx + vy + k * w) / radius,
            "rl": (vx + vy - k * w) / radius,
            "rr": (vx - vy + k * w) / radius,
        }
        command = np.zeros(len(dof_names), dtype=np.float32)
        for index, name in enumerate(dof_names):
            for prefix, value in order.items():
                if name.lower().startswith(prefix):
                    command[index] = value
        robot.set_joint_velocity_targets(command[None, :])

    device = "cuda" if torch.cuda.is_available() else "cpu"
    config = upstream.model_config("vint")
    model = upstream.build_model("vint")
    state = extract_state_dict(load_checkpoint(CKPT, trust_checkpoint=True))
    model.load_state_dict(state, strict=True)
    model = model.to(device).eval()
    record["model"] = "ViNT"
    record["checkpoint"] = str(CKPT.relative_to(REPO))
    record["checkpoint_sha256"] = sha256_file(CKPT)
    record["device"] = device
    record["context_size"] = int(config["context_size"])
    record["image_size"] = list(config["image_size"])
    record["MODEL_LOADED"] = True

    from vint_train.data.data_utils import resize_and_aspect_crop

    width, height = config["image_size"]

    def prep(array: np.ndarray) -> torch.Tensor:
        return resize_and_aspect_crop(PILImage.fromarray(array), (width, height))

    sx, sy, syaw = args.start
    gx, gy, gyaw = args.goal

    # Goal sealed before the robot moves. A final frame relabelled as the goal is
    # the defect the ImageNav work exists to prevent, and it is invisible after.
    teleport(gx, gy, gyaw)
    step(10)
    goal_image = grab()
    goal_digest = hashlib.sha256(goal_image.tobytes()).hexdigest()
    PILImage.fromarray(goal_image).save(out / "goal.jpg", quality=95)
    goal_tensor = prep(goal_image).unsqueeze(0).to(device)
    record["goal_image"] = "goal.jpg"
    record["goal_image_sha256"] = goal_digest
    record["goal_pose"] = [gx, gy, gyaw]
    record["goal_sealed_before_motion"] = True
    record["start_pose"] = [sx, sy, syaw]

    teleport(sx, sy, syaw)
    step(10)
    history = [grab()] * (config["context_size"] + 1)

    trace: list[dict[str, object]] = []
    # Poses are kept in their own typed list. Reading them back out of the
    # loosely typed trace dicts is what makes a distance sum untypeable.
    poses: list[tuple[float, float]] = []
    pd = PDConfig(dt=1.0 / CONTROL_HZ)
    goal_thumb = PILImage.fromarray(goal_image).resize((160, 120))

    try:
        for t in range(args.steps):
            frame = grab()
            history = [*history, frame][-(config["context_size"] + 1):]
            x, y, yaw = base_pose()
            poses.append((x, y))

            observation = torch.cat([prep(f) for f in history],
                                    dim=0).unsqueeze(0).to(device)
            with torch.no_grad():
                distance, action = model(observation, goal_tensor)
            waypoints = action[0].cpu().numpy()
            normalised = waypoints[EXECUTED_WAYPOINT_INDEX]
            metres = unnormalise_waypoint(
                normalised, metric_waypoint_spacing=METRIC_WAYPOINT_SPACING)
            vx, vy, w = waypoint_to_twist(
                [float(v) for v in metres], M3PRO_LIMITS, pd,
                kinematics=BaseKinematics.HOLONOMIC)
            set_twist(vx, vy, w)
            step(int(60 / CONTROL_HZ))

            panel = PILImage.new("RGB", (480, 300), (18, 18, 18))
            panel.paste(PILImage.fromarray(frame).resize((320, 240)), (0, 30))
            panel.paste(goal_thumb, (320, 30))
            draw = ImageDraw.Draw(panel)
            draw.rectangle([0, 0, 480, 28], fill=(140, 20, 20))
            draw.text((6, 9), BANNER, fill=(255, 255, 255))
            draw.text((324, 12), "GOAL RGB", fill=(200, 200, 200))
            draw.text((6, 274), f"ViNT dist {float(distance[0, 0]):6.2f}  "
                                f"wp[m] {metres[0]:+.3f},{metres[1]:+.3f}",
                      fill=(220, 220, 220))
            draw.text((6, 286), f"twist {vx:+.2f},{vy:+.2f},{w:+.2f}  "
                                f"step {t + 1}/{args.steps}  SAFETY: inactive",
                      fill=(180, 180, 180))
            panel.save(out / "frames" / f"{t:04d}.jpg", quality=92)

            trace.append({
                "step": t, "pose": [x, y, yaw],
                "vint_temporal_distance": float(distance[0, 0]),
                "waypoint_normalised": normalised.tolist(),
                "waypoint_metres": metres.tolist(),
                "twist": [vx, vy, w],
            })
        record["ROLLOUT_COMPLETED"] = True
    except Exception as exc:
        record["ROLLOUT_COMPLETED"] = False
        record["earliest_failure_stage"] = f"{type(exc).__name__}: {exc}"
        print(f"  rollout stopped at step {len(trace)}: {type(exc).__name__}: {exc}")

    set_twist(0.0, 0.0, 0.0)
    step(20)

    if trace:
        points = np.asarray(poses, dtype=np.float64)
        deltas = np.diff(points, axis=0) if len(points) > 1 else np.zeros((0, 2))
        path = float(np.linalg.norm(deltas, axis=1).sum())
        displacement = float(np.linalg.norm(points[-1] - points[0]))
        record["INFERENCE_EXECUTED"] = True
        record["steps_executed"] = len(trace)
        record["approx_duration_s"] = round(len(trace) / CONTROL_HZ, 2)
        record["waypoint_tensor_shape"] = list(np.asarray(waypoints).shape)
        record["net_displacement_m"] = round(displacement, 4)
        record["path_length_m"] = round(path, 4)
        record["ROBOT_VISIBLY_MOVED"] = bool(path > 0.01)
        record["temporal_distance_first"] = trace[0]["vint_temporal_distance"]
        record["temporal_distance_last"] = trace[-1]["vint_temporal_distance"]
    else:
        record["INFERENCE_EXECUTED"] = False
        record["ROBOT_VISIBLY_MOVED"] = False

    record["frames_written"] = len(list((out / "frames").glob("*.jpg")))
    record["output_dir"] = str(out)
    record["OUTSIDE_REPOSITORY"] = not str(out).startswith(str(REPO))
    record["finished_at"] = datetime.now(UTC).isoformat()

    (out / "trace.json").write_text(json.dumps(trace, indent=2))
    (out / "ENGINEERING_DEMO_ONLY.json").write_text(json.dumps(record, indent=2))

    print("=" * 70)
    print(BANNER)
    print("=" * 70)
    for key in ("scene_usd", "robot_usd", "ROBOT_ASSET", "model", "device",
                "MODEL_LOADED", "INFERENCE_EXECUTED", "steps_executed",
                "approx_duration_s", "waypoint_tensor_shape",
                "temporal_distance_first", "temporal_distance_last",
                "net_displacement_m", "path_length_m", "ROBOT_VISIBLY_MOVED",
                "SAFETY_LAYER", "STOPPING_LAYER", "SCIENTIFIC_ARM_A_N",
                "frames_written", "output_dir"):
        if key in record:
            print(f"  {key:26s} {record[key]}")
    if not record.get("ROLLOUT_COMPLETED", True):
        print(f"  earliest_failure_stage     {record.get('earliest_failure_stage')}")

    app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
