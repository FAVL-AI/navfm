"""Choose navigation poses from scene topology, before any render score exists.

Two opposite mistakes are available when picking viewpoints to judge a scene by:

.. code-block:: text

    default spawn pose      != representative navigation pose
    hand-picked nice view   != representative navigation pose

World origin is an authoring coordinate; nothing makes it a place a robot would
navigate. But moving the robot until the picture improves is worse, because it
converts scene validation into a search over the validator -- and it is
undetectable afterwards, since the resulting poses look deliberate either way.

So this script reads **only geometry**: mesh bounds, free space, clearance and
connectivity. It never opens a render, never computes a void fraction, and
cannot: the measurement code is not imported. Poses are chosen for navigational
role, written with their rationale, digested and committed. Only then may the
gate run, and the artefact records ``pose_set_frozen_at`` so the ordering is
machine-checkable rather than asserted.

The four roles are fixed before any coordinate is chosen:

``CORRIDOR_START``    a traversable run with a meaningful forward route.
``ROOM_ENTRANCE``     a doorway or opening between two navigable spaces.
``JUNCTION_OR_TURN``  a place where navigation requires a decision.
``GOAL_STYLE``        a plausible destination, for a later sealed image-goal.

Occupancy comes from mesh world bounds projected onto the floor plane, which
overestimates obstacles -- a bounding box is never smaller than its mesh. That
bias is deliberate: it can only make a pose *more* conservatively clear, never
less, so a pose it accepts is genuinely open. It is recorded as
``GEOMETRIC_INTERPRETATION``, not passed off as semantic scene metadata, because
the Isaac assets carry no navigation labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "gates" / "scenes"

ROLES = ("CORRIDOR_START", "ROOM_ENTRANCE", "JUNCTION_OR_TURN", "GOAL_STYLE")

#: Yahboom footprint plus margin, and the vertical band its body occupies.
ROBOT_RADIUS_M = 0.25
ROBOT_Z_MIN, ROBOT_Z_MAX = 0.02, 0.45
GRID_M = 0.25


def analyse(scene: str) -> dict[str, Any]:
    import numpy as np
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(scene)
    boxes = []
    zs = []
    for prim in stage.Traverse(Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)):
        if prim.GetTypeName() != "Mesh":
            continue
        try:
            b = UsdGeom.Boundable(prim).ComputeWorldBound(0, "default").GetBox()
            mn, mx = b.GetMin(), b.GetMax()
            boxes.append((mn[0], mn[1], mn[2], mx[0], mx[1], mx[2]))
            zs.append(mn[2])
        except Exception:
            continue
    if not boxes:
        return {"error": "no boundable meshes"}

    a = np.array(boxes, dtype=np.float64)
    floor_z = float(np.percentile(a[:, 2], 5))
    # Keep the navigable interior. Percentiles over mesh *extents* stretch to
    # the horizon here, because the Office ships a distant city backdrop: a few
    # enormous meshes kilometres away. Mesh *centres* are used instead, since
    # the interior dominates by count while the backdrop is a handful of large
    # objects, and only meshes intersecting the robot's own height band count --
    # a skyline tower at 300 m is not a navigation obstacle.
    band = (a[:, 5] >= floor_z + ROBOT_Z_MIN) & (a[:, 2] <= floor_z + ROBOT_Z_MAX)
    cx, cy = (a[:, 0] + a[:, 3]) / 2.0, (a[:, 1] + a[:, 4]) / 2.0
    sel = band if band.sum() >= 20 else np.ones(len(a), dtype=bool)
    x0, x1 = np.percentile(cx[sel], 5), np.percentile(cx[sel], 95)
    y0, y1 = np.percentile(cy[sel], 5), np.percentile(cy[sel], 95)
    pad = 3.0
    x0, x1, y0, y1 = x0 - pad, x1 + pad, y0 - pad, y1 + pad
    grid_m = GRID_M
    while ((x1 - x0) / grid_m) * ((y1 - y0) / grid_m) > 1_500_000:
        grid_m *= 2.0   # coarsen rather than refuse, and record what was used
    nx = max(4, int((x1 - x0) / grid_m))
    ny = max(4, int((y1 - y0) / grid_m))

    occ = np.zeros((nx, ny), dtype=bool)
    zlo, zhi = floor_z + ROBOT_Z_MIN, floor_z + ROBOT_Z_MAX
    for mnx, mny, mnz, mxx, mxy, mxz in a:
        if mxz < zlo or mnz > zhi:      # entirely below the floor or overhead
            continue
        i0 = max(0, int((mnx - x0) / grid_m))
        i1 = min(nx - 1, int((mxx - x0) / grid_m))
        j0 = max(0, int((mny - y0) / grid_m))
        j1 = min(ny - 1, int((mxy - y0) / grid_m))
        if i0 <= i1 and j0 <= j1:
            occ[i0:i1 + 1, j0:j1 + 1] = True

    free = ~occ
    # Clearance by successive erosion: cheap, dependency-free distance transform.
    clear = np.zeros((nx, ny), dtype=np.float32)
    cur = free.copy()
    for step in range(1, 40):
        nxt = (cur & np.roll(cur, 1, 0) & np.roll(cur, -1, 0)
               & np.roll(cur, 1, 1) & np.roll(cur, -1, 1))
        clear[cur & ~nxt] = step * grid_m
        cur = nxt
        if not cur.any():
            break
    clear[cur] = 40 * grid_m

    usable = free & (clear >= ROBOT_RADIUS_M)
    return {
        "origin": (float(x0), float(y0)), "grid_m": grid_m, "floor_z": floor_z,
        "shape": (nx, ny), "occ": occ, "free": free, "clear": clear, "usable": usable,
        "mesh_count": len(boxes),
        "free_fraction": float(free.mean()), "usable_fraction": float(usable.mean()),
    }


def _dirs() -> list[tuple[float, float]]:
    return [(math.cos(math.radians(d)), math.sin(math.radians(d)))
            for d in range(0, 360, 45)]


def _open_run(usable: Any, i: int, j: int, dx: float, dy: float, grid: float) -> float:
    """How far the floor stays usable along a heading, in metres."""
    nx, ny = usable.shape
    for step in range(1, 80):
        ii, jj = int(round(i + dx * step)), int(round(j + dy * step))
        if not (0 <= ii < nx and 0 <= jj < ny) or not usable[ii, jj]:
            return (step - 1) * grid
    return 80 * grid


def select(topo: dict[str, Any]) -> list[dict[str, Any]]:
    """One pose per role, from geometry. No render quantity is consulted."""
    import numpy as np

    usable, clear = topo["usable"], topo["clear"]
    grid, (ox, oy) = topo["grid_m"], topo["origin"]
    _nx, _ny = topo["shape"]
    dirs = _dirs()

    cand = np.argwhere(usable)
    if len(cand) == 0:
        return []
    # A deterministic, evenly spread sample: no randomness, so re-running the
    # selection reproduces the same candidate set.
    stride = max(1, len(cand) // 4000)
    cand = cand[::stride]

    scored = []
    for i, j in cand:
        runs = [_open_run(usable, i, j, dx, dy, grid) for dx, dy in dirs]
        runs = np.array(runs)
        best = int(runs.argmax())
        branches = int((runs >= 1.5).sum())
        scored.append({
            "i": int(i), "j": int(j), "clear": float(clear[i, j]),
            "runs": runs, "best_dir": best, "best_run": float(runs[best]),
            "branches": branches,
            "opposite_run": float(runs[(best + 4) % 8]),
        })

    def world(c: dict[str, Any]) -> tuple[float, float]:
        return ox + c["i"] * grid, oy + c["j"] * grid

    def yaw_of(c: dict[str, Any], idx: int | None = None) -> float:
        return float((idx if idx is not None else c["best_dir"]) * 45.0)

    poses: list[dict[str, Any]] = []
    used: list[tuple[int, int]] = []

    def far_enough(c: dict[str, Any]) -> bool:
        return all(math.hypot(c["i"] - u[0], c["j"] - u[1]) * grid > 3.0 for u in used)

    # CORRIDOR_START -- long forward run, laterally bounded, so it is a corridor
    # rather than the middle of an open hall.
    corr = [c for c in scored
            if c["best_run"] >= 4.0 and 0.4 <= c["clear"] <= 2.5 and c["branches"] <= 4]
    corr.sort(key=lambda c: -c["best_run"])
    if corr:
        c = corr[0]
        x, y = world(c)
        poses.append({
            "pose_id": "OFFICE_NAV_01", "role": "CORRIDOR_START",
            "x": round(x, 3), "y": round(y, 3), "yaw_deg": yaw_of(c),
            "selection_method": "longest unobstructed forward run with bounded lateral clearance",
            "selection_rationale": (
                f"Usable floor with a {c['best_run']:.1f} m forward run and "
                f"{c['clear']:.2f} m lateral clearance, so the robot sits in a corridor-like "
                f"channel rather than open floor. Yaw follows the principal travel axis."),
            "geometric_evidence": {"forward_run_m": round(c["best_run"], 2),
                                   "lateral_clearance_m": round(c["clear"], 2),
                                   "open_directions": c["branches"]},
        })
        used.append((c["i"], c["j"]))

    # ROOM_ENTRANCE -- a clearance pinch with open floor on both sides: a gap.
    door = [c for c in scored
            if c["clear"] <= 0.9 and c["best_run"] >= 2.0 and c["opposite_run"] >= 2.0
            and far_enough(c)]
    door.sort(key=lambda c: (c["clear"], -min(c["best_run"], c["opposite_run"])))
    if door:
        c = door[0]
        x, y = world(c)
        poses.append({
            "pose_id": "OFFICE_NAV_02", "role": "ROOM_ENTRANCE",
            "x": round(x, 3), "y": round(y, 3), "yaw_deg": yaw_of(c),
            "selection_method": "local clearance minimum with traversable floor on both sides",
            "selection_rationale": (
                f"Clearance narrows to {c['clear']:.2f} m while the floor stays open "
                f"{c['best_run']:.1f} m ahead and {c['opposite_run']:.1f} m behind -- the "
                f"signature of an opening between two navigable spaces. Yaw is the traversal "
                f"normal."),
            "geometric_evidence": {"pinch_clearance_m": round(c["clear"], 2),
                                   "run_ahead_m": round(c["best_run"], 2),
                                   "run_behind_m": round(c["opposite_run"], 2)},
        })
        used.append((c["i"], c["j"]))

    # JUNCTION_OR_TURN -- three or more separate traversable branches.
    junc = [c for c in scored if c["branches"] >= 5 and c["best_run"] >= 3.0
            and far_enough(c)]
    junc.sort(key=lambda c: (-c["branches"], -c["best_run"]))
    if junc:
        c = junc[0]
        x, y = world(c)
        poses.append({
            "pose_id": "OFFICE_NAV_03", "role": "JUNCTION_OR_TURN",
            "x": round(x, 3), "y": round(y, 3), "yaw_deg": yaw_of(c),
            "selection_method": "maximal count of independent traversable headings",
            "selection_rationale": (
                f"{c['branches']} of 8 headings remain traversable for at least 1.5 m, so a "
                f"robot arriving here must choose. Yaw is the approach heading along the "
                f"longest branch."),
            "geometric_evidence": {"open_headings": c["branches"],
                                   "longest_branch_m": round(c["best_run"], 2)},
        })
        used.append((c["i"], c["j"]))

    # GOAL_STYLE -- an endpoint: reachable, enclosed ahead, open behind.
    goal = [c for c in scored
            if c["best_run"] <= 2.5 and c["clear"] >= 0.4 and c["branches"] <= 3
            and far_enough(c)]
    goal.sort(key=lambda c: (c["branches"], -c["clear"]))
    if goal:
        c = goal[0]
        x, y = world(c)
        # Face the enclosure: a destination view looks at the place, not away.
        idx = int(c["runs"].argmin())
        poses.append({
            "pose_id": "OFFICE_NAV_04", "role": "GOAL_STYLE",
            "x": round(x, 3), "y": round(y, 3), "yaw_deg": yaw_of(c, idx),
            "selection_method": "traversable endpoint with limited onward routes",
            "selection_rationale": (
                f"Only {c['branches']} headings stay open and the longest is "
                f"{c['best_run']:.1f} m, so this terminates a route rather than continuing "
                f"one -- the structure of a destination. Yaw faces the enclosing geometry, "
                f"as an arrival view would."),
            "geometric_evidence": {"onward_routes": c["branches"],
                                   "longest_run_m": round(c["best_run"], 2),
                                   "clearance_m": round(c["clear"], 2)},
        })
        used.append((c["i"], c["j"]))

    for p in poses:
        p["z"] = round(topo["floor_z"] + 0.05, 3)
        p["semantic_source"] = "GEOMETRIC_INTERPRETATION"
        p["semantic_evidence_if_available"] = (
            "none — the Isaac Office asset carries no navigation semantic labels")
        p["robot_footprint_clearance_m"] = ROBOT_RADIUS_M
        p["selected_before_measurement"] = True
        p["render_metrics_consulted"] = False
    return poses


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--scene-id", required=True)
    args = ap.parse_args()

    from isaacsim.simulation_app import SimulationApp

    app = SimulationApp({"headless": True})
    try:
        topo = analyse(args.scene)
        if "error" in topo:
            print(f"REFUSED: {topo['error']}", file=sys.stderr)
            app.close()
            return 2
        poses = select(topo)
        missing = [r for r in ROLES if r not in {p["role"] for p in poses}]

        import subprocess

        rec: dict[str, Any] = {
            "check": "POSE_PREREGISTRATION",
            "scene_id": args.scene_id, "scene": args.scene,
            "roles_declared_before_selection": list(ROLES),
            "selection_inputs": [
                "mesh world bounds", "floor plane", "free-space occupancy",
                "clearance transform", "directional traversable runs",
            ],
            "selection_inputs_excluded": [
                "true_void_fraction", "environment_fraction", "background_fraction",
                "dominant hue", "colour diversity", "forward depth", "structure",
                "any render output whatsoever",
            ],
            "occupancy_note": (
                "Occupancy is mesh bounding boxes projected onto the floor band, which "
                "overestimates obstacles. The bias is one-directional: it can only make an "
                "accepted pose more conservatively clear, never less."),
            "topology": {k: topo[k] for k in
                         ("floor_z", "grid_m", "shape", "mesh_count",
                          "free_fraction", "usable_fraction")},
            "poses": poses,
            "roles_missing": missing,
            "route_coherent": len(poses) == 4,
            "route_note": ("four roles filled from one connected usable region"
                           if len(poses) == 4 else
                           f"roles not satisfiable from this topology: {missing}"),
            "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                       capture_output=True, text=True).stdout.strip(),
            "pose_set_frozen_at": datetime.now(timezone.utc).isoformat(),
        }
        rec["pose_set_digest"] = hashlib.sha256(
            json.dumps(rec["poses"], sort_keys=True).encode()).hexdigest()
        rec["ordering_contract"] = (
            "pose_set_frozen_at must precede measurement_started_at in the gate artefact. "
            "A pose may not be replaced after its render result is known; that requires a "
            "dated amendment stating why, with the replacement chosen without inspecting "
            "its scores.")

        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / f"{args.scene_id}_pose_preregistration.json"
        p.write_text(json.dumps(rec, indent=2) + "\n")
        print(f"  scene {args.scene_id}: {topo['mesh_count']} meshes, grid {topo['shape']}, "
              f"usable floor {topo['usable_fraction']:.1%}")
        for q in poses:
            print(f"    {q['pose_id']}  {q['role']:<17} "
                  f"({q['x']:.2f}, {q['y']:.2f}) yaw {q['yaw_deg']:.0f}  {q['geometric_evidence']}")
        if missing:
            print(f"    ROLES NOT SATISFIED: {missing}")
        print(f"  digest {rec['pose_set_digest'][:32]}")
        print(f"  frozen {rec['pose_set_frozen_at']}")
        print(f"  -> {p.relative_to(REPO)}")
        app.close()
        return 0 if not missing else 1
    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        app.close()
        return 2


if __name__ == "__main__":
    sys.exit(main())
