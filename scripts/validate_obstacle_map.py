"""Validate the cell-volume occupancy probe against geometry with known answers.

`OBSTACLE_CELL_OCCUPANCY_V1` defines an occupied cell as one whose full
horizontal area, extruded through the frozen slab, intersects blocking collision
geometry. That is exactly computable for boxes, so this builds real PhysX
colliders at chosen positions and compares the probe's raster with the analytic
one, set against set.

**Aggregate agreement is not accepted as validation.** The previous builder
raised furniture occupancy from 0% to 76% while dropping a known wall from 12.5%
to 0%, and the scene-wide numbers improved. So every fixture reports its false
negatives explicitly, and any false negative on blocking geometry fails the
fixture regardless of how the totals look.

Read-only with respect to production: it builds its own stage, admits no route,
and writes one evidence artefact.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402

RESOLUTION = 0.10
SLAB = (0.10, 0.60)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epsilon", type=float, default=0.0,
                    help="query inflation; frozen at 0.0 unless a tangency false "
                         "negative is demonstrated")
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp
    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    import numpy as np
    from isaacsim.core.api import SimulationContext
    from omni.physx import get_physx_scene_query_interface
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    from navfm.collection.occupancy import (
        AABB,
        compare_cells,
        expected_cells_for_boxes,
        measured_cells_from_grid,
    )
    from navfm.simenv import simulator_identity

    sim_id = simulator_identity()
    rec: dict[str, Any] = {
        "check": "OBSTACLE_CELL_OCCUPANCY_V1_VALIDATION",
        "artifact_semantics": "INSTRUMENT_VALIDATION_NOT_A_SCENE_RESULT",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "estimand": "OCCUPIED(C) iff blocking collision geometry intersects C x Z, "
                    "C the FULL cell area",
        "resolution_m": RESOLUTION,
        "slab_z_m": list(SLAB),
        "query": {"kind": "PhysX overlap_box", "half_extents_m": [RESOLUTION / 2,
                                                                  RESOLUTION / 2,
                                                                  (SLAB[1] - SLAB[0]) / 2],
                  "epsilon_m": args.epsilon, "rotation": "identity"},
        "provenance": {"isaac_sim_version": sim_id.isaac_sim_version,
                       "python": sim_id.python_version,
                       "interpreter": sim_id.interpreter,
                       "gpu": sim_id.gpu},
        "aggregate_rule": "scene-wide agreement is CORROBORATIVE ONLY; a false negative "
                          "on blocking geometry fails the fixture",
        "claim_boundary": "simulated obstacle-map correctness is not physical-robot "
                          "validation; F-TWIN-1 remains OPEN",
    }

    try:
        stage_utils.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0)
        stage = stage_utils.get_current_stage()

        def add_box(path: str, lo: tuple[float, float, float],
                    hi: tuple[float, float, float], *, collider: bool = True,
                    yaw_deg: float = 0.0) -> AABB:
            """A real collidable cube at a chosen world AABB."""
            cube = UsdGeom.Cube.Define(stage, path)
            cube.GetSizeAttr().Set(2.0)  # unit cube spans -1..1
            centre = [(lo[i] + hi[i]) / 2 for i in range(3)]
            scale = [max(1e-6, (hi[i] - lo[i]) / 2) for i in range(3)]
            xf = UsdGeom.Xformable(cube.GetPrim())
            xf.AddTranslateOp().Set(Gf.Vec3d(*centre))
            if yaw_deg:
                xf.AddRotateZOp().Set(yaw_deg)
            xf.AddScaleOp().Set(Gf.Vec3f(*scale))
            if collider:
                UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
            return AABB(lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])

        # World AABBs are MEASURED from USD after construction, never taken from
        # the numbers used to build the prim. An expectation derived from the
        # same literals as the geometry cannot detect a construction mistake, and
        # the instanced fixture is exactly where that bites: its collider lives
        # under a prototype and its world extent is only knowable by resolving
        # the instance.
        def measured_aabb(path: str) -> AABB:
            cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
            prim = stage.GetPrimAtPath(path)
            rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            lo, hi = rng.GetMin(), rng.GetMax()
            return AABB(float(lo[0]), float(lo[1]), float(lo[2]),
                        float(hi[0]), float(hi[1]), float(hi[2]))

        # ---- fixtures, each with an analytically known answer ---------------
        fixtures: dict[str, dict[str, Any]] = {}

        def fixture(name: str, boxes: list[AABB], *, note: str = "",
                    expect_empty: bool = False) -> None:
            fixtures[name] = {"boxes": [b.to_dict() for b in boxes], "note": note,
                              "expect_empty": expect_empty}

        # Every fixture except C is placed CLEAR of cell boundaries. Grid cells
        # are 0.10 m with centres on multiples of 0.10 from the fixture origin,
        # so geometry is offset by a third of a cell. Boundary coincidence makes
        # strict and touch conventions disagree, which confounds a fixture whose
        # subject is something else; C exists to study that case on its own.
        add_box("/W/A", (0.013, 0.013, 0.20), (0.047, 0.047, 0.40))
        fixture("A_box_inside_one_cell", [measured_aabb("/W/A")])

        add_box("/W/B", (1.033, 1.013, 0.20), (1.087, 1.047, 0.40))
        fixture("B_box_crossing_two_cells", [measured_aabb("/W/B")])

        add_box("/W/C", (2.050, 1.633, 0.00), (2.052, 2.367, 3.00))
        fixture("C_wall_on_cell_boundary", [measured_aabb("/W/C")],
                note="boundary tangency is the SUBJECT here; convention decided by measurement")

        add_box("/W/D", (3.023, 1.633, 0.00), (3.047, 2.367, 3.00))
        fixture("D_wall_offset_inside_cell", [measured_aabb("/W/D")])

        add_box("/W/E1", (4.113, 1.633, 0.00), (4.137, 2.367, 3.00))
        add_box("/W/E2", (4.413, 1.633, 0.00), (4.437, 2.367, 3.00))
        fixture("E_hollow_double_face_wall",
                [measured_aabb("/W/E1"), measured_aabb("/W/E2")],
                note="cavity between faces is genuinely empty; enclosure comes from inflation")

        add_box("/W/F", (5.023, 1.023, 0.00), (5.577, 1.277, 1.30))
        fixture("F_furniture_many_cells", [measured_aabb("/W/F")])

        add_box("/W/G", (6.113, 1.113, 0.20), (6.487, 1.187, 0.50), yaw_deg=30.0)
        fixture("G_rotated_obstacle", [measured_aabb("/W/G")],
                note="rotated; the measured AABB over-covers the true shape, so only "
                     "false negatives judge it")

        add_box("/W/H", (7.013, 1.013, 0.00), (7.047, 1.047, 0.15))
        fixture("H_partial_slab_overlap", [measured_aabb("/W/H")])

        add_box("/W/N1", (8.013, 1.013, 0.80), (8.047, 1.047, 1.20))
        fixture("N1_above_slab", [measured_aabb("/W/N1")], expect_empty=True)

        add_box("/W/N2", (9.013, 1.013, 0.00), (9.047, 1.047, 0.05))
        fixture("N2_below_slab", [measured_aabb("/W/N2")], expect_empty=True)

        add_box("/W/N3", (10.013, 1.013, 0.20), (10.287, 1.287, 0.50), collider=False)
        fixture("N3_visual_only_no_collider", [measured_aabb("/W/N3")], expect_empty=True)

        add_box("/W/N4", (12.013, 1.013, 0.20), (12.047, 1.047, 0.50))
        fixture("N4_nearby_obstacle_outside_cell", [measured_aabb("/W/N4")],
                note="a real collider; judged like any blocking fixture, present to show "
                     "that cells NOT containing it stay free")

        # instanced collidable object
        UsdGeom.Xform.Define(stage, "/W/Proto")
        pbox = UsdGeom.Cube.Define(stage, "/W/Proto/Box")
        pbox.GetSizeAttr().Set(2.0)
        pxf = UsdGeom.Xformable(pbox.GetPrim())
        # The prototype is a real prim with a real collider, so it must not sit
        # where a fixture is measured. Left at the default transform it spans
        # +/-0.05 about the world origin and contaminated fixture A, which read
        # as three false positives from the probe when the geometry was mine.
        pxf.AddTranslateOp().Set(Gf.Vec3d(500.0, 500.0, 0.0))
        pxf.AddScaleOp().Set(Gf.Vec3f(0.05, 0.05, 0.25))
        UsdPhysics.CollisionAPI.Apply(pbox.GetPrim())
        inst = UsdGeom.Xform.Define(stage, "/W/Instanced")
        UsdGeom.Xformable(inst.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(11.033, 1.033, 0.35))
        inst.GetPrim().GetReferences().AddInternalReference("/W/Proto")
        inst.GetPrim().SetInstanceable(True)
        fixture("I_instanced_collider", [measured_aabb("/W/Instanced")],
                note="USD instanceable prim; PhysX must still resolve the collider. "
                     "Its AABB is measured through the instance, not assumed.")

        sim.initialize_physics()
        for _ in range(5):
            sim.step(render=False)

        q = get_physx_scene_query_interface()
        eps = float(args.epsilon)
        half = [RESOLUTION / 2 + eps, RESOLUTION / 2 + eps, (SLAB[1] - SLAB[0]) / 2]
        z_mid = (SLAB[0] + SLAB[1]) / 2
        identity = [0.0, 0.0, 0.0, 1.0]

        def raster(origin: tuple[float, float], shape: tuple[int, int]) -> np.ndarray:
            rows, cols = shape
            grid = np.zeros((rows, cols), dtype=bool)
            for r in range(rows):
                y = origin[1] + r * RESOLUTION
                for c in range(cols):
                    x = origin[0] + c * RESOLUTION
                    if q.overlap_box(half, [x, y, z_mid], identity, lambda _h: False, True):
                        grid[r, c] = True
            return grid

        results: dict[str, Any] = {}
        for name, spec in fixtures.items():
            boxes = [AABB(**b) for b in spec["boxes"]]
            bx = min(b.min_x for b in boxes)
            by = min(b.min_y for b in boxes)
            # Offset by a third of a cell. The obvious `bx - 0.25` places every
            # box's minimum exactly 2.5 cells from the origin -- that is, exactly
            # on a cell boundary -- so every fixture became a tangency test and
            # the subject under study was confounded in all of them. C keeps the
            # boundary-aligned origin deliberately, because tangency is its
            # subject.
            shift = 0.0 if name.startswith("C_") else 0.033
            origin = (round(bx - 0.25 - shift, 4), round(by - 0.25 - shift, 4))
            shape = (
                int((max(b.max_y for b in boxes) - by + 0.5) / RESOLUTION) + 2,
                int((max(b.max_x for b in boxes) - bx + 0.5) / RESOLUTION) + 2,
            )
            measured = measured_cells_from_grid(raster(origin, shape))
            strict = expected_cells_for_boxes(boxes, origin, RESOLUTION, shape, slab=SLAB)
            touch = expected_cells_for_boxes(boxes, origin, RESOLUTION, shape, slab=SLAB,
                                             boundary_touch_counts=True)
            if spec["expect_empty"]:
                strict = touch = set()
            cs = compare_cells(strict, measured)
            ct = compare_cells(touch, measured)
            # A rotated box's world AABB strictly over-covers the true rotated
            # shape, so cells inside the AABB but outside the box SHOULD be
            # free. Judging it on "no false negatives against the AABB" was
            # backwards -- it demanded the probe mark cells that contain no
            # geometry. The sound test is containment: every measured cell must
            # lie inside the AABB expectation, and the object must be found at
            # all.
            rotated = name.startswith("G_")
            if rotated:
                passed = bool(measured) and measured <= strict
            else:
                passed = cs.exact_agreement or ct.exact_agreement
            results[name] = {
                "note": spec["note"],
                "origin": list(origin), "shape": list(shape),
                "strict_convention": cs.to_dict(),
                "touch_convention": ct.to_dict(),
                "judged_on": ("containment in the AABB expectation, which over-covers a "
                              "rotated shape") if rotated
                             else "exact set agreement under either boundary convention",
                "PASS": bool(passed),
            }
        rec["fixtures"] = results
        rec["fixtures_passed"] = sum(1 for v in results.values() if v["PASS"])
        rec["fixtures_total"] = len(results)

        blocking = {k: v for k, v in results.items()
                    if not k.startswith("N") and not k.startswith("G_")}
        rec["blocking_false_negatives_total"] = sum(
            v["strict_convention"]["false_negatives"] for v in blocking.values())
        rec["negative_control_false_positives_total"] = sum(
            results[k]["strict_convention"]["false_positives"]
            for k in results if k.startswith("N"))

        boundary = results["C_wall_on_cell_boundary"]
        rec["boundary_convention_measured"] = (
            "TOUCH" if boundary["touch_convention"]["exact_agreement"]
            else ("STRICT" if boundary["strict_convention"]["exact_agreement"]
                  else "UNRESOLVED"))

        all_pass = all(v["PASS"] for v in results.values())
        rec["OBSTACLE_MAP_INTEGRITY"] = "PASS" if all_pass else "INSTRUMENT_REVIEW_REQUIRED"

    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-3000:]
        rec["OBSTACLE_MAP_INTEGRITY"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=(
            "check", "artifact_semantics", "OBSTACLE_MAP_INTEGRITY"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
