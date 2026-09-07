"""Why do eight geometrically reachable Hospital blockers yield zero targetable?

The failure is upstream of every stage that has been examined so far. Selected
and reachable are both 8; targetable is 0; fired, adjudicated and probative are
therefore 0 by construction. No query ran, so no collider identity, hit distance,
residual or adjudication can explain it. The decision is made by
``navfm.targetability`` from geometry alone, before PhysX is consulted.

This extracts the exact pre-query inputs the production audit built, replays the
decision offline, and then ablates competitors to find which one is decisive. The
extraction needs Isaac because it needs the scene's world bounds; everything
after that is pure geometry and runs in-process without another query.

Fidelity over independence, deliberately. The audit's own ``classify`` and
``_ray_iv`` are imported rather than reimplemented, because the question here is
"why did *that* run decide *that*", and a second implementation would answer a
different question. FL-018 warns against a check sharing an implementation with
the thing it verifies -- that applies to verification, and this is a replay. The
replay is checked against the recorded audit states, which is what makes it a
replay rather than a restatement.

DIAGNOSTIC ONLY. No expectation, threshold, semantic or verdict changes, and the
production Hospital artefact is not touched.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.candidate_policy import (  # noqa: E402
    Aabb,
    Role,
    generate_candidates,
    policy_digest,
)
from navfm.evidence import emit_evidence  # noqa: E402
from navfm.targetability import (  # noqa: E402
    Targetability,
    TargetabilityInput,
    choose,
    decide,
)

QUOTA = 8
OCCLUSION_POOL = 400


def _load_audit_helpers():
    """Import the audit module for its helpers. main() is not called."""
    path = REPO / "scripts" / "audit_office_collision_coverage.py"
    spec = importlib.util.spec_from_file_location("_audit_under_diagnosis", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--audit", required=True, help="the audit artefact whose decisions to replay")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    audit = _load_audit_helpers()
    recorded = {
        p["expected_target_prim"]: p
        for p in json.loads(Path(args.audit).read_text())["behavioural"]["blocking"]["probes"]
    }

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    import numpy as np
    from isaacsim.core.api import SimulationContext
    from pxr import Usd, UsdGeom, UsdPhysics

    rec: dict[str, Any] = {
        "check": "BLOCKER_TARGETABILITY_ROOT_CAUSE",
        "artifact_semantics": "DIAGNOSTIC_ONLY_NOT_AN_EXPECTATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scene": args.scene,
        "replays": str(args.audit),
        "candidate_policy_digest": policy_digest(),
        "question": ("Which pre-query geometric condition makes every candidate fail to "
                     "isolate its declared blocker?"),
        "claim_boundary": ("Explains a pre-query decision. Establishes nothing about collider "
                           "identity, wrong_1, scene admissibility, or any verdict."),
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

        # ---- rebuild the audit's rows, by its own rules ----------------------
        rows: list[dict[str, Any]] = []
        zmins: list[float] = []
        for prim in stage.Traverse(Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)):
            if prim.GetTypeName() != "Mesh":
                continue
            r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            if r.IsEmpty():
                rows.append({"path": str(prim.GetPath()), "bounds": "EMPTY"})
                continue
            mn, mx = r.GetMin(), r.GetMax()
            zmins.append(mn[2])
            rows.append({
                "path": str(prim.GetPath()),
                "z": [round(mn[2], 3), round(mx[2], 3)],
                "size": round(max(mx[0] - mn[0], mx[1] - mn[1]), 3),
                "collision_enabled": bool(
                    prim.HasAPI(UsdPhysics.CollisionAPI)
                    and (UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
                         is not False)),
            })
        floor_z = float(np.percentile(zmins, 5)) if zmins else 0.0
        for row in rows:
            if row.get("bounds") == "EMPTY":
                continue
            row["classification"] = audit.classify(row["z"][0], row["z"][1], floor_z, row["size"])

        blocking = [r for r in rows if r.get("classification") == "BLOCKING_STRUCTURE"]
        support = [r for r in rows if r.get("classification") == "SUPPORT_SURFACE"]
        blk_c = [r for r in blocking if r.get("collision_enabled")][:QUOTA]
        pool = (support + blocking)[:OCCLUSION_POOL]
        rec["unit_definition"] = {
            "what_the_eight_are": ("eight declared BLOCKING_STRUCTURE target prims, each with a "
                                   "four-candidate BLOCKER set; not eight candidates"),
            "selection_rule": "first 8 collision-enabled BLOCKING_STRUCTURE rows, audit QUOTA",
            "blocking_rows_total": len(blocking),
            "occlusion_pool_size": len(pool),
            "floor_z": round(floor_z, 3),
        }

        def bounds(path: str):
            rr = cache.ComputeWorldBound(stage.GetPrimAtPath(path)).ComputeAlignedRange()
            return None if rr.IsEmpty() else (rr.GetMin(), rr.GetMax())

        # ---- extract the exact TargetabilityInputs ---------------------------
        units: list[dict[str, Any]] = []
        for row in blk_c:
            b = bounds(row["path"])
            if b is None:
                continue
            mn, mx = b
            cset = generate_candidates(row["path"], Role.BLOCKER,
                                       Aabb((mn[0], mn[1], mn[2]), (mx[0], mx[1], mx[2])))
            inputs: list[TargetabilityInput] = []
            for cand in cset.candidates:
                if not cand.valid:
                    continue
                ti = audit._ray_iv(mn, mx, cand.origin, cand.direction)
                comp = []
                for other in pool:
                    if other["path"] == row["path"]:
                        continue
                    ob = bounds(other["path"])
                    if ob is None:
                        continue
                    oi = audit._ray_iv(ob[0], ob[1], cand.origin, cand.direction)
                    if oi and oi.enter <= cand.max_range:
                        comp.append((other["path"], oi))
                inputs.append(TargetabilityInput(
                    declared_target=row["path"], origin=cand.origin,
                    direction=cand.direction, max_range=cand.max_range,
                    target_interval=ti, competing=tuple(comp),
                    origin_inside=tuple(c for c, ci in comp if ci.enter <= 0.0 < ci.exit)))

            dec = choose(inputs)
            rc = recorded.get(row["path"], {})
            per = []
            for inp in inputs:
                st, why = decide(inp)
                nearer = [(p, i) for p, i in inp.competing
                          if i.precedes(inp.target_interval, inp.isolation_margin)] \
                    if inp.target_interval else []
                strad = [(p, i) for p, i in inp.competing
                         if i.overlaps(inp.target_interval)] if inp.target_interval else []
                per.append({
                    "face_direction": list(inp.direction),
                    "origin": list(inp.origin),
                    "max_range": inp.max_range,
                    "target_interval": ([inp.target_interval.enter, inp.target_interval.exit]
                                        if inp.target_interval else None),
                    "state": st.value, "reason": why,
                    "competitors_total": len(inp.competing),
                    "competitors_nearer": [[p, [i.enter, i.exit]] for p, i in nearer[:5]],
                    "competitors_straddling": [[p, [i.enter, i.exit]] for p, i in strad[:5]],
                    "decisive_competitor": (strad[0][0] if strad else
                                            nearer[0][0] if nearer else None),
                })
            units.append({
                "declared_target": row["path"],
                "candidate_set_digest": cset.digest,
                "candidates_valid": len(inputs),
                "candidates_logical": len(cset.candidates),
                "replay_state": dec.state.value,
                "replay_reason": dec.reason,
                "recorded_state": rc.get("causal_targetability"),
                "recorded_reason": rc.get("targetability_reason"),
                "recorded_candidate_digest": rc.get("candidate_digest"),
                "replay_candidate_digest": dec.candidate_digest,
                "state_match": dec.state.value == rc.get("causal_targetability"),
                "reason_match": dec.reason == rc.get("targetability_reason"),
                "per_candidate": per,
            })
        rec["units"] = units
        rec["replay_all_states_match"] = all(u["state_match"] for u in units)
        rec["replay_all_reasons_match"] = all(u["reason_match"] for u in units)

        # ---- ablation: remove one competitor at a time -----------------------
        # Pure geometry, no query. Each unit is re-decided with the decisive
        # competitor removed, then with every sibling under the same parent prim
        # removed, so "one object" and "this authored wall" are separable.
        ablations = []
        for row, unit in zip(blk_c, units, strict=False):
            b = bounds(row["path"])
            if b is None:
                continue
            mn, mx = b
            cset = generate_candidates(row["path"], Role.BLOCKER,
                                       Aabb((mn[0], mn[1], mn[2]), (mx[0], mx[1], mx[2])))
            base_inputs = []
            for cand in cset.candidates:
                if not cand.valid:
                    continue
                ti = audit._ray_iv(mn, mx, cand.origin, cand.direction)
                comp = []
                for other in pool:
                    if other["path"] == row["path"]:
                        continue
                    ob = bounds(other["path"])
                    if ob is None:
                        continue
                    oi = audit._ray_iv(ob[0], ob[1], cand.origin, cand.direction)
                    if oi and oi.enter <= cand.max_range:
                        comp.append((other["path"], oi))
                base_inputs.append(TargetabilityInput(
                    declared_target=row["path"], origin=cand.origin,
                    direction=cand.direction, max_range=cand.max_range,
                    target_interval=ti, competing=tuple(comp),
                    origin_inside=tuple(c for c, ci in comp if ci.enter <= 0.0 < ci.exit)))

            decisive = next((c["decisive_competitor"] for c in unit["per_candidate"]
                             if c["decisive_competitor"]), None)
            parent = "/".join(row["path"].split("/")[:-1])

            def redecide(drop, _inputs=base_inputs) -> str:
                ins = [replace(i, competing=tuple((p, iv) for p, iv in i.competing if not drop(p)),
                               origin_inside=tuple(c for c in i.origin_inside if not drop(c)))
                       for i in _inputs]
                return choose(ins).state.value

            # Bound as defaults: these close over loop variables, and a late
            # binding would silently ablate the last unit's geometry for every
            # unit while still reporting per-unit results.
            ablations.append({
                "declared_target": row["path"],
                "decisive_competitor": decisive,
                "parent_prim": parent,
                "baseline": choose(base_inputs).state.value,
                "drop_decisive_only": (redecide(lambda p, _d=decisive: p == _d)
                                       if decisive else None),
                "drop_same_parent_siblings": redecide(
                    lambda p, _par=parent: p.startswith(_par + "/")),
                "drop_all_competitors": redecide(lambda p: True),
                "decisive_is_same_parent_sibling": bool(
                    decisive and decisive.startswith(parent + "/")),
            })
        rec["ablations"] = ablations

        # ---- negative controls, synthetic, pure geometry ---------------------
        def synth(target_iv, competing) -> str:
            return decide(TargetabilityInput(
                declared_target="/T", origin=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0),
                max_range=10.0, target_interval=target_iv,
                competing=tuple(competing)))[0].value

        from navfm.targetability import Interval as Iv
        rec["negative_controls"] = {
            "isolated_valid_blocker_is_targetable":
                synth(Iv(1.0, 2.0), []) == Targetability.TARGET_ISOLATABLE.value,
            "straddling_competitor_is_ambiguous":
                synth(Iv(1.0, 2.0), [("/C", Iv(1.5, 2.5))]) == Targetability.TARGET_AMBIGUOUS.value,
            "nearer_competitor_is_occluded":
                synth(Iv(2.0, 3.0), [("/C", Iv(0.5, 1.0))]) == Targetability.TARGET_OCCLUDED.value,
            "no_target_interval_is_invalid_geometry":
                synth(None, []) == Targetability.INVALID_GEOMETRY.value,
            "harmless_far_competitor_does_not_fail":
                synth(Iv(1.0, 2.0), [("/C", Iv(5.0, 6.0))]) == Targetability.TARGET_ISOLATABLE.value,
            "competitor_removed_recovers":
                synth(Iv(1.0, 2.0), []) == Targetability.TARGET_ISOLATABLE.value,
        }

    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=("check", "artifact_semantics"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
