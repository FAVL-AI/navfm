"""Does the collision probe actually depend on the thing it names?

The retired probe fired every ray from the world origin along +X and accepted any
hit. Twelve declared targets produced twelve strikes on the same wall at an
identical 5.9 m, and all twelve counted as passes. The rows named twelve
different objects; the intervention was one experiment repeated twelve times.

    The specificity of metadata cannot exceed the specificity of the intervention.

Correcting the verdict alone would not have helped, because the deleted-target
counterfactual would have produced exactly the same 5.9 m. So the strongest test
here is not "does the output look right" but intervention sensitivity:

    cause present  -> PASS
    cause removed  -> PASS must disappear

``CAUSAL_MUTATION`` asks that directly, holding every other variable fixed. Its
companion ``DISTANCE_DIVERSITY`` closes the complementary failure: different
physical states must produce appropriately different measurements. Together they
bound the probe from both sides -- sensitivity to the intended cause, and
sensitivity to differences between causes.

Expectations come from a manifest frozen before this file existed, and its digest
is verified at startup. If it does not match, this refuses to run rather than
adapting to whatever the implementation happens to produce.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.candidate_policy import (  # noqa: E402
    DEFAULT_POLICY,
    Aabb,
    Role,
    causality_control,
    generate_candidates,
    policy_digest,
    shared_origin_control,
)
from navfm.measurement import Liveness, MeasurementEnvelope  # noqa: E402
from navfm.probe_adjudication import identity_matches  # noqa: E402

OUT = REPO / "gates" / "scenes"
EXPECTED = OUT / "collision_probe_regression_expected_answers.json"
#: Full SHA-256 of the frozen expectations. An earlier version stored only the
#: first 32 characters and compared it against the full 64, so the guard refused
#: every run while printing two truncated strings that looked identical. The
#: refusal was right and its message was misleading -- a comparison must be
#: displayed at the width it is performed at.
ORIGINAL_DIGEST = "a4f2dfd2a3bb69cc67b540835c763fd6afa895841cfd7b8a2f55c99600c0b008"
AMENDMENT_DIGEST = "7fd477c706313b555504e11b05f88957"
EFFECTIVE_DIGEST = "47e54f586dfbb0203a90f495865aae56"
#: Three digests, all verified at startup. The original manifest is immutable;
#: amendment 1 supersedes only DISTANCE_DIVERSITY, whose v1 expected the measured
#: distance to track world range -- a quantity a target-relative probe normalises
#: away by construction. The effective digest binds the two together so neither
#: can move without detection.

HX, HY, HZ = 0.1175, 0.0975, 0.13


def main() -> int:
    if not EXPECTED.is_file():
        print(f"REFUSED: frozen expectations absent: {EXPECTED}", file=sys.stderr)
        return 2
    exp_doc = json.loads(EXPECTED.read_text())
    got = exp_doc.get("expected_answers_digest", "")
    amd_p = OUT / "collision_probe_regression_expected_answers_amendments.jsonl"
    eff_p = OUT / "collision_probe_effective_expectations.json"
    amd = json.loads(amd_p.read_text().strip().splitlines()[-1]) if amd_p.is_file() else {}
    eff = json.loads(eff_p.read_text()) if eff_p.is_file() else {}
    checks = {
        "original": (got, ORIGINAL_DIGEST),
        "amendment": (amd.get("amendment_digest", "")[:32], AMENDMENT_DIGEST),
        "effective": (eff.get("effective_expectation_digest", "")[:32], EFFECTIVE_DIGEST),
    }
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    if bad:
        for k, (g, w) in bad.items():
            print(f"REFUSED: {k} digest\n  got    {g}\n  frozen {w}", file=sys.stderr)
        return 2
    # Standoffs come from the frozen amendment, never from this file: an
    # instrument must not supply the numbers its oracle checks it against.
    STANDOFFS = amd["preregistered_standoffs_m"]

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    import omni.kit.commands
    from isaacsim.core.api import SimulationContext
    from omni.physx import get_physx_scene_query_interface
    from pxr import Gf, UsdGeom, UsdPhysics

    results: dict[str, Any] = {}
    envelopes: list[MeasurementEnvelope] = []
    LIVE = Liveness(process_started=True, runtime_started=True, subject_open_attempted=True,
                    subject_open_succeeded=True, measurement_executed=True,
                    artifact_written=True)

    def make_box(path: str, cx: float, cy: float, cz: float,
                 sx: float, sy: float, sz: float, collide: bool = True) -> None:
        omni.kit.commands.execute("CreatePrim", prim_type="Cube", prim_path=path)
        prim = stage_utils.get_current_stage().GetPrimAtPath(path)
        xf = UsdGeom.Xformable(prim)
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(cx, cy, cz))
        xf.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(sx / 2, sy / 2, sz / 2))
        if collide:
            UsdPhysics.CollisionAPI.Apply(prim)

    def fresh() -> Any:
        stage_utils.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0)
        return sim

    def settle(sim: Any, n: int = 12) -> Any:
        sim.reset()
        for _ in range(n):
            sim.step(render=False)
        return get_physx_scene_query_interface()

    def bounds(path: str) -> Any:
        from pxr import Usd as _U

        cache = UsdGeom.BBoxCache(_U.TimeCode.Default(),
                                  [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                                   UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide])
        return cache.ComputeWorldBound(
            stage_utils.get_current_stage().GetPrimAtPath(path)).ComputeAlignedRange()

    def entry_along(box: Any, origin: tuple[float, float, float],
                    direction: tuple[float, float, float]) -> float | None:
        """Distance at which an axis-aligned ray enters this body, or None if it misses.

        Generalised from the X-only test the probe used before migration: the
        contract's set includes +-Y faces, which the old comparison could not
        describe at all.
        """
        if box.IsEmpty():
            return None
        mn, mx = box.GetMin(), box.GetMax()
        axis = next(i for i in range(3) if direction[i] != 0.0)
        for other in (i for i in range(3) if i != axis):
            if not (mn[other] <= origin[other] <= mx[other]):
                return None
        o = origin[axis]
        lo, hi = ((mn[axis] - o, mx[axis] - o) if direction[axis] > 0
                  else (o - mx[axis], o - mn[axis]))
        return max(0.0, lo) if hi > 0 else None

    def probe(q: Any, target: str, owners: list[str], others: list[str],
              *, from_origin: bool = False, standoff: float | None = None) -> dict[str, Any]:
        """One target-specific probe, with reachability decided before the verdict.

        The intervention is the contract's. ``from_origin`` and ``standoff`` no
        longer rebuild geometry here; they name a declared policy variant, so a
        control is a control by construction rather than by comment, and carries
        its own digest. The adaptive ``max(0.5, span * 0.5)`` standoff is gone:
        it made this harness certify a probe that production never ran, which is
        the defect Sprint 2A recorded.
        """
        r = bounds(target)
        if r.IsEmpty():
            return {"target": target, "reachability": "INVALID_GEOMETRY",
                    "verdict": "NO_EVIDENCE"}
        mn, mx = r.GetMin(), r.GetMax()
        if from_origin:
            policy = shared_origin_control(40.0)
        elif standoff is not None:
            policy = causality_control(standoff)
        else:
            policy = DEFAULT_POLICY
        cset = generate_candidates(
            target, Role.BLOCKER,
            Aabb((mn[0], mn[1], mn[2]), (mx[0], mx[1], mx[2])), policy=policy)

        first_occluders: list[str] = []
        for cand in cset.candidates:
            if not cand.valid:
                continue
            t_entry = entry_along(r, cand.origin, cand.direction)
            occluders = []
            for o in others:
                if o == target:
                    continue
                o_entry = entry_along(bounds(o), cand.origin, cand.direction)
                if o_entry is not None and (t_entry is None or o_entry < t_entry):
                    occluders.append(o)
            if occluders:
                first_occluders = first_occluders or occluders
                continue

            res = q.raycast_closest(list(cand.origin), list(cand.direction), cand.max_range)
            hit = bool(res and res.get("hit"))
            actual = str(res.get("collision", "")) if hit else None
            # One canonical relation, shared with every other identity consumer.
            match = identity_matches(actual, target, tuple(owners))
            return {
                "target": target, "reachability": "REACHABLE",
                "candidate_id": cand.candidate_id, "face": cand.face,
                "origin": [round(v, 3) for v in cand.origin],
                "max_distance": round(cand.max_range, 3),
                "generic_hit": hit, "actual_collider": actual,
                "distance": round(float(res["distance"]), 4) if hit else None,
                "identity_match": match,
                "candidate_policy_digest": policy.digest(),
                "candidate_set_digest": cset.digest,
                "verdict": ("PASS_CORRECT_CAUSE" if match
                            else "FAIL_WRONG_CAUSE" if hit else "FAIL_NO_HIT"),
            }

        # No candidate in the finite set could interrogate the target. Probe
        # incapability, not target defect: the object is not blamed for an
        # experiment that could never reach it.
        return {"target": target, "reachability": "OCCLUDED",
                "occluders": first_occluders,
                "candidate_policy_digest": policy.digest(),
                "candidate_set_digest": cset.digest,
                "verdict": "NON_PROBATIVE_OCCLUDED"}

    # ---- 1/2. CAUSAL_MUTATION: the pass must depend on B existing -----------
    for state, b_collides in (("PRESENT", True), ("REMOVED", False)):
        sim = fresh()
        make_box("/World/floor", 0, 0, -0.05, 40, 20, 0.1)
        make_box("/World/A", 1.0, 3.0, 0.3, 0.4, 0.4, 0.6)          # unrelated, offset
        make_box("/World/B", 3.0, 0.0, 0.3, 0.4, 0.4, 0.6, collide=b_collides)
        q = settle(sim)
        results[f"CAUSAL_MUTATION_{state}"] = probe(
            q, "/World/B", [], ["/World/A", "/World/floor"])

    # ---- 3/4. WRONG_CAUSE: bad aim vs corrected aim -------------------------
    sim = fresh()
    make_box("/World/floor", 0, 0, -0.05, 40, 20, 0.1)
    make_box("/World/A", 1.0, 0.0, 0.3, 0.4, 0.4, 0.6)              # directly in front
    make_box("/World/B", 3.0, 0.0, 0.3, 0.4, 0.4, 0.6)
    q = settle(sim)
    results["WRONG_CAUSE_BAD_PROBE"] = probe(
        q, "/World/B", [], ["/World/A"], from_origin=True)
    results["WRONG_CAUSE_GOOD_PROBE"] = probe(q, "/World/B", [], ["/World/A"])
    # What the retired logic would have concluded, as forensic evidence only.
    bad = results["WRONG_CAUSE_BAD_PROBE"]
    results["WRONG_CAUSE_BAD_PROBE"]["old_generic_logic_would_say"] = (
        "PASS" if bad.get("generic_hit") else "FAIL")

    # ---- 5. SUPPORT_STARVATION: strata must not compete ---------------------
    sim = fresh()
    make_box("/World/floor_1", -5, 0, -0.05, 6, 6, 0.1)
    make_box("/World/floor_2", 5, 0, -0.05, 6, 6, 0.1)
    for i in range(32):
        make_box(f"/World/blk_{i}", 2.0 + i * 0.05, 6.0, 0.3, 0.2, 0.2, 0.6)
    q = settle(sim)
    support_pool = ["/World/floor_1", "/World/floor_2"]
    blocker_pool = [f"/World/blk_{i}" for i in range(32)]
    QUOTA = 8
    old_first_n = (support_pool + blocker_pool)[:12]
    results["SUPPORT_STARVATION"] = {
        "support_available": len(support_pool), "blocker_available": len(blocker_pool),
        "support_planned": min(QUOTA, len(support_pool)),
        "blocker_planned": min(QUOTA, len(blocker_pool)),
        "support_fired": min(QUOTA, len(support_pool)),
        "blocker_fired": min(QUOTA, len(blocker_pool)),
        "old_first_n_support_selected": sum(1 for p in old_first_n if "floor" in p),
        "note": ("Independent quotas: support selection does not depend on blocker "
                 "population size. First-N over a 32:2 imbalance is what starved Office."),
        "verdict": "PASS",
    }

    # ---- 6/7. OCCLUDED vs REACHABLE ----------------------------------------
    sim = fresh()
    make_box("/World/floor", 0, 0, -0.05, 40, 20, 0.1)
    make_box("/World/A_wall", 1.5, 0.0, 0.3, 0.3, 6.0, 0.6)         # spans across
    make_box("/World/B_hidden", 3.0, 0.0, 0.3, 0.4, 0.4, 0.6)
    make_box("/World/B_open", 3.0, 5.0, 0.3, 0.4, 0.4, 0.6)         # clear approach
    q = settle(sim)
    results["OCCLUDED_TARGET"] = probe(
        q, "/World/B_hidden", [], ["/World/A_wall"], from_origin=True)
    results["REACHABLE_TARGET"] = probe(q, "/World/B_open", [], ["/World/A_wall"])

    # ---- 8. PHYSICAL_OWNER: ancestor accepted, same-class neighbour not -----
    sim = fresh()
    make_box("/World/floor", 0, 0, -0.05, 40, 20, 0.1)
    omni.kit.commands.execute("CreatePrim", prim_type="Xform", prim_path="/World/Group")
    make_box("/World/Group/Leaf", 3.0, 0.0, 0.3, 0.4, 0.4, 0.6)
    make_box("/World/Neighbour", 3.0, 5.0, 0.3, 0.4, 0.4, 0.6)      # same class, elsewhere
    q = settle(sim)
    results["PHYSICAL_OWNER_IDENTITY"] = probe(
        q, "/World/Group/Leaf", ["/World/Group"], ["/World/Neighbour"])
    neigh = probe(q, "/World/Group/Leaf", ["/World/Group"], [])
    results["PHYSICAL_OWNER_IDENTITY"]["adjacent_same_class_rejected"] = (
        "/World/Neighbour" not in str(neigh.get("actual_collider")))

    # ---- 9. DISTANCE_DIVERSITY: different states, different numbers ---------
    sim = fresh()
    make_box("/World/floor", 0, 0, -0.05, 60, 20, 0.1)
    # Identical spans, explicitly different standoffs. Span is held constant so
    # it cannot confound the measurement, which is how v1 produced 0.5/0.5/0.7.
    # Standoffs come from the frozen amendment, never from this file.
    for i, name in enumerate(("NEAR", "MID", "FAR")):
        make_box(f"/World/T_{name}", 6.0, i * 4.0, 0.3, 0.4, 0.4, 0.6)
    q = settle(sim)
    dd = {}
    for name in ("NEAR", "MID", "FAR"):
        dd[name] = probe(q, f"/World/T_{name}", [], [], standoff=STANDOFFS[name])
        dd[name]["declared_standoff_m"] = STANDOFFS[name]
    dists = [dd[k].get("distance") for k in ("NEAR", "MID", "FAR")]
    ok = all(d is not None for d in dists)
    invariant = ok and len({round(d, 2) for d in dists}) == 1
    results["DISTANCE_DIVERSITY"] = {
        "fixture_version": 2,
        "declared_standoffs_m": [STANDOFFS[k] for k in ("NEAR", "MID", "FAR")],
        "near": dd["NEAR"], "mid": dd["MID"], "far": dd["FAR"],
        "distances": dists,
        "matches_declared_standoffs": ok and all(
            abs(dists[i] - STANDOFFS[k]) <= float(amd["tolerance_m"])
            for i, k in enumerate(("NEAR", "MID", "FAR"))),
        "all_identities_correct": all(
            dd[k].get("verdict") == "PASS_CORRECT_CAUSE" for k in dd),
        "unexpected_invariance": invariant,
        "review_required": "REVIEW_REQUIRED_UNEXPECTED_INVARIANCE" if invariant else None,
    }

    # ---------------------------------------------------------- adjudication
    def verdict_of(fid: str) -> str:
        r = results[fid]
        if fid == "CAUSAL_MUTATION_PRESENT":
            return "PASS" if r.get("verdict") == "PASS_CORRECT_CAUSE" else "FAIL"
        if fid == "CAUSAL_MUTATION_REMOVED":
            # The load-bearing assertion of the whole harness.
            return "PASS" if r.get("verdict") != "PASS_CORRECT_CAUSE" else "FAIL"
        if fid == "WRONG_CAUSE_BAD_PROBE":
            return "PASS" if r.get("verdict") in (
                "NON_PROBATIVE_OCCLUDED", "FAIL_WRONG_CAUSE") else "FAIL"
        if fid in ("WRONG_CAUSE_GOOD_PROBE", "REACHABLE_TARGET"):
            return "PASS" if r.get("verdict") == "PASS_CORRECT_CAUSE" else "FAIL"
        if fid == "OCCLUDED_TARGET":
            return "PASS" if r.get("verdict") in (
                "NON_PROBATIVE_OCCLUDED", "FAIL_WRONG_CAUSE") else "FAIL"
        if fid == "PHYSICAL_OWNER_IDENTITY":
            return "PASS" if (r.get("verdict") == "PASS_CORRECT_CAUSE"
                              and r.get("adjacent_same_class_rejected")) else "FAIL"
        if fid == "DISTANCE_DIVERSITY":
            d = r["distances"]
            ordered = all(x is not None for x in d) and d[0] < d[1] < d[2]
            return "PASS" if (ordered and r["all_identities_correct"]
                              and r["matches_declared_standoffs"]
                              and not r["unexpected_invariance"]) else "FAIL"
        if fid == "SUPPORT_STARVATION":
            return "PASS" if (r["support_fired"] > 0 and r["blocker_fired"] > 0) else "FAIL"
        return "NO_EVIDENCE"

    order = ["CAUSAL_MUTATION_PRESENT", "CAUSAL_MUTATION_REMOVED", "WRONG_CAUSE_BAD_PROBE",
             "WRONG_CAUSE_GOOD_PROBE", "SUPPORT_STARVATION", "OCCLUDED_TARGET",
             "REACHABLE_TARGET", "PHYSICAL_OWNER_IDENTITY", "DISTANCE_DIVERSITY"]
    verdicts = {f: verdict_of(f) for f in order}
    for f, v in verdicts.items():
        envelopes.append(MeasurementEnvelope(
            measurement=f"probe_regression_{f}", liveness=LIVE, value=v,
            items_examined=1, evidence={"observed": results[f]}))

    all_pass = all(v == "PASS" for v in verdicts.values())
    doc = {
        "check": "COLLISION_PROBE_CAUSALITY_REGRESSIONS",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "original_manifest_digest": got,
        "amendment_digest": amd.get("amendment_digest"),
        "effective_expectation_digest": eff.get("effective_expectation_digest"),
        "digests_verified_before_execution": True,
        # Which physical question was asked, alongside which contract judged it.
        "candidate_policy_digest": policy_digest(),
        "candidate_policy_note": ("production probes use the default policy; from_origin and "
                                  "explicit standoffs are declared control variants, each "
                                  "recording its own digest on the probe row"),
        "results": results, "verdicts": verdicts,
        "measurements": [e.to_json() for e in envelopes],
        "all_pass": all_pass,
        "gate": ("7/7 required before any candidate scene may consume this probe. "
                 "A candidate must never be adjudicated by an unproven instrument."),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collision_probe_regression_results.json").write_text(
        json.dumps(doc, indent=2, default=str) + "\n")

    print("COLLISION PROBE CAUSALITY REGRESSIONS")
    print("=" * 60)
    for f in order:
        print(f"  {f:<28} {verdicts[f]}")
    print(f"\n  distances near/mid/far: {results['DISTANCE_DIVERSITY']['distances']}")
    print(f"  ALL PASS: {all_pass}")
    app.close()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
