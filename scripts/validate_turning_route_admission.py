"""Hospital TURNING_ROUTE_POPULATION_V1 — all 96 attempts, every gate, no stopping.

Tests the hypothesis the controller fixtures left standing: that `run_00000`'s
collapse to one turn event was route structure rather than the controller. The
generator here enforces 3-9 m anchor separation and 30-135 degree bends, so its
routes have the separated corners route 050 lacked.

The budget means 96 ATTEMPTS, not 96 successful constructions. That is the
meaning it was frozen with -- the earlier Hospital populations loop
`for i in range(budget)` and a generator failure still consumes an index and is
recorded -- and it is used here rather than reinterpreted, because a budget that
silently became "keep trying until 96 succeed" would let a hostile scene inflate
the search without it appearing anywhere.

Every candidate carries ALL its gate failures, not just the first. A population
where nothing passes is still evidence, and it is only readable if the failure
distribution survives.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402

CONTROL_HZ = 12.0
CRUISE_V = 0.35


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--scene-id", required=True)
    ap.add_argument("--robot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", type=int, default=96)
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp
    app = SimulationApp({"headless": True})

    import dataclasses
    import math

    import isaacsim.core.utils.stage as stage_utils
    import numpy as np
    from isaacsim.core.api import SimulationContext
    from isaacsim.core.utils.extensions import enable_extension
    from omni.physx import get_physx_scene_query_interface

    from navfm.collection.clearance import ClearanceSample, evaluate_obstacle_clearance
    from navfm.collection.footprint import CircularFootprint, SweepResolution
    from navfm.collection.gates import GateStatus
    from navfm.collection.long_horizon import LONG_HORIZON_THRESHOLDS, window_counts
    from navfm.collection.scope import bo10_scope
    from navfm.collection.support import (
        SupportSample,
        evaluate_continuous_support,
        evaluate_end_support,
        evaluate_start_support,
    )
    from navfm.collection.turn_events import realised_turn_events
    from navfm.collection.turning_routes import (
        TURNING_ROUTE_GENERATOR_V1,
        sample_turning_route,
    )
    from navfm.isaac.app import SimConfig
    from navfm.isaac.collect import OCCUPANCY_BACKEND_PHYSX, CollectConfig, Collector
    from navfm.isaac.randomize import RandomizationConfig
    from navfm.isaac.robot import M3PRO
    from navfm.planning import PlannerError
    from navfm.simenv import simulator_identity

    gen_artefact = REPO / "gates/BO10/turning_route_population_v1_final_20260910.json"
    gen_src = REPO / "src/navfm/collection/turning_routes.py"
    sim_id = simulator_identity()

    rec: dict[str, Any] = {
        "check": "HOSPITAL_TURNING_ROUTE_POPULATION_V1",
        "artifact_semantics": "FROZEN_POPULATION_EVALUATION",
        "scene_id": args.scene_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": bo10_scope().to_manifest_fields(),
        "generator_artefact": str(gen_artefact.relative_to(REPO)),
        "generator_artefact_sha256": hashlib.sha256(gen_artefact.read_bytes()).hexdigest(),
        "generator_source_sha256": hashlib.sha256(gen_src.read_bytes()).hexdigest(),
        "generator": TURNING_ROUTE_GENERATOR_V1.to_dict(),
        "budget_meaning": ("96 ATTEMPTS, not 96 successful constructions. Inherited from the "
                           "earlier Hospital populations, which loop over the budget and record a "
                           "generator failure as a consumed index."),
        "search": {"seed": args.seed, "budget": args.budget,
                   "ordering": "seeded generation order", "no_optional_stopping": True},
        "occupancy_backend": OCCUPANCY_BACKEND_PHYSX,
        "provenance": {"isaac_sim_version": sim_id.isaac_sim_version,
                       "interpreter": sim_id.interpreter, "scene_asset": args.scene,
                       "robot_asset": args.robot, "gpu": sim_id.gpu},
        "claim_boundaries": ["F-TWIN-1 OPEN", "PHYSICAL_M3_PRO_GROUND_CLEARANCE NOT_MEASURED",
                             "DYNAMIC_WHEEL_DRIVE_V1 DEFERRED",
                             "kinematic collection establishes no drivetrain fidelity"],
    }

    try:
        # ---- generator independence, re-verified at execution time ----------
        src_text = gen_src.read_text()
        independence = {
            "imports_turn_events": "turn_events" in src_text,
            "imports_long_horizon": "long_horizon" in src_text,
            "references_evaluator": any(t in src_text for t in (
                "realised_turn_events", "heading_changes", "TURN_SEMANTICS",
                "predict_from_route", "measure_from_trajectory")),
        }
        rec["generator_independent_of_g10"] = not any(independence.values())
        rec["generator_independence_detail"] = independence
        if not rec["generator_independent_of_g10"]:
            raise RuntimeError("the generator references the G10 evaluator; refusing to evaluate")

        stage_utils.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0)
        stage_utils.add_reference_to_stage(args.scene, "/World/Scene")
        sim.initialize_physics()
        for _ in range(5):
            sim.step(render=False)
        enable_extension("isaacsim.asset.gen.omap")

        cfg = CollectConfig(scenes=[args.scene], seed=args.seed)
        robot_cfg = dataclasses.replace(M3PRO, usd_path=args.robot)
        collector = Collector("/tmp/_turning", cfg, SimConfig(headless=True), robot_cfg,
                              RandomizationConfig(enabled=False), scope=bo10_scope(),
                              occupancy_backend=OCCUPANCY_BACKEND_PHYSX)
        collector._app = app
        grid = collector.build_occupancy(args.scene, backend=OCCUPANCY_BACKEND_PHYSX)
        collector._grid = grid
        collector._clearance = grid.clearance()
        inflated = collector._inflated
        clearance_map = collector._inflated_clearance
        rec["occupancy"] = {"shape": list(grid.shape),
                            "backend_used": collector.occupancy_backend_used,
                            "query_failures": collector.occupancy_query_failures}

        footprint = CircularFootprint(robot_cfg.footprint_radius)
        resolution = SweepResolution.derive(robot_cfg.footprint_radius,
                                            grid_resolution_m=cfg.grid_resolution)
        q = get_physx_scene_query_interface()
        probe = q.raycast_closest([0.0, 0.0, 0.05], [0.0, 0.0, -1.0], 0.30)
        floor_z = (0.05 - float(probe["distance"])) if (probe and probe.get("hit")) else 0.0

        class SupportProbe:
            def __init__(self) -> None:
                self.cache: dict[tuple[int, int], SupportSample] = {}
                self.queries = 0

            def reset(self) -> None:
                self.cache.clear()

            def sample(self, x: float, y: float) -> SupportSample:
                key = (int(round(x / 0.005)), int(round(y / 0.005)))
                hit = self.cache.get(key)
                if hit is not None:
                    return hit
                self.queries += 1
                o = [x, y, floor_z + 0.05]
                r = q.raycast_closest(o, [0.0, 0.0, -1.0], 0.30)
                if not (r and r.get("hit")):
                    out = SupportSample(x, y, False, reason="NO_GROUND_HIT")
                else:
                    hz = o[2] - float(r["distance"])
                    prim = str(r.get("collision", "")) or None
                    out = (SupportSample(x, y, False, margin_m=hz - floor_z, prim=prim,
                                         reason="HIT_OFF_FLOOR")
                           if abs(hz - floor_z) > 0.08
                           else SupportSample(x, y, True, margin_m=hz - floor_z, prim=prim))
                self.cache[key] = out
                return out

        class ClearanceProbe:
            def __init__(self) -> None:
                self.cache: dict[tuple[int, int], ClearanceSample] = {}
                self.queries = 0

            def reset(self) -> None:
                self.cache.clear()

            def sample(self, x: float, y: float) -> ClearanceSample:
                key = (int(round(x / 0.005)), int(round(y / 0.005)))
                hit = self.cache.get(key)
                if hit is not None:
                    return hit
                self.queries += 1
                best, bh, bb, bp = 2.0, None, None, None
                for hz in (0.05, 0.12, 0.28):
                    for k in range(12):
                        a = 2 * math.pi * k / 12
                        r = q.raycast_closest([x, y, floor_z + hz],
                                              [math.cos(a), math.sin(a), 0.0], 2.0)
                        dd = float(r["distance"]) if (r and r.get("hit")) else 2.0
                        if dd < best:
                            best, bh = dd, hz
                            bb = round(math.degrees(a), 1)
                            bp = str(r.get("collision", "")) or None
                out = ClearanceSample(x, y, best, height_m=bh, bearing_deg=bb, prim=bp)
                self.cache[key] = out
                return out

        support, clear = SupportProbe(), ClearanceProbe()
        rng = np.random.default_rng(args.seed)
        candidates: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None

        for i in range(args.budget):
            cid = f"{args.scene_id}_turn_route_{i:03d}"
            support.reset()
            clear.reset()
            try:
                cand = sample_turning_route(inflated, rng,
                                            generator=TURNING_ROUTE_GENERATOR_V1,
                                            clearance_map=clearance_map)
            except PlannerError as exc:
                candidates.append({"ordering_index": i, "candidate_id": cid,
                                   "constructed": False,
                                   "generator_failure": str(exc)[:160]})
                continue

            path = cand.path
            length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
            sep = float(np.linalg.norm(cand.goal - cand.start))
            plan_events, plan_detail = realised_turn_events(path)
            est_frames = int(math.floor((length / CRUISE_V) * CONTROL_HZ))
            windows = window_counts(est_frames)

            row: dict[str, Any] = {
                "ordering_index": i, "candidate_id": cid, "constructed": True,
                **cand.to_dict(),
                "route_length_m": round(length, 4),
                "start_goal_separation_m": round(sep, 4),
                "planned_turn_events_v2": len(plan_events),
                "planned_turn_magnitudes_deg": [round(e.net_deg, 2) for e in plan_events],
                "planned_separator_runs_m": plan_detail.get("separator_runs_m"),
                "estimated_usable_frames": est_frames,
                "windows_per_model": windows,
                "limiting_window_count": min(windows.values()),
            }

            t = LONG_HORIZON_THRESHOLDS
            g10_checks = {
                "frames_capability": est_frames >= t.min_usable_frames,
                "planned_distance": length >= t.min_travelled_distance_m,
                "start_goal_separation": sep >= t.min_start_goal_separation_m,
                "planned_turn_events": len(plan_events) >= t.min_heading_changes,
                "context_windows": min(windows.values()) >= t.min_valid_context_windows,
            }
            row["G10_V2_PLAN_checks"] = g10_checks
            row["G10_V2_PLAN"] = "PASS" if all(g10_checks.values()) else "FAIL"

            # Geometry gates are evaluated for EVERY constructed candidate, so the
            # failure distribution is complete rather than truncated at the first
            # failing gate.
            g3 = evaluate_start_support(support, footprint,
                                        (float(cand.start[0]), float(cand.start[1])),
                                        cand.start_yaw, resolution)
            g6 = evaluate_end_support(support, footprint,
                                      (float(cand.goal[0]), float(cand.goal[1])),
                                      cand.start_yaw, resolution)
            g4 = evaluate_continuous_support(support, footprint, path, resolution,
                                             start_yaw=cand.start_yaw)
            g5 = evaluate_obstacle_clearance(clear, footprint, path, resolution,
                                             start_yaw=cand.start_yaw,
                                             planner_min_clearance_m=cfg.min_clearance_m)
            for g in (g3, g4, g5, g6):
                row[g.gate] = g.status.value
            row["G5_min_clearance_m"] = g5.detail.get("min_clearance_m")
            row["G4_first_failure"] = g4.detail.get("first_unsupported_configuration")

            failures = [g.gate for g in (g3, g4, g5, g6) if g.status is not GateStatus.PASS]
            if row["G10_V2_PLAN"] != "PASS":
                failures.append("G10_V2_PLAN:" + ",".join(
                    k for k, v in g10_checks.items() if not v))
            row["all_gate_failures"] = failures
            row["pre_motion_admissible"] = not failures
            candidates.append(row)
            if not failures and selected is None:
                selected = row
            # The budget is exhausted regardless: no optional stopping.

        rec["candidates"] = candidates
        constructed = [c for c in candidates if c.get("constructed")]
        rec["attempted"] = len(candidates)
        rec["constructed"] = len(constructed)
        rec["generator_failures"] = len(candidates) - len(constructed)
        rec["pre_motion_admissible_count"] = sum(
            1 for c in constructed if c.get("pre_motion_admissible"))
        rec["selected_candidate"] = selected
        rec["selection_rule"] = "first pre-motion-admissible candidate in frozen ordering"

        import collections
        rec["distributions"] = {
            "planned_turn_events_v2": dict(sorted(collections.Counter(
                c["planned_turn_events_v2"] for c in constructed).items())),
            "gate_failure_counts": dict(collections.Counter(
                f.split(":")[0] for c in constructed for f in c["all_gate_failures"])),
            "g10_subcheck_failures": dict(collections.Counter(
                k for c in constructed for k, v in c["G10_V2_PLAN_checks"].items() if not v)),
            # Keys are joined into strings: a tuple key is not JSON-serialisable,
            # and emit_evidence correctly refused to write the whole artefact
            # rather than emitting a partial one.
            "multi_gate_failure_combinations": {
                ("+".join(k) if k else "NONE"): v
                for k, v in collections.Counter(
                    tuple(sorted({f.split(":")[0] for f in c["all_gate_failures"]}))
                    for c in constructed).most_common(10)} if constructed else {},
        }
        rec["probe_queries"] = {"support": support.queries, "clearance": clear.queries}
        rec["controls"] = {
            "budget_fully_enumerated": len(candidates) == args.budget,
            "no_optional_stopping": True,
            "generator_independent_of_g10": rec["generator_independent_of_g10"],
            "support_fails_off_scene": support.sample(1e6, 1e6).supported is False,
        }
        rec["controls_all_pass"] = all(bool(v) for v in rec["controls"].values())
        rec["TURNING_ROUTE_ADMISSION"] = (
            "ROUTE_ADMITTED_FOR_COLLECTION" if selected is not None
            else "NO_ROUTE_SATISFIES_FROZEN_CONTRACT")
    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-3000:]
        rec["TURNING_ROUTE_ADMISSION"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=(
            "check", "artifact_semantics", "TURNING_ROUTE_ADMISSION"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
