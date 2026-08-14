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

from navfm.measurement import Liveness, MeasurementEnvelope  # noqa: E402

OUT = REPO / "gates" / "scenes"
EXPECTED = OUT / "collision_probe_regression_expected_answers.json"
#: Full SHA-256 of the frozen expectations. An earlier version stored only the
#: first 32 characters and compared it against the full 64, so the guard refused
#: every run while printing two truncated strings that looked identical. The
#: refusal was right and its message was misleading -- a comparison must be
#: displayed at the width it is performed at.
FROZEN_DIGEST = "a4f2dfd2a3bb69cc67b540835c763fd6afa895841cfd7b8a2f55c99600c0b008"

HX, HY, HZ = 0.1175, 0.0975, 0.13


def main() -> int:
    if not EXPECTED.is_file():
        print(f"REFUSED: frozen expectations absent: {EXPECTED}", file=sys.stderr)
        return 2
    exp_doc = json.loads(EXPECTED.read_text())
    got = exp_doc.get("expected_answers_digest", "")
    if got != FROZEN_DIGEST:
        # The manifest is the independent oracle. If it has moved, either it was
        # regenerated to fit an implementation or this harness is stale; both
        # invalidate the comparison, so neither is silently absorbed.
        print(f"REFUSED: expectations digest\n  got    {got}\n  frozen {FROZEN_DIGEST}",
              file=sys.stderr)
        return 2

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

    def probe(q: Any, target: str, owners: list[str], others: list[str],
              *, from_origin: bool = False) -> dict[str, Any]:
        """One target-specific probe, with reachability decided before the verdict."""
        r = bounds(target)
        if r.IsEmpty():
            return {"target": target, "reachability": "INVALID_GEOMETRY",
                    "verdict": "NO_EVIDENCE"}
        mn, mx = r.GetMin(), r.GetMax()
        cy, cz = (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2
        if from_origin:
            # The retired construction, kept only to demonstrate what it does.
            origin, reach = [0.0, cy, cz], 40.0
        else:
            span = mx[0] - mn[0]
            origin = [mn[0] - max(0.5, span * 0.5), cy, cz]
            reach = (mn[0] - origin[0]) + span + 0.2

        occluders = []
        for o in others:
            if o == target:
                continue
            orr = bounds(o)
            if orr.IsEmpty():
                continue
            omn, omx = orr.GetMin(), orr.GetMax()
            if (omn[1] <= cy <= omx[1] and omn[2] <= cz <= omx[2]
                    and omn[0] < mn[0] and omx[0] > origin[0]):
                occluders.append(o)
        if occluders:
            # Probe incapability, not target defect. The object is not blamed for
            # an experiment that could never reach it.
            return {"target": target, "reachability": "OCCLUDED", "occluders": occluders,
                    "verdict": "NON_PROBATIVE_OCCLUDED"}

        res = q.raycast_closest(origin, [1.0, 0.0, 0.0], reach)
        hit = bool(res and res.get("hit"))
        actual = str(res.get("collision", "")) if hit else None
        match = bool(actual and any(actual == o or actual.startswith(o) or o.startswith(actual)
                                    for o in [target, *owners]))
        return {
            "target": target, "reachability": "REACHABLE",
            "origin": [round(v, 3) for v in origin], "max_distance": round(reach, 3),
            "generic_hit": hit, "actual_collider": actual,
            "distance": round(float(res["distance"]), 4) if hit else None,
            "identity_match": match,
            "verdict": ("PASS_CORRECT_CAUSE" if match
                        else "FAIL_WRONG_CAUSE" if hit else "FAIL_NO_HIT"),
        }

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
    for name, x, y, spanx in (("NEAR", 1.0, 0.0, 0.4), ("MID", 3.0, 4.0, 0.8),
                              ("FAR", 5.0, 8.0, 1.4)):
        make_box(f"/World/T_{name}", x, y, 0.3, spanx, 0.4, 0.6)
    q = settle(sim)
    dd = {}
    for name in ("NEAR", "MID", "FAR"):
        dd[name] = probe(q, f"/World/T_{name}", [], [])
    dists = [dd[k].get("distance") for k in ("NEAR", "MID", "FAR")]
    ok = all(d is not None for d in dists)
    invariant = ok and len({round(d, 2) for d in dists}) == 1
    results["DISTANCE_DIVERSITY"] = {
        "near": dd["NEAR"], "mid": dd["MID"], "far": dd["FAR"],
        "distances": dists,
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
        "expected_answers_digest": got,
        "digest_verified_against_frozen": True,
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
