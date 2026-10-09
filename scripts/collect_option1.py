"""Collect ten local moving RGB demonstrations with strict runtime attestation."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.metadata
import json
import math
import os
import sys
import time
import traceback
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
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--robot", required=True)
    parser.add_argument("--max-steps", type=int, default=240)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--route-spec", type=Path, help="prospective external or tracked route/layout specification"
    )
    parser.add_argument("--route-id", action="append", help="recollect a named route; may repeat")
    parser.add_argument(
        "--actuation", choices=["wheel", "body_velocity", "pose_step"], default="pose_step"
    )
    parser.add_argument(
        "--checkpoint", type=Path, help="live RGB policy; never use teacher pose in policy"
    )
    parser.add_argument("--qualification", type=Path)
    parser.add_argument(
        "--checkpoint-sha256", help="required registered checkpoint identity for live policy"
    )
    parser.add_argument("--goal-root", type=Path, help="fixed raw goals indexed by route id")
    parser.add_argument(
        "--policy-period-frames",
        type=int,
        default=3,
        help="12 Hz frames per policy decision; 3 = 4 Hz (historical), 6 = 2 Hz",
    )
    parser.add_argument(
        "--stop-rule",
        choices=["project", "upstream_t3"],
        default="project",
        help="project = historical <=1 rule; upstream_t3 = pinned close_threshold 3",
    )
    parser.add_argument(
        "--goal-settle-steps",
        type=int,
        default=8,
        help="render steps after teleporting to the goal before its photograph; 8 is historical",
    )
    args = parser.parse_args()
    policy = None
    if args.checkpoint:
        if args.actuation != "wheel" or not args.qualification or not args.goal_root:
            parser.error(
                "live policy requires wheel actuation, qualified manifest and fixed RGB goals"
            )
        qualification = json.loads(args.qualification.read_text())
        if (
            not args.checkpoint_sha256
            or hashlib.sha256(args.checkpoint.read_bytes()).hexdigest() != args.checkpoint_sha256
        ):
            parser.error("registered checkpoint digest required and must match")
        if (
            qualification.get("robot_sha256")
            != hashlib.sha256(Path(args.robot).read_bytes()).hexdigest()
        ):
            parser.error("robot asset differs from qualification")
        if (
            not all(
                qualification.get(k)
                for k in ["analytic_colliders", "sphere_wheels", "acceleration_drive"]
            )
            or qualification.get("yaw_gain") != 1.5
            or qualification.get("mixed_yaw_gain") != 0.8
        ):
            parser.error("qualification does not describe this controller")
        if qualification["status"] != "PASS":
            parser.error("articulated qualification did not pass")
        from navfm.collection.rgb_baseline import RGBBaseline

        if args.policy_period_frames < 1:
            parser.error("policy period must be at least one frame")
        policy = RGBBaseline(
            args.checkpoint,
            action_scale_m=0.049994826316833496,
            stop_enabled=True,
            max_v=0.1,
            control_period_s=args.policy_period_frames / 12.0,
            stop_rule=args.stop_rule,
        )
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(REPO):
        parser.error("output must be new and external")
    out.mkdir(parents=True)
    from navfm.collection.demonstrations import DemonstrationTeacher, route_specs

    routes = (json.loads(args.route_spec.read_text()) if args.route_spec else route_specs())[
        : args.limit
    ]
    if args.route_id:
        known = {r["id"] for r in routes}
        if set(args.route_id) - known:
            parser.error("unknown route id")
        routes = [r for r in routes if r["id"] in args.route_id]
    (out / "frozen_routes.json").write_text(json.dumps(routes, indent=2) + "\n")
    summary = {"scope": "OPTION1_DATASET_ENGINEERING", "episodes": [], "status": "RUNNING"}

    def save_summary():
        (out / "collection.json").write_text(json.dumps(summary, indent=2, default=encode) + "\n")

    save_summary()
    from isaacsim import SimulationApp

    app = SimulationApp(
        {"headless": True, "renderer": "RayTracedLighting", "width": 320, "height": 240}
    )
    try:
        import carb
        import numpy as np
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
        from navfm.collection.source_stability import verify_source_stability
        from navfm.isaac.app import SimConfig
        from navfm.isaac.robot import M3PRO, SimRobot

        stage.create_new_stage()
        usd = omni.usd.get_context().get_stage()
        fixtures = {}

        def cube(name, xyz, size, color, collision=True):
            prim = UsdGeom.Cube.Define(usd, name)
            prim.CreateSizeAttr(1.0)
            xf = UsdGeom.XformCommonAPI(prim)
            xf.SetTranslate(Gf.Vec3d(*xyz))
            xf.SetScale(Gf.Vec3f(*size))
            prim.CreateDisplayColorAttr([Gf.Vec3f(*color)])
            if collision:
                UsdPhysics.CollisionAPI.Apply(prim.GetPrim())

        # All geometry is created before initializing physics. Scenes are spatially
        # separated; no live schema edits or tensor-view invalidation is needed.
        for scene in sorted({r["scene_index"] for r in routes}):
            origin = scene * 20.0
            half = next(r["wall_half_width"] for r in routes if r["scene_index"] == scene)
            root = f"/World/Fixture/Scene{scene}"
            cube(
                root + "/Floor",
                (2.0, origin, -0.05),
                (8.0, 8.0, 0.1),
                (0.35 + 0.04 * (scene % 5), 0.4, 0.45),
            )
            cube(
                root + "/WallLeft",
                (2.0, origin + half, 1.4),
                (6.0, 0.2, 2.8),
                (0.65, 0.7 - 0.05 * (scene % 5), 0.75),
            )
            cube(
                root + "/WallRight",
                (2.0, origin - half, 1.4),
                (6.0, 0.2, 2.8),
                (0.65, 0.7, 0.75 - 0.04 * (scene % 5)),
            )
            cube(root + "/EndWall", (5.0, origin, 1.4), (0.2, 2 * half, 2.8), (0.6, 0.65, 0.7))
            obstacle = (3.5 + 0.1 * (scene % 5), origin + 1.45, 0.4)
            cube(root + "/Obstacle", obstacle, (0.45, 0.4, 0.8), (0.1, 0.3, 0.7))
            # Prospective scene landmarks prevent plain-wall image-goal ambiguity.
            # These are rendered USD geometry, never overlays on captured images.
            for side in (-1, 1):
                for stripe in range(12):
                    color = (0.15, 0.35, 0.65) if stripe % 2 else (0.75, 0.35, 0.12)
                    cube(
                        root + f"/Stripe{'L' if side > 0 else 'R'}_{stripe}",
                        (-0.4 + stripe * 0.5, origin + side * (half - 0.105), 1.0),
                        (0.15, 0.015, 1.3),
                        color,
                        False,
                    )
            for ix in range(8):
                for iy in range(8):
                    if (ix + iy) % 2 == 0:
                        cube(
                            root + f"/Tile{ix}_{iy}",
                            (-1.5 + ix, origin - 3.5 + iy, 0.002),
                            (1.0, 1.0, 0.002),
                            (0.22, 0.26, 0.30),
                            False,
                        )
            fixtures[scene] = {
                "scene_index": scene,
                "origin_y": origin,
                "wall_half_width": half,
                "obstacle_xyz": obstacle,
            }
        if args.route_spec:
            # Distinct partition geometry is prospective and shared within each layout only.
            for scene in sorted(fixtures):
                origin = scene * 20.0
                for side in (-1, 1):
                    cube(
                        f"/World/Fixture/Scene{scene}/DoorPartition{side + 1}",
                        (1.75 + 0.12 * (scene % 5), origin + side * 1.45, 0.7),
                        (0.16, 0.65 + 0.08 * (scene % 5), 1.4),
                        (0.35, 0.45, 0.25),
                    )
                fixtures[scene]["door_partition_x"] = 1.75 + 0.12 * (scene % 5)
                fixtures[scene]["door_partition_width"] = 0.65 + 0.08 * (scene % 5)
        sun = UsdLux.DistantLight.Define(usd, "/World/Fixture/Sun")
        sun.CreateIntensityAttr(1500.0)
        UsdGeom.XformCommonAPI(sun).SetRotate(Gf.Vec3f(-45.0, 30.0, 0.0))
        dome = UsdLux.DomeLight.Define(usd, "/World/Fixture/Dome")
        dome.CreateIntensityAttr(800.0)
        summary["lighting"] = {
            "requested": {"distant_count": 1, "distant_intensity": 1500.0, "dome_intensity": 800.0},
            "observed_usd": {
                "distant_count": sum(prim.IsA(UsdLux.DistantLight) for prim in usd.Traverse()),
                "distant_intensity": sun.GetIntensityAttr().Get(),
                "dome_intensity": dome.GetIntensityAttr().Get(),
            },
        }
        save_summary()
        cfg = SimConfig(resolution=(320, 240), rt_subframes=1, physics_substeps=10 if policy else 1)
        robot_cfg = dataclasses.replace(
            M3PRO,
            usd_path=args.robot,
            camera=dataclasses.replace(
                M3PRO.camera, resolution=(320, 240), height=0.55, x_offset=0.2, pitch_deg=0.0
            ),
        )
        sim = SimulationContext(
            stage_units_in_meters=1.0, physics_dt=cfg.dt / cfg.physics_substeps, rendering_dt=cfg.dt
        )
        robot = SimRobot(app, robot_cfg)
        stage.add_reference_to_stage(args.robot, robot.prim_path)
        if policy:
            for link in ["base_link", "fl_wheel", "fr_wheel", "rl_wheel", "rr_wheel"]:
                root = robot.prim_path + "/" + link
                usd.OverridePrim(root + "/collisions").SetActive(False)
                if link == "base_link":
                    shape = UsdGeom.Cube.Define(usd, root + "/QualifiedCollision")
                    shape.CreateSizeAttr(1.0)
                    x = UsdGeom.XformCommonAPI(shape)
                    x.SetScale(Gf.Vec3f(0.29, 0.235, 0.08))
                    x.SetTranslate(Gf.Vec3d(0, 0, 0.04))
                else:
                    shape = UsdGeom.Sphere.Define(usd, root + "/QualifiedCollision")
                    shape.CreateRadiusAttr(0.04)
                UsdPhysics.CollisionAPI.Apply(shape.GetPrim())
        drives = []
        for prim in usd.Traverse():
            if str(prim.GetPath()).startswith(robot.prim_path):
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr(0.0)
                if prim.IsA(UsdPhysics.RevoluteJoint):
                    drive = UsdPhysics.DriveAPI.Get(prim, "angular")
                    previous = {
                        "stiffness": drive.GetStiffnessAttr().Get(),
                        "damping": drive.GetDampingAttr().Get(),
                    }
                    drive.GetStiffnessAttr().Set(0.0)
                    damping = 1000.0 if policy else 10.0 if args.actuation == "wheel" else 0.0
                    if policy:
                        drive.GetTypeAttr().Set("acceleration")
                    drive.GetDampingAttr().Set(damping)
                    drives.append(
                        {
                            "path": str(prim.GetPath()),
                            "asset": previous,
                            "requested": {"stiffness": 0.0, "damping": damping},
                            "observed": {
                                "stiffness": drive.GetStiffnessAttr().Get(),
                                "damping": drive.GetDampingAttr().Get(),
                            },
                        }
                    )
        sim.initialize_physics()
        sim.play()
        robot._attach()
        robot._articulation.initialize()
        for _ in range(5):
            sim.step(render=False)
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
        settings.set("/app/runLoops/main/rateLimitEnabled", True)
        settings.set("/app/runLoops/main/rateLimitFrequency", 12.0)
        settings.set("/omni/replicator/RTSubframes", 1)
        # Observed, not pinned: auto-exposure adapts over frames, so the state at
        # each capture depends on what the camera saw before it.
        summary["renderer_settings"] = {
            key: settings.get(key)
            for key in (
                "/rtx/post/histogram/enabled",
                "/rtx/post/histogram/tau",
                "/rtx/post/histogram/minEV",
                "/rtx/post/histogram/maxEV",
                "/rtx/post/histogram/whiteScale",
                "/rtx/post/histogram/useExposureClamping",
                "/rtx/post/tonemap/op",
                "/rtx/post/dlss/execMode",
            )
        }
        summary["goal_settle_steps"] = args.goal_settle_steps
        save_summary()
        sim.set_simulation_dt(physics_dt=cfg.dt / cfg.physics_substeps, rendering_dt=cfg.dt)
        rep.orchestrator.set_capture_on_play(False)

        def step():
            sim.play()
            rep.orchestrator.step(rt_subframes=1, delta_time=cfg.dt, pause_timeline=True)
            rep.orchestrator.step(rt_subframes=1, delta_time=0.0, pause_timeline=True)
            # Bounded re-render at unchanged physics time; never relabel an old frame.
            for _ in range(3):
                frame_time = cam.get_current_frame().get("rendering_time")
                if frame_time is not None and math.isclose(
                    float(frame_time), float(sim.current_time), abs_tol=1e-8
                ):
                    break
                rep.orchestrator.step(rt_subframes=1, delta_time=0.0, pause_timeline=True)

        names = list(robot._articulation.dof_names)
        indices = {
            p: [i for i, n in enumerate(names) if n.lower().startswith(p)]
            for p in ("fl", "fr", "rl", "rr")
        }
        if any(len(i) != 1 for i in indices.values()):
            raise ValueError("ambiguous wheel indices")

        def drive(command):
            if args.actuation == "pose_step":
                # Kinematic demonstration generation only. Record actual post-render
                # poses, not these requested positions, as the training labels.
                xy, yaw = robot.pose()
                vx, vy, w = command
                c, s = math.cos(yaw), math.sin(yaw)
                next_xy = xy + cfg.dt * np.array([c * vx - s * vy, s * vx + c * vy])
                robot.teleport(next_xy, yaw + cfg.dt * w)
                return
            if args.actuation == "body_velocity":
                # Privileged pose conversion belongs to the demonstration teacher.
                # This is not the deployed wheel-controller qualification.
                robot.set_body_velocity(*command)
                return
            v, vy, w = command
            if policy:
                w *= 1.5 if abs(v) < 1e-6 else 0.8
            k = 0.0775 + 0.085
            r = 0.04
            speeds = [
                (v - vy - k * w) / r,
                (v + vy + k * w) / r,
                (v + vy - k * w) / r,
                (v - vy + k * w) / r,
            ]
            values = np.zeros((1, len(names)), dtype=np.float32)
            for ids, value in zip(indices.values(), speeds, strict=True):
                values[0, ids[0]] = value
            robot._articulation.set_joint_velocity_targets(values)

        contacts = []

        def contact_event(headers, data):
            for h in headers:
                paths = [
                    str(PhysicsSchemaTools.intToSdfPath(actor)) for actor in (h.actor0, h.actor1)
                ]
                if any(p.startswith(robot.prim_path) for p in paths) and any(
                    "/World/Fixture/" in p and not p.endswith("/Floor") for p in paths
                ):
                    contacts.append(
                        {"time": float(sim.current_time), "paths": paths, "type": int(h.type)}
                    )

        subscription = omni.physx.get_physx_simulation_interface().subscribe_contact_report_events(
            contact_event
        )
        usd.GetRootLayer().Export(str(out / "fixture.usda"))
        identity = {}
        if policy:
            # A fixed goal photograph is valid only for the scene it photographed.
            from pxr import Usd

            from navfm.collection import fixture_identity

            goal_fixture = args.goal_root / "fixture.usda"
            goal_stage = Usd.Stage.Open(str(goal_fixture))
            try:
                for route in routes:
                    source = json.loads(
                        (args.goal_root / route["id"] / "runtime_manifest.json").read_text()
                    )
                    fixture_identity.require_identical(
                        {"route": source["route"]}, {"route": route}, what="route"
                    )
                    roots = fixture_identity.scene_roots(route["scene_index"])
                    expected = fixture_identity.prim_signature(goal_stage, roots)
                    observed = fixture_identity.prim_signature(usd, roots)
                    if not expected:
                        raise ValueError(f"goal-photo source has no prims under {roots[0]}")
                    fixture_identity.require_identical(
                        expected, observed, what=f"{route['id']} fixture"
                    )
                    identity[route["id"]] = {
                        "scene_signature_sha256": fixture_identity.digest(observed),
                        "signed_prims": len(observed),
                        "goal_source_fixture_sha256": hashlib.sha256(
                            goal_fixture.read_bytes()
                        ).hexdigest(),
                    }
            except ValueError as error:
                summary["status"] = "REFUSED_FIXTURE_IDENTITY"
                summary["refusal"] = str(error)
                save_summary()
                raise
            summary["fixture_identity"] = identity
            save_summary()
        source_expected = None
        for route in routes:
            episode = out / route["id"]
            episode.mkdir()
            manifest = {
                "status": "RUNNING",
                "scope": "OPTION1_SCRIPTED_DEMONSTRATION",
                "route": route,
                "fixture": fixtures[route["scene_index"]],
                "simulator_version": importlib.metadata.version("isaacsim"),
                "prospective_wheel_drives": drives,
                "wheel_mapping": indices,
                "teacher_privileged_inputs": []
                if policy
                else [
                    "simulation xy",
                    "simulation yaw",
                    "scripted waypoints",
                ],
                "deployed_policy_inputs": policy.manifest["policy_inputs"] if policy else None,
                "policy": policy.manifest if policy else None,
                "qualification_sha256": hashlib.sha256(args.qualification.read_bytes()).hexdigest()
                if policy
                else None,
                "teacher_actuation": args.actuation,
            }

            def save(episode=episode, manifest=manifest):
                (episode / "runtime_manifest.json").write_text(
                    json.dumps(manifest, indent=2, default=encode, allow_nan=False) + "\n"
                )

            save()
            writer = None
            try:
                np.random.seed(route["seed"])
                points = np.array(route["waypoints"])
                points[:, 1] += route["scene_index"] * 20.0
                # Goal image is a real camera capture at the scripted endpoint,
                # not a rendered label or a privileged input to the learned model.
                end_yaw = math.atan2(*(points[-1] - points[-2])[::-1])
                robot.teleport(points[-1], end_yaw)
                drive([0.0, 0.0, 0.0])
                for _ in range(args.goal_settle_steps):
                    step()
                settings.set("/rtx/post/dlss/execMode", 2)
                step()
                goal_time = float(cam.get_current_frame()["rendering_time"])
                Image.fromarray(robot.rgb()).save(episode / "goal.png")
                robot.teleport(points[0], route["start_yaw"])
                drive([0.0, 0.0, 0.0])
                for _ in range(8):
                    step()
                Image.fromarray(robot.rgb()).save(episode / "start.png")
                requested = {
                    "sim": dataclasses.replace(cfg, seed=route["seed"]).to_dict(),
                    "robot": robot_cfg.to_dict(),
                }
                manifest.update(
                    requested=requested,
                    camera_local_pose=[np.asarray(v).tolist() for v in cam.get_local_pose()],
                    observed_rates={
                        "physics_dt": sim.get_physics_dt(),
                        "rendering_dt": sim.get_rendering_dt(),
                    },
                )
                sources = {Path(__file__).resolve()}
                for name, module in list(sys.modules.items()):
                    file = getattr(module, "__file__", None)
                    if file and name.startswith(("navfm", "vint_train")):
                        sources.add(Path(file).resolve())
                if source_expected is None:
                    source_expected = {
                        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
                    }
                handles = RuntimeHandles(
                    repo=REPO,
                    influencing_files=sorted(sources),
                    camera=cam,
                    articulation=robot._articulation,
                    settings=settings,
                    render_product_camera_target_reader=render_product.get_camera_prim_path,
                    render_product_resolution_reader=render_product.get_resolution,
                    metadata=requested,
                    goal_capture_sim_time=goal_time,
                    intent_only_fields=(
                        "sim.seed",
                        "collect.episodes",
                        "collect.max_stationary_fraction",
                    ),
                )
                teacher = DemonstrationTeacher(points, route["speed"])
                if policy:
                    policy.stop_count = 0
                    policy.stopped = False
                    goal = np.asarray(
                        Image.open(args.goal_root / route["id"] / "goal.png").convert("RGB")
                    )
                    Image.fromarray(goal).save(episode / "goal.png")
                    goal_source_path = args.goal_root / route["id"] / "runtime_manifest.json"
                    goal_source = json.loads(goal_source_path.read_text())
                    fixture_identity.require_identical(
                        fixture_identity.camera_signature(goal_source),
                        fixture_identity.camera_signature(manifest),
                        what=f"{route['id']} camera",
                    )
                    manifest["fixture_identity"] = identity[route["id"]]
                    manifest["fixed_goal_source_manifest_sha256"] = hashlib.sha256(
                        goal_source_path.read_bytes()
                    ).hexdigest()
                    manifest["fixed_goal_source_capture_sim_time"] = next(
                        (
                            o["value"]
                            for o in goal_source.get("observations", [])
                            if o["name"] == "goal_capture_sim_time"
                        ),
                        None,
                    )
                    manifest["fixed_goal_time_epoch"] = args.goal_root.name
                    manifest["goal_time_definition"] = (
                        "R3 is unused local capture; policy goal has separate source collection clock and observed original capture time, possibly unknown"
                    )
                    manifest["fixed_goal_sha256"] = hashlib.sha256(
                        (episode / "goal.png").read_bytes()
                    ).hexdigest()
                    history = [robot.rgb().copy() for _ in range(6)]
                inference = []
                stop_frame = None
                command = [0.0, 0.0, 0.0]
                writer = RecordingTrajectoryWriter(
                    episode / "trajectory",
                    metadata={
                        **requested,
                        "policy_inputs": policy.manifest["policy_inputs"]
                        if policy
                        else "NOT_APPLICABLE_DEMONSTRATOR",
                    },
                )
                writer.open()
                captures = []
                contacts.clear()
                frame_available_wall = time.perf_counter()
                previous = float(cam.get_current_frame()["rendering_time"])
                reached = False
                for i in range(args.max_steps):
                    wall_start = time.perf_counter()
                    before = float(sim.current_time)
                    xy, yaw = robot.pose()
                    pose_before = [*xy.tolist(), yaw]
                    if policy:
                        if i % args.policy_period_frames == 0:
                            perception_start = time.perf_counter()
                            history = [*history, robot.rgb().copy()][-6:]
                            prediction = policy.step(history, goal)
                            command = prediction["command"]
                            drive(command)
                            prediction["perception_to_command_ms"] = (
                                time.perf_counter() - perception_start
                            ) * 1000
                            prediction["observed_frame_available_to_command_ms"] = (
                                time.perf_counter() - frame_available_wall
                            ) * 1000
                            prediction["frame"] = i
                            prediction["sensor_time"] = float(
                                cam.get_current_frame()["rendering_time"]
                            )
                            inference.append(prediction)
                            if prediction["policy_stop"] and stop_frame is None:
                                stop_frame = i
                        reached = stop_frame is not None and i - stop_frame >= 24
                    else:
                        command, reached = teacher.step(xy, yaw)
                    drive(command)
                    step()
                    after = float(sim.current_time)
                    sensor = float(cam.get_current_frame()["rendering_time"])
                    rgb = robot.rgb()
                    frame_available_wall = time.perf_counter()
                    xy, yaw = robot.pose()
                    pose = [*xy.tolist(), yaw]
                    validate_capture(
                        rgb,
                        pose,
                        command_time=before,
                        capture_time=after,
                        sensor_time=sensor,
                        previous_sensor_time=previous,
                        resolution=(320, 240),
                        dt=cfg.dt,
                    )
                    observations = collect_all(
                        dataclasses.replace(
                            handles,
                            sim_time_at_command=before,
                            sim_time_at_capture=sensor,
                            frame=rgb,
                        ),
                        run_id=route["id"],
                    )
                    observed_sources = next(
                        o.value for o in observations if o.name == "influencing_file_digests"
                    )
                    source_expected = verify_source_stability(source_expected, observed_sources)
                    decision = decide(observations, requested_values(requested), run_id=route["id"])
                    require_scientific_preflight(decision)
                    writer.append(
                        rgb,
                        xy,
                        yaw,
                        transition={
                            "frame_index": i,
                            "pre_image_index": i - 1 if i else None,
                            "time_before": before,
                            "time_after": after,
                            "pose_before": pose_before,
                            "pose_after": pose,
                            "command_requested": command,
                            "command_accepted": command,
                        },
                    )
                    captures.append(
                        {
                            "sensor_time": sensor,
                            "simulation_time": after,
                            "pose": pose,
                            "distance_to_goal_m": float(np.linalg.norm(xy - points[-1])),
                            "step_duration_s": after - before,
                            "wall_loop_ms": (time.perf_counter() - wall_start) * 1000,
                        }
                    )
                    previous = sensor
                    if reached and i >= 107:
                        break
                drive([0.0, 0.0, 0.0])
                writer.close()
                verify_saved_recording(episode / "trajectory", captures, (320, 240))
                manifest.update(
                    status="PASS",
                    frames=len(captures),
                    captures=captures,
                    contacts=contacts.copy(),
                    termination=("policy_stop" if reached else "timeout")
                    if policy
                    else "teacher_goal"
                    if reached
                    else "timeout",
                    inference=inference,
                    policy_stop_frame=stop_frame,
                    preflight=decision.to_dict(),
                    observations=[o.to_dict() for o in observations],
                    contact_subscription_active=subscription is not None,
                    file_sha256={
                        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (episode / "trajectory").iterdir()
                        if p.is_file()
                    },
                )
                if policy:
                    path_length = sum(
                        math.dist(a["pose"][:2], b["pose"][:2]) for a, b in pairwise(captures)
                    )
                    final_distance = captures[-1]["distance_to_goal_m"]
                    stopped_distance = (
                        captures[stop_frame]["distance_to_goal_m"]
                        if stop_frame is not None
                        else None
                    )
                    success = stop_frame is not None and final_distance <= 0.5 and not contacts
                    manifest["metrics"] = {
                        "success": int(success),
                        "correct_stopping": int(stop_frame is not None and stopped_distance <= 0.5),
                        "premature_stopping": int(
                            stop_frame is not None and stopped_distance > 0.5
                        ),
                        "collision_episode": int(bool(contacts)),
                        "path_length_m": path_length,
                        "path_efficiency": float(np.linalg.norm(points[-1] - points[0]))
                        / max(path_length, 1e-9)
                        if success
                        else 0.0,
                        "final_goal_distance_m": final_distance,
                        "perception_to_command_p95_ms": float(
                            np.percentile([r["perception_to_command_ms"] for r in inference], 95)
                        ),
                    }
                # Preserve exact executable source for future digest verification.
                archive = episode / "source_snapshot"
                archive.mkdir()
                for source in sources:
                    payload = source.read_bytes()
                    (archive / hashlib.sha256(payload).hexdigest()).write_bytes(payload)
                save()
                print(
                    route["id"],
                    manifest["termination"],
                    len(captures),
                    captures[-1]["distance_to_goal_m"],
                    flush=True,
                )
            except Exception as exc:
                drive([0.0, 0.0, 0.0])
                manifest.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
                save()
                print(route["id"], manifest["error"], flush=True)
            summary["episodes"].append(
                {
                    "id": route["id"],
                    "status": manifest["status"],
                    "error": manifest.get("error"),
                    "frames": manifest.get("frames"),
                }
            )
            save_summary()
        summary["status"] = "COMPLETED"
        save_summary()
    except BaseException as exc:
        refused = str(summary.get("status", "")).startswith("REFUSED")
        summary.update(
            status=summary["status"]
            if refused
            else ("INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAILED"),
            error=f"{type(exc).__name__}: {exc}",
        )
        save_summary()
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        # SimulationApp.close() can end the process with status 0; a failed or
        # refused collection must never report success to its caller.
        os._exit(3 if refused else 1)
    finally:
        app.close()


if __name__ == "__main__":
    main()
