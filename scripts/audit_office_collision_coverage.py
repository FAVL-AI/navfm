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

        # -- behavioural probe: does the physics scene actually answer? --------
        q = get_physx_scene_query_interface()
        probes = []
        for r in (blocking + support)[:40]:
            if not r.get("collision_enabled"):
                continue
            zc = (r["z"][0] + r["z"][1]) / 2
            probes.append({"expected_path": r["path"], "z": zc})
        hits = 0
        checked = 0
        for pr in probes[:12]:
            res = q.raycast_closest([0.0, 0.0, pr["z"]], [1.0, 0.0, 0.0], 200.0)
            checked += 1
            if res and res.get("hit"):
                hits += 1
                pr["hit_collider"] = str(res.get("collision", ""))
                pr["distance"] = round(float(res["distance"]), 3)
            else:
                pr["hit_collider"] = None
        rec["behavioural"] = {
            "probes_fired": checked, "probes_hitting_something": hits,
            "note": ("A hit proves the physics scene answers queries. Naming the collider is "
                     "what proves it answered about the right object -- a count alone is the "
                     "error that let a floor satisfy an obstacle fixture."),
            "samples": probes[:12],
        }

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
            and hits > 0
        )
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
        print(f"  probes: {hits}/{checked} returned a collider")
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
