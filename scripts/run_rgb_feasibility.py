"""Live articulated ViNT episode in a local primitive corridor; engineering only."""

from __future__ import annotations

import argparse
import dataclasses
import faulthandler
import hashlib
import importlib.metadata
import json
import math
import sys
import time
from itertools import pairwise
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def encode(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--robot", required=True)
    parser.add_argument("--steps", type=int, default=240, help="12 Hz physics frames; timeout 20 s")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--arm", choices=["baseline", "layer"], default="baseline")
    args = parser.parse_args()
    if args.arm == "layer":
        parser.error(
            "RGB_LAYER_UNRESOLVED: located CBF requires privileged geometry; GNM temporal head has no ViNT calibration or validated stopping authority"
        )
    out = Path(args.out).expanduser().resolve()
    if out.exists() or out.is_relative_to(REPO) or args.steps < 12:
        parser.error("output must be new and external; at least 12 frames required")
    out.mkdir(parents=True)
    faulthandler.enable()
    faulthandler.dump_traceback_later(120, repeat=True)
    manifest = {
        "status": "RUNNING",
        "scope": "SIMPLE_SCENE_ENGINEERING_FEASIBILITY",
        "arm": args.arm,
        "seed": args.seed,
        "scientific_test_n": 0,
        "simulator_version": importlib.metadata.version("isaacsim"),
    }

    def save(stage_name):
        manifest["stage"] = stage_name
        (out / "runtime_manifest.json").write_text(
            json.dumps(manifest, indent=2, default=encode, allow_nan=False) + "\n"
        )
        print(stage_name, flush=True)

    app = None
    try:
        save("MODEL_LOAD")
        import numpy as np

        from navfm.collection.rgb_baseline import RGBBaseline

        policy = RGBBaseline(Path(args.checkpoint).resolve())
        manifest["baseline"] = policy.manifest
        save("MODEL_LOADED")
        from isaacsim import SimulationApp

        app = SimulationApp(
            {"headless": True, "renderer": "RayTracedLighting", "width": 640, "height": 480}
        )
        import carb
        import omni.physx
        import omni.replicator.core as rep
        import omni.usd
        from isaacsim.core.api import SimulationContext
        from isaacsim.core.utils import render_product, stage
        from PIL import Image
        from pxr import Gf, PhysicsSchemaTools, PhysxSchema, UsdGeom, UsdLux, UsdPhysics

        from navfm.collection.attestation import RuntimeHandles, collect_all, requested_values
        from navfm.collection.attestation_gate import decide
        from navfm.collection.recording import RecordingTrajectoryWriter
        from navfm.collection.scientific_preflight import (
            require_scientific_preflight,
            validate_capture,
            verify_saved_recording,
        )
        from navfm.isaac.app import SimConfig
        from navfm.isaac.robot import M3PRO, SimRobot

        np.random.seed(args.seed)
        policy.torch.manual_seed(args.seed)
        stage.create_new_stage()
        usd = omni.usd.get_context().get_stage()
        boxes = []

        def cube(name, xyz, size, color, collision=True):
            prim = UsdGeom.Cube.Define(usd, "/World/Fixture/" + name)
            prim.CreateSizeAttr(1.0)
            xf = UsdGeom.XformCommonAPI(prim)
            xf.SetTranslate(Gf.Vec3d(*xyz))
            xf.SetScale(Gf.Vec3f(*size))
            prim.CreateDisplayColorAttr([Gf.Vec3f(*color)])
            if collision:
                UsdPhysics.CollisionAPI.Apply(prim.GetPrim())
            if name != "Floor" and collision:
                boxes.append({"name": name, "xy": xyz[:2], "size": size[:2]})

        cube("Floor", (4, 0, -0.05), (10, 4, 0.1), (0.38, 0.42, 0.48))
        cube("WallLeft", (4, 1.65, 1.4), (8, 0.2, 2.8), (0.65, 0.7, 0.75))
        cube("WallRight", (4, -1.65, 1.4), (8, 0.2, 2.8), (0.65, 0.7, 0.75))
        cube("EndWall", (8, 0, 1.4), (0.2, 3.4, 2.8), (0.7, 0.7, 0.75))
        cube("Obstacle", (2.5, 0.95, 0.4), (0.6, 0.5, 0.8), (0.1, 0.3, 0.7))
        cube("GoalPanel", (4.0, 0.0, 1.0), (0.05, 0.8, 1.3), (0.9, 0.22, 0.04), False)
        light = UsdLux.DomeLight.Define(usd, "/World/Fixture/Dome")
        light.CreateIntensityAttr(800.0)
        sun = UsdLux.DistantLight.Define(usd, "/World/Fixture/Sun")
        sun.CreateIntensityAttr(1500.0)
        UsdGeom.XformCommonAPI(sun).SetRotate(Gf.Vec3f(-45.0, 30.0, 0.0))
        cfg = SimConfig(rt_subframes=1, seed=args.seed)
        robot_cfg = dataclasses.replace(
            M3PRO,
            usd_path=args.robot,
            camera=dataclasses.replace(M3PRO.camera, height=0.55, x_offset=0.2, pitch_deg=0.0),
        )
        sim = SimulationContext(stage_units_in_meters=1.0, physics_dt=cfg.dt, rendering_dt=cfg.dt)
        robot = SimRobot(app, robot_cfg)
        stage.add_reference_to_stage(args.robot, robot.prim_path)
        wheel_drives = []
        for prim in usd.Traverse():
            if str(prim.GetPath()).startswith(robot.prim_path) and prim.IsA(
                UsdPhysics.RevoluteJoint
            ):
                drive_api = UsdPhysics.DriveAPI.Get(prim, "angular")
                before_drive = {
                    "stiffness": drive_api.GetStiffnessAttr().Get(),
                    "damping": drive_api.GetDampingAttr().Get(),
                }
                # The imported position servos oppose continuous wheel velocity.
                drive_api.GetStiffnessAttr().Set(0.0)
                drive_api.GetDampingAttr().Set(10.0)
                wheel_drives.append(
                    {
                        "joint": str(prim.GetPath()),
                        "asset": before_drive,
                        "requested": {"stiffness": 0.0, "damping": 10.0},
                        "observed": {
                            "stiffness": drive_api.GetStiffnessAttr().Get(),
                            "damping": drive_api.GetDampingAttr().Get(),
                        },
                    }
                )
        manifest["prospective_wheel_drives"] = wheel_drives
        # Configure contact-report schemas before tensor views are created. Adding
        # them while physics is live invalidates the articulation's link view.
        for prim in usd.Traverse():
            if str(prim.GetPath()).startswith(robot.prim_path) and prim.HasAPI(
                UsdPhysics.RigidBodyAPI
            ):
                PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr(0.0)
        save("PHYSICS_INITIALIZATION")
        sim.initialize_physics()
        sim.play()
        robot._attach()
        robot._articulation.initialize()
        for _ in range(5):
            sim.step(render=False)
        robot.teleport((1.0, 0.0), 0.0)
        robot.attach_camera()
        cam = robot._camera
        cam.set_local_pose(
            translation=np.array([0.2, 0.0, 0.55]),
            orientation=np.array([0.5, 0.5, -0.5, -0.5]),
            camera_axes="usd",
        )
        cam.set_clipping_range(0.05, 30.0)
        cam.set_focal_length(robot_cfg.camera.usd_focal_length(cam.get_horizontal_aperture()))
        settings = carb.settings.get_settings()
        settings.set("/omni/replicator/RTSubframes", 1)
        settings.set("/app/runLoops/main/rateLimitEnabled", True)
        settings.set("/app/runLoops/main/rateLimitFrequency", 12.0)
        sim.set_simulation_dt(physics_dt=cfg.dt, rendering_dt=cfg.dt)
        rep.orchestrator.set_capture_on_play(False)

        def capture_step():
            sim.play()
            rep.orchestrator.step(rt_subframes=1, delta_time=cfg.dt, pause_timeline=True)
            rep.orchestrator.step(rt_subframes=1, delta_time=0.0, pause_timeline=True)

        names = list(robot._articulation.dof_names)
        wheel_indices = {
            prefix: [j for j, name in enumerate(names) if name.lower().startswith(prefix)]
            for prefix in ("fl", "fr", "rl", "rr")
        }
        if any(len(indices) != 1 for indices in wheel_indices.values()):
            raise ValueError(f"ambiguous wheel mapping: {names}")

        def drive(command):
            vx, vy, wz = command
            k, radius = 0.0775 + 0.085, 0.040
            speeds = [
                (vx - vy - k * wz) / radius,
                (vx + vy + k * wz) / radius,
                (vx + vy - k * wz) / radius,
                (vx - vy + k * wz) / radius,
            ]
            values = np.zeros((1, len(names)), dtype=np.float32)
            for indices, speed in zip(wheel_indices.values(), speeds, strict=True):
                values[0, indices[0]] = speed
            robot._articulation.set_joint_velocity_targets(values)

        contacts = []

        def contact_event(headers, data):
            for header in headers:
                paths = [
                    str(PhysicsSchemaTools.intToSdfPath(actor))
                    for actor in (header.actor0, header.actor1)
                ]
                if any(path.startswith(robot.prim_path) for path in paths) and any(
                    "/World/Fixture/" in path and not path.endswith("Floor") for path in paths
                ):
                    contacts.append(
                        {
                            "sim_time": float(sim.current_time),
                            "paths": paths,
                            "type": int(header.type),
                        }
                    )

        subscription = omni.physx.get_physx_simulation_interface().subscribe_contact_report_events(
            contact_event
        )
        goal_xy = (3.0, 0.0)
        robot.teleport(goal_xy, 0.0)
        drive([0.0, 0.0, 0.0])
        for _ in range(8):
            capture_step()
        settings.set("/rtx/post/dlss/execMode", 2)
        capture_step()
        goal = robot.rgb().copy()
        goal_time = float(cam.get_current_frame()["rendering_time"])
        Image.fromarray(goal).save(out / "goal.png")
        robot.teleport((1.0, 0.0), 0.0)
        drive([0.0, 0.0, 0.0])
        for _ in range(8):
            capture_step()
        Image.fromarray(robot.rgb()).save(out / "start.png")
        usd.GetRootLayer().Export(str(out / "fixture.usda"))
        manifest.update(
            requested={"sim": cfg.to_dict(), "robot": robot_cfg.to_dict()},
            fixture={
                "boxes": boxes,
                "start": [1.0, 0.0, 0.0],
                "goal": [3.0, 0.0, 0.0],
                "goal_radius_m": 0.5,
                "safety_clearance_m": 0.3,
            },
            wheel_mapping=wheel_indices,
            camera_local_pose=[np.asarray(v).tolist() for v in cam.get_local_pose()],
            observed_rates={
                "physics_dt": sim.get_physics_dt(),
                "rendering_dt": sim.get_rendering_dt(),
            },
        )
        source = {Path(__file__).resolve()}
        for name, module in list(sys.modules.items()):
            file = getattr(module, "__file__", None)
            if file and name.startswith(("navfm", "vint_train")):
                source.add(Path(file).resolve())
        handles = RuntimeHandles(
            repo=REPO,
            influencing_files=sorted(source),
            camera=cam,
            articulation=robot._articulation,
            settings=settings,
            render_product_camera_target_reader=render_product.get_camera_prim_path,
            render_product_resolution_reader=render_product.get_resolution,
            metadata=manifest["requested"],
            goal_capture_sim_time=goal_time,
        )
        save("EPISODE")
        history = [robot.rgb().copy()] * 6
        captures, inference = [], []
        writer = RecordingTrajectoryWriter(out / "trajectory", metadata=manifest["requested"])
        writer.open()
        previous = float(cam.get_current_frame()["rendering_time"])
        contacts.clear()
        command = [0.0, 0.0, 0.0]
        bbox_cache = UsdGeom.BBoxCache(0.0, [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
        local_bound = bbox_cache.ComputeLocalBound(
            usd.GetPrimAtPath(robot.prim_path)
        ).ComputeAlignedRange()
        lower, upper = np.asarray(local_bound.GetMin())[:2], np.asarray(local_bound.GetMax())[:2]
        corners = np.array(
            [[lower[0], lower[1]], [lower[0], upper[1]], [upper[0], lower[1]], [upper[0], upper[1]]]
        )
        manifest["clearance_definition"] = (
            "world AABB of measured local robot visual bound transformed by evaluation-only articulation pose; conservative envelope, not exact surface distance"
        )
        manifest["local_robot_xy_corners"] = corners.tolist()
        for i in range(args.steps):
            loop_start = time.perf_counter()
            before = float(sim.current_time)
            xy, yaw = robot.pose()  # evaluator/recording only
            pose_before = [*xy.tolist(), yaw]
            if i % 3 == 0:
                history = [*history, robot.rgb().copy()][-6:]
                result = policy.step(history, goal)
                command = result["command"]
                inference.append(dict(result, physics_frame=i))
            drive(command)
            capture_step()
            after = float(sim.current_time)
            sensor = float(cam.get_current_frame()["rendering_time"])
            rgb = robot.rgb()
            xy, yaw = robot.pose()
            pose = [*xy.tolist(), yaw]
            validate_capture(
                rgb,
                pose,
                command_time=before,
                capture_time=after,
                sensor_time=sensor,
                previous_sensor_time=previous,
                resolution=(640, 480),
                dt=cfg.dt,
            )
            observations = collect_all(
                dataclasses.replace(
                    handles, sim_time_at_command=before, sim_time_at_capture=sensor, frame=rgb
                ),
                run_id=out.name,
            )
            decision = decide(
                observations, requested_values(manifest["requested"]), run_id=out.name
            )
            manifest["preflight"] = decision.to_dict()
            manifest["observations"] = [o.to_dict() for o in observations]
            require_scientific_preflight(decision)
            writer.append(
                rgb,
                xy,
                yaw,
                transition=dict(
                    frame_index=i,
                    pre_image_index=i - 1 if i else None,
                    time_before=before,
                    time_after=after,
                    pose_before=pose_before,
                    pose_after=pose,
                    command_requested=command,
                    command_accepted=command,
                ),
            )
            rotation = np.array([[math.cos(yaw), -math.sin(yaw)], [math.sin(yaw), math.cos(yaw)]])
            world_corners = corners @ rotation.T + xy
            lo, hi = world_corners.min(axis=0), world_corners.max(axis=0)
            gaps = []
            for box in boxes:
                low = np.asarray(box["xy"]) - np.asarray(box["size"]) / 2
                high = np.asarray(box["xy"]) + np.asarray(box["size"]) / 2
                gap = np.maximum(
                    np.maximum(low - np.asarray(hi)[:2], np.asarray(lo)[:2] - high), 0.0
                )
                gaps.append(float(np.linalg.norm(gap)))
            captures.append(
                {
                    "sensor_time": sensor,
                    "simulation_time": after,
                    "pose": pose,
                    "step_duration_s": after - before,
                    "distance_to_goal_m": float(math.dist(xy, goal_xy)),
                    "aabb_clearance_m": min(gaps),
                    "wall_loop_ms": (time.perf_counter() - loop_start) * 1000,
                }
            )
            previous = sensor
        drive([0.0, 0.0, 0.0])
        writer.close()
        verify_saved_recording(out / "trajectory", captures, (640, 480))
        final_distance = captures[-1]["distance_to_goal_m"]
        metrics = {
            "episodes": 1,
            "policy_stop_events": 0,
            "correct_stopping": 0,
            "premature_stopping": 0,
            "navigation_success_final_position": int(final_distance <= 0.5),
            "collision_episodes": int(bool(contacts)),
            "contact_events": len(contacts),
            "safety_violation_duration_s": sum(
                frame["step_duration_s"] for frame in captures if frame["aabb_clearance_m"] < 0.3
            ),
            "final_goal_distance_m": final_distance,
            "path_length_m": sum(
                math.dist(a["pose"][:2], b["pose"][:2]) for a, b in pairwise(captures)
            ),
            "policy_latency_p95_ms": float(np.percentile([r["latency_ms"] for r in inference], 95)),
            "wall_loop_p95_ms": float(np.percentile([r["wall_loop_ms"] for r in captures], 95)),
            "termination": "timeout",
            "physics_frames": len(captures),
            "inferences": len(inference),
        }
        manifest.update(
            status="PASS",
            frames=len(captures),
            captures=captures,
            inference=inference,
            contacts=contacts,
            metrics=metrics,
            contact_subscription_active=subscription is not None,
            file_sha256={
                file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                for file in (out / "trajectory").iterdir()
                if file.is_file()
            },
        )
        save("RECORDED")
        return 0
    except Exception as exc:
        manifest["error_stage"] = manifest.get("stage")
        manifest.update(status="BLOCKED", error=f"{type(exc).__name__}: {exc}")
        save("FAILED")
        raise
    finally:
        faulthandler.cancel_dump_traceback_later()
        if app is not None:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
