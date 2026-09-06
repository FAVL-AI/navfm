"""Is the SUPPORT invariance criterion identifiable under the frozen construction?

DIAGNOSTIC ONLY. This script measures nothing that any expectation depends on and
writes no production artefact. It exists to answer one question:

    The audit flags REVIEW_REQUIRED_UNEXPECTED_INVARIANCE when raw hit distance is
    identical across a stratum's probes. For SUPPORT, the policy places the ray
    origin at the target's own ``bounds_max_z + start_height_m`` and fires straight
    down, so a correct hit on that target's top face returns ``start_height_m``
    exactly -- the target's world elevation cancels. If that is so, raw distance
    CANNOT vary across correct hits, and the criterion asks for something the
    intervention forbids.

The repository has met this genus once already: amendment 1 to the causality
expectations retired DISTANCE_DIVERSITY v1 because "world range is normalised away
BY CONSTRUCTION", and replaced it with a standoff-response test. That reasoning was
never propagated to this consumer. This script tests whether it should be.

Three experiments, none of which change production policy:

1. GEOMETRY      -- expected vs observed distance per target, residual unrounded.
2. PERTURBATION  -- hold the target fixed, vary the diagnostic start height. If the
                    ray truly answers off the declared target, measured distance
                    must track the imposed height one-for-one.
3. REMOVAL       -- disable one target's collider in memory and re-probe. A hit that
                    survives its own target's removal was never target-specific.

The diagnostic policies are built with ``dataclasses.replace`` and live only in this
process. Their digests differ from production, which is the point: a diagnostic
reading must never be mistakable for a production one.

Nothing here may be promoted to an expectation. A replacement criterion chosen
because it makes a scene pass is a result fitted to its instrument.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.candidate_policy import (  # noqa: E402
    DEFAULT_POLICY,
    Aabb,
    Role,
    generate_candidates,
    policy_digest,
)
from navfm.evidence import emit_evidence  # noqa: E402

OUT = REPO / "gates" / "scenes"

#: Diagnostic start heights. 0.50 is production; the others bracket it so a
#: non-response is distinguishable from a one-for-one response.
DIAGNOSTIC_START_HEIGHTS = (0.25, 0.50, 0.75)

#: Ordering assertion for the perturbation control, fixed before execution.
#: A collapse to equality must FAIL -- that is the negative control.
PERTURBATION_TOLERANCE_M = 0.05


def _diagnostic_policy(start_height_m: float):
    """Production policy with only the support start height moved.

    Returns a NEW frozen Policy; the module-level DEFAULT_POLICY is untouched.
    """
    return replace(DEFAULT_POLICY,
                   support=replace(DEFAULT_POLICY.support, start_height_m=start_height_m))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--targets-from", required=True,
                    help="audit artefact whose SUPPORT probes name the targets to re-examine")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    src = json.loads(Path(args.targets_from).read_text())
    targets = [p["expected_target_prim"] for p in src["behavioural"]["support"]["probes"]]
    if not targets:
        print("REFUSED: no SUPPORT targets in the source artefact", file=sys.stderr)
        return 2

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    from isaacsim.core.api import SimulationContext
    from omni.physx import get_physx_scene_query_interface
    from pxr import Usd, UsdGeom, UsdPhysics

    rec: dict[str, Any] = {
        "check": "SUPPORT_INVARIANCE_DIAGNOSTIC",
        "artifact_semantics": "DIAGNOSTIC_ONLY_NOT_AN_EXPECTATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scene": args.scene,
        "targets_from": str(args.targets_from),
        "production_policy_digest": policy_digest(),
        "question": ("Can raw SUPPORT hit distance vary across correct hits, given an "
                     "origin defined as the target's own bounds_max_z + start_height?"),
        "claim_boundary": ("Concerns the identifiability of one criterion. Establishes "
                           "nothing about whether Hospital is suitable, and does not "
                           "change any expectation, verdict or policy."),
    }

    try:
        stage_utils.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0)
        stage_utils.add_reference_to_stage(args.scene, "/World/Scene")
        stage = stage_utils.get_current_stage()
        sim.initialize_physics()
        for _ in range(3):
            sim.step(render=False)

        purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                    UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide]
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes, useExtentsHint=False)
        q = get_physx_scene_query_interface()

        def bounds_of(path: str) -> Aabb | None:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                return None
            r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            if r.IsEmpty():
                return None
            mn, mx = r.GetMin(), r.GetMax()
            return Aabb((mn[0], mn[1], mn[2]), (mx[0], mx[1], mx[2]))

        def probe(path: str, box: Aabb, policy) -> dict[str, Any]:
            cset = generate_candidates(path, Role.SUPPORT, box, policy=policy)
            cand = cset.candidates[0]
            res = q.raycast_closest(list(cand.origin), list(cand.direction), cand.max_range)
            hit = bool(res and res.get("hit"))
            collider = str(res.get("collision", "")) if hit else None
            match = bool(collider and (collider == path
                                       or collider.startswith(path)
                                       or path.startswith(collider)))
            observed = float(res.get("distance")) if hit else None
            expected = cand.origin[2] - box.maximum[2]      # == start_height_m
            return {
                "policy_digest": policy.digest(),
                "start_height_m": policy.support.start_height_m,
                "origin": list(cand.origin), "direction": list(cand.direction),
                "max_range": cand.max_range,
                "target_bounds_max_z": box.maximum[2],
                "expected_distance_m": expected,
                "observed_distance_m": observed,
                "residual_m": (observed - expected) if observed is not None else None,
                "hit": hit, "collider": collider, "identity_match": match,
            }

        # ---- experiment 1: geometry, at production start height ---------------
        geometry = []
        boxes: dict[str, Aabb] = {}
        for path in targets:
            box = bounds_of(path)
            if box is None:
                geometry.append({"target": path, "error": "bounds empty or prim missing"})
                continue
            boxes[path] = box
            r = probe(path, box, DEFAULT_POLICY)
            geometry.append({"target": path, **r})
        rec["experiment_1_geometry"] = geometry

        zs = sorted({round(b.maximum[2], 6) for b in boxes.values()})
        rec["target_top_elevations_m"] = zs
        rec["targets_share_one_elevation"] = len(zs) == 1

        # ---- experiment 2: start-height perturbation ---------------------------
        # Representative targets, chosen by position in the frozen list rather than
        # by their observed values, so the choice cannot be outcome-driven.
        reps = [p for p in targets if p in boxes][:3]
        perturbation = []
        for path in reps:
            series = []
            for h in DIAGNOSTIC_START_HEIGHTS:
                series.append(probe(path, boxes[path], _diagnostic_policy(h)))
            tracks = all(
                s["observed_distance_m"] is not None
                and abs(s["observed_distance_m"] - s["start_height_m"]) <= PERTURBATION_TOLERANCE_M
                for s in series)
            distinct = len({round(s["observed_distance_m"], 3) for s in series
                            if s["observed_distance_m"] is not None})
            perturbation.append({
                "target": path, "series": series,
                "distance_tracks_start_height": tracks,
                "distinct_observed_distances": distinct,
                "identity_held_throughout": all(s["identity_match"] for s in series),
            })
        rec["experiment_2_perturbation"] = perturbation

        # ---- experiment 3: target removal -------------------------------------
        # Isolated: a failure here must not discard experiments 1 and 2, and
        # "could not run" must be recorded as that rather than as a null result.
        removal: dict[str, Any] = {"status": "NOT_ATTEMPTED"}
        if reps:
            path = reps[0]
            before = probe(path, boxes[path], DEFAULT_POLICY)
            try:
                prim = stage.GetPrimAtPath(before["collider"] or path)
                if not (prim and prim.IsValid()):
                    raise RuntimeError("collider prim not resolvable on the stage")
                capi = UsdPhysics.CollisionAPI.Apply(prim)
                capi.CreateCollisionEnabledAttr().Set(False)
                for _ in range(3):
                    sim.step(render=False)
                after = probe(path, boxes[path], DEFAULT_POLICY)
                removal = {
                    "status": "EXECUTED", "target": path,
                    "before": before, "after": after,
                    "observation_changed": (
                        before["collider"] != after["collider"]
                        or before["hit"] != after["hit"]
                        or before["observed_distance_m"] != after["observed_distance_m"]),
                }
            except Exception as exc:
                removal = {
                    "status": "NOT_RUN", "target": path, "before": before,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "interpretation": ("Hospital's floor prims are USD instance proxies, which "
                                       "cannot be authored on. The causal removal control therefore "
                                       "did NOT execute, and target-specific causality is NOT "
                                       "established by this diagnostic."),
                }
        rec["experiment_3_removal"] = removal

        # ---- experiment 4: displaced-origin negative control -------------------
        # Substitute for the blocked removal control. Declare the same target but
        # generate the intervention from bounds translated far away: the ray then
        # cannot be answered by that target. If identity_match stays True here, the
        # identity check is incapable of failing and proves nothing above.
        displaced = []
        for path in reps:
            b = boxes[path]
            far = Aabb((b.minimum[0] + 50.0, b.minimum[1] + 50.0, b.minimum[2]),
                       (b.maximum[0] + 50.0, b.maximum[1] + 50.0, b.maximum[2]))
            r = probe(path, far, DEFAULT_POLICY)
            displaced.append({"target": path, "displacement_m": [50.0, 50.0, 0.0], **r})
        rec["experiment_4_displaced_origin_control"] = displaced
        rec["identity_check_can_fail"] = any(not d["identity_match"] for d in displaced)

    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        # Persist BEFORE shutting Isaac down, and prove it landed. close() can
        # terminate the process outright, so a write placed after it never runs --
        # which produced exit 0 with no artefact on the first attempt here.
        # emit_evidence re-reads and re-parses, so reaching the next line means the
        # artefact exists; failing to means an exception, not a zero.
        digest = emit_evidence(args.out, rec, required_keys=("check", "artifact_semantics"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
