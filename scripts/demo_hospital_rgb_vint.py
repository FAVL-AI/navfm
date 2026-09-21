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
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "third_party" / "visualnav-transformer" / "train"))

#: The hospital BO-10 actually collected against, resolved from its evidence
#: rather than guessed. The local mirror was tried first and renders every
#: material as a flat error colour: its 70 .mdl files import OmniUe4Base,
#: OmniUe4Function and OmniUe4Translucent, and none of those base modules is
#: present in the mirror. Repairing that is a separate question; this points at
#: the asset the science already uses.
HOSPITAL_USD = (
    "https://omniverse-content-production.s3-us-west-2.amazonaws.com"
    "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")
HOSPITAL_SCENE_ID = "hospital_bo10"
HOSPITAL_EVIDENCE = "gates/BO10/bo10_production_collection_20260910.json"

#: The admitted BO-10 route, taken whole rather than shortened. A ten-second
#: demo will not traverse 12.8 m, and that is fine: this observes the pipeline,
#: it does not test arrival. Inventing a nearer goal to make the clip end well
#: would be choosing the result.
BO10_ROUTE_ID = "hospital_repaired_map_route_050"
BO10_START = (-39.90271172754076, 23.12059657138799, -1.3986055122719583)
BO10_GOAL_XY = (-28.7009700284671, 16.971295079647238)
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
    ap.add_argument("--start", type=float, nargs=3, default=list(BO10_START),
                    help="defaults to the admitted BO-10 start pose")
    ap.add_argument("--goal", type=float, nargs=2, default=list(BO10_GOAL_XY),
                    help="defaults to the admitted BO-10 goal position")
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

    # The hospital is referenced into a new stage rather than opened as one.
    # Opening the remote layer directly returns before it has resolved, and the
    # robot articulation is then created against a stage that has no physics in
    # it yet -- "did not match any articulations". This is the order the BO-10
    # collector uses, and it is the one scene-compatibility change this retest
    # required.
    stage_utils.create_new_stage()
    sim_bootstrap = SimulationContext(physics_dt=1.0 / 60.0,
                                      rendering_dt=1.0 / 60.0,
                                      stage_units_in_meters=1.0)
    stage_utils.add_reference_to_stage(HOSPITAL_USD, "/World/Scene")
    sim_bootstrap.initialize_physics()
    sim_bootstrap.play()
    for _ in range(10):
        sim_bootstrap.step(render=False)
    stage_utils.add_reference_to_stage(str(ROBOT_USD), "/World/YahboomM3Pro")
    for _ in range(10):
        sim_bootstrap.step(render=False)

    # A new stage carries no lights, so RTX renders every surface black however
    # complete the geometry is. Opening a layer directly brings its own lighting
    # and referencing it does not, which is why the mirror run looked lit and
    # this one did not. Same construction the existing pilot uses.
    import omni.kit.commands

    omni.kit.commands.execute(
        "CreatePrim", prim_type="DomeLight", prim_path="/World/demo_dome",
        attributes={"inputs:intensity": 1200.0},
    )
    omni.kit.commands.execute(
        "CreatePrim", prim_type="DistantLight", prim_path="/World/demo_sun",
        attributes={"inputs:intensity": 3000.0},
    )
    for _ in range(10):
        sim_bootstrap.step(render=False)
    record["scene_usd"] = HOSPITAL_USD
    record["scene_id"] = HOSPITAL_SCENE_ID
    record["scene_resolved_from"] = HOSPITAL_EVIDENCE
    record["scene_manually_downloaded"] = False
    record["scene_load_method"] = (
        "referenced into a new stage at /World/Scene, as the BO-10 collector "
        "does. Opening the remote layer directly returns before it resolves and "
        "the articulation is then created against an empty stage")
    record["compatibility_changes"] = [
        "the hospital is referenced into a new stage rather than opened as one, "
        "because opening the remote layer returns before it resolves and the "
        "articulation is then created against an empty stage",
        "a DomeLight and a DistantLight are added, because a new stage carries "
        "no lights and RTX renders complete geometry black without them. "
        "Opening a layer brings its own lighting; referencing it does not",
    ]
    record["unchanged_from_first_demo"] = [
        "ViNT checkpoint", "context length", "model preprocessing",
        "waypoint selection", "controller gains", "velocity limits",
        "inference cadence", "demo duration", "camera model",
        "robot engineering asset", "headless RaytracedLighting",
    ]
    record["robot_usd"] = str(ROBOT_USD.relative_to(REPO))
    record["robot_usd_sha256"] = sha256_file(ROBOT_USD)

    sim = sim_bootstrap
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
    gx, gy = args.goal
    # The admitted route records no goal yaw, so the goal camera looks along the
    # start-to-goal bearing. Stated rather than tuned: it is a derived value.
    gyaw = float(np.arctan2(gy - sy, gx - sx))
    record["route_id"] = BO10_ROUTE_ID
    record["goal_yaw_derivation"] = (
        "the admitted route records no goal yaw; the goal camera faces along the "
        "start-to-goal bearing")
    record["start_goal_separation_m"] = round(
        float(np.hypot(gx - sx, gy - sy)), 3)
    record["previous_demo_poses_not_transferable"] = (
        "the mirror demo used (0,0,0) to (2,0,0), which are not meaningful "
        "coordinates in this hospital and could sit inside geometry")

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

    # RENDER GATE. The previous attempt drove for ten seconds on imagery where
    # every material had failed to compile, which was only obvious afterwards
    # from the frames. The criteria are stated numerically so the gate can fail,
    # and nothing moves until it passes.
    def gate_metrics(frame: np.ndarray) -> dict[str, Any]:
        sample = np.asarray(frame, dtype=np.float64)
        means = sample.reshape(-1, 3).mean(axis=0)
        red_dominant = bool(means[0] > 1.8 * max(means[1], means[2]))
        detail = float(sample.mean(axis=2).std())
        luminance = float(sample.mean())
        return {
            "channel_means_rgb": [round(float(v), 2) for v in means],
            "max_channel_ratio": round(
                float(means.max() / max(means.min(), 1e-6)), 3),
            "red_error_material_dominant": red_dominant,
            "spatial_detail_std": round(detail, 3),
            "mean_luminance": round(luminance, 3),
            "frame_non_empty": bool(sample.max() > 5.0),
            "bright_enough": bool(luminance > 20.0),
            "passes": bool(sample.max() > 5.0 and detail > 8.0
                           and luminance > 20.0 and not red_dominant),
        }

    # The remote hospital streams in over many frames. Rather than guess a
    # warm-up length, render until the gate criteria are met or the budget runs
    # out, and record how many frames it actually took -- a scene that needs
    # 400 frames to become legible is itself worth knowing.
    warmup_budget = 1200
    rendered = 0
    metrics = gate_metrics(grab())
    trend: list[dict[str, Any]] = []
    while rendered < warmup_budget and not metrics["passes"]:
        step(20)
        rendered += 20
        metrics = gate_metrics(grab())
        trend.append({"frames": rendered,
                      "detail": metrics["spatial_detail_std"],
                      "means": metrics["channel_means_rgb"]})
    probe_frames = [grab()]
    render_ok = bool(metrics["passes"])

    record["RENDER_GATE"] = {
        **metrics,
        "warmup_frames_rendered": rendered,
        "warmup_budget": warmup_budget,
        "warmup_trend": trend[-6:],
        "criteria": {
            "non_empty": "max pixel value above 5",
            "has_detail": "greyscale standard deviation above 8, so the view is "
                          "structured rather than a flat fill",
            "not_red_dominant": "mean red below 1.8x the larger of green and "
                                "blue, which is what a failed material looks like",
            "bright_enough": "mean luminance above 20 of 255. A scene a viewer "
                             "cannot see without post-processing is not a "
                             "presentable demonstration whatever its structure",
        },
        "criterion_added_after_a_miss": (
            "the brightness criterion was added after an earlier version of this "
            "gate admitted a frame averaging 1.7 of 255. The gate checked "
            "structure and colour and never asked whether the picture was "
            "visible. It is recorded here because the addition makes the gate "
            "stricter against a result that had already passed, not more "
            "permissive"),
        "RENDER_VALIDITY": "PASS" if render_ok else "FAIL",
    }
    PILImage.fromarray(probe_frames[-1]).save(out / "render_gate_probe.jpg",
                                              quality=95)

    if not render_ok:
        record["ROLLOUT_COMPLETED"] = False
        record["earliest_failure_stage"] = "RENDER_GATE"
        record["robot_moved_after_gate_failure"] = False
        record["INFERENCE_EXECUTED"] = False
        record["ROBOT_VISIBLY_MOVED"] = False
        record["finished_at"] = datetime.now(UTC).isoformat()
        record["output_dir"] = str(out)
        (out / "ENGINEERING_DEMO_ONLY.json").write_text(json.dumps(record, indent=2))
        print("RENDER_VALIDITY = FAIL; the robot was not moved")
        print(json.dumps(record["RENDER_GATE"], indent=2))
        app.close()
        return 1

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
            # Diagnostic only. This never reaches the policy; ViNT sees RGB.
            geometric = float(np.hypot(gx - x, gy - y))

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
            draw.text((324, 156), "Model: ViNT", fill=(210, 210, 210))
            draw.text((324, 170), "In: RGB history + RGB goal",
                      fill=(190, 190, 190))
            draw.text((324, 184), "Out: nominal waypoints", fill=(190, 190, 190))
            draw.text((324, 202), "Safety layer:  inactive", fill=(200, 150, 150))
            draw.text((324, 216), "Stopping layer: inactive", fill=(200, 150, 150))
            draw.text((324, 234), "Scientific n = 0", fill=(255, 200, 120))
            # Predicted waypoints, drawn as a small plan view so the overlay
            # shows the output rather than only naming it. Robot at the origin,
            # x forward, scaled to fit; no metric claim is attached.
            cx, cy, scale = 400, 276, 90.0
            draw.line([cx - 30, cy, cx + 30, cy], fill=(70, 70, 70))
            draw.line([cx, cy - 16, cx, cy + 16], fill=(70, 70, 70))
            for k in range(waypoints.shape[0]):
                px = cx + float(waypoints[k][1]) * -scale
                py = cy - float(waypoints[k][0]) * scale
                colour = ((120, 220, 255) if k == EXECUTED_WAYPOINT_INDEX
                          else (90, 130, 150))
                draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=colour)
            draw.text((6, 274), f"ViNT temporal dist {float(distance[0, 0]):6.2f}"
                                f"   wp[m] {metres[0]:+.3f},{metres[1]:+.3f}",
                      fill=(220, 220, 220))
            draw.text((6, 286), f"twist {vx:+.2f},{vy:+.2f},{w:+.2f}   "
                                f"step {t + 1}/{args.steps}   "
                                f"diag dist {geometric:5.2f} m",
                      fill=(180, 180, 180))
            panel.save(out / "frames" / f"{t:04d}.jpg", quality=92)

            trace.append({
                "step": t, "pose": [x, y, yaw],
                "vint_temporal_distance": float(distance[0, 0]),
                "simulator_diagnostic_distance_m": geometric,
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
        temporal = [float(e["vint_temporal_distance"]) for e in trace]  # type: ignore[arg-type]
        geometric_series = [
            float(e["simulator_diagnostic_distance_m"]) for e in trace]  # type: ignore[arg-type]
        record["MODEL_TEMPORAL_DISTANCE"] = {
            "initial": round(temporal[0], 3), "minimum": round(min(temporal), 3),
            "maximum": round(max(temporal), 3), "final": round(temporal[-1], 3),
            "units": "ViNT temporal distance, not metres",
        }
        record["SIMULATOR_DIAGNOSTIC_DISTANCE"] = {
            "initial": round(geometric_series[0], 3),
            "minimum": round(min(geometric_series), 3),
            "final": round(geometric_series[-1], 3),
            "units": "metres",
            "NOT_FED_TO_POLICY": True,
            "note": ("recorded for engineering diagnosis. Neither series is "
                     "evidence of navigation success"),
        }
    else:
        record["INFERENCE_EXECUTED"] = False
        record["ROBOT_VISIBLY_MOVED"] = False

    frame_files = sorted((out / "frames").glob("*.jpg"))
    if frame_files:
        captures = {
            "start_frame": frame_files[0],
            "mid_frame": frame_files[len(frame_files) // 2],
            "final_frame": frame_files[-1],
        }
        for name, source in captures.items():
            target = out / f"{name}.jpg"
            target.write_bytes(source.read_bytes())
            record[name] = target.name
        images = [PILImage.open(f) for f in frame_files]
        gif = out / "demo.gif"
        images[0].save(gif, save_all=True, append_images=images[1:],
                       duration=250, loop=0)
        record["gif"] = gif.name

    # Descriptive only. There is no admitted collision instrumentation here, so
    # the vocabulary is deliberately observational and carries no rate, no
    # success and no safety claim.
    if trace:
        final_view = np.asarray(
            PILImage.open(frame_files[-1]).crop((0, 30, 320, 270)),
            dtype=np.float64)
        spread = float(final_view.mean(axis=2).std())
        record["ENGINEERING_OBSERVATION"] = (
            "NEAR_WALL" if spread < 18.0 else "OPEN_CORRIDOR")
        record["observation_basis"] = (
            f"spatial variation of the final frame ({spread:.1f}); a flat view "
            "means the camera is close to a surface. Descriptive only -- this is "
            "not a collision measurement, a rate, or a safety claim")
        record["observation_vocabulary"] = [
            "OPEN_CORRIDOR", "NEAR_WALL", "VISIBLE_CONTACT_OR_INTERSECTION",
            "INDETERMINATE"]

    record["frames_written"] = len(frame_files)
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
