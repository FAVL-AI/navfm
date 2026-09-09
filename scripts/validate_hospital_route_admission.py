"""Route admission for Hospital: G3, G4, G5, G6 and G10 in one read-only pass.

Generates candidate routes with the production planner, then tests each against
the frozen collection contract. Nothing is driven, nothing is written as a
trajectory, and no route is admitted here -- this decides which route *may* be
collected.

Two things it deliberately refuses to do:

* **No hand-picked route.** Candidates come from ``sample_episode_pair`` under a
  declared seed and a declared budget. Every candidate is recorded, including
  the rejected ones and the reason each was rejected. Searching until something
  passes, and reporting only that, is how a route gets selected for the property
  being measured.
* **No centreline-only support test.** Support is sampled across the swept
  footprint disc, because a robot that straddles the edge of a floor slab has a
  supported centreline and an unsupported wheel.

The frozen thresholds are PREDECLARED COLLECTION ADEQUACY THRESHOLDS. They are
not derived from ``context_size`` and may not be changed once route outcomes are
visible.

F-TWIN-1 is open: box colliders in the twin are squared. Route acceptance does
not depend on it -- the planner inflates by ``footprint_radius`` (0.24 m), which
exceeds the true circumscribed chassis radius (0.1866 m) -- but no contact-physics
claim may rest on this pass.
"""

from __future__ import annotations

import argparse
import contextlib
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.evidence import emit_evidence  # noqa: E402

# ---- FROZEN COLLECTION CONTRACT ------------------------------------------
MIN_USABLE_FRAMES = 120
MIN_TRAVEL_M = 8.0
MIN_START_GOAL_SEP_M = 5.0
MIN_HEADING_CHANGES = 3
HEADING_CHANGE_DEG = 30.0
MIN_CONTEXT_WINDOWS = 30

#: ViNT sampling spec: context_size 5 + len_traj_pred 8 => a window needs 14
#: consecutive frames. Recorded so the window count is reproducible.
CONTEXT_SIZE = 5
LEN_TRAJ_PRED = 8
WINDOW_FRAMES = CONTEXT_SIZE + LEN_TRAJ_PRED + 1

#: Collection rate, used only to convert path length into a frame estimate.
CONTROL_HZ = 12.0
CRUISE_V = 0.35

#: Support probe: start just above the floor, below any furniture, so the probe
#: measures floor presence rather than the nearest object overhead.
SUPPORT_PROBE_HEIGHT_M = 0.05
SUPPORT_MAX_RANGE_M = 0.30

#: G5 is measured against PhysX, not against the occupancy grid that planned the
#: route. Heights span the robot: wheels, chassis, mast/camera.
CLEARANCE_PROBE_HEIGHTS_M = (0.05, 0.12, 0.28)
CLEARANCE_RAY_COUNT = 12
CLEARANCE_MAX_RANGE_M = 2.0
#: A support hit must land within this distance of the floor to count as floor.
SUPPORT_FLOOR_TOL_M = 0.08
#: Samples across the footprint disc: centre plus a ring.
FOOTPRINT_RING_SAMPLES = 8
#: Spacing along the route for support/clearance sampling.
ROUTE_SAMPLE_STEP_M = 0.20

AMENDMENT_DIGEST = "61e5b3394c731289bb93905f4fcf0001dde8bbdb37fbccc96f76516a73d08476"


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
        "amendment_digest_pinned": AMENDMENT_DIGEST,
        "scene_asset": scene,
        "robot_asset": robot,
        "robot_asset_sha256": _sha(robot),
        "gpu": _sh("nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"),
    }


def resample(path: Any, step_m: float) -> Any:
    """Uniform arc-length samples along a polyline."""
    import numpy as np
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(s[-1])
    if total <= 0:
        return path[:1]
    n = max(2, int(total / step_m) + 1)
    targets = np.linspace(0.0, total, n)
    out = np.empty((n, 2))
    for i, t in enumerate(targets):
        out[i] = [np.interp(t, s, path[:, 0]), np.interp(t, s, path[:, 1])]
    return out


def heading_changes(path: Any, thresh_deg: float) -> tuple[int, list[float]]:
    """Count direction changes exceeding a threshold, on a decimated path.

    Decimation matters: consecutive samples of a smoothed path are nearly
    collinear, so per-sample angles measure planner noise rather than route
    structure. Turns are accumulated until they exceed the threshold, so one
    sweeping corner counts once rather than as many small deltas.
    """
    import numpy as np
    pts = resample(path, 0.5)
    if pts.shape[0] < 3:
        return 0, []
    d = np.diff(pts, axis=0)
    ang = np.arctan2(d[:, 1], d[:, 0])
    turns: list[float] = []
    acc = 0.0
    for k in range(1, len(ang)):
        delta = math.degrees(math.atan2(math.sin(ang[k] - ang[k - 1]),
                                        math.cos(ang[k] - ang[k - 1])))
        if acc != 0.0 and (delta > 0) != (acc > 0):
            acc = delta          # direction reversed: start a fresh turn
        else:
            acc += delta
        if abs(acc) >= thresh_deg:
            turns.append(round(acc, 2))
            acc = 0.0
    return len(turns), turns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--robot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", type=int, default=24, help="candidate search budget (frozen)")
    args = ap.parse_args()


    from isaacsim.simulation_app import SimulationApp
    app = SimulationApp({"headless": True})

    import isaacsim.core.utils.stage as stage_utils
    import numpy as np
    from isaacsim.core.api import SimulationContext
    from omni.physx import get_physx_scene_query_interface

    from navfm.planning import PlannerError, sample_episode_pair

    rec: dict[str, Any] = {
        "check": "HOSPITAL_ROUTE_ADMISSION_G3_G4_G5_G6_G10",
        "artifact_semantics": "DIAGNOSTIC_ONLY_NOT_AN_EXPECTATION",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": _provenance(args.scene, args.robot),
        "frozen_thresholds": {
            "label": "PREDECLARED COLLECTION ADEQUACY THRESHOLDS",
            "minimum_usable_frames": MIN_USABLE_FRAMES,
            "minimum_travelled_distance_m": MIN_TRAVEL_M,
            "minimum_start_goal_separation_m": MIN_START_GOAL_SEP_M,
            "minimum_heading_changes": MIN_HEADING_CHANGES,
            "heading_change_threshold_deg": HEADING_CHANGE_DEG,
            "minimum_valid_context_windows": MIN_CONTEXT_WINDOWS,
            "window_frames": WINDOW_FRAMES,
            "window_derivation": f"context_size {CONTEXT_SIZE} + len_traj_pred {LEN_TRAJ_PRED} + 1",
            "not_derived_from_context_size": "the six adequacy thresholds are predeclared; "
                                             "only WINDOW_FRAMES comes from the sampling spec",
        },
        "search": {"seed": args.seed, "budget": args.budget,
                   "method": "navfm.planning.sample_episode_pair under a declared seed",
                   "hand_picked": False},
        "f_twin_1": "OPEN -- no contact-physics claim rests on this pass",
        "claim_boundary": ("Selects a route for collection. Admits no data, drives nothing, "
                           "and makes no physical-hardware or contact-fidelity claim."),
    }

    try:
        # ---- production collector, so the gate tests the real artefact -----
        import dataclasses

        from navfm.isaac.collect import CollectConfig, Collector
        from navfm.isaac.randomize import RandomizationConfig
        from navfm.isaac.robot import M3PRO

        cfg = CollectConfig(scenes=[args.scene], seed=args.seed,
                            min_path_m=MIN_TRAVEL_M, max_path_m=40.0)
        robot_cfg = dataclasses.replace(M3PRO, usd_path=args.robot)
        sim_cfg_mod = __import__("navfm.isaac.app", fromlist=["SimConfig"])
        sim_cfg = sim_cfg_mod.SimConfig(headless=True)
        collector = Collector("/tmp/_route_admission_probe", cfg, sim_cfg, robot_cfg,
                              RandomizationConfig(enabled=False))
        collector._app = app  # reuse the already-open app rather than opening a second
        stage_utils.create_new_stage()
        simctx = SimulationContext(stage_units_in_meters=1.0)
        stage_utils.add_reference_to_stage(args.scene, "/World/Scene")
        simctx.initialize_physics()
        for _ in range(3):
            simctx.step(render=False)

        # The occupancy extension ships with Isaac 5.1 but is not enabled by the
        # base experience, so build_occupancy's primary path raises. Enable it
        # rather than falling back: the extension handles instanced geometry
        # correctly, and Hospital is heavily instanced.
        from isaacsim.core.utils.extensions import enable_extension
        ext_enabled = bool(enable_extension("isaacsim.asset.gen.omap"))
        rec["occupancy_extension_enabled"] = ext_enabled

        grid = collector.build_occupancy(args.scene)
        # open_scene() normally does this; we drive build_occupancy directly
        # because the robot is not needed for a read-only route study.
        collector._grid = grid
        collector._clearance = grid.clearance()
        # Persist the map: the collector accepts --occupancy-npz, which is the
        # documented route when the extension is unavailable at collection time.
        npz_path = Path(args.out).with_suffix(".occupancy.npz")
        np.savez_compressed(npz_path, grid=grid.grid, resolution=grid.resolution,
                            origin=np.asarray(grid.origin, dtype=float))
        rec["occupancy_npz"] = str(npz_path)
        inflated = collector._inflated
        clearance = collector._inflated_clearance
        rec["occupancy"] = {
            "resolution_m": cfg.grid_resolution,
            "shape": list(grid.shape),
            "footprint_radius_m": robot_cfg.footprint_radius,
            "min_clearance_m": cfg.min_clearance_m,
            "planner_inflation_exceeds_true_chassis_radius": robot_cfg.footprint_radius > 0.1866,
        }

        q = get_physx_scene_query_interface()

        # ---- floor reference, measured not assumed ------------------------
        probe = q.raycast_closest([0.0, 0.0, SUPPORT_PROBE_HEIGHT_M], [0.0, 0.0, -1.0],
                                  SUPPORT_MAX_RANGE_M)
        floor_z = (SUPPORT_PROBE_HEIGHT_M - float(probe["distance"])) if (
            probe and probe.get("hit")) else 0.0
        rec["floor_reference_z"] = floor_z

        def footprint_offsets() -> list[tuple[float, float]]:
            offs = [(0.0, 0.0)]
            r = robot_cfg.footprint_radius
            for k in range(FOOTPRINT_RING_SAMPLES):
                a = 2 * math.pi * k / FOOTPRINT_RING_SAMPLES
                offs.append((r * math.cos(a), r * math.sin(a)))
            return offs

        def support_at(x: float, y: float) -> dict[str, Any]:
            """Is there floor under the footprint disc?

            The probe starts just above the floor, NOT a metre up. A ray dropped
            from 1 m returns the nearest hit, which in a furnished scene is a
            supply cart or a wall handrail -- overhead clutter that says nothing
            about whether the floor exists beneath it. Reading that as
            "unsupported" conflates an obstacle with a hole, and obstacles are
            G5's question, not G4's.
            """
            unsupported = []
            margins = []
            for dx, dy in footprint_offsets():
                o = [x + dx, y + dy, floor_z + SUPPORT_PROBE_HEIGHT_M]
                res = q.raycast_closest(o, [0.0, 0.0, -1.0], SUPPORT_MAX_RANGE_M)
                if not (res and res.get("hit")):
                    unsupported.append({"dx": dx, "dy": dy, "reason": "NO_FLOOR_HIT",
                                        "prim": None})
                    continue
                hz = o[2] - float(res["distance"])
                margins.append(hz - floor_z)
                if abs(hz - floor_z) > SUPPORT_FLOOR_TOL_M:
                    unsupported.append({"dx": dx, "dy": dy, "reason": "HIT_OFF_FLOOR",
                                        "hit_z": hz, "prim": str(res.get("collision", ""))})
            return {"supported": not unsupported, "unsupported": unsupported,
                    "min_margin_m": (min(margins) if margins else None),
                    "samples": FOOTPRINT_RING_SAMPLES + 1}

        def physical_clearance_at(x: float, y: float) -> dict[str, Any]:
            """Horizontal distance to real geometry, measured with PhysX.

            Deliberately NOT read from the occupancy grid: the grid is what
            planned the route, so asking it to certify the route is circular --
            the same defect that made ``blocking_coverage_fraction = 1.0``
            uninformative about G2. This queries the scene instead, so geometry
            the map missed can still be found.
            """
            worst = None
            worst_at = None
            for hz in CLEARANCE_PROBE_HEIGHTS_M:
                for k in range(CLEARANCE_RAY_COUNT):
                    a = 2 * math.pi * k / CLEARANCE_RAY_COUNT
                    res = q.raycast_closest([x, y, floor_z + hz],
                                            [math.cos(a), math.sin(a), 0.0],
                                            CLEARANCE_MAX_RANGE_M)
                    dist = (float(res["distance"]) if (res and res.get("hit"))
                            else CLEARANCE_MAX_RANGE_M)
                    if worst is None or dist < worst:
                        worst = dist
                        worst_at = {"height_m": hz, "bearing_deg": round(math.degrees(a), 1),
                                    "prim": (str(res.get("collision", ""))
                                             if (res and res.get("hit")) else None)}
            return {"min_distance_m": worst, "at": worst_at}

        def clearance_at(x: float, y: float) -> float:
            """Metres to the nearest inflated obstacle, from the planner's own map."""
            try:
                r, c = inflated.world_to_cell((x, y))
            except Exception:
                return -1.0
            if not (0 <= r < clearance.shape[0] and 0 <= c < clearance.shape[1]):
                return -1.0
            return float(clearance[r, c]) * cfg.grid_resolution

        # ================= PHASE 2: deterministic candidate generation =====
        rng = np.random.default_rng(args.seed)
        candidates: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None

        for i in range(args.budget):
            cand: dict[str, Any] = {"route_id": f"hospital_route_{i:03d}"}
            try:
                start, yaw, goal, path = sample_episode_pair(
                    inflated, rng,
                    min_path_m=MIN_TRAVEL_M, max_path_m=40.0,
                    min_clearance_m=cfg.min_clearance_m, clearance_map=clearance)
            except PlannerError as exc:
                cand.update({"rejected": True, "rejection_reason": f"planner: {exc}"})
                candidates.append(cand)
                continue

            length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
            sep = float(np.linalg.norm(goal - start))
            nturns, turns = heading_changes(path, HEADING_CHANGE_DEG)
            est_frames = int((length / CRUISE_V) * CONTROL_HZ)
            est_windows = max(0, est_frames - WINDOW_FRAMES + 1)

            cand.update({
                "start_pose": [float(start[0]), float(start[1]), float(yaw)],
                "goal_pose": [float(goal[0]), float(goal[1])],
                "nominal_path_length_m": round(length, 4),
                "start_goal_separation_m": round(sep, 4),
                "heading_change_count": nturns,
                "heading_changes_deg": turns,
                "estimated_usable_frames": est_frames,
                "estimated_context_windows": est_windows,
                "rejected": False, "rejection_reason": None,
            })

            # ---- G10 structural adequacy, before any expensive geometry ----
            g10 = {
                "frames": est_frames >= MIN_USABLE_FRAMES,
                "travel": length >= MIN_TRAVEL_M,
                "separation": sep >= MIN_START_GOAL_SEP_M,
                "heading_changes": nturns >= MIN_HEADING_CHANGES,
                "context_windows": est_windows >= MIN_CONTEXT_WINDOWS,
            }
            cand["G10_LONG_HORIZON"] = "PASS" if all(g10.values()) else "FAIL"
            cand["G10_detail"] = g10
            if cand["G10_LONG_HORIZON"] == "FAIL":
                cand.update({"rejected": True,
                             "rejection_reason": "G10: " + ",".join(
                                 k for k, v in g10.items() if not v)})
                candidates.append(cand)
                continue

            # ---- G3 / G4 / G6 support, across the swept footprint ----------
            samples = resample(path, ROUTE_SAMPLE_STEP_M)
            s_start = support_at(float(path[0][0]), float(path[0][1]))
            s_end = support_at(float(path[-1][0]), float(path[-1][1]))
            cont_fail = []
            min_margin = None
            for idx, (px, py) in enumerate(samples):
                s = support_at(float(px), float(py))
                if s["min_margin_m"] is not None:
                    min_margin = (s["min_margin_m"] if min_margin is None
                                  else min(min_margin, s["min_margin_m"]))
                if not s["supported"]:
                    cont_fail.append({"sample_index": idx, "xy": [float(px), float(py)],
                                      "detail": s["unsupported"][:3]})
                    if len(cont_fail) >= 5:
                        break
            cand["G3_START_SUPPORT"] = "PASS" if s_start["supported"] else "FAIL"
            cand["G6_END_SUPPORT"] = "PASS" if s_end["supported"] else "FAIL"
            cand["G4_CONTINUOUS_SUPPORT"] = "PASS" if not cont_fail else "FAIL"
            cand["support_detail"] = {
                "route_samples": int(samples.shape[0]),
                "footprint_samples_per_point": FOOTPRINT_RING_SAMPLES + 1,
                "min_support_margin_m": min_margin,
                "first_failure": cont_fail[0] if cont_fail else None,
                "unsupported_events": len(cont_fail),
                "start_detail": s_start, "end_detail": s_end,
            }

            # ---- G5 obstacle clearance, measured against PhysX --------------
            phys = [physical_clearance_at(float(px), float(py)) for px, py in samples]
            pd = [p["min_distance_m"] for p in phys]
            min_phys = min(pd) if pd else -1.0
            arg_phys = int(np.argmin(pd)) if pd else -1
            # The map-derived reading is kept for comparison, never as the gate:
            # it is produced by the same grid that planned the route.
            grid_cl = [clearance_at(float(px), float(py)) for px, py in samples]
            min_grid = min(grid_cl) if grid_cl else -1.0
            cand["G5_OBSTACLE_CLEARANCE"] = (
                "PASS" if min_phys >= robot_cfg.footprint_radius else "FAIL")
            cand["clearance_detail"] = {
                "criterion": "min PhysX horizontal distance >= footprint_radius",
                "footprint_radius_m": robot_cfg.footprint_radius,
                "min_physical_clearance_m": round(min_phys, 4),
                "at_route_sample": arg_phys,
                "at_xy": ([float(samples[arg_phys][0]), float(samples[arg_phys][1])]
                          if arg_phys >= 0 else None),
                "closest_obstacle": phys[arg_phys]["at"] if arg_phys >= 0 else None,
                "map_derived_min_clearance_on_inflated_grid_m": round(min_grid, 4),
                "map_derived_reading_is_not_the_gate": (
                    "the inflated grid already removed footprint_radius, so requiring "
                    "min_clearance_m on top of it demands footprint_radius + 0.35 m of real "
                    "space and makes ordinary doorways impassable; and it is circular, being "
                    "the same map that planned the route"),
            }

            gates = {k: cand[k] for k in ("G3_START_SUPPORT", "G4_CONTINUOUS_SUPPORT",
                                          "G5_OBSTACLE_CLEARANCE", "G6_END_SUPPORT",
                                          "G10_LONG_HORIZON")}
            cand["all_gates_pass"] = all(v == "PASS" for v in gates.values())
            if not cand["all_gates_pass"]:
                cand.update({"rejected": True, "rejection_reason": ",".join(
                    k for k, v in gates.items() if v != "PASS")})
            candidates.append(cand)
            if cand["all_gates_pass"] and selected is None:
                selected = cand
                # Budget is exhausted regardless, so every candidate is recorded
                # and the selection is "first passing under a declared seed",
                # not "kept looking until something passed".

        rec["candidates"] = candidates
        rec["candidates_generated"] = len(candidates)
        rec["candidates_passing"] = sum(1 for c in candidates if c.get("all_gates_pass"))
        rec["selected_route"] = selected
        rec["selection_rule"] = "first candidate passing all gates, in seeded generation order"

        # ---- controls: the gates must be able to fail ---------------------
        far = 1e6
        ctrl_support = support_at(far, far)               # off-scene: no floor
        ctrl_clear = clearance_at(far, far)               # off-grid
        _, ctrl_turns = heading_changes(np.array([[0.0, 0.0], [5.0, 0.0], [10.0, 0.0]]), 30.0)
        rec["controls"] = {
            "support_fails_off_scene": ctrl_support["supported"] is False,
            "clearance_reports_offgrid": ctrl_clear < 0,
            "straight_line_has_no_heading_changes": len(ctrl_turns) == 0,
            "budget_fully_enumerated": len(candidates) == args.budget,
        }
        rec["controls_all_pass"] = all(rec["controls"].values())

        if not rec["controls_all_pass"]:
            verdict = "ROUTE_INSTRUMENT_REVIEW_REQUIRED"
        elif selected is not None:
            verdict = "ROUTE_ADMITTED_FOR_COLLECTION"
        else:
            verdict = "NO_ROUTE_SATISFIES_FROZEN_CONTRACT"
        rec["ROUTE_ADMISSION"] = verdict

    except Exception as exc:
        import traceback
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-3000:]
        rec["ROUTE_ADMISSION"] = "INCONCLUSIVE"
    finally:
        digest = emit_evidence(args.out, rec, required_keys=(
            "check", "artifact_semantics", "ROUTE_ADMISSION"))
        print(f"wrote {args.out} sha256={digest}", flush=True)
        with contextlib.suppress(Exception):
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
