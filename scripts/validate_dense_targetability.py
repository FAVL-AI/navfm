"""Dense-scene regression: the failure class contract 480d9f07 could not contain.

Nine sparse fixtures certified the probe's semantics and none embedded a target
in competing structure, so none could have exposed that geometric reachability
does not imply causal targetability. A fixture suite certifies the conditions it
contains.

These five reproduce that mechanism from first principles. No Hospital path,
prim, distance or observed answer appears anywhere -- Hospital supplied the
mechanism, not the oracle, and ``wrong_1`` is evidence for nothing here.

The load-bearing pair is the same target under two interventions:

    naive long ray   geometrically reachable, NOT causally targetable
    local short ray  geometrically reachable, causally targetable, target hit

Only the intervention changes. That is what makes it a test rather than two
observations.

Two guards keep the new stage honest. The counterfactual disables the target with
the intervention frozen: targetability must be *unchanged* while the observation
changes, since a targetability that moves with the outcome is a renamed outcome.
And the non-isolatable fixture wraps a target in competing shells on every face,
where ``PASS_CORRECT_CAUSE`` is forbidden -- a gate that always finds some working
ray is a search, not an adequacy test.

Structural distinctness is asserted before any query: A and B must share no
collision owner, rigid body or prototype. Without it this would silently become
an identity-mapping test and pass for the wrong reason.
"""

from __future__ import annotations

import hashlib
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
    generate_candidates,
    policy_digest,
    shared_origin_control,
)
from navfm.measurement import Liveness, MeasurementEnvelope  # noqa: E402
from navfm.targetability import (  # noqa: E402
    Interval,
    Targetability,
    TargetabilityInput,
    choose,
)

OUT = REPO / "gates" / "scenes"
PARENT_CONTRACT = "480d9f07770eaf2a95446793639e9aad"
DENSE_EXPECT = "49c5418859e3d6b5850e0018f718eb4a"
AMENDMENT = "6451a1f5cc799d6faebba002b70b5d87"
EFFECTIVE = "03ebdbc0f1c89d87c1b2813de157d1b7"
FIXTURE_COUNT = 5


def main() -> int:
    # ---- frozen provenance, verified before anything is written -------------
    checks = {
        "parent_contract": (json.loads((OUT / "collision_probe_contract.json").read_text())
                            .get("probe_contract_digest", "")[:32], PARENT_CONTRACT),
        "dense_expectations": (json.loads(
            (OUT / "causal_targetability_expected_answers.json").read_text())
            .get("expected_answers_digest", "")[:32], DENSE_EXPECT),
        "amendment": (json.loads(
            (OUT / "causal_targetability_expected_answers_amendments.jsonl")
            .read_text().strip().splitlines()[-1]).get("amendment_digest", "")[:32], AMENDMENT),
        "effective": (json.loads(
            (OUT / "causal_targetability_effective_expectations.json").read_text())
            .get("effective_expectations_digest", "")[:32], EFFECTIVE),
    }
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    if bad:
        for k, (g, w) in bad.items():
            print(f"REFUSED: {k}\n  got    {g}\n  frozen {w}", file=sys.stderr)
        return 2
    parent_doc = json.loads((OUT / "causal_targetability_expected_answers.json").read_text())
    amd_doc = json.loads((OUT / "causal_targetability_expected_answers_amendments.jsonl")
                         .read_text().strip().splitlines()[-1])
    fixtures = {f["fixture_id"]: f for f in
                [*parent_doc["fixtures"], *amd_doc["added_fixtures"]]}
    if len(fixtures) != FIXTURE_COUNT:
        print(f"REFUSED: fixture count {len(fixtures)} != frozen {FIXTURE_COUNT}",
              file=sys.stderr)
        return 2

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    import omni.kit.commands
    from isaacsim.core.api import SimulationContext
    from omni.physx import get_physx_scene_query_interface
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    rec: dict[str, Any] = {
        "check": "DENSE_TARGETABILITY_REGRESSION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "parent_contract_digest": PARENT_CONTRACT,
        "dense_expectations_digest": DENSE_EXPECT,
        "amendment_digest": AMENDMENT,
        "effective_expectations_digest": EFFECTIVE,
        # Provenance the contract digest alone cannot carry: two runs can share a
        # contract and still ask different physical questions.
        "candidate_policy_digest": policy_digest(),
        "candidate_policy_note": ("candidates come from navfm.candidate_policy; the naive "
                                  "fixture requests the retired shared-origin construction "
                                  "as a declared control variant with its own digest"),
        "no_hospital_content": ("No Hospital path, prim, distance or observed answer is used. "
                               "Hospital supplied the mechanism; these fixtures reproduce it "
                               "from first principles. wrong_1 is evidence for nothing here."),
        "fixtures": {},
    }
    envelopes: list[MeasurementEnvelope] = []
    LIVE = Liveness(process_started=True, runtime_started=True, subject_open_attempted=True,
                    subject_open_succeeded=True, measurement_executed=True,
                    artifact_written=True)

    def box(path: str, cx: float, cy: float, cz: float,
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
        return SimulationContext(stage_units_in_meters=1.0)

    def settle(sim: Any) -> Any:
        sim.reset()
        for _ in range(12):
            sim.step(render=False)
        return get_physx_scene_query_interface()

    def bounds(path: str) -> Any:
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                                  [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                                   UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide])
        return cache.ComputeWorldBound(
            stage_utils.get_current_stage().GetPrimAtPath(path)).ComputeAlignedRange()

    def owners(path: str) -> dict[str, Any]:
        stage = stage_utils.get_current_stage()
        prim = stage.GetPrimAtPath(path)
        chain, node = [], prim
        while node and str(node.GetPath()) != "/":
            chain.append(str(node.GetPath()))
            node = node.GetParent()
        return {
            "collision_owner": next((c for c in chain if stage.GetPrimAtPath(c)
                                     and stage.GetPrimAtPath(c).HasAPI(
                                         UsdPhysics.CollisionAPI)), None),
            "rigid_body": next((c for c in chain if stage.GetPrimAtPath(c)
                                and stage.GetPrimAtPath(c).HasAPI(
                                    UsdPhysics.RigidBodyAPI)), None),
            "prototype": (str(prim.GetPrototype().GetPath())
                          if prim and prim.IsInstance() and prim.GetPrototype() else None),
        }

    def structurally_distinct(a: str, b: str) -> dict[str, Any]:
        """All three must differ. If they cannot be established the fixture is
        NO_EVIDENCE, because a targetability test whose A and B share a physical
        owner has quietly become an identity test and would pass wrongly."""
        oa, ob = owners(a), owners(b)
        reasons = []
        if oa["collision_owner"] == ob["collision_owner"]:
            reasons.append("shared collision owner")
        if oa["rigid_body"] is not None and oa["rigid_body"] == ob["rigid_body"]:
            reasons.append("shared rigid body")
        if oa["prototype"] is not None and oa["prototype"] == ob["prototype"]:
            reasons.append("shared prototype")
        return {"a": oa, "b": ob, "distinct": not reasons,
                "violations": reasons,
                "note": "asserted before any query; without it this becomes an identity test"}

    def ray_interval(path: str, origin: tuple[float, float, float],
                     direction: tuple[float, float, float]) -> Interval | None:
        """Where an axis-aligned ray meets this body, or None if it misses.

        The extent along the travel axis alone is not an intersection. An earlier
        version compared only X spans, so the 40x20 m floor registered as
        competing geometry on every ray -- including rays half a metre above it.
        Every local candidate then looked occluded and no target could ever be
        isolated. The ray must actually pass through the body in the two axes it
        does not travel along.

        Generalised from X-only when the shared policy brought the +-Y faces:
        the old helper could not have described a Y-directed candidate at all.
        """
        r = bounds(path)
        if r.IsEmpty():
            return None
        mn, mx = r.GetMin(), r.GetMax()
        axis = next(i for i in range(3) if direction[i] != 0.0)
        for other in (i for i in range(3) if i != axis):
            if not (mn[other] <= origin[other] <= mx[other]):
                return None
        o = origin[axis]
        if direction[axis] > 0:
            lo, hi = mn[axis] - o, mx[axis] - o
        else:
            lo, hi = o - mx[axis], o - mn[axis]
        return Interval(max(0.0, lo), hi) if hi > 0 else None

    def candidates_for(target: str, competitors: list[str], *, naive: bool) -> list[Any]:
        """The contract's intervention set, described for the targetability stage.

        Generation is no longer this script's. It asks navfm.candidate_policy for
        the candidates and only computes what targetability needs on top of them:
        where the ray meets the declared target, and which competitors precede it.
        Those are analyses of a candidate, not choices about one.

        ``naive`` is the retired shared-origin construction, now requested by
        name through a declared control variant instead of being rebuilt inline.
        Its wrongness is the point of the fixture, so it must stay reachable --
        but only deliberately, and only with its own policy digest.
        """
        r = bounds(target)
        if r.IsEmpty():
            return []
        mn, mx = r.GetMin(), r.GetMax()
        box = Aabb((mn[0], mn[1], mn[2]), (mx[0], mx[1], mx[2]))
        policy = shared_origin_control(mx[0] + 0.2) if naive else DEFAULT_POLICY
        out = []
        for cand in generate_candidates(target, Role.BLOCKER, box, policy=policy).candidates:
            if not cand.valid:
                # Not fireable, so not an intervention the gate can choose. It
                # stays in the policy's population and out of this list.
                continue
            ti = ray_interval(target, cand.origin, cand.direction)
            comp = []
            for c in competitors:
                ci = ray_interval(c, cand.origin, cand.direction)
                if ci and ci.enter <= cand.max_range:
                    comp.append((c, ci))
            inside = tuple(c for c, ci in comp if ci.enter <= 0.0 < ci.exit)
            out.append(TargetabilityInput(
                declared_target=target, origin=cand.origin,
                direction=cand.direction, max_range=cand.max_range,
                target_interval=ti, competing=tuple(comp), origin_inside=inside))
        return out

    def fire(q: Any, inp: TargetabilityInput) -> dict[str, Any]:
        res = q.raycast_closest(list(inp.origin), list(inp.direction), inp.max_range)
        hit = bool(res and res.get("hit"))
        actual = str(res.get("collision", "")) if hit else None
        return {"query_fired": True, "generic_hit": hit, "actual_collider": actual,
                "distance": round(float(res["distance"]), 4) if hit else None,
                "identity_match": bool(actual and (actual == inp.declared_target
                                                   or actual.startswith(inp.declared_target)))}

    def validate_ordering(cand: Any, target: str, expect_intercepted_by: str | None
                          ) -> dict[str, Any]:
        """Prove the fixture creates the geometry the expectation assumes.

        A frozen expectation is only meaningful if the physical arrangement that
        makes it true actually existed during execution. A correct verdict from a
        malformed fixture is not a passing regression -- it is the wrong-cause
        failure moved into the fixture world.
        """
        ti = cand.target_interval
        comp = {p: iv for p, iv in cand.competing}
        out = {"target_interval": [ti.enter, ti.exit] if ti else None,
               "competing_intervals": {p: [iv.enter, iv.exit] for p, iv in comp.items()},
               "target_present": ti is not None}
        if expect_intercepted_by:
            iv = comp.get(expect_intercepted_by)
            out["expected_interceptor"] = expect_intercepted_by
            out["interceptor_present"] = iv is not None
            out["ordering_holds"] = bool(ti and iv and iv.enter < ti.enter)
            out["valid"] = bool(out["target_present"] and out["interceptor_present"]
                                and out["ordering_holds"])
            if not out["valid"]:
                out["why_invalid"] = ("the fixture does not create the intended interception; "
                                      "any verdict from it would be accidental")
        else:
            ahead = [p for p, iv in comp.items() if ti and iv.enter < ti.enter]
            out["nothing_ahead_of_target"] = not ahead
            out["bodies_ahead"] = ahead
            out["valid"] = bool(out["target_present"] and not ahead)
            if not out["valid"]:
                out["why_invalid"] = "the local intervention does not actually isolate B"
        return out

    def build_ab(b_collides: bool = True) -> None:
        box("/World/floor", 0, 0, -0.05, 40, 20, 0.1)
        box("/World/A", 2.0, 0.0, 0.5, 0.4, 2.0, 1.0)      # intercepts the naive ray
        box("/World/B", 4.0, 0.0, 0.5, 0.4, 2.0, 1.0, collide=b_collides)

    # ---------------------------------------------------------------- run ----
    def run(fid: str, fn) -> None:
        rec["fixtures"][fid] = fn()
        (OUT / "dense_targetability_evidence").mkdir(parents=True, exist_ok=True)
        (OUT / "dense_targetability_evidence" / f"{fid}.json").write_text(
            json.dumps(rec["fixtures"][fid], indent=2, default=str) + "\n")

    def f_naive() -> dict[str, Any]:
        sim = fresh()
        build_ab()
        q = settle(sim)
        sd = structurally_distinct("/World/A", "/World/B")
        cands = candidates_for("/World/B", ["/World/A", "/World/floor"], naive=True)
        fv = validate_ordering(cands[0], "/World/B", "/World/A") if cands else {"valid": False}
        d = choose(cands)
        digest_before = d.candidate_digest
        decided_at = datetime.now(timezone.utc).isoformat()
        obs = fire(q, cands[0]) if cands else {}
        return {"structural_distinctness": sd, "fixture_validity": fv,
                "geometric_reachability": "REACHABLE",
                "targetability": d.to_json(), "targetability_decided_at": decided_at,
                "candidate_digest_before": digest_before,
                "candidate_digest_after": choose(cands).candidate_digest,
                "observation": obs, "observed_at": datetime.now(timezone.utc).isoformat(),
                "interpretation": ("non-probative: the intervention never isolated B, so the "
                                   "hit on A is not evidence against B")}

    def f_local() -> dict[str, Any]:
        sim = fresh()
        build_ab()
        q = settle(sim)
        cands = candidates_for("/World/B", ["/World/A", "/World/floor"], naive=False)
        d = choose(cands)
        fv = validate_ordering(d.chosen, "/World/B", None) if d.chosen else {"valid": False}
        digest_before = d.candidate_digest
        decided_at = datetime.now(timezone.utc).isoformat()
        obs = fire(q, d.chosen) if d.chosen else {}
        return {"geometric_reachability": "REACHABLE", "targetability": d.to_json(),
                "fixture_validity": fv, "structural_distinctness":
                    structurally_distinct("/World/A", "/World/B"),
                "candidate_digest_before": digest_before,
                "candidate_digest_after": choose(cands).candidate_digest,
                "targetability_decided_at": decided_at, "observation": obs,
                "target_digest": hashlib.sha256(b"/World/B").hexdigest()[:16]}

    def f_unrelated() -> dict[str, Any]:
        sim = fresh()
        build_ab()
        q = settle(sim)
        cands = candidates_for("/World/B", ["/World/A", "/World/floor"], naive=True)
        obs = fire(q, cands[0]) if cands else {}
        sd = structurally_distinct("/World/A", "/World/B")
        return {"observation": obs, "structural_distinctness": sd,
                "unrelated_accepted": bool(obs.get("identity_match")),
                "interpretation": ("A must never be accepted as B; accepting it would turn a "
                                   "visible failure into a silent pass")}

    def f_nonisolatable() -> dict[str, Any]:
        sim = fresh()
        box("/World/floor", 0, 0, -0.05, 40, 20, 0.1)
        box("/World/C", 4.0, 0.0, 0.5, 0.4, 0.4, 0.4)
        for i, (dx, dy) in enumerate(((-0.6, 0.0), (0.6, 0.0), (0.0, -0.6), (0.0, 0.6))):
            box(f"/World/shell_{i}", 4.0 + dx, dy, 0.5, 0.3, 1.6, 1.0)
        settle(sim)
        comp = ["/World/floor", *[f"/World/shell_{i}" for i in range(4)]]
        cands = candidates_for("/World/C", comp, naive=False)
        d = choose(cands)
        return {"geometric_reachability": "REACHABLE", "targetability": d.to_json(),
                "query_fired": False,
                "interpretation": ("shell on every face; a gate that finds a working ray here "
                                   "is searching, not testing adequacy")}

    def f_counterfactual() -> dict[str, Any]:
        out = {}
        for state, collides in (("B_present", True), ("B_disabled", False)):
            sim = fresh()
            build_ab(b_collides=collides)
            q = settle(sim)
            cands = candidates_for("/World/B", ["/World/A", "/World/floor"], naive=False)
            d = choose(cands)
            obs = fire(q, d.chosen) if d.chosen else {}
            out[state] = {"targetability": d.state.value,
                          "candidate_digest": d.candidate_digest, "observation": obs}
        out["targetability_unchanged"] = (
            out["B_present"]["targetability"] == out["B_disabled"]["targetability"])
        out["observation_changed"] = (
            bool(out["B_present"]["observation"].get("identity_match"))
            != bool(out["B_disabled"]["observation"].get("identity_match")))
        out["interpretation"] = ("targetability is a property of the intervention; if it moved "
                                 "with the outcome it would be a renamed outcome")
        return out

    run("DENSE_LONG_RAY_NOT_TARGETABLE", f_naive)
    run("DENSE_LOCAL_RAY_TARGETABLE", f_local)
    run("DENSE_UNRELATED_NOT_ACCEPTED", f_unrelated)
    run("DENSE_NONISOLATABLE_TARGET", f_nonisolatable)
    run("DENSE_TARGET_REMOVED_COUNTERFACTUAL", f_counterfactual)

    # ------------------------------------------------------- adjudication ----
    F = rec["fixtures"]

    def verdict(fid: str) -> str:
        f = F[fid]
        # Fixture validity gates the verdict. A correct answer from a fixture
        # that did not construct the intended physics is not a pass.
        fv = f.get("fixture_validity")
        if fv is not None and not fv.get("valid"):
            return "NO_EVIDENCE"
        sd = f.get("structural_distinctness")
        if sd is not None and not sd.get("distinct"):
            return "NO_EVIDENCE"
        cb, ca = f.get("candidate_digest_before"), f.get("candidate_digest_after")
        if cb is not None and cb != ca:
            return "FAIL"
        if fid == "DENSE_LONG_RAY_NOT_TARGETABLE":
            t = f["targetability"]["causal_targetability"]
            return "PASS" if t != Targetability.TARGET_ISOLATABLE.value else "FAIL"
        if fid == "DENSE_LOCAL_RAY_TARGETABLE":
            return "PASS" if (f["targetability"]["causal_targetability"]
                              == Targetability.TARGET_ISOLATABLE.value
                              and f["observation"].get("identity_match")) else "FAIL"
        if fid == "DENSE_UNRELATED_NOT_ACCEPTED":
            return "PASS" if not f["unrelated_accepted"] else "FAIL"
        if fid == "DENSE_NONISOLATABLE_TARGET":
            return "PASS" if (f["targetability"]["causal_targetability"]
                              != Targetability.TARGET_ISOLATABLE.value) else "FAIL"
        if fid == "DENSE_TARGET_REMOVED_COUNTERFACTUAL":
            return "PASS" if (f["targetability_unchanged"]
                              and f["observation_changed"]) else "FAIL"
        return "NO_EVIDENCE"

    verdicts = {f: verdict(f) for f in F}
    for f, v in verdicts.items():
        envelopes.append(MeasurementEnvelope(
            measurement=f"dense_{f}", liveness=LIVE, value=v, items_examined=1))
    rec["verdicts"] = verdicts
    rec["measurements"] = [e.to_json() for e in envelopes]
    rec["all_pass"] = all(v == "PASS" for v in verdicts.values())
    rec["results_digest"] = hashlib.sha256(
        json.dumps(verdicts, sort_keys=True).encode()).hexdigest()

    (OUT / "dense_targetability_regression_results.json").write_text(
        json.dumps(rec, indent=2, default=str) + "\n")
    print("DENSE TARGETABILITY REGRESSION")
    print("=" * 60)
    for f, v in verdicts.items():
        t = F[f].get("targetability", {})
        print(f"  {f:<38} {v:<5} {t.get('causal_targetability', '')}")
    print(f"\n  ALL PASS: {rec['all_pass']}")
    print(f"  results digest: {rec['results_digest'][:32]}")
    app.close()
    return 0 if rec["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
