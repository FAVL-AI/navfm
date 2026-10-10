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
    parser.add_argument(
        "--limit", type=int, help="first N routes (default 10; all for --layout-spec)"
    )
    parser.add_argument(
        "--route-spec", type=Path, help="prospective external or tracked route/layout specification"
    )
    parser.add_argument(
        "--layout-spec", type=Path, help="explicit scene boxes plus routes (scene_layouts.py)"
    )
    parser.add_argument(
        "--unseal-heldout",
        type=Path,
        metavar="LEDGER_DIR",
        help="external unseal ledger directory; required for any sealed held-out route",
    )
    parser.add_argument("--unseal-role", help="pre-declared unseal slot (spec protocol)")
    parser.add_argument(
        "--yaw-feedback",
        action="store_true",
        help="policy runs: 120 Hz PI on measured body yaw rate (yaw_rate_tracker.py)",
    )
    parser.add_argument(
        "--policy-max-v", type=float, default=0.1, help="must lie inside the qualified envelope"
    )
    parser.add_argument(
        "--topomap-root",
        type=Path,
        help="routes of reference images (build_topomap.py); policy navigates the chain",
    )
    parser.add_argument("--topomap-radius", type=int, default=4, help="upstream default 4")
    parser.add_argument("--comparison-config", type=Path, help="frozen component comparison")
    parser.add_argument("--variant", help="variant name in --comparison-config")
    parser.add_argument(
        "--topomap-close-threshold", type=float, default=3.0, help="upstream default 3"
    )
    parser.add_argument(
        "--start-arc-fraction",
        type=float,
        default=0.0,
        help="prospective start at this fraction of route arc length (perturbation.py)",
    )
    parser.add_argument("--start-lateral-m", type=float, default=0.0, help="left-positive offset")
    parser.add_argument(
        "--start-yaw-deg", type=float, default=0.0, help="offset from route heading"
    )
    parser.add_argument("--route-id", action="append", help="recollect a named route; may repeat")
    parser.add_argument("--trial", help="declared trial in a v2 --comparison-config")
    parser.add_argument(
        "--resume-from",
        type=Path,
        help="matched-state start: a recorded topomap episode directory (same route and chain)",
    )
    parser.add_argument(
        "--resume-decision",
        type=int,
        help="decision index of --resume-from whose inputs the first decision reproduces",
    )
    parser.add_argument(
        "--start-lost", action="store_true", help="policy starts in its lost state (no node)"
    )
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
    if bool(args.variant) != bool(args.comparison_config) or (
        args.variant and not args.topomap_root
    ):
        parser.error("--variant needs --comparison-config and --topomap-root")
    if args.variant:
        # Every runtime field of the frozen comparison must match this invocation.
        comparison = json.loads(args.comparison_config.read_text())
        if args.variant not in comparison["variants"]:
            parser.error(f"unknown variant {args.variant!r}")
        rt = comparison["runtime"]
        roots = {
            str(Path(c["root"]).resolve()): c["chain_json_sha256"]
            for c in comparison["conditions"].values()
        }
        chain_root = str(args.topomap_root.resolve())
        checks = {
            "radius": args.topomap_radius == rt["radius"],
            "close_threshold": args.topomap_close_threshold == rt["close_threshold"],
            "max_v": args.policy_max_v == rt["max_v"],
            "decision_hz": abs(12.0 / args.policy_period_frames - rt["decision_hz"]) < 1e-9,
            "budget_frames": args.max_steps == rt["budget_frames"],
            "checkpoint_sha256": args.checkpoint_sha256 == comparison["checkpoint"]["sha256"],
            "goal_root": args.goal_root is not None
            and args.goal_root.resolve() == Path(rt["goal_root"]).resolve(),
            "qualification": args.qualification is not None
            and args.qualification.resolve() == Path(rt["qualification"]).resolve(),
            "yaw_feedback": bool(args.yaw_feedback),
            "condition_root": chain_root in roots,
            "chain_json_sha256": chain_root in roots
            and hashlib.sha256((args.topomap_root / "chain.json").read_bytes()).hexdigest()
            == roots[chain_root],
        }
        trials = comparison.get("trials")
        if trials is not None:
            # v2: every start condition must be a declared trial.
            if args.trial not in trials:
                parser.error(f"--trial must name a declared trial: {sorted(trials)}")
            t = trials[args.trial]
            checks.update(
                {
                    "trial_variant": args.variant in t["variants"],
                    "trial_condition": chain_root
                    == str(Path(comparison["conditions"][t["condition"]]["root"]).resolve()),
                    # A subset is allowed so that a declared rerun covers only failed routes.
                    "trial_routes": bool(args.route_id) and set(args.route_id) <= set(t["routes"]),
                    "trial_budget": args.max_steps == t.get("budget_frames", rt["budget_frames"]),
                    "trial_start_lost": bool(args.start_lost) == bool(t.get("start_lost")),
                    "trial_resume": (
                        None if args.resume_from is None else str(args.resume_from.resolve()),
                        args.resume_decision,
                    )
                    == (
                        None
                        if t.get("resume_from") is None
                        else str(Path(t["resume_from"]).resolve()),
                        t.get("resume_decision"),
                    ),
                    "trial_perturbation": [
                        args.start_arc_fraction,
                        args.start_lateral_m,
                        args.start_yaw_deg,
                    ]
                    == t.get("perturbation", [0.0, 0.0, 0.0]),
                }
            )
            checks["budget_frames"] = checks.pop("trial_budget")
            # The analysis finds collections by name; a misnamed one would be invisible.
            checks["out_name"] = args.out.name.startswith(f"v2-{args.trial}-{args.variant}-") and (
                len(args.out.name) > len(f"v2-{args.trial}-{args.variant}-")
            )
        elif args.trial or args.resume_from or args.start_lost:
            parser.error("trial start options need a v2 comparison config with declared trials")
        mismatches = sorted(k for k, ok in checks.items() if not ok)
        if mismatches:
            parser.error(f"invocation differs from the frozen comparison: {mismatches}")
    if (args.trial or args.resume_from or args.start_lost) and not args.variant:
        parser.error("trial start options need --variant with a v2 comparison config")
    if (args.resume_from is None) != (args.resume_decision is None):
        parser.error("--resume-from and --resume-decision go together")
    if args.resume_from and (
        args.start_lost or args.start_arc_fraction or args.start_lateral_m or args.start_yaw_deg
    ):
        parser.error("a matched-state start takes no other start option")
    if args.unseal_heldout:
        # A sealed collection follows the frozen protocol exactly: every route,
        # the declared budget and speed, no perturbation, the sealed bytes only.
        from navfm.collection.scene_layouts import SEALED_SPECS

        sealed_spec = json.loads((REPO / SEALED_SPECS[0]).read_text())
        given = json.loads(args.layout_spec.read_text()) if args.layout_spec else {}
        if given.get("content_digest") != sealed_spec["content_digest"] or given != sealed_spec:
            parser.error("--unseal-heldout requires --layout-spec to be the sealed spec itself")
        proto = sealed_spec["protocol"]
        if args.limit is not None or args.route_id:
            parser.error("a sealed collection takes every route; no --limit or --route-id")
        if args.start_arc_fraction or args.start_lateral_m or args.start_yaw_deg:
            parser.error("a sealed collection takes no start perturbation")
        budget = proto["policy_max_steps"] if args.checkpoint else proto["teacher_max_steps"]
        if args.max_steps != budget:
            parser.error(f"sealed protocol fixes --max-steps {budget}")
        if args.checkpoint and args.policy_max_v != proto["policy_max_v_m_s"]:
            parser.error(f"sealed protocol fixes --policy-max-v {proto['policy_max_v_m_s']}")
        if args.unseal_role not in proto["unseal_slots"]:
            parser.error(f"--unseal-role must be one of {sorted(proto['unseal_slots'])}")
        from navfm.collection.scene_layouts import pinned_ledger

        ledger_dir = args.unseal_heldout.expanduser().resolve()
        if ledger_dir != pinned_ledger():
            parser.error(f"unseal ledger must be the pinned ledger {pinned_ledger()}")
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
        if args.policy_max_v > qualification.get("qualified_command_envelope", {}).get(
            "max_v", 0.1
        ):
            parser.error("policy speed outside the qualified envelope")
        if args.yaw_feedback:
            import dataclasses as _dc

            from navfm.collection.yaw_rate_tracker import YawRateGains

            feedback = qualification.get("yaw_feedback") or {}
            if feedback.get("update_hz") != 120.0 or any(
                feedback.get(k) != v for k, v in _dc.asdict(YawRateGains()).items()
            ):
                parser.error("qualification does not describe the 120 Hz yaw-rate tracker")
            if not any(e.get("name") == "command_replay" for e in qualification["episodes"]):
                parser.error("yaw feedback qualification must include a command replay")
        elif qualification.get("yaw_feedback"):
            parser.error("qualification describes yaw feedback; pass --yaw-feedback")
        from navfm.collection.rgb_baseline import RGBBaseline

        if args.policy_period_frames < 1:
            parser.error("policy period must be at least one frame")
        if args.topomap_root:
            from navfm.collection.rgb_baseline import RGBTopomapBaseline, topomap_components

            component = {}
            if args.variant:
                # Frozen component comparison: the variant fixes both components.
                spec = json.loads(args.comparison_config.read_text())["variants"][args.variant]
                component = topomap_components(spec, start_lost=bool(args.start_lost))
            elif args.start_lost:
                parser.error("--start-lost needs a frozen variant")
            policy = RGBTopomapBaseline(
                args.checkpoint,
                radius=args.topomap_radius,
                close_threshold=args.topomap_close_threshold,
                **component,
                action_scale_m=0.049994826316833496,
                stop_enabled=True,
                max_v=args.policy_max_v,
                control_period_s=args.policy_period_frames / 12.0,
            )
        else:
            policy = RGBBaseline(
                args.checkpoint,
                action_scale_m=0.049994826316833496,
                stop_enabled=True,
                max_v=args.policy_max_v,
                control_period_s=args.policy_period_frames / 12.0,
                stop_rule=args.stop_rule,
            )
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(REPO):
        parser.error("output must be new and external")
    out.mkdir(parents=True)
    from navfm.collection.demonstrations import DemonstrationTeacher, route_specs
    from navfm.collection.perturbation import StartPerturbation, perturbed_start

    perturbation = StartPerturbation(
        args.start_arc_fraction, args.start_lateral_m, args.start_yaw_deg
    )
    layout_spec = None
    if args.layout_spec:
        if args.route_spec:
            parser.error("choose --route-spec or --layout-spec")
        layout_spec = json.loads(args.layout_spec.read_text())
        routes = layout_spec["routes"][: args.limit]
    else:
        loaded = json.loads(args.route_spec.read_text()) if args.route_spec else route_specs()
        if not isinstance(loaded, list):
            parser.error("--route-spec must be a route list; layout specs use --layout-spec")
        routes = loaded[: args.limit or 10]
    if args.route_id:
        known = {r["id"] for r in routes}
        if set(args.route_id) - known:
            parser.error("unknown route id")
        routes = [r for r in routes if r["id"] in args.route_id]
    from navfm.collection.scene_layouts import (
        check_heldout_goals,
        claim_unseal_slot,
        sealed_matches,
    )

    # Sealed held-out routes and scenes are refused from any source; unsealing
    # claims one pre-declared slot in the external ledger.
    sealed = sealed_matches(routes, REPO, (layout_spec or {}).get("scenes")) + (
        ["layout spec marked sealed"] if (layout_spec or {}).get("sealed") else []
    )
    if sealed and not args.unseal_heldout:
        parser.error(f"sealed held-out data refused: {sorted(set(sealed))}")
    if args.unseal_heldout:
        try:
            if args.checkpoint:
                check_heldout_goals(args.goal_root, routes, args.unseal_role, ledger_dir)
            claim_unseal_slot(
                ledger_dir,
                sealed_spec,
                out=out,
                role=args.unseal_role,
                routes=[r["id"] for r in routes],
                checkpoint_sha256=args.checkpoint_sha256 if args.checkpoint else None,
                repo=REPO,
            )
        except ValueError as exc:
            parser.error(str(exc))
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
        from navfm.collection.scene_layouts import layout_boxes, legacy_boxes

        explicit = {s["scene_index"]: s for s in (layout_spec or {}).get("scenes", [])}
        for scene in sorted({r["scene_index"] for r in routes}):
            origin = scene * 20.0
            half = next(r["wall_half_width"] for r in routes if r["scene_index"] == scene)
            root = f"/World/Fixture/Scene{scene}"
            if scene in explicit:
                boxes = layout_boxes(explicit[scene])
            else:
                # Distinct partition geometry is prospective and shared within each layout only.
                boxes = legacy_boxes(scene, half, partitions=bool(args.route_spec))
            for b in boxes:
                cube(root + "/" + b["name"], b["xyz"], b["size"], b["color"], b["collision"])
            named = {b["name"]: b for b in boxes}
            fixtures[scene] = {
                "scene_index": scene,
                "origin_y": origin,
                "wall_half_width": half,
                "obstacle_xyz": tuple(named["Obstacle"]["xyz"]) if "Obstacle" in named else None,
                "layout": explicit[scene]["group"] if scene in explicit else "legacy_corridor",
            }
            if "DoorPartition0" in named:
                fixtures[scene]["door_partition_x"] = named["DoorPartition0"]["xyz"][0]
                fixtures[scene]["door_partition_width"] = named["DoorPartition0"]["size"][1]
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

        from navfm.collection.yaw_rate_tracker import YawRateTracker

        tracker = YawRateTracker() if policy and args.yaw_feedback else None
        held = {"command": (0.0, 0.0, 0.0), "updates": 0, "idle": 0}

        def wheel_targets(v, vy, w):
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

        def on_physics_step(dt):
            # Base-controller loop at the physics rate; policy commands are held.
            v, vy, w = held["command"]
            if v == 0 and vy == 0 and w == 0:
                tracker.reset()
                wheel_targets(0.0, 0.0, 0.0)
                held["idle"] += 1
                return
            measured = float(np.asarray(robot._articulation.get_velocities()).reshape(-1, 6)[0, 5])
            wheel_targets(v, vy, tracker.update(w, measured, dt))
            held["updates"] += 1

        held["subscription"] = (
            omni.physx.get_physx_interface().subscribe_physics_step_events(on_physics_step)
            if tracker
            else None
        )

        def drive(command):
            if tracker:
                held["command"] = tuple(float(c) for c in command)
                if not any(held["command"]):
                    tracker.reset()
                    wheel_targets(0.0, 0.0, 0.0)
                return
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
            wheel_targets(v, vy, w)

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
                resume = None
                if args.resume_from is not None:
                    # Matched-state start by replay to handover: start where the recorded
                    # episode started and replay its recorded commands, decision by
                    # decision, through the same drive path; the policy takes over at the
                    # handover decision K from the recorded node at K-1. The robot is then
                    # moving and its image history is live. Pose never enters a decision;
                    # it is only compared with the recording to report replay fidelity.
                    rm = json.loads((args.resume_from / "runtime_manifest.json").read_text())
                    K = args.resume_decision
                    if rm["route"]["id"] != route["id"] or not 6 <= K < len(rm["inference"]):
                        raise ValueError("resume episode must be this route; decision >= 6")
                    if rm["inference"][K]["frame"] != K * args.policy_period_frames:
                        raise ValueError("resume episode has another decision period")
                    resume = {
                        "episode": str(args.resume_from.resolve()),
                        "manifest_sha256": hashlib.sha256(
                            (args.resume_from / "runtime_manifest.json").read_bytes()
                        ).hexdigest(),
                        "mode": "replay_to_handover",
                        "decision": K,
                        "handover_frame": K * args.policy_period_frames,
                        "replayed_commands": [rm["inference"][k]["command"] for k in range(K)],
                        "recorded_start_pose": rm["start_pose"],
                        "recorded_handover_pose": rm["captures"][K * args.policy_period_frames - 1][
                            "pose"
                        ],
                        "initial_node": rm["inference"][K - 1]["chain"]["closest_node"],
                        "chain_json_sha256": rm["topomap"]["chain_json_sha256"],
                        "fixed_goal_sha256": rm.get("fixed_goal_sha256"),
                        "source_checkpoint_sha256": rm["policy"]["sha256"],
                        "source_variant": (rm.get("component_variant") or {}).get("variant"),
                    }
                    if resume["source_checkpoint_sha256"] != args.checkpoint_sha256:
                        raise ValueError("resume episode ran another checkpoint")
                    sp = rm["start_pose"]
                    start_xy, start_yaw, teacher_points = np.asarray(sp[:2]), sp[2], points
                    manifest["resume"] = resume
                elif perturbation.is_identity:
                    start_xy, start_yaw, teacher_points = points[0], route["start_yaw"], points
                else:
                    start_xy, start_yaw, teacher_points = perturbed_start(points, perturbation)
                manifest["start_perturbation"] = perturbation.to_dict()
                manifest["start_pose"] = [float(start_xy[0]), float(start_xy[1]), float(start_yaw)]
                robot.teleport(start_xy, start_yaw)
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
                teacher = DemonstrationTeacher(teacher_points, route["speed"])
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
                    definition_path = args.goal_root / "goal_source.json"
                    if definition_path.exists():
                        # Goal is a frame of a prior traversal, not the root's photograph.
                        definition = json.loads(definition_path.read_text())
                        source = definition["goals"][route["id"]]
                        source_bytes = Path(source["source"]).read_bytes()
                        goal_bytes = (args.goal_root / route["id"] / "goal.png").read_bytes()
                        if (
                            hashlib.sha256(source_bytes).hexdigest() != source["source_sha256"]
                            or source_bytes != goal_bytes
                        ):
                            raise ValueError("goal does not match its declared source frame")
                        manifest["goal_definition"] = definition["definition"]
                        manifest["goal_source_frame"] = source
                        manifest["fixed_goal_source_capture_sim_time"] = source["capture_sim_time"]
                        manifest["goal_time_definition"] = (
                            "capture time of the declared prior-traversal source frame"
                        )
                    if args.topomap_root:
                        # Route of reference images: every node verified against the
                        # chain record and its source traversal frame, decoded as the goal is.
                        chain_path = args.topomap_root / "chain.json"
                        chain = json.loads(chain_path.read_text())["routes"][route["id"]]
                        images = []
                        for node in chain["nodes"]:
                            data = (
                                args.topomap_root / route["id"] / f"{node['node']}.jpg"
                            ).read_bytes()
                            if (
                                hashlib.sha256(data).hexdigest() != node["sha256"]
                                or Path(node["source"]).read_bytes() != data
                            ):
                                raise ValueError(
                                    f"{route['id']}: chain node {node['node']} changed"
                                )
                            images.append(
                                np.asarray(
                                    Image.open(
                                        args.topomap_root / route["id"] / f"{node['node']}.jpg"
                                    ).convert("RGB")
                                )
                            )
                        policy.initial_node = 0
                        if resume is not None:
                            if resume["chain_json_sha256"] != hashlib.sha256(
                                chain_path.read_bytes()
                            ).hexdigest() or resume["fixed_goal_sha256"] != manifest.get(
                                "fixed_goal_sha256"
                            ):
                                raise ValueError("resume episode used another chain or goal")
                            policy.initial_node = resume["initial_node"]
                        policy.set_chain(images)
                        trial_spec = (
                            json.loads(args.comparison_config.read_text())
                            .get("trials", {})
                            .get(args.trial)
                            if args.comparison_config and args.trial
                            else None
                        )
                        manifest["component_variant"] = {
                            "trial": args.trial,
                            "stage": None if trial_spec is None else trial_spec["stage"],
                            "variant": args.variant,
                            "comparison_config_sha256": hashlib.sha256(
                                args.comparison_config.read_bytes()
                            ).hexdigest()
                            if args.comparison_config
                            else None,
                        }
                        manifest["topomap"] = {
                            "root": str(args.topomap_root.resolve()),
                            "chain_json_sha256": hashlib.sha256(
                                chain_path.read_bytes()
                            ).hexdigest(),
                            "chain_source_route": chain["chain_source_route"],
                            "control": chain["control"],
                            "nodes": [[n["frame"], n["sha256"]] for n in chain["nodes"]],
                            "final_node_is_goal": chain["nodes"][-1]["sha256"]
                            == (manifest.get("goal_source_frame") or {}).get("source_sha256"),
                            # Effective per-episode policy state before the first decision.
                            "initial_node": int(policy.state.closest_node),
                            "start_lost": bool(getattr(policy.state, "lost", False)),
                        }
                    history = [robot.rgb().copy() for _ in range(6)]
                inference = []
                stop_frame = None
                abstain_frame = abstain_reason = None
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
                feedback_start = held["updates"] + held["idle"]
                for i in range(args.max_steps):
                    wall_start = time.perf_counter()
                    before = float(sim.current_time)
                    xy, yaw = robot.pose()
                    pose_before = [*xy.tolist(), yaw]
                    replaying = resume is not None and i < resume["handover_frame"]
                    if policy and replaying:
                        if i % args.policy_period_frames == 0:
                            # Replay phase: the history fills with live images, the
                            # recorded command is applied, no policy decision is made.
                            history = [*history, robot.rgb().copy()][-6:]
                            command = resume["replayed_commands"][i // args.policy_period_frames]
                            drive(command)
                    elif policy:
                        if i % args.policy_period_frames == 0:
                            perception_start = time.perf_counter()
                            history = [*history, robot.rgb().copy()][-6:]
                            if resume is not None and i == resume["handover_frame"]:
                                rp = resume["recorded_handover_pose"]
                                resume["handover_pose"] = pose_before
                                resume["handover_position_error_m"] = float(
                                    np.hypot(pose_before[0] - rp[0], pose_before[1] - rp[1])
                                )
                                resume["handover_yaw_error_deg"] = float(
                                    abs(
                                        math.degrees(
                                            (pose_before[2] - rp[2] + math.pi) % (2 * math.pi)
                                            - math.pi
                                        )
                                    )
                                )
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
                            if prediction.get("policy_abstain") and abstain_frame is None:
                                abstain_frame = i
                                abstain_reason = prediction["policy_abstain"]
                        end = stop_frame if stop_frame is not None else abstain_frame
                        reached = end is not None and i - end >= 24
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
                if tracker:
                    # The PI must have run on every physics step of the episode.
                    feedback_steps = held["updates"] + held["idle"] - feedback_start
                    manifest["base_controller"] = {
                        "yaw_feedback": dataclasses.asdict(tracker.gains),
                        "update_hz": 1.0 / sim.get_physics_dt(),
                        "measurement": "articulation root angular velocity z (ideal gyro)",
                        "physics_steps_observed": feedback_steps,
                        "physics_steps_expected": len(captures) * cfg.physics_substeps,
                    }
                    if (
                        abs(feedback_steps - len(captures) * cfg.physics_substeps)
                        > 2 * cfg.physics_substeps
                    ):
                        raise RuntimeError("yaw feedback did not run on every physics step")
                manifest.update(
                    status="PASS",
                    frames=len(captures),
                    captures=captures,
                    contacts=contacts.copy(),
                    termination=(
                        "policy_stop"
                        if stop_frame is not None
                        else "abstained"
                        if abstain_frame is not None
                        else "timeout"
                    )
                    if policy
                    else "teacher_goal"
                    if reached
                    else "timeout",
                    inference=inference,
                    policy_stop_frame=stop_frame,
                    policy_abstain_frame=abstain_frame,
                    policy_abstain_reason=abstain_reason,
                    max_steps=args.max_steps,
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
                        "path_efficiency": float(np.linalg.norm(points[-1] - start_xy))
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
