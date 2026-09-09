"""Scene-agnostic BO-10 route admission: G3, G4, G5, G6 and predicted G10.

Supersedes ``validate_hospital_route_admission.py``, whose gate logic was inline
and whose labels were Hospital-specific. The gates now live in
``navfm.collection`` and are exercised here through the same code the collector
will use, so this harness tests the production gates rather than a copy of them.

Two refusals inherited deliberately:

* **No hand-picked route.** Candidates come from ``sample_episode_pair`` under a
  declared seed and a declared budget, and every candidate is recorded with its
  rejection reason. Searching until something passes and reporting only that is
  how a route gets selected for the property being measured.
* **No centreline-only test.** Support and clearance are evaluated across the
  swept footprint at the frozen resolution.

Gate order is cheapest-first: predicted G10 is pure geometry, so a candidate
failing it is rejected before any raycast. That is not a shortcut -- every gate
is required under an all-must-pass rule, so a candidate failing one is rejected
whatever the others would have said.

The probes memoise by quantised world position. The scene is static for the
whole read-only pass, so a repeated query has a single answer; consecutive swept
configurations overlap heavily and would otherwise re-probe the same ground tens
of times.
"""

from __future__ import annotations

import argparse
import contextlib
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402

#: Support probe geometry. The ray starts just above the floor, NOT a metre up:
#: a ray dropped from 1 m returns the nearest hit, which in a furnished scene is
#: a supply cart or a handrail. Reading that as "unsupported" conflates an
#: obstacle with a hole, and obstacles are G5's question.
SUPPORT_PROBE_HEIGHT_M = 0.05
SUPPORT_MAX_RANGE_M = 0.30
SUPPORT_FLOOR_TOL_M = 0.08

#: Clearance probe heights span the SIMULATED collision body, not the chassis.
#: The wheel colliders reach ground contact, so geometry at 0.05 m is inside the
#: collision band even though it passes under the chassis.
CLEARANCE_PROBE_HEIGHTS_M = (0.05, 0.12, 0.28)
CLEARANCE_RAY_COUNT = 12
CLEARANCE_MAX_RANGE_M = 2.0

#: Memoisation grid. Finer than the probe spacing, so distinct probes never
#: collapse onto one cache entry.
CACHE_QUANT_M = 0.005

#: Cache entries are dropped between candidates. The overlap memoisation exists
#: to exploit is WITHIN a route -- consecutive swept configurations re-probe the
#: same ground tens of times -- and it does not carry between candidates whose
#: routes are elsewhere in the scene. Keeping every entry for the whole search
#: made the caches grow without bound: the first Office run reached 7 GB RSS at
#: three minutes and the machine began shedding processes. A bounded cache keeps
#: the speedup and drops the growth.
CACHE_MAX_ENTRIES = 400_000


def _provenance(scene: str, robot: str) -> dict[str, Any]:
    import hashlib
    import subprocess

    def sh(*c: str) -> str:
        try:
            return subprocess.run(c, cwd=REPO, capture_output=True, text=True).stdout.strip()
        except Exception:
            return "unavailable"

    def sha(p: str) -> str:
        path = Path(p)
        if not path.is_file():
            return "not-a-local-file"
        return hashlib.sha256(path.read_bytes()).hexdigest()

    import platform
    return {
        "hostname": platform.node(),
        "interpreter": sys.executable,
        "python": platform.python_version(),
        "git_head": sh("git", "rev-parse", "HEAD"),
        "git_branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "worktree_dirty": bool(sh("git", "status", "--porcelain")),
        "harness_sha256": sha(str(Path(__file__).resolve())),
        "scene_asset": scene,
        "robot_asset": robot,
        "robot_asset_sha256": sha(robot),
    }


#: Fields whose per-configuration lists would make the artefact enormous without
#: adding evidence: the first failure and the counts are what a reader needs, and
#: both are kept.
_BULK_DETAIL_FIELDS = ("unsupported_configurations", "violations", "unsupported_samples")


def _trim(gate: dict[str, Any]) -> dict[str, Any]:
    """Drop bulk per-configuration lists, keeping first-failure and counts."""
    detail = dict(gate.get("detail") or {})
    for field in _BULK_DETAIL_FIELDS:
        if isinstance(detail.get(field), list) and len(detail[field]) > 1:
            detail[field] = detail[field][:1]
            detail[f"{field}_truncated_to"] = 1
    gate["detail"] = detail
    return gate


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--scene-id", required=True)
    ap.add_argument("--robot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", type=int, default=96,
                    help="candidate search budget (frozen; matches the Hospital search)")
    ap.add_argument("--region-declaration", default=None,
                    help="frozen collection-region declaration JSON. REQUIRED for a scene "
                         "with no intrinsic geometric boundary (see gates/failures/F-BOUNDS-1.md); "
                         "omit to map the whole stage bound, which is the unchanged default.")
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp
    app = SimulationApp({"headless": True})

    import dataclasses

    import isaacsim.core.utils.stage as stage_utils
    import numpy as np
    from isaacsim.core.api import SimulationContext
    from omni.physx import get_physx_scene_query_interface

    from navfm.collection.admission import BO10CollectionAdmission
    from navfm.collection.clearance import ClearanceSample, evaluate_obstacle_clearance
    from navfm.collection.footprint import CircularFootprint, SweepResolution
    from navfm.collection.gates import GateStatus
    from navfm.collection.long_horizon import LONG_HORIZON_THRESHOLDS, predict_from_route
    from navfm.collection.scope import bo10_scope
    from navfm.collection.support import (
        SupportSample,
        evaluate_continuous_support,
        evaluate_end_support,
        evaluate_start_support,
    )
    from navfm.isaac.app import SimConfig
    from navfm.isaac.collect import CollectConfig, Collector
    from navfm.isaac.randomize import RandomizationConfig
    from navfm.isaac.robot import M3PRO
    from navfm.planning import PlannerError, sample_episode_pair

    rec: dict[str, Any] = {
        "check": "BO10_ROUTE_ADMISSION_G3_G4_G5_G6_G10",
        "artifact_semantics": "DIAGNOSTIC_ONLY_NOT_AN_EXPECTATION",
        "scene_id": args.scene_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": _provenance(args.scene, args.robot),
        "scope": bo10_scope().to_manifest_fields(),
        "search": {"seed": args.seed, "budget": args.budget,
                   "method": "navfm.planning.sample_episode_pair under a declared seed",
                   "candidate_ordering": "seeded generation order",
                   "hand_picked": False},
        "gate_order": ("predicted G10 first (pure geometry), then G3/G6, then G4, then G5. "
                       "All gates are required, so a candidate failing one is rejected "
                       "whatever the others would have said."),
        "claim_boundary": ("Selects a route for collection. Admits no data, drives nothing, "
                           "and makes no physical-hardware or contact-fidelity claim."),
        "f_twin_1": "OPEN -- no contact-physics claim rests on this pass",
    }

    try:
        cfg = CollectConfig(scenes=[args.scene], seed=args.seed,
                            min_path_m=LONG_HORIZON_THRESHOLDS.min_travelled_distance_m,
                            max_path_m=40.0)
        robot_cfg = dataclasses.replace(M3PRO, usd_path=args.robot)
        collector = Collector("/tmp/_bo10_route_probe", cfg, SimConfig(headless=True),
                              robot_cfg, RandomizationConfig(enabled=False),
                              scope=bo10_scope())
        collector._app = app

        stage_utils.create_new_stage()
        simctx = SimulationContext(stage_units_in_meters=1.0)
        stage_utils.add_reference_to_stage(args.scene, "/World/Scene")
        simctx.initialize_physics()
        for _ in range(3):
            simctx.step(render=False)

        from isaacsim.core.utils.extensions import enable_extension
        rec["occupancy_extension_enabled"] = bool(enable_extension("isaacsim.asset.gen.omap"))

        region_bounds = None
        if args.region_declaration:
            import json as _json
            decl = _json.loads(Path(args.region_declaration).read_text())
            import hashlib as _hashlib
            rec["region_declaration"] = {
                "path": args.region_declaration,
                "sha256": _hashlib.sha256(
                    Path(args.region_declaration).read_bytes()).hexdigest(),
                "check": decl.get("check"),
                "region_centre": decl["region_centre"]["value"],
                "window": decl["window"],
                "frozen_before_any_candidate_enumerated": decl.get("artifact_semantics"),
            }
            region_bounds = (tuple(decl["window"]["bounds_min"]),
                             tuple(decl["window"]["bounds_max"]))
        rec["occupancy_bounds_source"] = ("declared region" if region_bounds
                                          else "stage bound (default)")
        grid = collector.build_occupancy(args.scene, bounds=region_bounds)
        collector._grid = grid
        collector._clearance = grid.clearance()
        inflated = collector._inflated
        clearance_map = collector._inflated_clearance

        footprint = CircularFootprint(robot_cfg.footprint_radius)
        resolution = SweepResolution.derive(robot_cfg.footprint_radius,
                                            grid_resolution_m=cfg.grid_resolution)
        rec["sweep_resolution"] = resolution.to_dict()
        rec["occupancy"] = {
            "resolution_m": cfg.grid_resolution,
            "shape": list(grid.shape),
            "footprint_radius_m": robot_cfg.footprint_radius,
            "planner_min_clearance_m": cfg.min_clearance_m,
        }

        q = get_physx_scene_query_interface()

        probe = q.raycast_closest([0.0, 0.0, SUPPORT_PROBE_HEIGHT_M], [0.0, 0.0, -1.0],
                                  SUPPORT_MAX_RANGE_M)
        floor_z = (SUPPORT_PROBE_HEIGHT_M - float(probe["distance"])) if (
            probe and probe.get("hit")) else 0.0
        rec["floor_reference_z"] = floor_z

        class IsaacSupportProbe:
            """Is there floor beneath this point? Memoised; the scene is static."""

            def __init__(self) -> None:
                self.cache: dict[tuple[int, int], SupportSample] = {}
                self.queries = 0

            def reset(self) -> None:
                self.cache.clear()

            def sample(self, x: float, y: float) -> SupportSample:
                key = (int(round(x / CACHE_QUANT_M)), int(round(y / CACHE_QUANT_M)))
                hit = self.cache.get(key)
                if hit is not None:
                    return hit
                if len(self.cache) >= CACHE_MAX_ENTRIES:
                    self.cache.clear()
                self.queries += 1
                origin = [x, y, floor_z + SUPPORT_PROBE_HEIGHT_M]
                res = q.raycast_closest(origin, [0.0, 0.0, -1.0], SUPPORT_MAX_RANGE_M)
                if not (res and res.get("hit")):
                    out = SupportSample(x, y, False, reason="NO_GROUND_HIT")
                else:
                    hz = origin[2] - float(res["distance"])
                    prim = str(res.get("collision", "")) or None
                    if abs(hz - floor_z) > SUPPORT_FLOOR_TOL_M:
                        out = SupportSample(x, y, False, margin_m=hz - floor_z, prim=prim,
                                            reason="HIT_OFF_FLOOR")
                    else:
                        out = SupportSample(x, y, True, margin_m=hz - floor_z, prim=prim)
                self.cache[key] = out
                return out

        class IsaacClearanceProbe:
            """Horizontal distance to blocking geometry. Memoised."""

            def __init__(self) -> None:
                self.cache: dict[tuple[int, int], ClearanceSample] = {}
                self.queries = 0

            def reset(self) -> None:
                self.cache.clear()

            def sample(self, x: float, y: float) -> ClearanceSample:
                key = (int(round(x / CACHE_QUANT_M)), int(round(y / CACHE_QUANT_M)))
                hit = self.cache.get(key)
                if hit is not None:
                    return hit
                if len(self.cache) >= CACHE_MAX_ENTRIES:
                    self.cache.clear()
                self.queries += 1
                best = CLEARANCE_MAX_RANGE_M
                best_h: float | None = None
                best_b: float | None = None
                best_prim: str | None = None
                for hz in CLEARANCE_PROBE_HEIGHTS_M:
                    for k in range(CLEARANCE_RAY_COUNT):
                        a = 2 * math.pi * k / CLEARANCE_RAY_COUNT
                        res = q.raycast_closest([x, y, floor_z + hz],
                                                [math.cos(a), math.sin(a), 0.0],
                                                CLEARANCE_MAX_RANGE_M)
                        d = (float(res["distance"]) if (res and res.get("hit"))
                             else CLEARANCE_MAX_RANGE_M)
                        if d < best:
                            best, best_h = d, hz
                            best_b = round(math.degrees(a), 1)
                            best_prim = str(res.get("collision", "")) or None
                out = ClearanceSample(x, y, best, height_m=best_h, bearing_deg=best_b,
                                      prim=best_prim)
                self.cache[key] = out
                return out

        support = IsaacSupportProbe()
        clearance = IsaacClearanceProbe()

        # ---- deterministic candidate enumeration --------------------------
        rng = np.random.default_rng(args.seed)
        candidates: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None

        for i in range(args.budget):
            cand: dict[str, Any] = {"route_id": f"{args.scene_id}_route_{i:03d}"}
            support.reset()
            clearance.reset()
            try:
                start, yaw, goal, path = sample_episode_pair(
                    inflated, rng,
                    min_path_m=LONG_HORIZON_THRESHOLDS.min_travelled_distance_m,
                    max_path_m=40.0,
                    min_clearance_m=cfg.min_clearance_m, clearance_map=clearance_map)
            except PlannerError as exc:
                cand.update({"rejected": True, "rejection_reason": f"planner: {exc}",
                             "gates": {}})
                candidates.append(cand)
                continue

            cand["start_pose"] = [float(start[0]), float(start[1]), float(yaw)]
            cand["goal_pose"] = [float(goal[0]), float(goal[1])]
            cand["nominal_path_length_m"] = float(
                np.linalg.norm(np.diff(path, axis=0), axis=1).sum())

            adm = BO10CollectionAdmission(scope=bo10_scope(),
                                          route_id=cand["route_id"], scene=args.scene_id)

            g10 = predict_from_route(path, control_hz=12.0, cruise_v=cfg.cruise_v)
            adm.record(g10)
            if g10.status is not GateStatus.PASS:
                cand.update({"rejected": True, "rejection_reason": f"G10: {g10.reason}",
                             "gates": {g10.gate: _trim(g10.to_dict())}})
                candidates.append(cand)
                continue

            g3 = evaluate_start_support(support, footprint,
                                        (float(path[0][0]), float(path[0][1])), float(yaw),
                                        resolution)
            g6 = evaluate_end_support(support, footprint,
                                      (float(path[-1][0]), float(path[-1][1])), float(yaw),
                                      resolution)
            adm.record(g3)
            adm.record(g6)
            gates = [g10, g3, g6]

            if g3.admits and g6.admits:
                g4 = evaluate_continuous_support(support, footprint, path, resolution,
                                                 start_yaw=float(yaw))
                adm.record(g4)
                gates.append(g4)
                if g4.admits:
                    g5 = evaluate_obstacle_clearance(
                        clearance, footprint, path, resolution, start_yaw=float(yaw),
                        planner_min_clearance_m=cfg.min_clearance_m)
                    adm.record(g5)
                    gates.append(g5)

            cand["gates"] = {g.gate: _trim(g.to_dict()) for g in gates}
            failed = [g.gate for g in gates if not g.admits]
            evaluated = {g.gate for g in gates}
            required = {"G10_LONG_HORIZON", "G3_START_SUPPORT", "G6_END_SUPPORT",
                        "G4_CONTINUOUS_ROUTE_SUPPORT", "G5_OBSTACLE_CLEARANCE"}
            not_evaluated = sorted(required - evaluated)
            cand["all_route_gates_pass"] = not failed and not not_evaluated
            cand["gates_not_evaluated"] = not_evaluated
            cand["rejected"] = not cand["all_route_gates_pass"]
            cand["rejection_reason"] = (",".join(failed) if failed else
                                        (f"not evaluated: {not_evaluated}"
                                         if not_evaluated else None))
            candidates.append(cand)
            if cand["all_route_gates_pass"] and selected is None:
                selected = cand
            # The budget is exhausted regardless, so the selection is "first
            # passing under a declared seed", not "kept looking until one passed".

        rec["candidates"] = candidates
        rec["candidates_generated"] = len(candidates)
        rec["candidates_passing"] = sum(1 for c in candidates if c.get("all_route_gates_pass"))
        rec["selected_route"] = selected
        rec["selection_rule"] = "first candidate passing all route gates, in seeded order"
        # Snapshot BEFORE the control probes run, so the control cannot satisfy
        # itself. Counting after would make "probes were queried" true because
        # the control probe queried one -- a check certifying its own execution
        # rather than the candidate evaluation's.
        candidate_support_queries = support.queries
        candidate_clearance_queries = clearance.queries
        geometry_gates_evaluated = sum(
            1 for c in candidates
            if any(g in (c.get("gates") or {})
                   for g in ("G3_START_SUPPORT", "G4_CONTINUOUS_ROUTE_SUPPORT",
                             "G5_OBSTACLE_CLEARANCE", "G6_END_SUPPORT")))
        rec["probe_queries"] = {
            "support_during_candidates": candidate_support_queries,
            "clearance_during_candidates": candidate_clearance_queries,
            "candidates_reaching_a_geometry_gate": geometry_gates_evaluated,
            "zero_is_expected_when": ("every candidate is rejected by predicted G10, which is "
                                      "pure route geometry and needs no raycast"),
        }

        # ---- instrument controls: the gates must be able to fail ----------
        far = 1.0e6
        off_scene = support.sample(far, far)
        open_space = clearance.sample(far, far)
        rec["controls"] = {
            "support_fails_off_scene": off_scene.supported is False,
            "clearance_is_unobstructed_off_scene": (
                open_space.distance_m >= CLEARANCE_MAX_RANGE_M),
            "budget_fully_enumerated": len(candidates) == args.budget,
            # Conditional, and deliberately so. An earlier form asserted
            # support.queries > 0 unconditionally and was evaluated AFTER the
            # control probes, so the control probe made the control pass: it
            # certified its own execution, not the candidate evaluation's. Zero
            # candidate probes is CORRECT when every candidate is rejected by
            # predicted G10 before any geometry gate is reached, so the control
            # asks the question that can actually be wrong -- did the probes run
            # where a geometry gate was in fact evaluated?
            "probes_queried_where_a_geometry_gate_was_evaluated": (
                candidate_support_queries > 0 if geometry_gates_evaluated else True),
            "control_probes_are_not_counted_as_candidate_probes": (
                support.queries > candidate_support_queries),
        }
        rec["controls_all_pass"] = all(rec["controls"].values())

        if not rec["controls_all_pass"]:
            verdict = "ROUTE_INSTRUMENT_REVIEW_REQUIRED"
        elif selected is not None:
            verdict = "ROUTE_ADMITTED_FOR_COLLECTION"
        else:
            verdict = "NO_ROUTE_SATISFIES_FROZEN_CONTRACT"
        rec["ROUTE_ADMISSION"] = verdict

    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-3000:]
        rec["ROUTE_ADMISSION"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=(
            "check", "artifact_semantics", "ROUTE_ADMISSION"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
