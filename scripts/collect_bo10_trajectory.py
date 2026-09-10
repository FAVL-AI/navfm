"""Collect the single BO-10 trajectory on a pre-admitted route.

Drives the route that route admission cleared -- not a freshly sampled one --
through the production collector, with the pre-motion gates enforced and the
post-episode gates measured from what was actually recorded.

The route is FIXED rather than re-sampled. Re-sampling inside the episode would
drive a different route from the one the gates passed, which would make the
admission meaningless.

Nothing here is E2-eligible. The scope block is stamped into the trajectory
metadata and the manifest, so the trajectory carries its own exclusion.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--scene-id", required=True)
    ap.add_argument("--robot", required=True)
    ap.add_argument("--admission-artefact", required=True,
                    help="the route-admission result whose selected_route is collected")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--episode-index", type=int, default=0,
                    help="episode number; run_00000 is immutable, so a fresh run uses 1")
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--occupancy-backend", default="physx_cell_overlap_v1")
    ap.add_argument("--region-declaration", default=None)
    ap.add_argument("--scope-declaration",
                    default="gates/BO10/bo10_e2_scope_declaration_20260907.json")
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp
    app = SimulationApp({"headless": True})

    import dataclasses

    import isaacsim.core.utils.stage as stage_utils
    import numpy as np
    from isaacsim.core.api import SimulationContext
    from isaacsim.core.utils.extensions import enable_extension

    from navfm.collection.controller import ControllerIdentity, verify_motion_occurred
    from navfm.collection.gates import GateStatus
    from navfm.collection.goal_seal import evaluate_goal_seal, image_digest
    from navfm.collection.long_horizon import measure_from_trajectory
    from navfm.collection.scope import authorise_g2_acknowledgement
    from navfm.isaac.app import SimConfig
    from navfm.isaac.collect import CollectConfig, Collector
    from navfm.isaac.randomize import RandomizationConfig
    from navfm.isaac.robot import M3PRO
    from navfm.simenv import simulator_identity

    sim_id = simulator_identity()
    rec: dict[str, Any] = {
        "check": "BO10_PRODUCTION_COLLECTION",
        "artifact_semantics": "PRODUCTION_TRAJECTORY_EVIDENCE",
        "scene_id": args.scene_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {"isaac_sim_version": sim_id.isaac_sim_version,
                       "interpreter": sim_id.interpreter, "scene_asset": args.scene,
                       "robot_asset": args.robot, "gpu": sim_id.gpu,
                       "isaac_lab": sim_id.isaac_lab},
        "occupancy_backend": args.occupancy_backend,
    }

    try:
        scope = authorise_g2_acknowledgement(REPO / args.scope_declaration)
        rec["scope"] = scope.to_manifest_fields()

        admission = json.loads(Path(args.admission_artefact).read_text())
        # Two admission artefact shapes exist: the shortest-path population uses
        # `selected_route`, the turning population `selected_candidate`. They are
        # NOT normalised into one -- they describe different experiments, and a
        # collector that could not say which it was driving would be unable to
        # bind the trajectory to its population.
        turning = "selected_candidate" in admission
        selected = admission.get("selected_candidate" if turning else "selected_route")
        if not selected:
            raise RuntimeError("the admission artefact selected no route")
        rec["population_kind"] = ("TURNING_ROUTE_POPULATION_V1" if turning
                                  else "shortest_path_population")
        rec["admitted_route"] = {
            "route_id": selected.get("candidate_id") or selected.get("route_id"),
            "ordering_index": selected.get("ordering_index"),
            "start_pose": selected["start_pose"], "goal_pose": selected["goal_pose"],
            "admission_artefact": args.admission_artefact,
            "admission_artefact_sha256": hashlib.sha256(
                Path(args.admission_artefact).read_bytes()).hexdigest(),
            "anchors": selected.get("anchors"),
            "planned_turn_events_v2": selected.get("planned_turn_events_v2"),
            "planned_turn_magnitudes_deg": selected.get("planned_turn_magnitudes_deg"),
            "predicted": (None if turning else
                          ((selected["gates"]["G10_LONG_HORIZON"]["detail"] or {})
                           .get("measurement"))),
        }

        cfg = CollectConfig(scenes=[args.scene], seed=admission["search"]["seed"],
                            scene_name=args.scene_id)
        robot_cfg = dataclasses.replace(M3PRO, usd_path=args.robot)
        sim_cfg = SimConfig(headless=True, seed=cfg.seed)
        collector = Collector(args.out_dir, cfg, sim_cfg, robot_cfg,
                              RandomizationConfig(enabled=False), scope=scope,
                              occupancy_backend=args.occupancy_backend)
        # run_episode drives the app through IsaacApp's contract -- step()
        # returns simulation time and blocks until the renderer has finished the
        # frame, so a pose or image read afterwards refers to the same instant.
        # The raw SimulationApp has no such method, so a shim provides exactly
        # that contract over the SimulationContext this script owns.
        class _AppShim:
            """Minimal IsaacApp surface: synchronised step, update, sim_time."""

            def __init__(self, sim_ctx: Any, raw: Any) -> None:
                self._ctx = sim_ctx
                self._raw = raw

            def step(self) -> float:
                self._ctx.step(render=True)
                return float(self._ctx.current_time)

            def update(self) -> None:
                self._raw.update()

            def sim_time(self) -> float:
                return float(self._ctx.current_time)


        stage_utils.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0, physics_dt=1.0 / sim_cfg.hz,
                                rendering_dt=1.0 / sim_cfg.hz)
        collector._app = _AppShim(sim, app)
        stage_utils.add_reference_to_stage(args.scene, "/World/Scene")
        sim.initialize_physics()
        sim.play()
        for _ in range(5):
            sim.step(render=False)
        enable_extension("isaacsim.asset.gen.omap")

        # The occupancy map is built BEFORE the robot is spawned, and the order
        # is load-bearing rather than tidy. The robot carries colliders, so a
        # robot standing in the scene is rasterised as an obstacle: its cells
        # leave the free set, the seeded sampler draws from a different
        # population, and replaying candidate 050 produced a different route
        # from the one route admission cleared -- start (-25.099, 36.082)
        # against the admitted (-39.903, 23.121). Route admission builds its map
        # with no robot present, so collection must too.
        bounds = None
        if args.region_declaration:
            decl = json.loads(Path(args.region_declaration).read_text())
            bounds = (tuple(decl["window"]["bounds_min"]), tuple(decl["window"]["bounds_max"]))
        grid = collector.build_occupancy(args.scene, bounds=bounds,
                                         backend=args.occupancy_backend)
        collector._grid = grid
        collector._clearance = grid.clearance()
        rec["occupancy"] = {"shape": list(grid.shape),
                            "backend_used": collector.occupancy_backend_used,
                            "query_failures": collector.occupancy_query_failures}

        # Robot spawned only after the map exists.
        from navfm.isaac.robot import SimRobot
        robot = SimRobot(app, robot_cfg)
        robot.spawn()
        for _ in range(5):
            sim.step(render=False)
        robot.attach_camera()
        for _ in range(3):
            sim.step(render=True)
        collector._robot = robot
        rec["camera_prim"] = robot.camera_path

        # Reproduce the admitted route by REPLAYING the seeded sampler to the
        # selected index, rather than re-planning from the stored poses.
        #
        # Re-planning looked simpler and is wrong. sample_free_pose returns a
        # continuous pose, which can round back to a different cell than the one
        # it was sampled from -- the stored start (-39.903, 23.121) maps to cell
        # (279, 97), which A* reports as occupied. Replaying the same generator
        # with the same seed against the same map regenerates the identical
        # candidate, including the path the gates actually evaluated.
        from navfm.planning import PlannerError, sample_episode_pair
        rng = np.random.default_rng(admission["search"]["seed"])
        target = int((selected.get("candidate_id") or selected["route_id"]).rsplit("_", 1)[-1])
        inflated = collector._inflated
        clearance_map = collector._inflated_clearance
        replayed = None
        if turning:
            from navfm.collection.turning_routes import (
                TURNING_ROUTE_GENERATOR_V1,
                sample_turning_route,
            )
            for i in range(target + 1):
                try:
                    cand = sample_turning_route(inflated, rng,
                                                generator=TURNING_ROUTE_GENERATOR_V1,
                                                clearance_map=clearance_map)
                except PlannerError:
                    continue
                if i == target:
                    replayed = (cand.start, cand.start_yaw, cand.goal, cand.path)
        else:
            for i in range(target + 1):
                try:
                    cand = sample_episode_pair(
                        inflated, rng,
                        min_path_m=8.0, max_path_m=40.0,
                        min_clearance_m=cfg.min_clearance_m, clearance_map=clearance_map)
                except PlannerError:
                    continue
                if i == target:
                    replayed = cand
        if replayed is None:
            raise RuntimeError(f"replaying the generator did not reproduce candidate {target}")
        start_r, yaw_r, goal_r, path_r = replayed
        matches = (abs(float(start_r[0]) - selected["start_pose"][0]) < 1e-9
                   and abs(float(start_r[1]) - selected["start_pose"][1]) < 1e-9
                   and abs(float(goal_r[0]) - selected["goal_pose"][0]) < 1e-9
                   and abs(float(goal_r[1]) - selected["goal_pose"][1]) < 1e-9)
        rec["route_reproduction"] = {
            "method": ("replay the seeded generator to the selected candidate index; the "
                       "generator replayed is the one the population was evaluated with"),
            "generator": ("TURNING_ROUTE_POPULATION_V1" if turning
                          else "sample_episode_pair"),
            "target_index": target,
            "start_matches_admitted": bool(matches),
            "replayed_start": [float(start_r[0]), float(start_r[1]), float(yaw_r)],
            "replayed_goal": [float(goal_r[0]), float(goal_r[1])],
            "path_points": int(path_r.shape[0]),
        }
        if not matches:
            raise RuntimeError(
                "the replayed candidate does not match the admitted one; refusing to collect "
                "a route the gates did not evaluate")
        collector.fixed_route = (start_r, float(yaw_r), goal_r, path_r)
        collector.enforce_premotion_gates = True

        # KINEMATIC_COLLECTION_DRIVE_V1 with its swept-collision invariant.
        # The guard queries the SCENE, not the planner's occupancy map: the map
        # planned the route, and a previous map omitted a reception desk
        # entirely, so it is not an acceptable sole protection.
        from omni.physx import get_physx_scene_query_interface

        from navfm.collection.footprint import CircularFootprint, SweepResolution
        from navfm.collection.kinematic_drive import KinematicDriveConfig, KinematicDriver

        q = get_physx_scene_query_interface()
        footprint = CircularFootprint(robot_cfg.footprint_radius)
        sweep_res = SweepResolution.derive(robot_cfg.footprint_radius,
                                           grid_resolution_m=cfg.grid_resolution)
        SLAB = (0.10, 0.60)
        z_mid = (SLAB[0] + SLAB[1]) / 2
        half_z = (SLAB[1] - SLAB[0]) / 2
        ident = [0.0, 0.0, 0.0, 1.0]
        ROBOT_PRIM = robot.prim_path

        class SceneCollisionGuard:
            """Is the robot footprint free of blocking scene geometry here?

            The robot's own colliders are in the scene, so a naive overlap at the
            robot's current pose always reports a hit -- the robot detecting
            itself. Hits whose prim lies under the robot are therefore excluded,
            which is the same class of mistake as H-ORDER-1 and H-INSTANCE-1 and
            is handled explicitly rather than by hoping it does not arise.
            """

            def __init__(self) -> None:
                self.queries = 0
                self.self_hits = 0

            def pose_is_free(self, x: float, y: float, yaw: float) -> bool:
                self.queries += 1
                blocking: list[str] = []

                def _cb(hit: Any) -> bool:
                    path = str(getattr(hit, "collision", ""))
                    if path.startswith(ROBOT_PRIM):
                        self.self_hits += 1
                        return True
                    blocking.append(path)
                    return False

                for px, py in footprint.points(x, y, yaw, sweep_res.probe_spacing_m):
                    blocking.clear()
                    q.overlap_box([sweep_res.probe_spacing_m / 2,
                                   sweep_res.probe_spacing_m / 2, half_z],
                                  [float(px), float(py), z_mid], ident, _cb, False)
                    if blocking:
                        return False
                return True

        guard = SceneCollisionGuard()
        drive_cfg = KinematicDriveConfig(dt=1.0 / sim_cfg.hz)
        collector.kinematic_driver = KinematicDriver(guard=guard, config=drive_cfg)
        rec["kinematic_drive"] = {
            "preregistration": "gates/BO10/kinematic_collection_drive_v1_20260910.json",
            "config": drive_cfg.to_dict(),
            "guard": "PhysX overlap against scene collision geometry, robot self-hits excluded",
            "footprint_radius_m": robot_cfg.footprint_radius,
            "probe_spacing_m": sweep_res.probe_spacing_m,
        }

        result = collector.run_episode(int(args.episode_index), args.scene_id)
        rec["kinematic_drive"]["steps_applied"] = collector.kinematic_driver.applied
        rec["kinematic_drive"]["steps_rejected"] = collector.kinematic_driver.rejections
        rec["kinematic_drive"]["guard_queries"] = guard.queries
        rec["kinematic_drive"]["self_hits_excluded"] = guard.self_hits
        rec["kinematic_drive"]["motion_model"] = "KINEMATIC_SE2"
        rec["kinematic_drive"]["contact_response"] = "NOT_EVALUATED"
        rec["kinematic_drive"]["wheel_dynamics"] = "NOT_EVALUATED"
        if getattr(collector, "_drive_rejection", None):
            rec["kinematic_drive"]["rejection"] = collector._drive_rejection
        rec["episode"] = dataclasses.asdict(result)

        traj_dir = Path(args.out_dir) / result.name
        rec["trajectory_dir"] = str(traj_dir)
        if not result.accepted:
            rec["BO10_COLLECTION"] = "EPISODE_NOT_ACCEPTED"
            rec["reason"] = result.reason
        else:
            import pickle

            with open(traj_dir / "traj_data.pkl", "rb") as fh:
                traj = pickle.load(fh)
            positions = np.asarray(traj["position"], dtype=float)
            yaws = np.asarray(traj["yaw"], dtype=float)

            g10 = measure_from_trajectory(positions, yaws)
            motion = verify_motion_occurred(positions, yaws)
            limits = robot_cfg.limits
            identity_after = ControllerIdentity(
                implementation="navfm.control.PurePursuit",
                control_hz=float(sim_cfg.hz), max_v=limits.max_v, max_w=limits.max_w,
                max_vy=limits.max_vy, max_a=limits.max_a, max_alpha=limits.max_alpha,
                cruise_v=cfg.cruise_v, lookahead_m=cfg.lookahead_m,
                goal_tol_m=cfg.goal_tol_m, demonstrator_mode=cfg.demonstrator,
                seed=int(cfg.seed))
            from navfm.collection.controller import evaluate_controller_identity
            g8 = evaluate_controller_identity(collector._identity_before, identity_after)

            frames = sorted(traj_dir.glob("*.jpg"))
            final_digest = image_digest(frames[-1].read_bytes()) if frames else None
            g9 = evaluate_goal_seal(collector._goal_seal,
                                    final_observation_digest=final_digest)

            rec["post_episode"] = {
                "G10_realised": g10.to_dict(),
                "G8_controller_identity": g8.to_dict(),
                "G9_goal_image_seal": g9.to_dict(),
                "MOTION_REALISED": motion.to_dict(),
            }
            rec["data_integrity"] = {
                "n_frames": int(positions.shape[0]),
                "n_images": len(frames),
                "positions_shape": list(positions.shape),
                "yaw_shape": list(yaws.shape),
                "positions_finite": bool(np.isfinite(positions).all()),
                "yaws_finite": bool(np.isfinite(yaws).all()),
                "images_match_frames": len(frames) == int(positions.shape[0]),
                "goal_image_sha256": collector._goal_seal.goal_image_sha256,
                "final_observation_sha256": final_digest,
                "goal_is_not_final_observation":
                    collector._goal_seal.goal_image_sha256 != final_digest,
            }
            all_pass = (g10.status is GateStatus.PASS and g8.status is GateStatus.PASS
                        and g9.status is GateStatus.PASS and motion.status is GateStatus.PASS
                        and rec["data_integrity"]["images_match_frames"]
                        and rec["data_integrity"]["positions_finite"])
            rec["BO10_COLLECTION"] = "TRAJECTORY_ADMITTED" if all_pass else "TRAJECTORY_NOT_ADMITTED"
    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-3000:]
        rec["BO10_COLLECTION"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.evidence, rec, required_keys=(
            "check", "artifact_semantics", "BO10_COLLECTION"))
        print(f"wrote {args.evidence} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
