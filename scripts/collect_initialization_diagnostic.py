"""Bounded scripted initialization probe; never invokes a learned policy."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import math
import sys
import traceback
from pathlib import Path

from initialization_diagnostic import REPO, frozen, history, sha, validate_render_interval

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
    if a.case not in cfg["cases"] or a.out.exists():
        p.error("undeclared case or existing output")
    if (a.role == "replay") != bool(a.reference):
        p.error("replay requires reference")
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

        def render_call(delta):
            before = float(sim.current_time)
            before_updates = updates
            sim.play()
            rep.orchestrator.step(rt_subframes=1, delta_time=delta, pause_timeline=True)
            after = float(sim.current_time)
            report.setdefault("render_calls", []).append(
                dict(
                    index=len(report.get("render_calls", [])),
                    requested_delta_s=delta,
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

        def capture(label, physical_step):
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
                observed["/rtx/post/dlss/execMode"] != 2
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
        frames = []
        for i, command in enumerate(commands):
            report.setdefault("command_readbacks", []).append(
                dict(index=i, pre_step_time=float(sim.current_time), command=command)
            )
            drive(command)
            step()
            frames.append(capture(f"script_{i:02d}", i + 1))
        continuous = copy.deepcopy(frames[-1])
        continuous["history"] = history(frames)
        method = "continuous" if a.role == "reference" else "command_replay"
        report["methods"][method] = continuous
        save()
        if a.role == "reference":
            original = copy.deepcopy(continuous)
            art.set_world_poses(
                np.array([original["root"]["position"]]), np.array([original["root"]["quaternion"]])
            )
            art.set_velocities(np.zeros((1, 6)))
            drive([0.0, 0.0, 0.0])
            for _ in range(8):
                step()
            roots = []
            for i in range(6):
                stationary_render()
                roots.append(capture(f"direct_root_{i}", 44))
            root = copy.deepcopy(roots[-1])
            root["history"] = [copy.deepcopy(roots[-1]) for _ in range(6)]
            report["methods"]["direct_root"] = root
            save()
            art.set_world_poses(
                np.array([original["root"]["position"]]), np.array([original["root"]["quaternion"]])
            )
            art.set_velocities(np.array([original["root_velocity"]]))
            art.set_joint_positions(np.array([original["joint_positions"]]))
            art.set_joint_velocities(np.array([original["joint_velocities"]]))
            art.set_joint_position_targets(np.array([original["joint_position_targets"]]))
            art.set_joint_velocity_targets(np.array([original["joint_velocity_targets"]]))
            held[:] = original["held_command"]
            tracker.integral = original["controller_integral"]
            proxy = copy.deepcopy(original["proxy_policy"])
            fulls = []
            for i in range(6):
                stationary_render()
                fulls.append(capture(f"direct_full_{i}", 44))
            full = copy.deepcopy(fulls[-1])
            full["history"] = [*copy.deepcopy(original["history"][:-1]), copy.deepcopy(fulls[-1])]
            report["methods"]["direct_full"] = full
            save()
        if subscription is None:
            raise ValueError("missing physics feedback subscription")
        frozen(a.freeze_commit, launch=True)
        report["post_run_actual_asset_sha256"] = {
            path: sha(Path(path)) for path in cfg["asset_sha256"]
        }
        report["post_run_actual_source_sha256"] = {
            name: sha(REPO / name) for name in __import__("initialization_diagnostic").FILES
        }
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
