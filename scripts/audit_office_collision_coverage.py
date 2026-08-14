"""Does PhysX see enough of this scene to be trusted about free space?

A validated query harness is still useless on a scene that omits collision for
geometry the robot would physically hit. The failure is one-directional and
therefore dangerous: missing collision never produces a false obstacle, it
produces false *free space* -- exactly where the robot would crash.

The question deliberately is **not** "does every render mesh have a collider?".
That equivalence is wrong: decorative trim, ceiling detail and a distant skyline
need no collision. The question is whether the surfaces and objects capable of
blocking a Yahboom, within its own height band, are physically queryable.

Two independent lines of evidence, because either alone is weak:

**Declared** -- prims carrying UsdPhysics.CollisionAPI with collision enabled,
classified against the navigation band.

**Behavioural** -- directed probes fired at visible structures whose identity is
declared *before* the query runs, checking that the returned collider is the one
expected. A count of hits proves something was there; naming the collider proves
it was the right thing. That distinction is the whole lesson of the fixture round
where the floor satisfied an obstacle expectation.

Support is audited separately from obstruction. A scene with beautiful walls and
no floor collision would report abundant free space and drop the robot through
it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.measurement import Liveness, MeasurementEnvelope, not_run  # noqa: E402

OUT = REPO / "gates" / "scenes"

#: Target reachability and sample representativeness are different questions. A
#: probe that reaches 1 of 8 targets can be perfectly causal about that one
#: collider and still say almost nothing about the scene. Below this fraction the
#: stratum reports NON_PROBATIVE_SAMPLE rather than a scene-level verdict --
#: a strong failure claim needs a sample capable of supporting it.
MIN_REACHABLE_FRACTION = 0.5

#: The probe may only judge a candidate scene after earning the right to, which
#: is what 9/9 causality regressions established. The digest is mandatory
#: provenance: a behavioural row without it is not admissible evidence, because
#: nothing would distinguish it from the retired probe's output.
REQUIRED_CONTRACT_DIGEST = "480d9f07770eaf2a95446793639e9aad"

#: The robot's own band. Geometry outside it cannot block a Yahboom, so its
#: collision state is irrelevant and must not count against coverage.
NAV_Z_MIN, NAV_Z_MAX = 0.02, 0.2803
FOOTPRINT = (0.235, 0.195)


def classify(z_lo: float, z_hi: float, floor_z: float, size: float) -> str:
    """What role could this geometry play for a robot on this floor?"""
    band_lo, band_hi = floor_z + NAV_Z_MIN, floor_z + NAV_Z_MAX
    if z_hi <= band_lo + 0.02 and size > 1.0:
        return "SUPPORT_SURFACE"
    if z_lo > band_hi:
        return "NON_BLOCKING_VISUAL_GEOMETRY"      # entirely overhead
    if z_hi < band_lo:
        return "NON_BLOCKING_VISUAL_GEOMETRY"      # entirely below
    return "BLOCKING_STRUCTURE" if size >= 0.15 else "DECORATIVE"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--scene-id", required=True)
    args = ap.parse_args()

    contract_p = OUT / "collision_probe_contract.json"
    if not contract_p.is_file():
        print("REFUSED: no frozen probe contract; the probe has not earned adjudication rights",
              file=sys.stderr)
        return 2
    contract = json.loads(contract_p.read_text())
    cd = contract.get("probe_contract_digest", "")
    if cd[:32] != REQUIRED_CONTRACT_DIGEST:
        print(f"REFUSED: contract digest\n  got    {cd}\n  required {REQUIRED_CONTRACT_DIGEST}",
              file=sys.stderr)
        return 2

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})
    envelopes: list[MeasurementEnvelope] = []
    rec: dict[str, Any] = {
        "check": "COLLISION_COVERAGE_AUDIT",
        "scene_id": args.scene_id, "scene": args.scene,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "navigation_band_m": [NAV_Z_MIN, NAV_Z_MAX],
        "footprint_m": list(FOOTPRINT),
        "question": ("Are the surfaces and objects capable of blocking a Yahboom, within its "
                     "own height band, physically queryable? NOT 'does every render mesh "
                     "carry a collider' -- that equivalence is false and would fail every "
                     "real asset."),
        "risk_direction": ("Missing collision never invents an obstacle; it invents free "
                           "space, precisely where the robot would collide."),
        "probe_contract_digest": cd,
        "probe_contract_regressions": contract.get("gate"),
        "evidence_channels_kept_separate": (
            "authored CollisionAPI state and live behavioural response are reported as "
            "independent lines and never merged into one percentage"),
    }

    try:
        import isaacsim.core.utils.stage as stage_utils
        import numpy as np
        from isaacsim.core.api import SimulationContext
        from omni.physx import get_physx_scene_query_interface
        from pxr import Usd, UsdGeom, UsdPhysics

        sim = SimulationContext(stage_units_in_meters=1.0)
        stage_utils.add_reference_to_stage(args.scene, "/World/Scene")
        stage = stage_utils.get_current_stage()
        sim.reset()
        for _ in range(40):
            sim.step(render=False)

        purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                    UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide]
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes, useExtentsHint=False)

        rows: list[dict[str, Any]] = []
        zmins = []
        for prim in stage.Traverse(Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)):
            if prim.GetTypeName() != "Mesh":
                continue
            r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            # An empty range reports inverted FLT_MAX sentinels that read as an
            # enormous box if used numerically. Validity is checked, not assumed.
            if r.IsEmpty():
                rows.append({"path": str(prim.GetPath()), "bounds": "EMPTY",
                             "coverage": "UNKNOWN"})
                continue
            mn, mx = r.GetMin(), r.GetMax()
            zmins.append(mn[2])
            rows.append({
                "path": str(prim.GetPath()),
                "z": [round(mn[2], 3), round(mx[2], 3)],
                "size": round(max(mx[0] - mn[0], mx[1] - mn[1]), 3),
                "has_collision_api": bool(prim.HasAPI(UsdPhysics.CollisionAPI)),
                "collision_enabled": bool(
                    prim.HasAPI(UsdPhysics.CollisionAPI)
                    and (UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
                         is not False)),
            })

        floor_z = float(np.percentile(zmins, 5)) if zmins else 0.0
        for row in rows:
            if row.get("bounds") == "EMPTY":
                continue
            row["classification"] = classify(row["z"][0], row["z"][1], floor_z, row["size"])
            needs = row["classification"] in ("SUPPORT_SURFACE", "BLOCKING_STRUCTURE")
            row["coverage"] = (
                "NOT_REQUIRED" if not needs
                else "COVERED" if row["collision_enabled"]
                else "MISSING_COLLISION")

        def count(pred) -> int:
            return sum(1 for r in rows if pred(r))

        blocking = [r for r in rows if r.get("classification") == "BLOCKING_STRUCTURE"]
        support = [r for r in rows if r.get("classification") == "SUPPORT_SURFACE"]
        missing = [r for r in rows if r.get("coverage") == "MISSING_COLLISION"]
        unknown = [r for r in rows if r.get("coverage") == "UNKNOWN"]

        rec["floor_z"] = round(floor_z, 3)
        rec["declared"] = {
            "meshes_total": len(rows),
            "support_surfaces": len(support),
            "blocking_structures": len(blocking),
            "non_blocking": count(lambda r: r.get("classification")
                                  == "NON_BLOCKING_VISUAL_GEOMETRY"),
            "decorative": count(lambda r: r.get("classification") == "DECORATIVE"),
            "unknown_bounds": len(unknown),
            "covered": count(lambda r: r.get("coverage") == "COVERED"),
            "missing_collision": len(missing),
            "blocking_coverage_fraction": (
                round(sum(1 for r in blocking if r["collision_enabled"]) / len(blocking), 4)
                if blocking else None),
            "support_coverage_fraction": (
                round(sum(1 for r in support if r["collision_enabled"]) / len(support), 4)
                if support else None),
            "missing_examples": [r["path"] for r in missing[:10]],
        }

        # -- behavioural probe: did the INTENDED object cause the observation? --
        # The first version fired every ray from the world origin along +X and
        # accepted any hit. All 12 probes struck the same wall at an identical
        # 5.9 m while declaring 12 different targets, and all 12 counted as
        # passes. Two defects: the verdict consumed hit existence rather than
        # collider identity, and support targets were starved because the
        # candidate list was "first N collision-enabled prims" in a scene where
        # blockers outnumber floors.
        #
        # Now each probe is aimed so the declared target is necessarily first
        # along the ray -- launched from just outside its own bounds, toward its
        # own centre -- and the verdict requires the returned collider to be
        # that target.
        q = get_physx_scene_query_interface()

        def probe_target(row: dict[str, Any], role: str) -> dict[str, Any]:
            r = cache.ComputeWorldBound(
                stage.GetPrimAtPath(row["path"])).ComputeAlignedRange()
            if r.IsEmpty():
                return {"probe_role": role, "expected_target_prim": row["path"],
                        "verdict": "NO_EVIDENCE", "reason": "target bounds empty"}
            mn, mx = r.GetMin(), r.GetMax()
            cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
            if role == "SUPPORT":
                # Straight down onto the target's own top face.
                origin = [cx, cy, mx[2] + 0.5]
                direction = [0.0, 0.0, -1.0]
                reach = 1.5
            else:
                # In from outside the target's own -X face, toward its centre,
                # so nothing of the target's own scale can be in front of it.
                span = mx[0] - mn[0]
                origin = [mn[0] - max(0.6, span * 0.25), cy, (mn[2] + mx[2]) / 2]
                direction = [1.0, 0.0, 0.0]
                reach = max(0.6, span * 0.25) * 2 + span
            # Reachability preflight. Aiming from outside the target's bounds
            # toward its centre is a large improvement on a shared origin, but it
            # is not a guarantee: rotated, concave, nested, overlapping or
            # instanced colliders can put something else first along the segment.
            # A probe that cannot isolate its target is NON_PROBATIVE, which is a
            # statement about the experiment -- not a failure of the target.
            # A verifier cannot recover causal specificity the experiment never
            # created, so this is checked before the verdict, not after.
            occluders = []
            for other in candidates_for_occlusion:
                if other["path"] == row["path"]:
                    continue
                orr = cache.ComputeWorldBound(
                    stage.GetPrimAtPath(other["path"])).ComputeAlignedRange()
                if orr.IsEmpty():
                    continue
                omn, omx = orr.GetMin(), orr.GetMax()
                # Does the other collider straddle the probe segment ahead of the
                # target, in the two axes the ray does not travel along?
                if role == "SUPPORT":
                    if (omn[0] <= cx <= omx[0] and omn[1] <= cy <= omx[1]
                            and omx[2] > mx[2] and omn[2] < origin[2]):
                        occluders.append(other["path"])
                elif (omn[1] <= cy <= omx[1] and omn[2] <= (mn[2] + mx[2]) / 2 <= omx[2]
                        and omn[0] < mn[0] and omx[0] > origin[0]):
                    occluders.append(other["path"])
            if occluders:
                return {"probe_role": role, "expected_target_prim": row["path"],
                        "probe_reachability_status": "OCCLUDED",
                        "occluders": occluders[:4],
                        "verdict": "NON_PROBATIVE_OCCLUDED",
                        "reason": ("another collider necessarily precedes the declared target "
                                   "along this segment, so the probe cannot interrogate it")}

            res = q.raycast_closest(origin, direction, reach)
            hit = bool(res and res.get("hit"))
            actual = str(res.get("collision", "")) if hit else None
            # Identity, not category: "some wall" is not "this wall".
            match = bool(actual and (actual == row["path"]
                                     or actual.startswith(row["path"])
                                     or row["path"].startswith(actual)))
            return {
                "probe_role": role, "expected_target_prim": row["path"],
                "origin": [round(v, 3) for v in origin], "direction": direction,
                "max_distance": round(reach, 3),
                "actual_hit": hit,
                "actual_collider_prim": actual,
                "actual_distance": round(float(res["distance"]), 4) if hit else None,
                "probe_reachability_status": "REACHABLE",
                "identity_match": match,
                "verdict": ("PASS_CORRECT_CAUSE" if match
                            else "FAIL_WRONG_CAUSE" if hit else "FAIL_NO_HIT"),
            }

        # Stratified quotas: blockers cannot consume support slots, because the
        # rare role is the decision-critical one.
        QUOTA = 8
        sup_c = [r for r in support if r.get("collision_enabled")][:QUOTA]
        blk_c = [r for r in blocking if r.get("collision_enabled")][:QUOTA]
        candidates_for_occlusion = (support + blocking)[:400]
        sup_probes = [probe_target(r, "SUPPORT") for r in sup_c]
        blk_probes = [probe_target(r, "BLOCKING") for r in blk_c]

        def summarise(probes: list[dict[str, Any]], planned: int) -> dict[str, Any]:
            fired = len(probes)
            reachable = sum(1 for p_ in probes
                            if p_.get("probe_reachability_status") == "REACHABLE")
            nonprob = sum(1 for p_ in probes if str(p_["verdict"]).startswith("NON_PROBATIVE"))
            correct = sum(1 for p_ in probes if p_["verdict"] == "PASS_CORRECT_CAUSE")
            wrong = sum(1 for p_ in probes if p_["verdict"] == "FAIL_WRONG_CAUSE")
            dists = [p_.get("actual_distance") for p_ in probes if p_.get("actual_distance")]
            invariant = len(dists) > 2 and len(set(round(d, 2) for d in dists)) == 1
            return {
                "planned": planned, "fired": fired,
                "reachable": reachable, "non_probative": nonprob,
                "correct_target_hits": correct, "wrong_target_hits": wrong,
                "generic_hit_rate": (
                    round(sum(1 for p_ in probes if p_.get("actual_hit")) / fired, 3)
                    if fired else None),
                # The scientifically relevant number, kept separate on purpose.
                "correct_target_hit_rate": round(correct / fired, 3) if fired else None,
                "unexpected_invariance": invariant,
                "review_required": ("REVIEW_REQUIRED_UNEXPECTED_INVARIANCE" if invariant else None),
                # Only reachable probes can carry causal evidence, so the
                # verdict is judged over that subset, and a stratum with no
                # reachable probe is NON_PROBATIVE rather than a pass or a fail.
                "reachable_fraction": round(reachable / fired, 3) if fired else None,
                "min_reachable_fraction": MIN_REACHABLE_FRACTION,
                # Order matters: an unrepresentative sample is disqualified before
                # its contents are judged, so a 1-of-8 result cannot become a
                # scene-level failure claim.
                "verdict": ("NOT_RUN" if planned and not fired
                            else "NO_EVIDENCE" if not fired
                            else "NON_PROBATIVE_SAMPLE"
                            if reachable / fired < MIN_REACHABLE_FRACTION
                            else "REVIEW_REQUIRED_INVARIANCE" if invariant
                            else "PROBATIVE_PASS" if correct == reachable
                            else "CONTRADICTION" if correct and correct < reachable
                            else "PROBATIVE_FAIL"),
                "probes": probes,
            }

        rec["behavioural"] = {
            "contract": ("A probe passes only when the declared target caused the observation. "
                         "Generic activity is not evidence of target-specific correctness."),
            "support": summarise(sup_probes, len(sup_c)),
            "blocking": summarise(blk_probes, len(blk_c)),
        }
        sup_ok = rec["behavioural"]["support"]["verdict"] == "PROBATIVE_PASS"
        blk_ok = rec["behavioural"]["blocking"]["verdict"] == "PROBATIVE_PASS"
        hits = rec["behavioural"]["support"]["correct_target_hits"] + \
            rec["behavioural"]["blocking"]["correct_target_hits"]
        checked = (rec["behavioural"]["support"]["fired"]
                   + rec["behavioural"]["blocking"]["fired"])

        live = Liveness(process_started=True, runtime_started=True,
                        subject_open_attempted=True, subject_open_succeeded=True,
                        measurement_executed=True, artifact_written=True)
        envelopes.append(MeasurementEnvelope(
            measurement="blocking_structures_missing_collision", liveness=live,
            value=len(missing), items_examined=len(blocking) + len(support),
            expected_items=len(blocking) + len(support),
            evidence={"scene_id": args.scene_id}))
        envelopes.append(MeasurementEnvelope(
            measurement="physics_probe_hit_rate", liveness=live,
            value=round(hits / checked, 3) if checked else None,
            items_examined=checked))

        admissible = (
            bool(support) and bool(blocking)
            and (rec["declared"]["support_coverage_fraction"] or 0) >= 0.5
            and (rec["declared"]["blocking_coverage_fraction"] or 0) >= 0.5
            and sup_ok and blk_ok
        )
        # HOLD is not BLOCKED. A scene whose evidence lines disagree, or whose
        # sample cannot support a claim, has not been shown deficient -- the
        # measurement has. Recording it as BLOCKED would attribute an
        # instrumentation failure to the asset.
        states = {rec["behavioural"]["support"]["verdict"],
                  rec["behavioural"]["blocking"]["verdict"]}
        rec["scientific_status"] = (
            "ADMISSIBLE" if admissible
            else "HOLD_CONTRADICTION" if "CONTRADICTION" in states
            else "HOLD_INVARIANCE" if "REVIEW_REQUIRED_INVARIANCE" in states
            else "HOLD_INSUFFICIENT_SAMPLE" if "NON_PROBATIVE_SAMPLE" in states
            else "BLOCKED")
        rec["verdict"] = {
            "physx_traversability_admissible": admissible,
            "reason": ("collision coverage sufficient for support and blocking geometry, and "
                       "the physics scene answers queries"
                       if admissible else
                       "insufficient collision coverage: a PhysX free-space map built here "
                       "would manufacture traversable space where geometry actually blocks"),
        }
        rec["measurements"] = [e.to_json() for e in envelopes]
        rec["rows_sample"] = rows[:40]

        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{args.scene_id}_collision_coverage_audit.json").write_text(
            json.dumps(rec, indent=2) + "\n")

        d = rec["declared"]
        print(f"  meshes {d['meshes_total']}  support {d['support_surfaces']}  "
              f"blocking {d['blocking_structures']}  non-blocking {d['non_blocking']}")
        print(f"  coverage: support {d['support_coverage_fraction']}  "
              f"blocking {d['blocking_coverage_fraction']}  missing {d['missing_collision']}")
        bh = rec["behavioural"]
        print(f"  support probes  {bh['support']['fired']}/{bh['support']['planned']} fired, "
              f"correct-cause {bh['support']['correct_target_hits']} -> {bh['support']['verdict']}")
        print(f"  blocking probes {bh['blocking']['fired']}/{bh['blocking']['planned']} fired, "
              f"correct-cause {bh['blocking']['correct_target_hits']} -> {bh['blocking']['verdict']}")
        print(f"  ADMISSIBLE: {admissible}")
        app.close()
        return 0 if admissible else 1
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        envelopes.append(not_run("blocking_structures_missing_collision", note=rec["error"][:200]))
        rec["measurements"] = [e.to_json() for e in envelopes]
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{args.scene_id}_collision_coverage_audit.json").write_text(
            json.dumps(rec, indent=2) + "\n")
        print(f"FAILED: {rec['error']}", file=sys.stderr)
        app.close()
        return 2


if __name__ == "__main__":
    sys.exit(main())
