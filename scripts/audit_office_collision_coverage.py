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

from navfm.candidate_policy import Aabb, Role, generate_candidates, policy_digest  # noqa: E402
from navfm.measurement import Liveness, MeasurementEnvelope, not_run  # noqa: E402
from navfm.population import Disposition, build  # noqa: E402
from navfm.probe_adjudication import (  # noqa: E402
    DEFAULT_TOLERANCE_M,
    adjudicate,
    verdict_label,
)
from navfm.targetability import Interval, TargetabilityInput, choose  # noqa: E402


def _ray_iv(mn, mx, origin, direction):
    """Ray/body interval along the travel axis, requiring passage in the other two.

    Generalised from an X-only helper when the contract's set brought the +-Y
    faces and the -Z support probe. The old version could not describe either.
    """
    axis = next(i for i in range(3) if direction[i] != 0.0)
    for other in (i for i in range(3) if i != axis):
        if not (mn[other] <= origin[other] <= mx[other]):
            return None
    o = origin[axis]
    lo, hi = ((mn[axis] - o, mx[axis] - o) if direction[axis] > 0
              else (o - mx[axis], o - mn[axis]))
    return Interval(max(0.0, lo), hi) if hi > 0 else None

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
REQUIRED_CONTRACT_DIGEST = "aa1bdfe9ecb3bbd674f97e6b30614a9f"
#: The effective contract, not the sparse parent. 480d9f07 certified probe
#: semantics in geometry that contained no competing structure, so it could not
#: license a claim about a dense authored scene. Behavioural rows measured under
#: the parent are retired.
#:
#: Repointed 24bf0a8c (amendment 1, causal-targetability) -> ad78a804
#: (amendment 2, reproduced behavioural contract, 8f222b2) -> aa1bdfe9
#: (amendment 3, raw-distance invariance retired for geometry plus identity,
#: 43f407a). Amendment 3 IS a semantic change to how an observation is judged, so
#: unlike amendment 2 the identity move is the point rather than a side effect.
#: The pin
#: stays an explicit frozen literal rather than a value read back from the
#: amendments file: deriving it at runtime would make the check agree with
#: whatever the file currently says, which is the one thing it exists to detect.
#: Amendment 2 changed no intervention semantics -- candidate count, order,
#: origins, directions, standoff, range, targetability, identity adjudication and
#: accounting are all unchanged -- so this is an identity rebind and not a
#: behavioural change. tests/test_office_contract_pin.py proves both directions.

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
    amd_p = OUT / "collision_probe_contract_amendments.jsonl"
    if not amd_p.is_file():
        print("REFUSED: no causal-targetability amendment; the parent contract cannot "
              "license a dense-scene behavioural claim", file=sys.stderr)
        return 2
    contract = json.loads(amd_p.read_text().strip().splitlines()[-1])
    cd = contract.get("effective_contract_digest", "")
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
        # The contract says how an observation is judged; the policy digest says
        # which physical question produced it. A row carrying only the first is
        # incomplete provenance, because two runs can share a contract and still
        # interrogate a target from different places.
        "candidate_policy_digest": policy_digest(),
        "probe_contract_regressions": contract.get("dense_result"),
        "parent_contract_digest": contract.get("parent_contract_digest"),
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

            # The intervention is the contract's. Before migration this function
            # computed a role-specific origin, direction and reach -- a downward
            # probe for SUPPORT, a lateral one for BLOCKING -- and then discarded
            # all three, because the candidate list built below them was X-only
            # and role-blind, and its choice overwrote them. Every SUPPORT target
            # was therefore interrogated edge-on: the audit asked whether a
            # floor's rim obstructs, never whether the floor bears weight. The
            # role now selects the policy role, and the policy decides the
            # geometry, so the two cannot drift apart again.
            policy_role = Role.SUPPORT if role == "SUPPORT" else Role.BLOCKER
            cset = generate_candidates(
                row["path"], policy_role,
                Aabb((mn[0], mn[1], mn[2]), (mx[0], mx[1], mx[2])))

            cands = []
            reachable_geometrically = False
            for cand in cset.candidates:
                if not cand.valid:
                    continue
                ti = _ray_iv(mn, mx, cand.origin, cand.direction)
                if ti is not None:
                    reachable_geometrically = True
                comp = []
                for other in candidates_for_occlusion:
                    if other["path"] == row["path"]:
                        continue
                    orr = cache.ComputeWorldBound(
                        stage.GetPrimAtPath(other["path"])).ComputeAlignedRange()
                    if orr.IsEmpty():
                        continue
                    oi = _ray_iv(orr.GetMin(), orr.GetMax(), cand.origin, cand.direction)
                    if oi and oi.enter <= cand.max_range:
                        comp.append((other["path"], oi))
                cands.append(TargetabilityInput(
                    declared_target=row["path"], origin=cand.origin,
                    direction=cand.direction, max_range=cand.max_range,
                    target_interval=ti, competing=tuple(comp),
                    origin_inside=tuple(c for c, ci in comp if ci.enter <= 0.0 < ci.exit)))

            common = {"probe_role": role, "expected_target_prim": row["path"],
                      "candidate_policy_digest": policy_digest(),
                      "candidate_set_digest": cset.digest}

            # GEOMETRIC_REACHABILITY, before targetability and before any query.
            if not reachable_geometrically:
                return {**common, "probe_reachability_status": "OCCLUDED",
                        "verdict": "NON_PROBATIVE_OCCLUDED",
                        "reason": ("no candidate in the contract's finite set meets the "
                                   "declared target at all, so the probe cannot "
                                   "interrogate it")}

            # CAUSAL_TARGETABILITY, decided before the query. A target that no
            # candidate can isolate is not queried at all, so it can never be
            # recorded as a target failure for an experiment that never reached
            # it -- which is what produced five phantom Hospital wall failures.
            tdec = choose(cands)
            if not tdec.state.probative:
                return {**common, "probe_reachability_status": "REACHABLE",
                        "causal_targetability": tdec.state.value,
                        "targetability_reason": tdec.reason,
                        "candidate_digest": tdec.candidate_digest,
                        "verdict": "NON_PROBATIVE_NOT_TARGETABLE"}

            origin = list(tdec.chosen.origin)
            direction = list(tdec.chosen.direction)
            reach = tdec.chosen.max_range
            res = q.raycast_closest(origin, direction, reach)
            hit = bool(res and res.get("hit"))
            actual = str(res.get("collision", "")) if hit else None
            observed = float(res["distance"]) if hit else None

            # Where the declared target's own geometry says the ray must first
            # meet it. Derived from the candidate and the target bounds, never
            # from the observation -- an expectation computed from the hit would
            # agree with any hit.
            iv = _ray_iv(mn, mx, tdec.chosen.origin, tdec.chosen.direction)
            expected = iv.enter if iv is not None else None

            # Amendment 3: identity AND geometry, neither substituting for the
            # other. The retired rule asked whether raw distances differed across
            # targets, which target-relative construction makes constant for every
            # correct probe -- so it fired on correctness and on the 12x5.9
            # shared-collider defect alike.
            verdict_obj = (
                adjudicate(hit=hit, returned_collider=actual,
                           declared_target=row["path"],
                           observed_distance_m=observed,
                           expected_distance_m=expected,
                           tolerance_m=DEFAULT_TOLERANCE_M)
                if expected is not None else None)
            verdict = "NO_EVIDENCE" if verdict_obj is None else verdict_label(verdict_obj)

            return {
                **common,
                "origin": [round(v, 3) for v in origin], "direction": direction,
                "max_distance": round(reach, 3),
                "actual_hit": hit,
                "actual_collider_prim": actual,
                "actual_distance": round(observed, 4) if observed is not None else None,
                "expected_geometric_distance": (round(expected, 4)
                                                if expected is not None else None),
                "geometric_residual_m": (round(verdict_obj.residual_m, 6)
                                         if verdict_obj is not None
                                         and verdict_obj.residual_m is not None else None),
                "residual_tolerance_m": DEFAULT_TOLERANCE_M,
                "geometry_consistent": (verdict_obj.geometry_ok
                                        if verdict_obj is not None else None),
                "probe_reachability_status": "REACHABLE",
                "causal_targetability": tdec.state.value,
                "candidate_digest": tdec.candidate_digest,
                "identity_match": (verdict_obj.identity_ok
                                   if verdict_obj is not None else False),
                "adjudication": "navfm.probe_adjudication.adjudicate",
                "verdict": verdict,
            }

        # Stratified quotas: blockers cannot consume support slots, because the
        # rare role is the decision-critical one.
        QUOTA = 8
        sup_c = [r for r in support if r.get("collision_enabled")][:QUOTA]
        blk_c = [r for r in blocking if r.get("collision_enabled")][:QUOTA]
        candidates_for_occlusion = (support + blocking)[:400]
        sup_probes = [probe_target(r, "SUPPORT") for r in sup_c]
        blk_probes = [probe_target(r, "BLOCKING") for r in blk_c]

        #: Verdict -> where the probe finally landed. Exactly one disposition per
        #: selected probe, which is what makes the partition checkable. A probe
        #: that fired is PROBATIVE whatever it found: probative means the
        #: experiment could speak, not that it said something welcome.
        _DISPOSITION = {
            "NO_EVIDENCE": Disposition.NO_EVIDENCE,
            "NON_PROBATIVE_OCCLUDED": Disposition.NONPROBATIVE_UNREACHABLE,
            "NON_PROBATIVE_NOT_TARGETABLE": Disposition.NONPROBATIVE_NOT_TARGETABLE,
            "PASS_CORRECT_CAUSE": Disposition.PROBATIVE,
            "FAIL_WRONG_CAUSE": Disposition.PROBATIVE,
            # The experiment spoke and said the geometry disagrees. Probative
            # means the experiment could speak, not that it said something
            # welcome, so this sits beside FAIL_WRONG_CAUSE rather than among
            # the non-probative dispositions.
            "FAIL_GEOMETRY_INCONSISTENT": Disposition.PROBATIVE,
            "FAIL_NO_HIT": Disposition.PROBATIVE,
        }

        def summarise(probes: list[dict[str, Any]], planned: int) -> dict[str, Any]:
            # Populations are sets of probe identities, never counts reconstructed
            # by subtraction. reachable - non_probative once produced -1 here,
            # because the two counted probes surviving different stages: a number
            # no population can have then fed the representativeness gate. A set
            # has no negative cardinality, so that is now unrepresentable rather
            # than guarded against.
            selected: dict[str, Disposition] = {}
            reachable_s: set[str] = set()
            targetable_s: set[str] = set()
            fired_s: set[str] = set()
            for p_ in probes:
                pid = str(p_["expected_target_prim"])
                verdict = str(p_["verdict"])
                selected[pid] = _DISPOSITION[verdict]
                if p_.get("probe_reachability_status") == "REACHABLE":
                    reachable_s.add(pid)
                if verdict not in ("NO_EVIDENCE", "NON_PROBATIVE_OCCLUDED",
                                   "NON_PROBATIVE_NOT_TARGETABLE"):
                    targetable_s.add(pid)
                    fired_s.add(pid)
            pop = build(selected, reachable=reachable_s, targetable=targetable_s,
                        fired=fired_s, adjudicated=fired_s)

            fired = len(probes)
            reachable = len(pop.reachable)
            nonprob = sum(1 for p_ in probes if str(p_["verdict"]).startswith("NON_PROBATIVE"))
            not_targetable = sum(1 for p_ in probes
                                 if p_["verdict"] == "NON_PROBATIVE_NOT_TARGETABLE")
            correct = sum(1 for p_ in probes if p_["verdict"] == "PASS_CORRECT_CAUSE")
            wrong = sum(1 for p_ in probes if p_["verdict"] == "FAIL_WRONG_CAUSE")
            probative = pop.probative_population
            dists = [p_.get("actual_distance") for p_ in probes if p_.get("actual_distance")]
            invariant = len(dists) > 2 and len(set(round(d, 2) for d in dists)) == 1
            return {
                "planned": planned, "fired": fired,
                "reachable": reachable, "non_probative": nonprob,
                "not_targetable": not_targetable,
                "probative_population": probative,
                "accounting": pop.to_json(),
                "correct_target_hits": correct, "wrong_target_hits": wrong,
                "generic_hit_rate": (
                    round(sum(1 for p_ in probes if p_.get("actual_hit")) / fired, 3)
                    if fired else None),
                # The scientifically relevant number, kept separate on purpose.
                "correct_target_hit_rate": round(correct / fired, 3) if fired else None,
                # RETIRED by amendment 3 as NON_IDENTIFIABLE_UNDER_TARGET_RELATIVE_
                # CONSTRUCTION. Retained for provenance comparability with rows
                # measured before the amendment, and deliberately stripped of
                # verdict authority: see the verdict chain below, which no longer
                # consults it.
                "unexpected_invariance": invariant,
                "raw_distance_invariance_diagnostic_only": True,
                "raw_distance_invariance_retired_by": "collision_probe_contract_amendments.jsonl#3",
                "review_required": None,
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
                            if probative / fired < MIN_REACHABLE_FRACTION
                            else "PROBATIVE_PASS" if correct == probative
                            else "CONTRADICTION" if correct and correct < probative
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
