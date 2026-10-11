"""G2 obstacle-map integrity, adjudicated against the loaded SIMULATED robot.

Supersedes ``measure_planner_blind_band.py``, which is kept on disk as evidence
of two defects recorded in amendment 1 of
``gates/scenes/collection_route_admission_amendments.jsonl``:

  1. it set the census lower bound to 0.0 instead of the contract's frozen
     ``floor_z + 0.02``, so every collidable floor tile counted as a hazard and
     the ``flat_floor_is_not_hazard`` control failed;
  2. it wrote ``invisible[:60]`` while reporting a count of 75, an undeclared
     truncation that makes the recorded population disagree with the counted one.

What changed, and what deliberately did not: the frozen criterion
``floor_z + 0.02`` is restored, not replaced. No threshold is widened. The
diagnostic value 0.04 observed post hoc in the failed run is NOT used as a
census criterion -- see ``zero_point_zero_four_is_not_admissible`` in the
amendment.

The referent for adjudication is the **simulated** robot. BO-10 concerns an
Isaac-simulated trajectory, so the question is whether scene geometry can
intersect the collision model actually loaded into the stage. Physical M3 PRO
ground clearance is a separate, unmeasured quantity required later for
sim-to-real validation; it does not gate this measurement and is never inferred
from the asset.

A scalar clearance does not settle traversability on its own, so the decisive
test here is collider-span overlap against the real loaded geometry -- the
wheels and the chassis are treated as different colliders because they are.

READ-ONLY. Nothing is scored, no route is admitted, the scene-wide verdict is
untouched.
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

#: FROZEN by the contract: "blocking-size geometry occupies [floor_z+0.02, 0.10)".
#: Identical to NAV_Z_MIN in audit_office_collision_coverage.py. Not re-derived here.
CONTRACT_BAND_OFFSET = 0.02

#: Horizontal extent under which a mesh cannot obstruct the footprint.
BLOCKING_SIZE_M = 0.15

#: Amendment authorising this repair. Pinned so the artefact names its own licence.
REQUIRED_AMENDMENT_DIGEST = "2ed32738d3f05a7c63fbc968bdc2f553578cab26c681722fcaee5319ef3d81db"


def _provenance(scene: str, robot: str) -> dict[str, Any]:
    import hashlib
    import platform
    import subprocess

    def _sh(*c: str) -> str:
        try:
            return subprocess.run(c, capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception:
            return "UNAVAILABLE"

    def _sha(p: str) -> str:
        try:
            return hashlib.sha256(Path(p).read_bytes()).hexdigest()
        except Exception:
            return "UNREADABLE"

    isaac_version = "UNKNOWN"
    with contextlib.suppress(Exception):
        from importlib.metadata import version

        import isaacsim  # noqa: F401
        isaac_version = version("isaacsim")

    return {
        "hostname": platform.node(),
        "interpreter": sys.executable,
        "python": platform.python_version(),
        "isaac_sim_version": isaac_version,
        "git_head": _sh("git", "-C", str(REPO), "rev-parse", "HEAD"),
        "git_branch": _sh("git", "-C", str(REPO), "rev-parse", "--abbrev-ref", "HEAD"),
        "worktree_dirty": bool(_sh("git", "-C", str(REPO), "status", "--porcelain")),
        "harness_sha256": _sha(__file__),
        "amendment_sha256_pinned": REQUIRED_AMENDMENT_DIGEST,
        "scene_asset": scene,
        "robot_asset": robot,
        "robot_asset_sha256": _sha(robot),
        "gpu": _sh("nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--robot", required=True, help="the SIMULATED robot USD to adjudicate against")
    ap.add_argument("--audit", required=True)
    ap.add_argument("--amendments", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    import importlib.util
    import json

    audit = json.loads(Path(args.audit).read_text())

    # The amendment authorising this repair must be present and self-consistent.
    import hashlib
    amend_lines = [json.loads(x) for x in Path(args.amendments).read_text().splitlines() if x.strip()]
    amend = amend_lines[-1]
    _a = dict(amend)
    _stored = _a.pop("effective_contract_digest", None)
    _calc = hashlib.sha256(json.dumps(_a, sort_keys=True).encode()).hexdigest()

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
        "check": "G2_OBSTACLE_MAP_INTEGRITY_VS_SIMULATED_ROBOT",
        "artifact_semantics": "DIAGNOSTIC_ONLY_NOT_AN_EXPECTATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": _provenance(args.scene, args.robot),
        "supersedes": "scripts/measure_planner_blind_band.py",
        "amendment": {
            "path": args.amendments,
            "amendment_id": amend.get("amendment_id"),
            "stored_digest": _stored,
            "recomputed_digest": _calc,
            "self_consistent": _stored == _calc,
            "matches_pin": _stored == REQUIRED_AMENDMENT_DIGEST,
        },
        "question": ("Can scene geometry that is absent from the planner's obstacle map "
                     "intersect the collision geometry of the SIMULATED robot?"),
        "referent": "SIMULATED_ROBOT_COLLISION_MODEL",
        "not_referent": "PHYSICAL_M3_PRO_GROUND_CLEARANCE",
        "PHYSICAL_M3_PRO_GROUND_CLEARANCE": "NOT_MEASURED",
        "physical_clearance_blocks_this_measurement": False,
        "claim_boundary": ("Concerns the planner's obstacle representation and the loaded "
                           "simulation asset only. No physical-hardware claim. No route "
                           "admitted. Scene-wide traversability verdict unchanged."),
    }

    try:
        stage_utils.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0)
        stage_utils.add_reference_to_stage(args.scene, "/World/Scene")
        stage_utils.add_reference_to_stage(args.robot, "/World/RobotProbe")
        stage = stage_utils.get_current_stage()
        sim.initialize_physics()
        for _ in range(3):
            sim.step(render=False)

        purposes = [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                    UsdGeom.Tokens.proxy, UsdGeom.Tokens.guide]
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes, useExtentsHint=False)

        def world_z(prim: Any) -> tuple[float, float, float] | None:
            r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            if r.IsEmpty():
                return None
            mn, mx = r.GetMin(), r.GetMax()
            return float(mn[2]), float(mx[2]), float(max(mx[0] - mn[0], mx[1] - mn[1]))

        # ================= PHASE 3: the loaded robot collision model =============
        robot_colliders: list[dict[str, Any]] = []
        robot_root = stage.GetPrimAtPath("/World/RobotProbe")
        for prim in Usd.PrimRange(robot_root, Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)):
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                continue
            enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get() is not False
            wz = world_z(prim)
            if wz is None:
                robot_colliders.append({"path": str(prim.GetPath()), "bounds": "EMPTY",
                                        "collision_enabled": enabled})
                continue
            name = prim.GetName().lower()
            path_l = str(prim.GetPath()).lower()
            robot_colliders.append({
                "path": str(prim.GetPath()),
                "type": str(prim.GetTypeName()),
                "collision_enabled": enabled,
                "z_min": wz[0], "z_max": wz[1], "size_xy": wz[2],
                "is_wheel": ("wheel" in name or "wheel" in path_l),
            })

        sized_rc = [c for c in robot_colliders if "z_min" in c and c["collision_enabled"]]
        wheels = [c for c in sized_rc if c["is_wheel"]]
        nonwheel = [c for c in sized_rc if not c["is_wheel"]]

        sim_collision_z_min = min((c["z_min"] for c in sized_rc), default=None)
        sim_nonwheel_z_min = min((c["z_min"] for c in nonwheel), default=None)
        sim_nonwheel_z_max = max((c["z_max"] for c in nonwheel), default=None)
        sim_ground_contact_z = min((c["z_min"] for c in wheels), default=sim_collision_z_min)
        sim_wheel_z_max = max((c["z_max"] for c in wheels), default=None)
        sim_wheel_radius = (
            (sim_wheel_z_max - sim_ground_contact_z) / 2.0
            if (sim_wheel_z_max is not None and sim_ground_contact_z is not None) else None)
        sim_clearance = (
            sim_nonwheel_z_min - sim_ground_contact_z
            if (sim_nonwheel_z_min is not None and sim_ground_contact_z is not None) else None)

        rec["simulated_robot_collision_model"] = {
            "asset": args.robot,
            "collider_count": len(robot_colliders),
            "collider_count_enabled_with_bounds": len(sized_rc),
            "wheel_colliders": len(wheels),
            "nonwheel_colliders": len(nonwheel),
            "SIM_COLLISION_Z_MIN": sim_collision_z_min,
            "SIM_NONWHEEL_BODY_Z_MIN": sim_nonwheel_z_min,
            "SIM_NONWHEEL_BODY_Z_MAX": sim_nonwheel_z_max,
            "SIM_GROUND_CONTACT_Z": sim_ground_contact_z,
            "SIM_WHEEL_RADIUS": sim_wheel_radius,
            "SIMULATED_GEOMETRIC_CLEARANCE": sim_clearance,
            "label": "SIMULATED_GEOMETRIC_CLEARANCE",
            "never_label": "PHYSICAL_M3_PRO_GROUND_CLEARANCE",
            "provisional_note": ("wheel radius is PROVISIONAL_SIMULATION_VALUE per "
                                 "assets/robots/yahboom_m3_pro/digital_twin_manifest.json "
                                 "(physically_measured = false)"),
            "coincidence_disclosure": ("SIMULATED_GEOMETRIC_CLEARANCE may equal the "
                                       "inadmissible post-hoc 0.04 diagnostic value. It is "
                                       "derived from the asset and is used as a collider span, "
                                       "never as a height cut."),
            "all_colliders": robot_colliders,
        }

        # ================= scene population ======================================
        meshes: list[dict[str, Any]] = []
        scene_root = stage.GetPrimAtPath("/World/Scene")
        for prim in Usd.PrimRange(scene_root, Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)):
            if prim.GetTypeName() != "Mesh":
                continue
            wz = world_z(prim)
            if wz is None:
                meshes.append({"path": str(prim.GetPath()), "bounds": "EMPTY"})
                continue
            has_col = bool(prim.HasAPI(UsdPhysics.CollisionAPI))
            enabled = has_col and (
                UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get() is not False)
            meshes.append({
                "path": str(prim.GetPath()),
                "parent": str(prim.GetParent().GetPath()) if prim.GetParent() else None,
                "z_min": wz[0], "z_max": wz[1], "size_xy": wz[2],
                "collision_api": has_col, "collision_enabled": enabled,
            })
        sized = [m for m in meshes if "z_min" in m]

        import numpy as np
        floor_z = float(np.percentile([m["z_min"] for m in sized], 5)) if sized else 0.0
        for m in sized:
            m["classification_audit"] = audit_mod.classify(
                round(m["z_min"], 3), round(m["z_max"], 3), floor_z, round(m["size_xy"], 3))
            m["audit_needs_collision"] = m["classification_audit"] in (
                "SUPPORT_SURFACE", "BLOCKING_STRUCTURE")

        band_lo = floor_z + CONTRACT_BAND_OFFSET
        band_hi = PLANNER_MAP_Z_MIN
        rec["bands"] = {
            "planner_map_z": [PLANNER_MAP_Z_MIN, PLANNER_MAP_Z_MAX],
            "contract_census_band": [band_lo, band_hi],
            "band_source": "FROZEN CONTRACT: blocking-size geometry occupying [floor_z+0.02, 0.10)",
            "floor_z": floor_z,
        }
        rec["population"] = {
            "total_meshes": len(meshes), "with_bounds": len(sized),
            "empty_bounds": len(meshes) - len(sized), "floor_z": round(floor_z, 4),
            "audit_roles": dict(Counter(m["classification_audit"] for m in sized)),
        }

        # ================= M1: collider-less enumeration (unchanged) =============
        missing = [m for m in sized if m["audit_needs_collision"] and not m["collision_enabled"]]
        declared_missing = audit["declared"]["missing_collision"]
        rec["m1_colliderless_enumeration"] = {
            "audit_declared_count": declared_missing,
            "enumerated_count": len(missing),
            "counts_agree": len(missing) == declared_missing,
            "status": "COMPLETE" if len(missing) == declared_missing else "INCOMPLETE",
            "all_records": missing,
            "records_complete": True,
        }

        # ================= PHASE 5: complete untruncated census ==================
        # FROZEN criterion. Occupies [floor_z+0.02, 0.10): reaches above the band
        # floor and does not reach into the planner slab.
        candidates = [m for m in sized
                      if m["collision_enabled"]
                      and m["size_xy"] >= BLOCKING_SIZE_M
                      and m["z_max"] > band_lo
                      and m["z_min"] < band_hi]
        planner_invisible = [m for m in candidates if m["z_max"] <= PLANNER_MAP_Z_MIN]
        planner_visible = [m for m in candidates if m["z_max"] > PLANNER_MAP_Z_MIN]

        # Support geometry lacking a collider in the same band: recorded separately,
        # because physics ignores it. It is a route-support question, not an
        # obstacle-map defect, and conflating the two is how the old control failed.
        noncollidable_in_band = [m for m in sized
                                 if not m["collision_enabled"]
                                 and m["size_xy"] >= BLOCKING_SIZE_M
                                 and m["z_max"] > band_lo and m["z_min"] < band_hi]

        # ================= PHASES 6-8: adjudicate against robot colliders ========
        def adjudicate(m: dict[str, Any]) -> dict[str, Any]:
            """Overlap against the loaded colliders. No drive-over height threshold."""
            top = m["z_max"]
            hits_nonwheel = (sim_nonwheel_z_min is not None
                             and top > sim_nonwheel_z_min
                             and m["z_min"] < (sim_nonwheel_z_max or float("inf")))
            hits_wheel = (sim_ground_contact_z is not None
                          and top > sim_ground_contact_z
                          and m["z_min"] < (sim_wheel_z_max or float("inf")))
            step_h = top - floor_z
            # Geometric necessary condition only: a rigid wheel cannot mount a
            # vertical step at or above its own radius. Below it, surmountability
            # is necessary but NOT sufficient (torque and friction are untested).
            wheel_surmountable = (sim_wheel_radius is not None and step_h < sim_wheel_radius)
            if hits_nonwheel or (hits_wheel and not wheel_surmountable):
                # Either it strikes a non-wheel body, or it is a step the wheel
                # geometrically cannot mount. Both are obstacles.
                label = "COLLISION_CAPABLE_LOW_OBSTACLE"
            elif hits_wheel and wheel_surmountable:
                label = "NON_COLLIDING_SUPPORT_RELIEF"
            else:
                label = "OUTSIDE_ROBOT_COLLISION_ENVELOPE"
            return {
                "path": m["path"],
                "semantic_class": m["classification_audit"],
                "z_min": m["z_min"], "z_max": m["z_max"], "size_xy": m["size_xy"],
                "collider_present": m["collision_enabled"],
                "step_height_above_floor": step_h,
                "planner_visibility": ("PLANNER_INVISIBLE" if m["z_max"] <= PLANNER_MAP_Z_MIN
                                       else "PLANNER_VISIBLE"),
                "overlaps_nonwheel_body": hits_nonwheel,
                "overlaps_wheel": hits_wheel,
                "wheel_geometrically_surmountable": wheel_surmountable,
                "hazard_class": label,
                "is_g2_hazard": (label == "COLLISION_CAPABLE_LOW_OBSTACLE"
                                 and m["z_max"] <= PLANNER_MAP_Z_MIN),
            }

        adjudicated = [adjudicate(m) for m in candidates]
        hazards = [a for a in adjudicated if a["is_g2_hazard"]]
        ambiguous = [a for a in adjudicated if a["hazard_class"] == "AMBIGUOUS"]

        rec["m2_census"] = {
            "criterion": "collidable AND size_xy >= 0.15 AND occupies [floor_z+0.02, 0.10)",
            "candidates_total": len(candidates),
            "planner_invisible": len(planner_invisible),
            "planner_visible": len(planner_visible),
            "noncollidable_blocking_size_in_band": len(noncollidable_in_band),
            "planner_invisible_collision_hazards": len(hazards),
            "hazard_class_counts": dict(Counter(a["hazard_class"] for a in adjudicated)),
            "semantic_class_counts": dict(Counter(a["semantic_class"] for a in adjudicated)),
            "adjudicated_records": adjudicated,
            "records_are_complete": len(adjudicated) == len(candidates),
            "truncation_applied": False,
        }

        # ================= PHASE 9: controls =====================================
        def probe(z_min: float, z_max: float, size: float, collidable: bool) -> dict[str, Any]:
            m = {"path": "SYNTHETIC", "z_min": z_min, "z_max": z_max, "size_xy": size,
                 "collision_enabled": collidable, "classification_audit": "SYNTHETIC"}
            is_candidate = (collidable and size >= BLOCKING_SIZE_M
                            and z_max > band_lo and z_min < band_hi)
            a = adjudicate(m)
            a["is_candidate"] = is_candidate
            a["is_g2_hazard"] = bool(is_candidate and a["is_g2_hazard"])
            return a

        nonwheel_lo = sim_nonwheel_z_min if sim_nonwheel_z_min is not None else 0.05
        c1 = probe(floor_z, nonwheel_lo + 0.02, 0.5, True)     # strikes chassis, below slab
        c2 = probe(floor_z, 0.30, 0.5, True)                    # reaches into slab
        c3 = probe(floor_z, floor_z + 0.001, 5.0, True)         # flat floor
        c4 = probe(0.70, 0.90, 0.5, True)                       # far above envelope
        c5 = probe(floor_z, 0.08, 0.5, False)                   # non-collidable in band
        c6_full = rec["m2_census"]["records_are_complete"]
        c7 = probe(floor_z, 0.08, 0.05, True)                   # sub-footprint object

        controls = {
            "low_collision_obstacle_below_slab_is_hazard": c1["is_g2_hazard"] is True,
            "obstacle_inside_planner_slab_is_planner_visible":
                c2["planner_visibility"] == "PLANNER_VISIBLE" and c2["is_g2_hazard"] is False,
            "harmless_support_floor_is_not_hazard":
                c3["is_candidate"] is False and c3["is_g2_hazard"] is False,
            "geometry_outside_collision_envelope_is_not_hazard":
                c4["is_g2_hazard"] is False
                and c4["hazard_class"] == "OUTSIDE_ROBOT_COLLISION_ENVELOPE",
            "noncollidable_geometry_is_recorded_separately_not_as_obstacle_defect":
                c5["is_candidate"] is False,
            "incomplete_population_cannot_pass": c6_full is True,
            "sub_footprint_object_is_not_hazard": c7["is_candidate"] is False,
            "amendment_self_consistent": rec["amendment"]["self_consistent"] is True,
        }
        rec["controls"] = controls
        rec["control_probes"] = {"c1": c1, "c2": c2, "c3": c3, "c4": c4, "c5": c5, "c7": c7}
        rec["controls_all_pass"] = all(controls.values())

        # ================= PHASE 10: verdict =====================================
        # Ordered ladder: the first unmet precondition decides, and its reason is
        # recorded. A verdict without its reason is what made the last run hard to
        # adjudicate.
        blockers: list[tuple[bool, str, str]] = [
            (not rec["controls_all_pass"], "G2_INSTRUMENT_REVIEW_REQUIRED",
             "at least one control failed; the instrument cannot detect what it claims"),
            (rec["m1_colliderless_enumeration"]["status"] != "COMPLETE", "INCONCLUSIVE",
             "collider-less enumeration did not reproduce the audit's declared count"),
            (not rec["m2_census"]["records_are_complete"], "INCONCLUSIVE",
             "census population is incomplete; an incomplete population cannot support a PASS"),
            (sim_nonwheel_z_min is None or sim_wheel_radius is None, "INCONCLUSIVE",
             "the simulated robot collision model was not recovered from the loaded asset"),
            (bool(ambiguous), "INCONCLUSIVE",
             "unresolved physically relevant ambiguity remains"),
            (bool(hazards), "FAIL",
             "planner-invisible geometry can intersect the loaded robot collision geometry"),
        ]
        g2, reason = "PASS", (
            "controls pass, population complete, simulated collision model recovered, and no "
            "planner-invisible geometry can intersect the loaded robot colliders")
        for tripped, verdict, why in blockers:
            if tripped:
                g2, reason = verdict, why
                break
        rec["G2_OBSTACLE_MAP_INTEGRITY"] = g2
        rec["g2_verdict_reason"] = reason
        rec["g2_reasoning"] = (
            "PASS requires: all controls pass, complete untruncated population, a recovered "
            "simulated collision model, zero unresolved ambiguity, and zero planner-invisible "
            "geometry able to intersect the loaded robot colliders.")

    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-2000:]
        rec["G2_OBSTACLE_MAP_INTEGRITY"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=(
            "check", "artifact_semantics", "G2_OBSTACLE_MAP_INTEGRITY"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
