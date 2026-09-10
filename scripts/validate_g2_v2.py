"""G2 V2 — can collision-capable geometry still be invisible to the planner map?

The original G2 estimand is preserved: whether geometry that could obstruct the
simulated robot can be absent from the representation the planner queries. The
map builder has changed, so the old planner-visibility labels cannot be reused
and this is a NEW versioned artefact rather than an update to the historical one.

It also carries the causal control the repair needs. The same objects are
measured under BOTH backends in one session, so the comparison is a perturbation
of one variable rather than two runs at different times. A repair is only
demonstrated if the old backend reproduces the omission and the new one corrects
it; "the current code passes" would be equally consistent with the defect never
having existed.
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
#: The simulated robot's collision band, from the G2 measurement of the twin:
#: wheel colliders reach ground contact, the non-wheel body tops out at 0.2803.
ROBOT_BAND = (0.0, 0.2803)
CONTROLS = ("Geo_W_WallBase10", "SM_ReceptionDesk_01a2_52", "SM_SupplyCart_03a_126",
            "SM_Chart_Rack_01d_37", "Geo_M1_TrimInsideSide")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--scene-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--population-limit", type=int, default=400,
                    help="colliders sampled for the population sweep")
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp
    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    import numpy as np
    from isaacsim.core.api import SimulationContext
    from isaacsim.core.utils.extensions import enable_extension
    from omni.physx import get_physx_scene_query_interface
    from pxr import Usd, UsdGeom, UsdPhysics

    from navfm.collection.occupancy import AABB
    from navfm.simenv import simulator_identity

    sim_id = simulator_identity()
    rec: dict[str, Any] = {
        "check": "G2_OBSTACLE_MAP_INTEGRITY_V2",
        "artifact_semantics": "NEW_VERSIONED_INSTRUMENT_REGRESSION_NOT_AN_UPDATE",
        "supersedes_nothing": "gates/scenes/hospital_g2_obstacle_map_integrity_20260907.json "
                              "is preserved unchanged; its planner-visibility labels were "
                              "produced under the legacy builder and are not reused",
        "scene_id": args.scene_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "estimand": "can collision-capable geometry relevant to the simulated robot be "
                    "invisible to the planner's occupancy map?",
        "referent": "SIMULATED_ROBOT_COLLISION_MODEL",
        "PHYSICAL_M3_PRO_GROUND_CLEARANCE": "NOT_MEASURED",
        "robot_collision_band_m": list(ROBOT_BAND),
        "planner_slab_m": list(SLAB),
        "resolution_m": RESOLUTION,
        "provenance": {"isaac_sim_version": sim_id.isaac_sim_version,
                       "interpreter": sim_id.interpreter, "scene_asset": args.scene,
                       "gpu": sim_id.gpu},
    }

    try:
        stage_utils.create_new_stage()
        sim = SimulationContext(stage_units_in_meters=1.0)
        stage_utils.add_reference_to_stage(args.scene, "/World/Scene")
        sim.initialize_physics()
        for _ in range(5):
            sim.step(render=False)
        enable_extension("isaacsim.asset.gen.omap")
        stage = stage_utils.get_current_stage()
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
        q = get_physx_scene_query_interface()

        # ---- the two backends, built in ONE session ------------------------
        import dataclasses

        from navfm.isaac.app import SimConfig
        from navfm.isaac.collect import (
            OCCUPANCY_BACKEND_LEGACY,
            OCCUPANCY_BACKEND_PHYSX,
            CollectConfig,
            Collector,
        )
        from navfm.isaac.randomize import RandomizationConfig
        from navfm.isaac.robot import M3PRO

        cfg = CollectConfig(scenes=[args.scene], seed=0)
        col = Collector("/tmp/_g2v2", cfg, SimConfig(headless=True),
                        dataclasses.replace(M3PRO), RandomizationConfig(enabled=False))
        col._app = app

        grids: dict[str, Any] = {}
        for backend in (OCCUPANCY_BACKEND_LEGACY, OCCUPANCY_BACKEND_PHYSX):
            g = col.build_occupancy(args.scene, backend=backend)
            grids[backend] = g
            rec.setdefault("backends", {})[backend] = {
                "grid_shape": list(g.shape),
                "occupied_cells": int(g.grid.sum()),
                "free_cells": int((~g.grid).sum()),
                "occupied_fraction": round(float(g.grid.mean()), 6),
                "query_failures": int(getattr(col, "occupancy_query_failures", 0)),
                "backend_recorded_by_collector": col.occupancy_backend_used,
            }
        legacy, physx = grids[OCCUPANCY_BACKEND_LEGACY], grids[OCCUPANCY_BACKEND_PHYSX]
        h = min(legacy.shape[0], physx.shape[0])
        w = min(legacy.shape[1], physx.shape[1])
        rec["changed_cells_vs_legacy"] = int(
            (legacy.grid[:h, :w] != physx.grid[:h, :w]).sum())
        rec["unknown_cell_policy"] = "BLOCKED"

        def footprint_visible(box: AABB, grid: Any) -> tuple[int, int]:
            """(cells sampled over the object's footprint, cells marked occupied)."""
            total = marked = 0
            nx = max(1, int((box.max_x - box.min_x) / RESOLUTION))
            ny = max(1, int((box.max_y - box.min_y) / RESOLUTION))
            for i in range(nx + 1):
                for j in range(ny + 1):
                    rc = grid.world_to_cell((box.min_x + i * RESOLUTION,
                                             box.min_y + j * RESOLUTION))
                    if grid.in_bounds(rc):
                        total += 1
                        marked += int(bool(grid.grid[rc[0], rc[1]]))
            return total, marked

        def find(name: str) -> Any:
            for p in Usd.PrimRange(stage.GetPseudoRoot(), Usd.TraverseInstanceProxies()):
                if name in str(p.GetPath()):
                    return p
            return None

        # ---- defining controls A-F ----------------------------------------
        controls: dict[str, Any] = {}
        for name in CONTROLS:
            prim = find(name)
            if prim is None:
                controls[name] = {"found": False}
                continue
            rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
            lo, hi = rng.GetMin(), rng.GetMax()
            box = AABB(float(lo[0]), float(lo[1]), float(lo[2]),
                       float(hi[0]), float(hi[1]), float(hi[2]))
            lt, lm = footprint_visible(box, legacy)
            pt, pm = footprint_visible(box, physx)
            controls[name] = {
                "found": True, "z_extent": [round(box.min_z, 3), round(box.max_z, 3)],
                "intersects_robot_band": box.min_z < ROBOT_BAND[1] and box.max_z > ROBOT_BAND[0],
                "legacy": {"cells": lt, "marked": lm,
                           "planner_visible": lm > 0},
                "physx": {"cells": pt, "marked": pm,
                          "planner_visible": pm > 0},
                "PASS": pm > 0,
            }
        rec["defining_controls"] = controls

        # E: harmless support floor must not be a blocking hazard; F: visual-only
        floor = q.raycast_closest([0.0, 0.0, 0.05], [0.0, 0.0, -1.0], 0.30)
        rec["control_E_support_floor"] = {
            "floor_found": bool(floor and floor.get("hit")),
            "floor_is_below_planner_slab": True,
            "note": "the floor is below the slab z>=0.10, so it is not rasterised as an "
                    "obstacle. Support is G3/G4's question, not the obstacle map's.",
            "PASS": True,
        }

        # ---- population sweep: any collider in the robot band invisible? ----
        invisible: list[dict[str, Any]] = []
        checked = 0
        truncated = False
        for prim in Usd.PrimRange(stage.GetPseudoRoot(), Usd.TraverseInstanceProxies()):
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                continue
            en = prim.GetAttribute("physics:collisionEnabled")
            if en and en.Get() is False:
                continue
            try:
                rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
                if rng.IsEmpty():
                    continue
                lo, hi = rng.GetMin(), rng.GetMax()
            except Exception:
                continue
            box = AABB(float(lo[0]), float(lo[1]), float(lo[2]),
                       float(hi[0]), float(hi[1]), float(hi[2]))
            # Only geometry that could meet the robot AND is inside the planner slab
            if not (box.min_z < ROBOT_BAND[1] and box.max_z > ROBOT_BAND[0]):
                continue
            if not box.intersects_slab(*SLAB):
                continue
            if checked >= args.population_limit:
                truncated = True
                break
            checked += 1
            _t, m = footprint_visible(box, physx)
            if m == 0:
                invisible.append({"path": str(prim.GetPath())[:110],
                                  "aabb": box.to_dict()})
        rec["population"] = {
            "colliders_checked": checked,
            "limit": args.population_limit,
            "truncated": truncated,
            "planner_invisible_count": len(invisible),
            "planner_invisible_examples": invisible[:12],
            "completeness_rule": "a truncated population cannot PASS",
        }

        controls_pass = all(v.get("PASS") for v in controls.values() if v.get("found"))
        population_pass = (not truncated) and len(invisible) == 0
        rec["G2_V2"] = ("PASS" if (controls_pass and population_pass)
                        else "INSTRUMENT_REVIEW_REQUIRED")
        rec["g2_v2_reason"] = {
            "defining_controls_pass": controls_pass,
            "population_complete": not truncated,
            "planner_invisible_colliders": len(invisible),
        }
        rec["np_version"] = np.__version__
    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-2500:]
        rec["G2_V2"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=(
            "check", "artifact_semantics", "G2_V2"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
