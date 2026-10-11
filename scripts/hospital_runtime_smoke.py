"""Stationary Hospital instrumentation smoke; never scientific route admission."""
from __future__ import annotations

import argparse
import dataclasses
import faulthandler
import hashlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def json_value(value):
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"unsupported runtime evidence type: {type(value).__name__}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scene", required=True)
    p.add_argument("--robot", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--frames", type=int, default=12)
    p.add_argument("--rt-subframes", type=int, default=1,
                   help="prospective capture setting; not historical reconstruction")
    args = p.parse_args()
    out = Path(args.out).expanduser().resolve()
    if out.is_relative_to(REPO) or out.exists() or not 12 <= args.frames <= 240 or args.rt_subframes < 1:
        p.error("output must be new and outside repository; frames must be 12..240")
    version = importlib.metadata.version("isaacsim")
    if not version.startswith("5.1."):
        p.error(f"installed simulator {version}: this probe is verified for 5.1 only")
    out.mkdir(parents=True)
    faulthandler.enable()
    faulthandler.dump_traceback_later(120, repeat=True)
    manifest = {"run_class": "STATIONARY_ENGINEERING_SMOKE", "scientific_arm_a_n": 0,
                "simulator_version": version, "scene": args.scene,
                "launch_environment": {"OMNICLIENT_HUB_MODE": os.environ.get("OMNICLIENT_HUB_MODE")},
                "ground_truth_use": "instrumentation and evaluation only; no deployed policy"}
    app = None
    def progress(stage_name):
        manifest.update(status="RUNNING", stage=stage_name)
        (out / "runtime_manifest.json").write_text(json.dumps(manifest, indent=2,
            default=json_value, allow_nan=False)+"\n")
        print(stage_name, flush=True)

    try:
        progress("BEFORE_APP")
        from isaacsim import SimulationApp
        app = SimulationApp({"headless": True, "renderer": "RayTracedLighting",
                             "width": 640, "height": 480})
        progress("AFTER_APP")
        import carb
        import numpy as np
        import omni.replicator.core as rep
        from isaacsim.core.api import SimulationContext
        from isaacsim.core.utils import render_product, stage
        from PIL import Image

        from navfm.collection.attestation import (
            Provenance,
            RuntimeHandles,
            collect_all,
            requested_values,
        )
        from navfm.collection.attestation_gate import decide
        from navfm.collection.recording import RecordingTrajectoryWriter
        from navfm.collection.scientific_preflight import (
            require_scientific_preflight,
            validate_capture,
            verify_saved_recording,
        )
        from navfm.isaac.app import SimConfig
        from navfm.isaac.robot import M3PRO, SimRobot

        cfg = SimConfig(rt_subframes=args.rt_subframes)
        robot_cfg = dataclasses.replace(M3PRO, usd_path=args.robot)
        metadata = {"sim": cfg.to_dict(), "robot": robot_cfg.to_dict()}
        manifest["requested"] = metadata
        settings = carb.settings.get_settings()
        settings.set("/rtx/post/dlss/execMode", 2)
        settings.set("/omni/replicator/RTSubframes", cfg.rt_subframes)
        rep.orchestrator.set_capture_on_play(False)
        progress("BEFORE_STAGE")
        stage.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0, physics_dt=cfg.dt, rendering_dt=cfg.dt)
        stage.add_reference_to_stage(args.scene, "/World/Scene")
        sim.initialize_physics()
        sim.play()
        progress("BEFORE_ROBOT")
        robot = SimRobot(app, robot_cfg)
        robot.spawn(position=(-39.90271172754076, 23.12059657138799, robot_cfg.spawn_height),
                    yaw=-1.3986055122719583)
        for _ in range(5):
            sim.step(render=False)
        robot.attach_camera()
        progress("AFTER_CAMERA")
        camera = robot._camera
        # Prospective application, never a reconstruction of historical intrinsics.
        camera.set_focal_length(robot_cfg.camera.usd_focal_length(camera.get_horizontal_aperture()))
        settings.set("/app/runLoops/main/rateLimitEnabled", True)
        settings.set("/app/runLoops/main/rateLimitFrequency", cfg.hz)
        # Stage/physics initialization may override rates; apply after construction
        # and retain independent getters rather than asserting the request took effect.
        sim.set_simulation_dt(physics_dt=cfg.dt, rendering_dt=cfg.dt)
        manifest["observed_rates"] = {"physics_dt": sim.get_physics_dt(),
                                      "rendering_dt": sim.get_rendering_dt()}
        def step_capture():
            sim.play()
            rep.orchestrator.step(rt_subframes=cfg.rt_subframes, delta_time=cfg.dt,
                                  pause_timeline=True)
            # Subframes on a moving timeline can expose an intermediate sensor
            # timestamp. Capture again at the completed, paused physics instant.
            rep.orchestrator.step(rt_subframes=cfg.rt_subframes, delta_time=0.0,
                                  pause_timeline=True)
        for _ in range(cfg.warmup_frames):
            step_capture()
        progress("AFTER_WARMUP")
        # Camera/render-product initialization can override post-processing.
        settings.set("/rtx/post/dlss/execMode", 2)
        goal_time = float(camera.get_current_frame()["rendering_time"])
        Image.fromarray(robot.rgb()).save(out / "reference.png")
        manifest["reference_capture"] = {"sensor_time": goal_time,
            "role": "stationary smoke reference only; not a navigation goal"}
        source_files = {Path(__file__).resolve()}
        for name, module in list(sys.modules.items()):
            file = getattr(module, "__file__", None)
            if file and name.startswith(("navfm", "isaacsim.sensors.camera", "isaacsim.core.api",
                                         "isaacsim.core.utils.render_product")):
                source_files.add(Path(file).resolve())
        handles = RuntimeHandles(repo=REPO, influencing_files=sorted(source_files),
            camera=camera, articulation=robot._articulation, settings=settings,
            render_product_camera_target_reader=render_product.get_camera_prim_path,
            render_product_resolution_reader=render_product.get_resolution, metadata=metadata,
            goal_capture_sim_time=goal_time)
        manifest["observed_intrinsics_matrix"] = np.asarray(camera.get_intrinsics_matrix()).tolist()
        manifest["observed_camera_world_pose"] = [np.asarray(v).tolist() for v in camera.get_world_pose()]
        manifest["observed_camera_local_pose"] = [np.asarray(v).tolist() for v in camera.get_local_pose()]
        manifest["robot_asset_sha256"] = hashlib.sha256(Path(args.robot).read_bytes()).hexdigest()
        records = []
        writer = RecordingTrajectoryWriter(out / "trajectory", metadata=metadata)
        writer.open()
        previous = goal_time
        for i in range(args.frames):
            before = float(sim.current_time)
            xy, yaw = robot.pose()
            pose_before = [*xy.tolist(), yaw]
            robot.set_body_velocity(0.0, 0.0, 0.0)
            step_capture()
            after = float(sim.current_time)
            frame = camera.get_current_frame()
            sensor_time = float(frame["rendering_time"])
            rgb = robot.rgb()
            xy, yaw = robot.pose()
            pose = [*xy.tolist(), yaw]
            manifest["last_capture"] = {"command_time": before, "simulation_time": after,
                                        "sensor_time": sensor_time, "pose": pose}
            observations = collect_all(dataclasses.replace(handles, sim_time_at_command=before,
                sim_time_at_capture=sensor_time, frame=rgb), run_id=out.name, provenance=Provenance.LIVE_RUNTIME)
            decision = decide(observations, requested_values(metadata), run_id=out.name)
            manifest["preflight"] = decision.to_dict()
            manifest["observations"] = [o.to_dict() for o in observations]
            validate_capture(rgb, pose, command_time=before, capture_time=after,
                sensor_time=sensor_time, previous_sensor_time=previous,
                resolution=robot_cfg.camera.resolution, dt=cfg.dt)
            require_scientific_preflight(decision)
            transition = dict(frame_index=i, pre_image_index=i-1 if i else None,
                time_before=before, time_after=after, pose_before=pose_before, pose_after=pose,
                command_requested=[0., 0., 0.], command_accepted=[0., 0., 0.])
            writer.append(rgb, xy, yaw, transition=transition)
            records.append({"sensor_time": sensor_time, "simulation_time": after,
                "rendering_frame": frame["rendering_frame"], "pose": pose,
                "image_statistic": next(o.to_dict() for o in observations if o.requirement == "R7")})
            previous = sensor_time
        writer.close()
        verify_saved_recording(out / "trajectory", records, robot_cfg.camera.resolution)
        manifest.update(status="PASS", frames=len(records), captures=records,
            file_sha256={f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                         for f in (out / "trajectory").iterdir() if f.is_file()})
        return 0
    except Exception as exc:
        manifest.update(status="BLOCKED", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        faulthandler.cancel_dump_traceback_later()
        try:
            (out / "runtime_manifest.json").write_text(json.dumps(manifest, indent=2,
                default=json_value, allow_nan=False)+"\n")
        finally:
            if app is not None:
                app.close()


if __name__ == "__main__":
    raise SystemExit(main())
