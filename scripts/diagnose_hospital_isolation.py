"""Can the declared Hospital blocker be isolated in the live PhysX scene?

CollisionAPI reports 1066/1066 Hospital blockers authored. Eight target-specific
probes, all classified REACHABLE, returned 3 correct and 5 wrong-target hits. Two
independent evidence channels disagree, and the disagreement is the result until
its cause is known.

This is diagnosis, not repair. It modifies no probe, no identity rule, no
sampling policy and no asset. The production probe stays exactly as it was while
being diagnosed, because changing it would dissolve the contradiction without
explaining it.

The fork it exists to decide:

    original ray hits the wrong object
            |
    short-range local isolation from several faces
            |
      +-- declared target now hit  -> the instrument could not isolate it (H1)
      |
      +-- still never hit          -> inspect ownership and compound semantics;
                                      an authored/runtime gap stays possible (H3)

The three originally-correct cases run through the identical protocol as
controls. That is the load-bearing part of the design: an explanation that
behaves the same on the 3 correct and the 5 wrong cases has explained neither.
Every hypothesis must discriminate the failures from the controls.

Path strings decide nothing here. ``Section0`` beside ``Section1`` is equally
consistent with one collision shape under a shared owner and with two distinct
shapes where one occludes the other -- opposite conclusions from identical text.
Ownership comes from the USD/PhysX structure or it is recorded UNKNOWN.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.candidate_policy import Aabb, Role, generate_candidates, policy_digest  # noqa: E402
from navfm.measurement import Liveness, MeasurementEnvelope, not_run  # noqa: E402

OUT = REPO / "gates" / "scenes"
CASES = OUT / "hospital_blocker_contradiction_original.json"
HYPO = OUT / "hospital_contradiction_hypotheses.json"
EVIDENCE_DIGEST = "63a63fccec638bbd1e31e5a25e4e8cda"
HYPOTHESES_DIGEST = "12e4359e2a7e03004635dabe7083c284"
SCENE = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com/"
         "Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")

#: The intervention is the contract's, not this script's. Before migration the
#: four faces were built here from a local standoff and margin that happened to
#: equal the policy's -- and happening to equal is not the same as being the
#: same, which is precisely the finding Sprint 2A recorded. The numbers now come
#: from navfm.candidate_policy, so a change there reaches this diagnostic
#: instead of silently diverging from it.


def main() -> int:
    for p, want, name in ((CASES, EVIDENCE_DIGEST, "evidence"),
                          (HYPO, HYPOTHESES_DIGEST, "hypotheses")):
        if not p.is_file():
            print(f"REFUSED: frozen {name} absent", file=sys.stderr)
            return 2
        doc = json.loads(p.read_text())
        got = doc.get("evidence_digest") or doc.get("hypotheses_digest", "")
        if got[:32] != want:
            print(f"REFUSED: {name} digest\n  got    {got}\n  frozen {want}", file=sys.stderr)
            return 2

    frozen = json.loads(CASES.read_text())
    wrong = frozen["wrong_target_cases"]
    correct = frozen["correct_target_cases"]

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})
    rec: dict[str, Any] = {
        "check": "HOSPITAL_BLOCKER_ISOLATION_DIAGNOSIS",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_digest": EVIDENCE_DIGEST, "hypotheses_digest": HYPOTHESES_DIGEST,
        "diagnostic_only": ("No probe, identity rule, sampling policy or asset is modified. "
                            "The production probe is diagnosed as-is."),
        "discrimination_requirement": ("An explanation must separate the 5 wrong cases from "
                                       "the 3 correct controls. One that fits both explains "
                                       "neither."),
        "cases": {},
    }
    envelopes: list[MeasurementEnvelope] = []

    try:
        import isaacsim.core.utils.stage as stage_utils
        from isaacsim.core.api import SimulationContext
        from omni.physx import get_physx_scene_query_interface
        from pxr import Usd, UsdGeom, UsdPhysics

        sim = SimulationContext(stage_units_in_meters=1.0)
        stage_utils.add_reference_to_stage(SCENE, "/World/Scene")
        stage = stage_utils.get_current_stage()
        sim.reset()
        for _ in range(40):
            sim.step(render=False)
        q = get_physx_scene_query_interface()
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                                  [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                                   UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide])
        live = Liveness(process_started=True, runtime_started=True,
                        subject_open_attempted=True, subject_open_succeeded=True,
                        measurement_executed=True, artifact_written=True)

        def ownership(path: str) -> dict[str, Any]:
            """Structure, not names. UNKNOWN when the stage does not say."""
            prim = stage.GetPrimAtPath(path)
            if not prim:
                return {"exists": False}
            chain, node = [], prim
            while node and str(node.GetPath()) != "/":
                chain.append(str(node.GetPath()))
                node = node.GetParent()
            owner = next((c for c in chain
                          if stage.GetPrimAtPath(c)
                          and stage.GetPrimAtPath(c).HasAPI(UsdPhysics.CollisionAPI)), None)
            rb = next((c for c in chain
                       if stage.GetPrimAtPath(c)
                       and stage.GetPrimAtPath(c).HasAPI(UsdPhysics.RigidBodyAPI)), None)
            return {
                "exists": True,
                "has_collision_api": bool(prim.HasAPI(UsdPhysics.CollisionAPI)),
                "collision_enabled": bool(
                    prim.HasAPI(UsdPhysics.CollisionAPI)
                    and UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get() is not False),
                "nearest_collision_owner": owner,
                "nearest_rigid_body": rb,
                "is_instance": bool(prim.IsInstance()),
                "is_instance_proxy": bool(prim.IsInstanceProxy()),
                "prototype": (str(prim.GetPrototype().GetPath())
                              if prim.IsInstance() and prim.GetPrototype() else None),
                "ancestor_chain": chain[:6],
            }

        def relation(target: str, actual: str | None) -> str:
            """Structural relationship between declared and returned prim."""
            if not actual:
                return "NO_HIT"
            if actual == target:
                return "SAME_PRIM"
            to, ao = ownership(target), ownership(actual)
            if to.get("nearest_collision_owner") and \
                    to["nearest_collision_owner"] == ao.get("nearest_collision_owner"):
                return "SHARED_COLLISION_OWNER"
            if to.get("nearest_rigid_body") and \
                    to["nearest_rigid_body"] == ao.get("nearest_rigid_body"):
                return "SHARED_RIGID_BODY"
            if to.get("prototype") and to["prototype"] == ao.get("prototype"):
                return "SHARED_PROTOTYPE"
            return "DISTINCT_OBJECT"

        def local_probes(path: str) -> dict[str, Any]:
            r = cache.ComputeWorldBound(stage.GetPrimAtPath(path)).ComputeAlignedRange()
            if r.IsEmpty():
                return {"bounds": "EMPTY", "directions": []}
            mn, mx = r.GetMin(), r.GetMax()
            cset = generate_candidates(
                path, Role.BLOCKER,
                Aabb((mn[0], mn[1], mn[2]), (mx[0], mx[1], mx[2])))
            out = []
            for cand in cset.candidates:
                if not cand.valid:
                    # A degenerate axis is recorded, never quietly dropped: the
                    # logical population stays four so the set digest remains
                    # comparable across targets.
                    out.append({
                        "direction": cand.face, "candidate_id": cand.candidate_id,
                        "fired": False, "invalid_reason": cand.invalid_reason,
                        "origin": None, "ray": None, "range": None,
                        "hit": None, "actual_collider": None, "distance": None,
                        "relation_to_target": "NOT_FIRED_INVALID_GEOMETRY",
                    })
                    continue
                origin, direction = list(cand.origin), list(cand.direction)
                res = q.raycast_closest(origin, direction, cand.max_range)
                hit = bool(res and res.get("hit"))
                actual = str(res.get("collision", "")) if hit else None
                out.append({
                    "direction": cand.face,
                    "candidate_id": cand.candidate_id,
                    "origin": [round(v, 3) for v in origin],
                    "ray": direction, "range": round(cand.max_range, 3),
                    "fired": True,
                    "hit": hit, "actual_collider": actual,
                    "distance": round(float(res["distance"]), 4) if hit else None,
                    "relation_to_target": relation(path, actual),
                })
            return {"bounds": [[round(v, 3) for v in mn], [round(v, 3) for v in mx]],
                    "candidate_policy_digest": policy_digest(),
                    "candidate_set_digest": cset.digest,
                    "directions": out}

        def classify(path: str, lp: dict[str, Any], own: dict[str, Any]) -> str:
            dirs = [d for d in lp.get("directions", []) if d.get("fired")]
            if not dirs:
                return "UNRESOLVED"
            rels = [d["relation_to_target"] for d in dirs]
            if "SAME_PRIM" in rels:
                return "TARGET_CAUSALLY_ISOLATABLE"
            if any(r in ("SHARED_COLLISION_OWNER", "SHARED_RIGID_BODY", "SHARED_PROTOTYPE")
                   for r in rels):
                return "TARGET_QUERYABLE_ONLY_VIA_OWNER"
            if all(r == "NO_HIT" for r in rels):
                # No shape answered from any local face. Authored yet unqueryable
                # is the H3 signature -- but only if collision really is authored.
                return ("TARGET_RUNTIME_UNQUERYABLE" if own.get("collision_enabled")
                        else "NO_VALID_ISOLATION_DIRECTION")
            return "TARGET_OCCLUDED_BY_NEIGHBOUR"

        for group, cases in (("wrong", wrong), ("correct", correct)):
            for i, case in enumerate(cases):
                tgt = case["expected_target_prim"]
                own = ownership(tgt)
                lp = local_probes(tgt)
                cls = classify(tgt, lp, own)
                pid = f"{group}_{i}"
                rec["cases"][pid] = {
                    "group": group,
                    "declared_target": tgt,
                    "original_actual_collider": case.get("actual_collider_prim"),
                    "original_verdict": case.get("verdict"),
                    "original_relation": relation(tgt, case.get("actual_collider_prim")),
                    "ownership": own,
                    "local_isolation": lp,
                    "causal_targetability": cls,
                }
                (OUT / "hospital_blocker_isolation").mkdir(parents=True, exist_ok=True)
                (OUT / "hospital_blocker_isolation" / f"{pid}.json").write_text(
                    json.dumps(rec["cases"][pid], indent=2) + "\n")

        w = [c for c in rec["cases"].values() if c["group"] == "wrong"]
        k = [c for c in rec["cases"].values() if c["group"] == "correct"]

        def tally(group: list[dict[str, Any]]) -> dict[str, int]:
            out: dict[str, int] = {}
            for c in group:
                out[c["causal_targetability"]] = out.get(c["causal_targetability"], 0) + 1
            return out

        rec["summary"] = {
            "wrong_cases": tally(w), "correct_controls": tally(k),
            "original_relations_wrong": [c["original_relation"] for c in w],
            "original_relations_correct": [c["original_relation"] for c in k],
        }
        # The discriminator is only meaningful if the two groups differ.
        rec["discriminates"] = tally(w) != tally(k)
        envelopes.append(MeasurementEnvelope(
            measurement="hospital_wrong_cases_isolatable", liveness=live,
            value=tally(w).get("TARGET_CAUSALLY_ISOLATABLE", 0), items_examined=len(w),
            expected_items=len(w)))
        rec["measurements"] = [e.to_json() for e in envelopes]
        rec["root_cause"] = "PENDING_ADJUDICATION"
        rec["contradiction_resolved"] = False

        (OUT / "hospital_isolation_diagnosis.json").write_text(
            json.dumps(rec, indent=2) + "\n")
        print("HOSPITAL ISOLATION DIAGNOSIS")
        print("=" * 60)
        print("  wrong cases   :", tally(w))
        print("  correct ctrls :", tally(k))
        print("  original relation, wrong  :", rec["summary"]["original_relations_wrong"])
        print("  original relation, correct:", rec["summary"]["original_relations_correct"])
        print("  discriminates :", rec["discriminates"])
        app.close()
        return 0
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["measurements"] = [not_run("hospital_wrong_cases_isolatable",
                                       note=rec["error"][:200]).to_json()]
        (OUT / "hospital_isolation_diagnosis.json").write_text(json.dumps(rec, indent=2) + "\n")
        print(f"FAILED: {rec['error']}", file=sys.stderr)
        app.close()
        return 2


if __name__ == "__main__":
    sys.exit(main())
