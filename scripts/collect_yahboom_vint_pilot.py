"""Closed-loop ViNT driving the Yahboom digital twin, and the trajectories it records.

Runs under the Isaac Sim interpreter. The loop is:

    Yahboom front RGB -> ViNT -> normalised waypoint -> un-normalisation
      -> body twist -> mecanum wheel velocities -> Isaac physics
      -> new robot pose -> new front RGB -> repeat

Three things this deliberately does not do, each of which would make the result
look better and mean less:

* **No camera teleportation.** The camera is a child of ``base_link``; it moves
  because the *robot* moves under physics. The predecessor pilot moved a camera
  along a scripted path with physics off, and that is why its evidence could say
  nothing about a robot.
* **No privileged state into the policy.** ViNT sees the front RGB and a goal
  image. Ground-truth pose is read every step -- for labels, for the motion trace
  and for the camera-attachment proof -- and never reaches the network.
* **No goal chosen after the fact.** The goal image is captured at a predeclared
  pose *before* the robot moves, and its digest is recorded before the first
  step. A final frame relabelled as the goal is the failure the ImageNav draft
  exists to prevent, and it is invisible in the output if you allow it.

**The un-normalisation is the dangerous part**, so it is stated rather than
buried. ViNT predicts waypoints normalised by ``metric_waypoint_spacing``; for
GO Stanford that is 0.12 m. Multiplying back is what turns a prediction into
metres. Feeding the raw prediction to a controller that expects metres would
rescale every command by ~8x, would not raise, and would produce a plausible
trajectory that is wrong everywhere. `tests/test_vint_action_bridge.py` pins it.

Stage: SIMULATION_DEVELOPMENT. Not admitted for training or evaluation. The
wheel radius it depends on is a project record, not a caliper measurement.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "third_party" / "visualnav-transformer" / "train"))

ROBOT_USD = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd"
CKPT = REPO / "checkpoints/vint.pth"

#: Declared, not discovered. GO Stanford's metric waypoint spacing, the constant
#: ViNT's action labels were normalised by.
METRIC_WAYPOINT_SPACING = 0.12
#: Which of the 5 predicted waypoints is executed. Upstream's NoMaD deployment
#: takes index 2 of 8; ViNT ships no deployment subsection, so this is declared
#: here rather than inferred, and recorded in every trajectory manifest.
EXECUTED_WAYPOINT_INDEX = 2
CONTROL_HZ = 4.0


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def unnormalise_waypoint(wp_norm, spacing: float = METRIC_WAYPOINT_SPACING):
    """Normalised ViNT waypoint -> metres in the robot frame.

    ViNT's labels are produced by dividing robot-frame displacements by
    ``metric_waypoint_spacing``; this multiplies back. The angle components
    (cos, sin) are directions and are NOT scaled.
    """
    import numpy as np

    wp = np.asarray(wp_norm, dtype=np.float64).copy()
    wp[..., 0] *= spacing
    wp[..., 1] *= spacing
    return wp


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-root", default=str(Path.home() / "navfm-data" / "simulation_development"))
    ap.add_argument("--evidence", default=str(REPO / "gates/digital_twin"))
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--pilots", type=int, default=2)
    ap.add_argument("--pilot-index", type=int, default=None,
                    help="run exactly one pilot. Isaac plus the renderer plus ViNT is heavy; "
                         "one pilot per process keeps peak memory inside this workstation")
    ap.add_argument("--skip-proofs", action="store_true",
                    help="articulation and camera-mount proofs already archived")
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True, "renderer": "RaytracedLighting"})

    import numpy as np
    import omni.replicator.core as rep
    import torch
    from isaacsim.core.api import SimulationContext
    from isaacsim.core.prims import Articulation
    from isaacsim.core.utils import stage as stage_utils
    from pxr import Gf, UsdGeom

    from navfm import upstream
    from navfm.control import M3PRO_LIMITS, BaseKinematics, PDConfig, waypoint_to_twist
    from navfm.models.loader import extract_state_dict, load_checkpoint, sha256

    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    ev = Path(args.evidence)
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "frames").mkdir(exist_ok=True)

    # ---- scene ------------------------------------------------------------
    stage_utils.create_new_stage()
    from isaacsim.core.api.objects.ground_plane import GroundPlane

    GroundPlane(prim_path="/World/groundPlane", size=40.0)
    import omni.kit.commands

    omni.kit.commands.execute(
        "CreatePrim", prim_type="DistantLight", prim_path="/World/light",
        attributes={"inputs:intensity": 3000.0},
    )
    # Landmarks, so successive frames differ and the camera proof is legible.
    for i, (x, y, c) in enumerate(
        [(2.5, 0.0, (0.9, 0.2, 0.2)), (0.0, 2.5, (0.2, 0.8, 0.3)),
         (-2.5, 0.0, (0.2, 0.4, 0.9)), (0.0, -2.5, (0.9, 0.8, 0.2)),
         (2.0, 2.0, (0.8, 0.3, 0.8)), (-2.0, 2.0, (0.3, 0.8, 0.8))]
    ):
        p = f"/World/landmark_{i}"
        omni.kit.commands.execute("CreatePrim", prim_type="Cube", prim_path=p)
        prim = stage_utils.get_current_stage().GetPrimAtPath(p)
        xf = UsdGeom.Xformable(prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(x, y, 0.35))
        xf.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(0.3, 0.3, 0.35))
        UsdGeom.Gprim(prim).CreateDisplayColorAttr([Gf.Vec3f(*c)])

    stage_utils.add_reference_to_stage(str(ROBOT_USD), "/World/YahboomM3Pro")
    sim = SimulationContext(physics_dt=1.0 / 60.0, rendering_dt=1.0 / 60.0, stage_units_in_meters=1.0)
    sim.initialize_physics()

    robot = Articulation("/World/YahboomM3Pro")
    robot.initialize()
    dof_names = list(robot.dof_names or [])
    wheel_dofs = [i for i, n in enumerate(dof_names) if "wheel" in n.lower()]

    # Velocity control needs a velocity drive. A URDF whose joints declare no
    # dynamics imports with zero stiffness AND zero damping, so a velocity target
    # is accepted, recorded, and produces no torque -- the robot stands still
    # while the log shows 0.45 m/s. Set kp=0 (no position servo) and kd high
    # (track the velocity target). This is the difference between a wired
    # pipeline and a moving robot, and it is invisible in the trajectory file.
    n_dof = len(dof_names)
    kps = np.zeros((1, n_dof), dtype=np.float32)
    kds = np.zeros((1, n_dof), dtype=np.float32)
    for i in wheel_dofs:
        kds[0, i] = 1.0e4
    robot.set_gains(kps=kps, kds=kds)
    with contextlib.suppress(Exception):
        robot.switch_control_mode("velocity")

    # Top-arm mount, not the chassis. The URDF importer flattens links to
    # siblings, so camera_link is its own prim placed at the mast top by the
    # joint chain -- 0.280 m from ground against base_link at 0.040 m.
    cam_path = "/World/YahboomM3Pro/camera_link/front_rgb_camera"
    rp = rep.create.render_product(cam_path, (320, 240))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach([rp])

    def step(n: int = 1):
        for _ in range(n):
            sim.step(render=True)

    def base_pose():
        pos, quat = robot.get_world_poses()
        p = np.asarray(pos[0], dtype=np.float64)
        q = np.asarray(quat[0], dtype=np.float64)  # w,x,y,z
        w, x, y, z = q
        yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
        return float(p[0]), float(p[1]), float(yaw)

    def cam_world():
        xc = UsdGeom.Xformable(stage_utils.get_current_stage().GetPrimAtPath(cam_path))
        m = xc.ComputeLocalToWorldTransform(0)
        t = m.ExtractTranslation()
        return np.array([t[0], t[1], t[2]], dtype=np.float64)

    def grab():
        step(2)
        a = rgb.get_data()
        arr = np.asarray(a)
        if arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[:, :, :3]
        return arr.astype(np.uint8)

    def set_twist(vx, vy, w):
        # Mecanum body twist -> wheel angular velocities.
        r, lx, ly = 0.040, 0.0775, 0.085
        k = lx + ly
        fl = (vx - vy - k * w) / r
        fr = (vx + vy + k * w) / r
        rl = (vx + vy - k * w) / r
        rr = (vx - vy + k * w) / r
        cmd = np.zeros(len(dof_names), dtype=np.float32)
        order = {"fl": fl, "fr": fr, "rl": rl, "rr": rr}
        for i, n in enumerate(dof_names):
            for key, v in order.items():
                if n.lower().startswith(key):
                    cmd[i] = v
        robot.set_joint_velocity_targets(cmd[None, :])

    def teleport(x, y, yaw):
        set_twist(0.0, 0.0, 0.0)
        q = np.array([[math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]], dtype=np.float32)
        robot.set_world_poses(np.array([[x, y, 0.05]], dtype=np.float32), q)
        robot.set_joint_velocities(np.zeros((1, len(dof_names)), dtype=np.float32))
        step(20)

    record: dict[str, Any] = {
        "stage": "SIMULATION_DEVELOPMENT", "admission_status": "NOT_ADMITTED",
        "claim_status": "ENGINEERING_EVIDENCE_ONLY", "robot_source": "ISAAC_SIM",
        "physical_robot_validation": "NOT_PERFORMED",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "robot_usd_sha256": sha256(ROBOT_USD), "checkpoint_sha256": sha256(CKPT),
        "dof_names": dof_names, "wheel_dof_indices": wheel_dofs,
        "executed_waypoint_index": EXECUTED_WAYPOINT_INDEX,
        "metric_waypoint_spacing": METRIC_WAYPOINT_SPACING,
        "control_hz": CONTROL_HZ,
        "wheel_radius_m": 0.040, "wheel_radius_status": "PROVISIONAL_SIMULATION_VALUE",
    }

    # ---- proof 1: articulation moves under physics ------------------------
    if args.skip_proofs:
        record['proofs'] = 'skipped -- archived from a prior invocation'
    teleport(0.0, 0.0, 0.0)
    p0 = base_pose()
    set_twist(0.25, 0.0, 0.0)
    step(120)
    p1 = base_pose()
    set_twist(0.0, 0.0, 0.0)
    step(30)
    teleport(0.0, 0.0, 0.0)
    set_twist(0.0, 0.0, 0.8)
    step(120)
    p2 = base_pose()
    set_twist(0.0, 0.0, 0.0)
    step(30)
    _ap = {
        "forward": {"before": p0, "after": p1,
                    "displacement_m": math.hypot(p1[0] - p0[0], p1[1] - p0[1])},
        "rotate": {"after": p2, "yaw_change_rad": p2[2]},
        "moved_forward": math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 0.05,
        "rotated": abs(p2[2]) > 0.1,
    }
    record["articulation_proof"] = _ap

    # ---- proof 2: the camera is bolted to the robot -----------------------
    teleport(0.0, 0.0, 0.0)
    step(10)
    rb_a, cw_a = base_pose(), cam_world()
    img_a = grab()
    set_twist(0.2, 0.0, 0.9)
    step(150)
    set_twist(0.0, 0.0, 0.0)
    step(30)
    rb_b, cw_b = base_pose(), cam_world()
    img_b = grab()

    def rel(base, cam):
        dx, dy = cam[0] - base[0], cam[1] - base[1]
        c, s = math.cos(-base[2]), math.sin(-base[2])
        return [c * dx - s * dy, s * dx + c * dy, float(cam[2])]

    ra, rb_ = rel(rb_a, cw_a), rel(rb_b, cw_b)
    drift = max(abs(ra[i] - rb_[i]) for i in range(3))
    world_moved = float(np.linalg.norm(cw_a - cw_b))
    dpix = float(np.mean(np.abs(img_a.astype(np.int16) - img_b.astype(np.int16))))
    record["camera_mount_proof"] = {
        "camera_prim": cam_path,
        "robot_pose_A": rb_a, "robot_pose_B": rb_b,
        "camera_world_A": cw_a.tolist(), "camera_world_B": cw_b.tolist(),
        "camera_relative_to_base_A": ra, "camera_relative_to_base_B": rb_,
        "relative_transform_drift_m": drift,
        "camera_world_moved_m": world_moved,
        "mean_abs_pixel_change": dpix,
        "extrinsics_constant": drift < 1e-3,
        "world_pose_changed": world_moved > 0.05,
        "view_changed": dpix > 1.0,
        "verdict": "PASS" if (drift < 1e-3 and world_moved > 0.05 and dpix > 1.0) else "FAIL",
    }
    from PIL import Image as PILImage

    PILImage.fromarray(img_a).save(ev / "frames/yahboom_front_camera_A.jpg", quality=95)
    PILImage.fromarray(img_b).save(ev / "frames/yahboom_front_camera_B.jpg", quality=95)

    # ---- ViNT --------------------------------------------------------------
    cfg = upstream.model_config("vint")
    model = upstream.build_model("vint")
    state = extract_state_dict(load_checkpoint(CKPT, trust_checkpoint=True))
    model.load_state_dict(state, strict=True)
    # ViNT runs on CPU deliberately. A PyTorch CUDA context in the same process
    # as Isaac's RTX renderer segfaults this build reproducibly -- SIGSEGV at the
    # first inference, identically in both pilots. ViNT is 29M parameters, so CPU
    # inference costs about a second a step and buys a loop that completes.
    dev = "cpu"
    torch.set_num_threads(8)
    model.to(dev).eval()
    record["vint"] = {"device": dev, "strict_load": True,
                      "context_size": cfg["context_size"], "len_traj_pred": cfg["len_traj_pred"]}

    from vint_train.data.data_utils import resize_and_aspect_crop

    W, H = cfg["image_size"]

    def prep(arr):
        return resize_and_aspect_crop(PILImage.fromarray(arr), (W, H))

    pd = PDConfig(dt=1.0 / CONTROL_HZ)
    starts = [((0.0, 0.0, 0.0), (1.6, 0.35, 0.2)), ((0.0, 0.0, 0.0), (1.0, 1.4, 1.1))]
    pilots = []

    idxs = [args.pilot_index] if args.pilot_index is not None else list(range(min(args.pilots, len(starts))))
    for pi in idxs:
        (sx, sy, syaw), (gx, gy, gyaw) = starts[pi]
        name = f"pilot_{pi + 1:04d}"
        tdir = out_root / name
        (tdir / "raw").mkdir(parents=True, exist_ok=True)

        # GOAL SEALED BEFORE THE ROBOT MOVES.
        teleport(gx, gy, gyaw)
        goal_img = grab()
        goal_digest = sha256_bytes(goal_img.tobytes())
        PILImage.fromarray(goal_img).save(tdir / "raw" / "goal.jpg", quality=95)
        goal_t = prep(goal_img).unsqueeze(0).to(dev)

        teleport(sx, sy, syaw)
        step(10)
        hist = [grab()] * (cfg["context_size"] + 1)
        xs, ys, yaws, raw = [], [], [], []

        try:
         for t in range(args.steps):
            frame = grab()
            hist = [*hist, frame][-(cfg["context_size"] + 1):]
            PILImage.fromarray(frame).save(tdir / f"{t}.jpg", quality=95)
            x, y, yaw = base_pose()
            xs.append(x)
            ys.append(y)
            yaws.append(yaw)

            obs = torch.cat([prep(f) for f in hist], dim=0).unsqueeze(0).to(dev)
            with torch.no_grad():
                dist, action = model(obs, goal_t)
            wp_norm = action[0, EXECUTED_WAYPOINT_INDEX].cpu().numpy()
            wp_m = unnormalise_waypoint(wp_norm)
            vx, vy, w = waypoint_to_twist(
                wp_m, M3PRO_LIMITS, pd, kinematics=BaseKinematics.HOLONOMIC
            )
            set_twist(vx, vy, w)
            step(int(60 / CONTROL_HZ))
            raw.append({"t": t, "pose": [x, y, yaw],
                        "vint_dist": float(dist[0, 0]),
                        "waypoint_normalised": wp_norm.tolist(),
                        "waypoint_metres": wp_m.tolist(),
                        "twist": [vx, vy, w]})
        except Exception as exc:  # partial data is evidence; losing it is not
            record["rollout_error"] = f"{type(exc).__name__}: {exc}"
            print(f"  rollout stopped at step {len(xs)}: {type(exc).__name__}: {exc}")

        set_twist(0.0, 0.0, 0.0)
        step(20)
        pos = np.array([xs, ys], dtype=np.float64).T
        yaw_arr = np.unwrap(np.array(yaws, dtype=np.float64))
        with open(tdir / "traj_data.pkl", "wb") as fh:
            pickle.dump({"position": pos, "yaw": yaw_arr}, fh)
        (tdir / "raw" / "control_log.json").write_text(json.dumps(raw, indent=2))
        meta = {
            "stage": "SIMULATION_DEVELOPMENT", "admission_status": "NOT_ADMITTED",
            "training_allowed": False, "final_evaluation_allowed": False,
            "source": "ISAAC_SIM", "source_policy": "released ViNT (closed loop)",
            "robot": "Yahboom ROSMASTER M3 Pro digital twin",
            "camera": {
                "prim": cam_path, "type": "monocular_rgb",
                "viewpoint": "egocentric_forward", "mount": "yahboom_top_arm",
                "mount_height_m": 0.280, "height_above_base_link_m": 0.240,
                "forward_offset_m": 0.100, "lateral_offset_m": 0.0,
                "roll_rad": 0.0, "pitch_rad": 0.0, "yaw_rad": 0.0,
                "resolution": [320, 240],
                "calibration_status": "PROVISIONAL_SIMULATION",
            },
            "camera_prim": cam_path, "goal_image_sha256": goal_digest,
            "goal_pose": [gx, gy, gyaw], "start_pose": [sx, sy, syaw],
            "executed_waypoint_index": EXECUTED_WAYPOINT_INDEX,
            "metric_waypoint_spacing": METRIC_WAYPOINT_SPACING,
            "wheel_radius_m": 0.040, "wheel_radius_status": "PROVISIONAL_SIMULATION_VALUE",
            "frames": len(xs),
        }
        (tdir / "raw" / "metadata.json").write_text(json.dumps(meta, indent=2))
        pilots.append({
            "name": name, "path": str(tdir), "frames": len(xs),
            "position_shape": list(pos.shape), "position_dtype": str(pos.dtype),
            "yaw_shape": list(yaw_arr.shape), "yaw_dtype": str(yaw_arr.dtype),
            "start": [xs[0], ys[0], yaws[0]], "end": [xs[-1], ys[-1], yaws[-1]],
            "net_displacement_m": float(math.hypot(xs[-1] - xs[0], ys[-1] - ys[0])),
            "total_yaw_change_deg": float(math.degrees(yaw_arr[-1] - yaw_arr[0])),
            "goal_image_sha256": goal_digest,
        })
        print(f"  {name}: {len(xs)} frames, moved "
              f"{pilots[-1]['net_displacement_m']:.3f} m, yaw "
              f"{pilots[-1]['total_yaw_change_deg']:+.1f} deg")

    record["pilots"] = pilots
    suffix = f"_{args.pilot_index}" if args.pilot_index is not None else ""
    (ev / f"closed_loop_collection{suffix}.json").write_text(json.dumps(record, indent=2) + "\n")

    print("\nCLOSED-LOOP ViNT -> YAHBOOM DIGITAL TWIN")
    print("=" * 44)
    a = record["articulation_proof"]
    print(f"  articulation      : forward {a['forward']['displacement_m']:.3f} m, "
          f"rotate {math.degrees(a['rotate']['yaw_change_rad']):+.1f} deg -> "
          f"{'PASS' if a['moved_forward'] and a['rotated'] else 'FAIL'}")
    c = record["camera_mount_proof"]
    print(f"  camera mount      : drift {c['relative_transform_drift_m']:.2e} m, "
          f"world moved {c['camera_world_moved_m']:.3f} m, "
          f"dpix {c['mean_abs_pixel_change']:.2f} -> {c['verdict']}")
    print(f"  pilots collected  : {len(pilots)}")
    app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
