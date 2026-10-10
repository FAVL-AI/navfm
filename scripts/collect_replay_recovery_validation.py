"""First-pair actual learned-policy replay initialization validation; no efficacy."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import math
import os
import sys
import traceback
from pathlib import Path

from initialization_diagnostic import REPO, history, sha, validate_render_interval
from initialization_diagnostic_v2 import bootstrap_ok, eligibility_ok
from replay_recovery_contracts import (
    FILES,
    acquisition_ok,
    boundary_history,
    forced_entry,
    frozen,
    snapshot,
)

sys.path.insert(0, str(REPO / "src"))
SETTINGS = [
    "/rtx/post/histogram/" + k
    for k in ["enabled", "tau", "minEV", "maxEV", "whiteScale", "useExposureClamping"]
] + [
    "/rtx/post/tonemap/op",
    "/rtx/post/tonemap/exposureTime",
    "/rtx/post/tonemap/filmIso",
    "/rtx/post/tonemap/fNumber",
    "/rtx/post/dlss/execMode",
    "/omni/replicator/RTSubframes",
    "/rtx/rendermode",
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze-commit", required=True)
    p.add_argument("--case", required=True)
    p.add_argument("--role", choices=["reference", "replay"], required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--reference", type=Path)
    a = p.parse_args()
    cfg = frozen(a.freeze_commit, launch=True)
    if (
        a.case != cfg["first_case"]
        or a.out.exists()
        or a.out.name != cfg["authorized_processes"][["reference", "replay"].index(a.role)]
    ):
        p.error("undeclared case or existing output")
    if (a.role == "replay") != bool(a.reference):
        p.error("replay requires reference")
    expected_root = Path(cfg["evidence_root"]) / cfg["probe_prefix"]
    if a.out.parent != expected_root or (
        a.reference and a.reference != expected_root / cfg["authorized_processes"][0]
    ):
        p.error("Undeclared output/reference path")
    a.out.mkdir(parents=True)
    report = dict(
        status="RUNNING",
        case=a.case,
        role=a.role,
        freeze_commit=a.freeze_commit,
        methods={},
        captures=[],
        expected_asset_sha256=cfg["asset_sha256"],
    )

    def save():
        (a.out / "trace.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")

    save()
    from isaacsim import SimulationApp

    app = SimulationApp(
        {"headless": True, "renderer": "RayTracedLighting", "width": 320, "height": 240}
    )
    failed = False
    try:
        import carb
        import numpy as np
        import omni.physx
        import omni.replicator.core as rep
        import omni.timeline
        import omni.usd
        from isaacsim.core.api import SimulationContext
        from PIL import Image
        from pxr import UsdLux, UsdPhysics

        from navfm.collection.yaw_rate_tracker import YawRateTracker
        from navfm.isaac.robot import M3PRO, SimRobot

        omni.usd.get_context().open_stage(cfg["fixture"])
        usd = omni.usd.get_context().get_stage()
        if usd is None:
            raise ValueError("fixture open failed")
        sim = SimulationContext(stage_units_in_meters=1.0, physics_dt=1 / 120, rendering_dt=1 / 12)
        sim.initialize_physics()
        sim.play()
        robot_cfg = dataclasses.replace(
            M3PRO,
            usd_path=cfg["robot"],
            camera=dataclasses.replace(
                M3PRO.camera, resolution=(320, 240), height=0.55, x_offset=0.2, pitch_deg=0.0
            ),
        )
        robot = SimRobot(app, robot_cfg)
        robot._attach()
        art = robot._articulation
        if robot._is_v6:
            raise ValueError("unreviewed articulation backend")
        art.initialize()
        for _ in range(5):
            sim.step(render=False)
        robot.attach_camera()
        cam = robot._camera
        if robot._is_v6:
            raise ValueError("unreviewed camera backend")
        cam.set_local_pose(
            translation=np.array([0.2, 0, 0.55]),
            orientation=np.array([0.5, 0.5, -0.5, -0.5]),
            camera_axes="usd",
        )
        cam.set_clipping_range(0.05, 30.0)
        cam.set_focal_length(robot_cfg.camera.usd_focal_length(cam.get_horizontal_aperture()))
        settings = carb.settings.get_settings()
        settings.set("/app/runLoops/main/rateLimitEnabled", True)
        settings.set("/app/runLoops/main/rateLimitFrequency", 12.0)
        settings.set("/omni/replicator/RTSubframes", 1)
        sim.set_simulation_dt(physics_dt=1 / 120, rendering_dt=1 / 12)
        report["observed_rates"] = {
            "physics_dt": float(sim.get_physics_dt()),
            "rendering_dt": float(sim.get_rendering_dt()),
        }
        save()
        if (
            abs(report["observed_rates"]["physics_dt"] - 1 / 120) > 1e-8
            or abs(report["observed_rates"]["rendering_dt"] - 1 / 12) > 1e-8
        ):
            raise ValueError("Unqualified timestep readback")
        rep.orchestrator.set_capture_on_play(False)
        names = list(art.dof_names)
        indices = [
            [i for i, n in enumerate(names) if n.lower().startswith(prefix)]
            for prefix in ["fl", "fr", "rl", "rr"]
        ]
        if any(len(ids) != 1 for ids in indices):
            raise ValueError("unqualified wheel mapping")
        drives = []
        for prim in usd.Traverse():
            if str(prim.GetPath()).startswith(robot.prim_path) and prim.IsA(
                UsdPhysics.RevoluteJoint
            ):
                d = UsdPhysics.DriveAPI.Get(prim, "angular")
                v = {
                    "path": str(prim.GetPath()),
                    "stiffness": d.GetStiffnessAttr().Get(),
                    "damping": d.GetDampingAttr().Get(),
                    "type": d.GetTypeAttr().Get(),
                }
                if v["stiffness"] != 0 or v["damping"] != 1000 or v["type"] != "acceleration":
                    raise ValueError("unqualified drive readback")
                drives.append(v)
        if not drives:
            raise ValueError("missing drive qualification")
        report["lights"] = [
            {
                "path": str(prim.GetPath()),
                "attributes": {
                    str(attr.GetName()): str(attr.Get()) for attr in prim.GetAttributes()
                },
            }
            for prim in usd.Traverse()
            if prim.IsA(UsdLux.DistantLight) or prim.IsA(UsdLux.DomeLight)
        ]
        report["drives"] = drives
        report["dof_names"] = names
        tracker = YawRateTracker()
        held = [0.0, 0.0, 0.0]
        updates = 0

        def targets(v, vy, w):
            k = 0.1625
            r = 0.04
            speeds = [
                (v - vy - k * w) / r,
                (v + vy + k * w) / r,
                (v + vy - k * w) / r,
                (v - vy + k * w) / r,
            ]
            values = np.zeros((1, len(names)), dtype=np.float32)
            for ids, val in zip(indices, speeds, strict=True):
                values[0, ids[0]] = val
            art.set_joint_velocity_targets(values)

        def feedback(dt):
            nonlocal updates
            if not any(held):
                tracker.reset()
                targets(0, 0, 0)
            else:
                targets(
                    held[0],
                    held[1],
                    tracker.update(
                        held[2], float(np.asarray(art.get_velocities()).reshape(-1, 6)[0, 5]), dt
                    ),
                )
            updates += 1

        subscription = omni.physx.get_physx_interface().subscribe_physics_step_events(feedback)

        def drive(command):
            held[:] = command
            if not any(held):
                tracker.reset()
                targets(0, 0, 0)

        acquisition_events = []
        acquisition_enabled = False
        active_render_index = None

        def acquisition(event):
            if not acquisition_enabled:
                return
            try:
                parsed = cam._sdg_interface.parse_rendered_simulation_event(
                    event.payload["product_path_handle"], event.payload["results"]
                )
                if parsed[0] != cam.get_render_product_path():
                    return
                # Order 1001 follows camera's measured order-1000 graph acquisition.
                rgb = robot.rgb()
                acquisition_events.append(
                    dict(
                        sequence=len(acquisition_events),
                        render_call_index=active_render_index,
                        render_product=parsed[0],
                        rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
                        sim_time=float(sim.current_time),
                        camera_sensor_time=cam.get_current_frame().get("rendering_time"),
                        supported=True,
                    )
                )
            except Exception as exc:
                acquisition_events.append(
                    dict(supported=False, failure=str(exc), render_call_index=active_render_index)
                )

        acquisition_subscription = (
            omni.usd.get_context()
            .get_rendering_event_stream()
            .create_subscription_to_pop_by_type(
                int(omni.usd.StageRenderingEventType.NEW_FRAME),
                acquisition,
                name="replay_boundary_acquisition",
                order=1001,
            )
        )

        def render_call(delta):
            nonlocal active_render_index
            before = float(sim.current_time)
            before_updates = updates
            before_status = rep.orchestrator.get_status().name
            before_timeline_time = float(omni.timeline.get_timeline_interface().get_current_time())
            before_sensor_time = cam.get_current_frame().get("rendering_time")
            sim.play()
            active_render_index = len(report.get("render_calls", []))
            rep.orchestrator.step(rt_subframes=1, delta_time=delta, pause_timeline=True)
            active_render_index = None
            after = float(sim.current_time)
            report.setdefault("render_calls", []).append(
                dict(
                    index=len(report.get("render_calls", [])),
                    requested_delta_s=delta,
                    before_orchestrator_status=before_status,
                    before_timeline_time=before_timeline_time,
                    before_sensor_time=before_sensor_time,
                    after_orchestrator_status=rep.orchestrator.get_status().name,
                    timeline_time=float(omni.timeline.get_timeline_interface().get_current_time()),
                    before_sim_time=before,
                    after_sim_time=after,
                    sensor_time=cam.get_current_frame().get("rendering_time"),
                    feedback_updates=updates - before_updates,
                )
            )
            save()
            validate_render_interval(before, after, delta, updates - before_updates)

        def step():
            # Exactly two calls, without outcome-selected extra warmup.
            render_call(1 / 12)
            render_call(0.0)

        def stationary_render():
            # Exactly one call for each of the six declared direct rerenders.
            render_call(0.0)

        proxy = dict(
            closest_node=0,
            lost=True,
            far=0,
            pending=[],
            attempts=1,
            scan=0,
            stop_count=0,
            stopped=False,
            verified_count=0,
            chain_reached_decisions=0,
        )

        def pose_record(v):
            pos, q = v
            return {
                "position": np.asarray(pos).reshape(-1, 3)[0].tolist(),
                "quaternion": np.asarray(q).reshape(-1, 4)[0].tolist(),
            }

        def capture(label, physical_step, expected_dlss=2):
            image = f"{label}.png"
            rgb = robot.rgb()
            if rgb.shape != (240, 320, 3):
                raise ValueError("invalid live RGB")
            Image.fromarray(rgb).save(a.out / image)
            frame = cam.get_current_frame()
            report.setdefault("capture_provenance", []).append(
                dict(
                    label=label,
                    physical_step=physical_step,
                    image_sha256=sha(a.out / image),
                    sim_time=float(sim.current_time),
                    frame_time=frame.get("rendering_time"),
                    observed_settings={k: settings.get(k) for k in SETTINGS},
                )
            )
            save()
            sensor = float(frame["rendering_time"])
            now = float(sim.current_time)
            if abs(sensor - now) > 1e-8:
                raise ValueError("stale live capture")
            actions = art.get_applied_actions()
            jp, jv = actions.joint_positions, actions.joint_velocities
            if jp is None or jv is None:
                raise ValueError("UNKNOWN articulation targets")
            observed = {k: settings.get(k) for k in SETTINGS}
            unknown = [k for k, v in observed.items() if v is None]
            if unknown:
                raise ValueError("UNKNOWN required setting readback: " + str(unknown))
            if (
                observed["/rtx/post/dlss/execMode"] != expected_dlss
                or observed["/omni/replicator/RTSubframes"] != 1
                or observed["/rtx/rendermode"] != "RaytracedLighting"
            ):
                raise ValueError("capture setting mismatch")
            value = dict(
                image=image,
                image_sha256=sha(a.out / image),
                physical_step=physical_step,
                sensor_time=sensor,
                sim_time=now,
                rendering_frame=frame.get("rendering_frame"),
                root=pose_record(art.get_world_poses()),
                camera_world=pose_record(cam.get_world_pose(camera_axes="usd")),
                camera_local=pose_record(cam.get_local_pose(camera_axes="usd")),
                root_velocity=np.asarray(art.get_velocities()).reshape(-1).tolist(),
                joint_positions=np.asarray(art.get_joint_positions()).reshape(-1).tolist(),
                joint_velocities=np.asarray(art.get_joint_velocities()).reshape(-1).tolist(),
                joint_position_targets=np.asarray(jp).reshape(-1).tolist(),
                joint_velocity_targets=np.asarray(jv).reshape(-1).tolist(),
                held_command=list(held),
                controller_integral=tracker.integral,
                controller_updates=updates,
                dof_names=names,
                settings=observed,
                proxy_policy=copy.deepcopy(proxy),
                asset_sha256=cfg["asset_sha256"],
                digest_provenance="Expected identities, verified at preflight; require matching postflight before PASS",
                unknown=[],
                mechanical_ok=True,
            )
            report["captures"].append(value)
            save()
            return value

        # Explicit first-use initialization is not a qualified physics interval.
        startup_mode = settings.get("/rtx/post/dlss/execMode")
        report["startup_dlss_mode"] = startup_mode
        save()
        if startup_mode is None:
            raise ValueError("UNKNOWN startup DLSS mode")
        render_call(0.0)
        report["bootstrap"] = dict(report["render_calls"][-1], qualified_policy_observation=False)
        save()
        bootstrap_ok(report["bootstrap"])
        eligibility = []
        for i in range(cfg["eligibility_frames"]):
            step()
            eligibility.append(capture(f"eligibility_{i}", i + 1, expected_dlss=startup_mode))
        report["eligibility"] = eligibility
        eligibility_ok(eligibility, startup_mode)
        report["eligibility_passed"] = True
        save()

        # Actual original backend; only pre-kidnap diagnostic decisions.
        os.environ["NAVFM_UPSTREAM"] = cfg["upstream"]
        import torch

        from navfm.collection.perturbation import StartPerturbation, perturbed_start
        from navfm.collection.rgb_baseline import RGBTopomapBaseline, topomap_components

        torch.set_num_threads(4)
        torch.manual_seed(0)
        comparison = json.loads((REPO / "configs/eval/prospective_r2_recovery_v1.json").read_text())
        policy = RGBTopomapBaseline(
            Path(cfg["checkpoint"]),
            radius=4,
            close_threshold=3.0,
            **topomap_components(comparison["variants"][cfg["first_arm"]], start_lost=False),
            action_scale_m=0.049994826316833496,
            stop_enabled=True,
            max_v=0.1,
            control_period_s=0.5,
        )
        if policy.device != "cuda":
            raise ValueError("Original CUDA backend required")
        nodes = json.loads(Path(cfg["chain_json"]).read_text())["routes"][a.case]["nodes"]
        policy.set_chain([np.asarray(Image.open(n["source"]).convert("RGB")) for n in nodes])
        goal = np.asarray(
            Image.open(
                Path(cfg["evidence_root"])
                / "v2-prospective_r2_a-R2_recover-20261010-01"
                / a.case
                / "goal.png"
            ).convert("RGB")
        )
        report["observed_learned_runtime"] = dict(
            python=sys.executable,
            torch_version=torch.__version__,
            cuda_version=torch.version.cuda,
            device_name=torch.cuda.get_device_name(0),
            model_training=policy.model.training,
        )
        if policy.model.training or sys.executable != cfg["python"]:
            raise ValueError("Unqualified learned runtime")
        report["policy_initialized"] = snapshot(policy)
        report["learned_invocations"] = []

        def invoke(buffers, physical_step):
            before = snapshot(policy)
            prediction = policy.step(
                [np.asarray(Image.open(a.out / x["image"]).convert("RGB")) for x in buffers], goal
            )
            prediction.pop("latency_ms", None)
            report["learned_invocations"].append(
                dict(
                    physical_step=physical_step,
                    history=[
                        {
                            k: x[k]
                            for k in [
                                "image",
                                "image_sha256",
                                "sensor_time",
                                "sim_time",
                                "physical_step",
                            ]
                        }
                        for x in buffers
                    ],
                    before=before,
                    prediction=prediction,
                    after=snapshot(policy),
                    requested_command_applied=False,
                )
            )
            save()

        # Fixed cold conditioning, mirroring original goal/start lifecycle.
        case = cfg["cases"][a.case]
        route = case["route"]
        points = np.array(route["waypoints"])
        points[:, 1] += route["scene_index"] * 20.0
        end = points[-1] - points[-2]
        robot.teleport(points[-1], math.atan2(end[1], end[0]))
        drive([0.0, 0.0, 0.0])
        for _ in range(8):
            step()
        settings.set("/rtx/post/dlss/execMode", 2)
        step()
        capture("condition_goal", -1)
        start = case["start_pose"]
        robot.teleport(start[:2], start[2])
        drive([0.0, 0.0, 0.0])
        for _ in range(8):
            step()
        report["initial"] = capture("initial", 0)
        commands = [
            segment["command"]
            for segment in cfg["command_segments"]
            for _ in range(segment["frames"])
        ]
        if a.role == "replay":
            ref = json.loads((a.reference / "trace.json").read_text())
            if (
                ref["case"] != a.case
                or ref["status"] != "PASS"
                or ref["freeze_commit"] != a.freeze_commit
            ):
                raise ValueError("invalid replay provenance")
            if ref["commands"] != commands:
                raise ValueError("script divergence")
            commands = ref["commands"]
        report["commands"] = commands
        invoke([report["initial"]] * 6, 0)
        frames = []
        for i, command in enumerate(commands):
            report.setdefault("command_readbacks", []).append(
                dict(index=i, pre_step_time=float(sim.current_time), command=command)
            )
            drive(command)
            step()
            frames.append(capture(f"script_{i:02d}", i + 1))
            if (i + 1) % 6 == 0:
                sampled = [frames[j] for j in range(5, i + 1, 6)]
                invoke(([report["initial"]] * (6 - len(sampled))) + sampled, i + 1)
        report["pre_kidnap"] = copy.deepcopy(frames[-1])
        report["pre_kidnap"]["history"] = history(frames)
        before_policy, after_policy = forced_entry(policy)
        report["policy_before_kidnap"] = before_policy
        report["policy_after_kidnap"] = after_policy
        xy, heading, _ = perturbed_start(points, StartPerturbation(*cfg["kidnap_tuple"]))
        original = report["pre_kidnap"]
        position = [float(xy[0]), float(xy[1]), original["root"]["position"][2]]
        quaternion = [math.cos(heading / 2), 0.0, 0.0, math.sin(heading / 2)]
        report["kidnap_intent"] = dict(
            position=position,
            quaternion=quaternion,
            root_velocity=[0.0] * 6,
            joint_positions=original["joint_positions"],
            joint_velocities=original["joint_velocities"],
            held_command=[0.0] * 3,
            controller_integral=0.0,
        )
        acquisition_enabled = True
        report["kidnap_acquisition_before"] = len(acquisition_events)
        art.set_world_poses(np.array([position]), np.array([quaternion]))
        art.set_velocities(np.zeros((1, 6)))
        # Preserve joint q/dq; explicitly zero applied position/velocity targets.
        art.set_joint_position_targets(np.zeros((1, len(names))))
        drive([0.0, 0.0, 0.0])
        stationary_render()
        boundary = capture("post_kidnap", 36)
        report["kidnap_acquisition_events"] = copy.deepcopy(acquisition_events)
        report["boundary_render_call_index"] = report["render_calls"][-1]["index"]
        report["boundary_raw_rgb_sha256"] = hashlib.sha256(
            np.asarray(Image.open(a.out / boundary["image"]).convert("RGB")).tobytes()
        ).hexdigest()
        report["acquisition_subscription_present"] = acquisition_subscription is not None
        save()
        boundary["history"] = boundary_history(frames, boundary)
        report["boundary"] = boundary
        report["boundary_policy"] = snapshot(policy)
        report["recovery_invocations"] = 0
        report["first_six_boundary"] = [
            dict(
                image=x["image"],
                sensor_time=x["sensor_time"],
                sim_time=x["sim_time"],
                physical_step=x["physical_step"],
                age_s=boundary["sim_time"] - x["sensor_time"],
            )
            for x in boundary["history"]
        ]
        report["authorized_horizon_completed"] = True
        save()
        acquisition_ok(report)
        if subscription is None:
            raise ValueError("missing physics feedback subscription")
        frozen(a.freeze_commit, launch=True)
        report["post_run_actual_asset_sha256"] = {
            path: sha(Path(path)) for path in cfg["asset_sha256"]
        }
        report["post_run_actual_source_sha256"] = {name: sha(REPO / name) for name in FILES}
        report["source_asset_preflight_and_postflight_match"] = True
        report["status"] = "PASS"
        save()
    except Exception as exc:
        failed = True
        report["status"] = "FAIL"
        report["failure"] = str(exc)
        report["traceback"] = traceback.format_exc()
        save()
    finally:
        app.close()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
