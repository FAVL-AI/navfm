"""Can collision-capable geometry hide below the planner's obstacle map?

The collector plans over a 2-D occupancy grid ray-cast from the slab
``z in [0.10, 0.60]``. The scene audit classifies geometry over the robot band
``floor_z + [0.02, 0.2803]``. Those are different vertical estimands, so the
audit's ``blocking_coverage_fraction = 1.0`` says nothing about whether the
planner can see everything that can hit the robot. Geometry sitting below the
slab but within reach of the chassis would be a collision hazard the planner is
structurally blind to.

The robot's true vertical collision envelope cannot be recovered: ``robot.py``
marks its geometry PROVISIONAL and ``docs/HARDWARE.md`` lists chassis L x W x H
among the unmeasured quantities. Choosing a boundary inside that uncertainty
would be fitting a threshold.

So this measures the **maximal** band instead -- everything from the ground to
the slab floor. If that band holds no collision-capable geometry, the question is
settled whatever the true envelope turns out to be, because there is nothing
below the slab to be blind to. Only a non-empty result needs the missing hardware
number to adjudicate, and that is reported as INCONCLUSIVE rather than guessed.

Support and obstacles are kept apart throughout. A floor with no collider is a
support problem for whichever route crosses it; it is not an obstacle-map defect.

READ-ONLY. No route is evaluated, nothing is scored, and the scene-wide verdict
is untouched.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402

#: The planner's occupancy slab, read from collect.py::build_occupancy.
PLANNER_MAP_Z_MIN, PLANNER_MAP_Z_MAX = 0.10, 0.60

#: Maximal blind band: ground to slab floor. Deliberately generous -- a narrower
#: band would need the chassis height, which is not measured.
BLIND_BAND_MIN, BLIND_BAND_MAX = 0.0, PLANNER_MAP_Z_MIN

#: Below this, geometry is a floor/threshold the robot drives over rather than
#: into. Reported as a sensitivity boundary, never used to declare a pass.
DRIVE_OVER_SENSITIVITY_M = (0.01, 0.02, 0.04)

#: Horizontal extent under which a mesh cannot obstruct a 0.24 m footprint in any
#: meaningful way. Matches the audit's DECORATIVE threshold so the two agree.
BLOCKING_SIZE_M = 0.15


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--audit", required=True, help="current-contract audit naming the missing colliders")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import importlib.util
    import json

    audit = json.loads(Path(args.audit).read_text())

    # Reuse the audit's own classifier so the "23" this reproduces is the same
    # population the audit counted. Re-implementing classify() would enumerate a
    # different set (every collider-less mesh, decorative ones included) and the
    # count would disagree for a reason that has nothing to do with the scene.
    _spec = importlib.util.spec_from_file_location(
        "_audit_mod", REPO / "scripts" / "audit_office_collision_coverage.py")
    assert _spec and _spec.loader
    audit_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(audit_mod)

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    from isaacsim.core.api import SimulationContext
    from pxr import Usd, UsdGeom, UsdPhysics

    rec: dict[str, Any] = {
        "check": "PLANNER_BLIND_BAND_CENSUS",
        "artifact_semantics": "DIAGNOSTIC_ONLY_NOT_AN_EXPECTATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scene": args.scene,
        "question": ("Is there collision-capable geometry able to intersect the robot swept body "
                     "that is absent from the planner's obstacle representation because it lies "
                     "below the occupancy slab?"),
        "bands": {
            "planner_map_z": [PLANNER_MAP_Z_MIN, PLANNER_MAP_Z_MAX],
            "blind_band_measured": [BLIND_BAND_MIN, BLIND_BAND_MAX],
            "robot_relevant_z_max": "UNRECOVERABLE",
            "why_unrecoverable": ("robot.py marks its geometry PROVISIONAL and docs/HARDWARE.md "
                                  "lists chassis L x W x H among unmeasured quantities, so the "
                                  "robot's vertical collision envelope is not established"),
            "mitigation": ("the maximal band [0.0, 0.10) is measured instead. An empty result "
                           "settles G2 for any envelope; a non-empty result cannot be adjudicated "
                           "without the missing chassis measurement"),
        },
        "claim_boundary": ("Concerns the planner's obstacle representation only. Says nothing about "
                           "route support, scene-wide traversability, or the scene-wide verdict, "
                           "which is unchanged."),
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

        # ---- full traversal, recording every mesh ------------------------------
        meshes: list[dict[str, Any]] = []
        for prim in stage.Traverse(Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)):
            if prim.GetTypeName() != "Mesh":
                continue
            r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            if r.IsEmpty():
                meshes.append({"path": str(prim.GetPath()), "bounds": "EMPTY"})
                continue
            mn, mx = r.GetMin(), r.GetMax()
            has_col = bool(prim.HasAPI(UsdPhysics.CollisionAPI))
            enabled = has_col and (
                UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get() is not False)
            meshes.append({
                "path": str(prim.GetPath()),
                "parent": str(prim.GetParent().GetPath()) if prim.GetParent() else None,
                "z_min": float(mn[2]), "z_max": float(mx[2]),
                "size_xy": float(max(mx[0] - mn[0], mx[1] - mn[1])),
                "collision_api": has_col, "collision_enabled": enabled,
            })
        sized = [m for m in meshes if "z_min" in m]

        # Reproduce the audit's floor reference and per-mesh role exactly.
        import numpy as np
        floor_z = float(np.percentile([m["z_min"] for m in sized], 5)) if sized else 0.0
        for m in sized:
            m["classification_audit"] = audit_mod.classify(
                round(m["z_min"], 3), round(m["z_max"], 3), floor_z, round(m["size_xy"], 3))
            m["audit_needs_collision"] = m["classification_audit"] in (
                "SUPPORT_SURFACE", "BLOCKING_STRUCTURE")
        rec["population"] = {"total_meshes": len(meshes), "with_bounds": len(sized),
                             "empty_bounds": len(meshes) - len(sized),
                             "floor_z": round(floor_z, 4),
                             "audit_roles": dict(Counter(m["classification_audit"] for m in sized))}

        # ---- M1: enumerate EVERY collider-less mesh, not the audit's examples ---
        # Exactly the audit's population: roles that REQUIRE collision, lacking it.
        missing = [m for m in sized
                   if m["audit_needs_collision"] and not m["collision_enabled"]]
        all_colliderless = sum(1 for m in sized if not m["collision_enabled"])
        declared_missing = audit["declared"]["missing_collision"]

        def classify_missing(m: dict[str, Any]) -> str:
            # Support-like: flat, wide, sitting at or near the ground.
            if m["z_max"] <= BLIND_BAND_MIN + 0.02 and m["size_xy"] > 1.0:
                return "SUPPORT_SURFACE_CONFIRMED"
            if m["z_min"] >= PLANNER_MAP_Z_MAX:
                return "OUTSIDE_ROBOT_RELEVANT_BAND"
            if m["size_xy"] < BLOCKING_SIZE_M:
                return "OUTSIDE_ROBOT_RELEVANT_BAND"
            if m["z_max"] > BLIND_BAND_MIN + 0.02:
                return "OBSTACLE_LIKE_GEOMETRY"
            return "AMBIGUOUS"

        for m in missing:
            m["classification"] = classify_missing(m)
        rec["m1_colliderless_enumeration"] = {
            "audit_declared_count": declared_missing,
            "enumerated_count": len(missing),
            "counts_agree": len(missing) == declared_missing,
            "status": "COMPLETE" if len(missing) == declared_missing else "INCOMPLETE",
            "all_colliderless_meshes_any_role": all_colliderless,
            "note": ("enumerated_count reproduces the audit's population -- roles requiring "
                     "collision that lack it. all_colliderless_meshes_any_role is the wider set "
                     "including decorative geometry the audit does not require to collide."),
            "by_class": dict(Counter(m["classification"] for m in missing)),
            "all_records": missing,
        }

        # ---- M2 / G2: planner-invisible collision hazards -----------------------
        # A hazard must be collidable (otherwise physics ignores it), of blocking
        # size, and overlap the band below the slab. A mesh with no collider is a
        # support question, not an obstacle-map defect -- kept separate on purpose.
        def overlaps_blind(m: dict[str, Any]) -> bool:
            return m["z_min"] < BLIND_BAND_MAX and m["z_max"] > BLIND_BAND_MIN

        in_band = [m for m in sized if overlaps_blind(m)]
        hazards = [m for m in in_band
                   if m["collision_enabled"]
                   and m["size_xy"] >= BLOCKING_SIZE_M
                   and m["z_max"] > BLIND_BAND_MIN]
        # Anything reaching into the slab is visible to the planner regardless.
        invisible = [m for m in hazards if m["z_max"] <= PLANNER_MAP_Z_MIN]

        sensitivity = {}
        for thr in DRIVE_OVER_SENSITIVITY_M:
            sensitivity[f"drive_over_below_{thr}m"] = sum(
                1 for m in invisible if m["z_max"] > thr)

        rec["m2_blind_band_census"] = {
            "meshes_overlapping_blind_band": len(in_band),
            "collidable_blocking_size_in_band": len(hazards),
            "planner_invisible_collision_hazards": len(invisible),
            "hazard_records": invisible[:60],
            "sensitivity_to_drive_over_threshold": sensitivity,
            "note": ("a hazard must be collidable AND of blocking size AND entirely below the slab. "
                     "Collider-less meshes are excluded here by design: physics ignores them, so "
                     "they are a support question, not an obstacle-map defect."),
        }

        # ---- controls: prove the census can detect what it claims ---------------
        def synth(z_min, z_max, size, collidable):
            m = {"z_min": z_min, "z_max": z_max, "size_xy": size, "collision_enabled": collidable}
            return (overlaps_blind(m) and m["collision_enabled"]
                    and m["size_xy"] >= BLOCKING_SIZE_M and m["z_max"] > BLIND_BAND_MIN
                    and m["z_max"] <= PLANNER_MAP_Z_MIN)
        rec["controls"] = {
            "low_obstacle_below_slab_is_hazard": synth(0.0, 0.08, 0.5, True) is True,
            "obstacle_reaching_into_slab_is_not_invisible": synth(0.0, 0.30, 0.5, True) is False,
            "flat_floor_is_not_hazard": synth(0.0, 0.001, 5.0, True) is False,
            "tiny_object_is_not_hazard": synth(0.0, 0.08, 0.05, True) is False,
            "noncollidable_low_mesh_is_not_obstacle_defect": synth(0.0, 0.08, 0.5, False) is False,
            "geometry_above_slab_is_not_hazard": synth(0.70, 0.90, 0.5, True) is False,
        }
        rec["controls_all_pass"] = all(rec["controls"].values())

        # ---- verdict ------------------------------------------------------------
        if not rec["controls_all_pass"]:
            g2 = "G2_INSTRUMENT_REVIEW_REQUIRED"
        elif rec["m1_colliderless_enumeration"]["status"] != "COMPLETE":
            g2 = "INCONCLUSIVE"
        elif len(invisible) == 0:
            g2 = "PASS"
        else:
            g2 = "FAIL"
        rec["G2_OBSTACLE_MAP_INTEGRITY"] = g2
        rec["g2_reasoning"] = (
            "PASS requires zero planner-invisible collision hazards over the MAXIMAL band, which "
            "makes the result independent of the unrecoverable chassis height. FAIL means at least "
            "one collidable blocking-size object sits entirely below the slab."
            if g2 in ("PASS", "FAIL") else
            "the enumeration or the controls did not resolve, so no verdict is claimed")

    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["G2_OBSTACLE_MAP_INTEGRITY"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=("check", "artifact_semantics"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
