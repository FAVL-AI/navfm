"""What evidence would let several authored meshes be declared one physical target?

The eight Hospital blockers are defeated by their own sibling ``SectionN`` meshes,
so the question is whether those sections are components of one wall. That cannot
be answered from path names: ``BP_DoorEntrance_2651`` groups door leaves and glass
panels under one parent, and those are not one physical obstacle. Same parent is
not same owner, and this enumeration must not re-derive that rule by accident.

So every candidate owner/component relation is classified by *independent*
evidence -- collision ownership, rigid-body ownership, semantic labels, explicit
metadata -- and the three weak classes (authoring group, transform parent, naming)
are recorded but never sufficient on their own. The distinction the artefact must
carry is whether ownership is *declared* by the scene or *inferred* by us.

Complete traversal, no sampling: the previous evidence covered 1.9% of the scene,
which is why a counterexample was found by accident rather than by search.

READ-ONLY. The USD is never modified, nothing is scored, and no manifest is
produced. Evidence is persisted before the runtime shuts down.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402

#: Weak classes: recorded, never sufficient alone. Named here so the rule is data
#: rather than a comment a later reader might not reach.
INSUFFICIENT_ALONE = ("AUTHORING_GROUP_ONLY", "TRANSFORM_PARENT_ONLY", "NAMING_ONLY")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    from isaacsim.core.api import SimulationContext
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade

    rec: dict[str, Any] = {
        "check": "PHYSICAL_OWNERSHIP_ENUMERATION",
        "artifact_semantics": "DIAGNOSTIC_ONLY_NOT_AN_EXPECTATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scene": args.scene,
        "sampling": "NONE — complete traversal",
        "claim_boundary": ("Enumerates ownership evidence. Declares no owner, produces no manifest, "
                           "amends nothing and scores no scene."),
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

        # ---- complete traversal ------------------------------------------------
        prims: list[dict[str, Any]] = []
        types: Counter[str] = Counter()
        for prim in stage.Traverse(Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)):
            path = str(prim.GetPath())
            tn = str(prim.GetTypeName())
            types[tn] += 1
            has_col = bool(prim.HasAPI(UsdPhysics.CollisionAPI))
            has_rb = bool(prim.HasAPI(UsdPhysics.RigidBodyAPI))
            # Semantics may be authored as a schema or as customData; check both,
            # because absence in one place is not absence of a declaration.
            sem = None
            for attr in ("semantic:Semantics:params:semanticData",
                         "semantic:Semantics:params:semanticType"):
                a = prim.GetAttribute(attr)
                if a and a.HasAuthoredValue():
                    sem = str(a.Get())
                    break
            cd = prim.GetCustomData() or {}
            owner_meta = next((str(cd[k]) for k in cd
                               if "owner" in k.lower() or "object_id" in k.lower()), None)
            mat = None
            with contextlib.suppress(Exception):
                b = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
                mat = str(b.GetPath()) if b else None
            rec_p: dict[str, Any] = {
                "path": path, "type": tn,
                "parent": str(prim.GetParent().GetPath()) if prim.GetParent() else None,
                "collision_api": has_col, "rigid_body_api": has_rb,
                "instance_proxy": bool(prim.IsInstanceProxy()),
                "semantic": sem, "owner_metadata": owner_meta, "material": mat,
                "has_authored_references": bool(prim.HasAuthoredReferences()),
                "has_payload": bool(prim.HasPayload()),
            }
            if tn == "Mesh":
                r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                rec_p["bounds"] = (None if r.IsEmpty() else
                                   [list(r.GetMin()), list(r.GetMax())])
            prims.append(rec_p)

        meshes = [p for p in prims if p["type"] == "Mesh"]
        rec["completeness"] = {
            "total_prims": len(prims),
            "total_meshes": len(meshes),
            "meshes_with_collision_api": sum(1 for p in meshes if p["collision_api"]),
            "prims_with_rigid_body_api": sum(1 for p in prims if p["rigid_body_api"]),
            "prims_with_semantic_label": sum(1 for p in prims if p["semantic"]),
            "prims_with_owner_metadata": sum(1 for p in prims if p["owner_metadata"]),
            "instance_proxies": sum(1 for p in prims if p["instance_proxy"]),
            "meshes_with_empty_bounds": sum(1 for p in meshes if p.get("bounds") is None),
            "prim_types": dict(types.most_common()),
            "omissions": "none — every prim reachable by TraverseInstanceProxies is recorded",
        }

        # ---- candidate owner relations, classified by evidence -----------------
        by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for m in meshes:
            if m["parent"]:
                by_parent[m["parent"]].append(m)
        groups = {k: v for k, v in by_parent.items() if len(v) > 1}

        def classify(parent: str, children: list[dict[str, Any]]) -> dict[str, Any]:
            ev: list[str] = []
            par = next((p for p in prims if p["path"] == parent), {})
            if any(c["owner_metadata"] for c in children) or par.get("owner_metadata"):
                ev.append("EXPLICIT_OWNER_METADATA")
            if par.get("rigid_body_api"):
                ev.append("SHARED_RIGID_BODY")
            if par.get("collision_api"):
                ev.append("SHARED_COLLISION_OWNER")
            sems = {c["semantic"] for c in children if c["semantic"]}
            if len(sems) == 1 and sems != {None}:
                ev.append("SHARED_SEMANTIC_OBJECT")
            elif len(sems) > 1:
                ev.append("CONFLICTING_EVIDENCE")
            names = {c["path"].rsplit("/", 1)[-1] for c in children}
            if all(n.startswith("Section") for n in names):
                ev.append("NAMING_ONLY")
            ev.append("TRANSFORM_PARENT_ONLY")
            ev.append("AUTHORING_GROUP_ONLY")
            strong = [e for e in ev if e not in INSUFFICIENT_ALONE and e != "CONFLICTING_EVIDENCE"]
            conf = ("DECLARED" if "EXPLICIT_OWNER_METADATA" in ev
                    else "CONFLICTED" if "CONFLICTING_EVIDENCE" in ev
                    else "STRONGLY_SUPPORTED" if strong
                    else "UNSUPPORTED")
            return {"parent": parent, "n_children": len(children),
                    "child_leaf_names": sorted(names)[:6],
                    "evidence": ev, "strong_evidence": strong, "confidence": conf,
                    "ownership_source": "DECLARED_BY_SCENE" if conf == "DECLARED" else "INFERRED_BY_US"}

        classified = [classify(k, v) for k, v in groups.items()]
        rec["candidate_owner_relations"] = {
            "multi_child_parents": len(groups),
            "confidence_distribution": dict(Counter(c["confidence"] for c in classified)),
            "evidence_distribution": dict(Counter(e for c in classified for e in c["strong_evidence"])),
            "declared_by_scene": sum(1 for c in classified if c["ownership_source"] == "DECLARED_BY_SCENE"),
            "inferred_by_us": sum(1 for c in classified if c["ownership_source"] == "INFERRED_BY_US"),
            "sample_records": classified[:40],
        }

        # ---- heuristic generalisation over every multi-child relation ----------
        def heuristic_counts(pred) -> dict[str, int]:
            acc = sum(1 for c in classified if pred(c))
            return {"considered": len(classified), "accepted": acc,
                    "rejected": len(classified) - acc}
        rec["heuristics"] = {
            "same_parent": heuristic_counts(lambda c: True),
            "same_rigid_body": heuristic_counts(lambda c: "SHARED_RIGID_BODY" in c["evidence"]),
            "same_collision_owner": heuristic_counts(lambda c: "SHARED_COLLISION_OWNER" in c["evidence"]),
            "same_semantic_object": heuristic_counts(lambda c: "SHARED_SEMANTIC_OBJECT" in c["evidence"]),
            "explicit_declaration": heuristic_counts(lambda c: "EXPLICIT_OWNER_METADATA" in c["evidence"]),
            "naming_prefix_family": heuristic_counts(lambda c: "NAMING_ONLY" in c["evidence"]),
            "note": ("accepted counts are coverage, not validity. A heuristic is not adopted for "
                     "grouping more relations."),
        }

        # ---- the eight blockers, decomposed ------------------------------------
        blk = [c for c in classified
               if any(n.startswith("Section") for n in c["child_leaf_names"])
               and "Wall" in c["parent"]]
        rec["hospital_wall_decomposition"] = {
            "wall_like_multi_section_parents": len(blk),
            "records": blk[:20],
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
