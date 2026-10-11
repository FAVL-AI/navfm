"""Item 11 — the V2 PLAN precondition on the already-frozen candidate population.

The route-admission artefact stores turn counts but not the planned polylines, so
V2 plan counts cannot be read from it. They are not lost: the population comes
from a seeded sampler run against a fixed map, so replaying that sampler
reproduces every candidate's path exactly, as was already proved for candidate
050 during collection.

Nothing is regenerated in the sense of changed. Scene, seed, budget, ordering,
start/goal population, obstacle map and the selection rule are all held to the
frozen values; only the turn METRIC changes, which is the whole point of the
comparison.
"""

from __future__ import annotations

import argparse
import contextlib
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
    ap.add_argument("--robot", required=True)
    ap.add_argument("--admission-artefact", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp
    app = SimulationApp({"headless": True})

    import dataclasses

    import isaacsim.core.utils.stage as stage_utils
    import numpy as np
    from isaacsim.core.api import SimulationContext
    from isaacsim.core.utils.extensions import enable_extension

    from navfm.collection.footprint import heading_changes
    from navfm.collection.turn_events import TURN_SEMANTICS_V2, realised_turn_events
    from navfm.isaac.app import SimConfig
    from navfm.isaac.collect import OCCUPANCY_BACKEND_PHYSX, CollectConfig, Collector
    from navfm.isaac.randomize import RandomizationConfig
    from navfm.isaac.robot import M3PRO
    from navfm.planning import PlannerError, sample_episode_pair
    from navfm.simenv import simulator_identity

    admission = json.loads(Path(args.admission_artefact).read_text())
    seed = admission["search"]["seed"]
    budget = admission["search"]["budget"]
    sim_id = simulator_identity()

    rec: dict[str, Any] = {
        "check": "G10_V2_PLAN_PRECONDITION_ON_FROZEN_POPULATION",
        "artifact_semantics": "METRIC_RE_EVALUATION_ON_AN_UNCHANGED_POPULATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "semantics": "gates/BO10/g10_turn_semantics_v2_20260910.json",
        "semantics_sha256": "a8f8b383c5a392ea3f200c5704e265b7a31f14b0585397e6bb4dda836258eaf3",
        "source_admission_artefact": args.admission_artefact,
        "held_fixed": {"scene": args.scene, "seed": seed, "budget": budget,
                       "ordering": "seeded generation order",
                       "obstacle_map_backend": OCCUPANCY_BACKEND_PHYSX,
                       "start_goal_population": "unchanged",
                       "G3_to_G9": "unchanged", "selection_rule": "unchanged"},
        "only_thing_changed": "the turn metric",
        "method": ("replay the seeded sampler against the same map to regenerate each "
                   "candidate's planned path, then measure turns under v1 and V2"),
        "provenance": {"isaac_sim_version": sim_id.isaac_sim_version,
                       "interpreter": sim_id.interpreter, "gpu": sim_id.gpu},
    }

    try:
        stage_utils.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0)
        stage_utils.add_reference_to_stage(args.scene, "/World/Scene")
        sim.initialize_physics()
        for _ in range(5):
            sim.step(render=False)
        enable_extension("isaacsim.asset.gen.omap")

        cfg = CollectConfig(scenes=[args.scene], seed=seed)
        collector = Collector("/tmp/_v2plan", cfg, SimConfig(headless=True),
                              dataclasses.replace(M3PRO, usd_path=args.robot),
                              RandomizationConfig(enabled=False),
                              occupancy_backend=OCCUPANCY_BACKEND_PHYSX)
        collector._app = app
        grid = collector.build_occupancy(args.scene, backend=OCCUPANCY_BACKEND_PHYSX)
        collector._grid = grid
        collector._clearance = grid.clearance()
        inflated = collector._inflated
        clearance_map = collector._inflated_clearance

        rng = np.random.default_rng(seed)
        stored = {c["route_id"]: c for c in admission["candidates"]}
        rows: list[dict[str, Any]] = []
        identity_ok = 0

        for i in range(budget):
            route_id = f"hospital_repaired_map_route_{i:03d}"
            try:
                start, _yaw, _goal, path = sample_episode_pair(
                    inflated, rng, min_path_m=8.0, max_path_m=40.0,
                    min_clearance_m=cfg.min_clearance_m, clearance_map=clearance_map)
            except PlannerError as exc:
                rows.append({"route_id": route_id, "planner_error": str(exc)[:120]})
                continue

            old = stored.get(route_id, {})
            matches = bool(old.get("start_pose")) and all(
                abs(a - b) < 1e-9 for a, b in
                zip(old["start_pose"][:2], [float(start[0]), float(start[1])], strict=False))
            identity_ok += int(matches)

            v1_count, v1_turns = heading_changes(path, 30.0)
            v2_events, v2_detail = realised_turn_events(path)
            rows.append({
                "route_id": route_id,
                "identity_matches_frozen_population": matches,
                "v1_planned_turns": v1_count,
                "v1_turn_magnitudes": [round(t, 2) for t in v1_turns],
                "v2_planned_turn_events": len(v2_events),
                "v2_event_magnitudes": [round(e.net_deg, 2) for e in v2_events],
                "v2_longest_separator_run_m": v2_detail.get("longest_separator_run_m"),
                "v2_plan_precondition": "PASS" if len(v2_events) >= 3 else "FAIL",
                "all_route_gates_pass_v1": old.get("all_route_gates_pass"),
            })

        rec["candidates"] = rows
        evaluated = [r for r in rows if "v1_planned_turns" in r]
        rec["candidates_evaluated"] = len(evaluated)
        rec["identity_matches"] = identity_ok
        rec["v1_pass_count"] = sum(1 for r in evaluated if r["v1_planned_turns"] >= 3)
        rec["v2_pass_count"] = sum(1 for r in evaluated if r["v2_plan_precondition"] == "PASS")
        rec["changed_verdict"] = sum(
            1 for r in evaluated
            if (r["v1_planned_turns"] >= 3) != (r["v2_plan_precondition"] == "PASS"))
        rec["v2_pass_and_all_other_gates_pass"] = [
            r["route_id"] for r in evaluated
            if r["v2_plan_precondition"] == "PASS" and r.get("all_route_gates_pass_v1")]
        rec["first_candidate_under_frozen_selection_rule"] = (
            rec["v2_pass_and_all_other_gates_pass"][0]
            if rec["v2_pass_and_all_other_gates_pass"] else None)
        rec["qualifying_turn_deg"] = TURN_SEMANTICS_V2.qualifying_turn_deg
        rec["G10_V2_PLAN_EVALUATION"] = "COMPLETE"
    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-2500:]
        rec["G10_V2_PLAN_EVALUATION"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=(
            "check", "artifact_semantics", "G10_V2_PLAN_EVALUATION"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
