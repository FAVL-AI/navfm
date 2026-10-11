"""Scene geometry as data: the legacy corridor family and explicit layout specs.

The legacy family varies appearance only through ``scene_index % 5``, so a new
index silently recreates an existing scene. Explicit layouts list every box,
which lets a held-out family be frozen, digested and checked for route
clearance before anything is rendered. Pure Python; the collector turns each
box into a USD cube.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from itertools import pairwise
from typing import Any

SCENE_SPACING_M = 20.0


def box(name, xyz, size, color, collision=True) -> dict[str, Any]:
    return {
        "name": name,
        "xyz": [float(v) for v in xyz],
        "size": [float(v) for v in size],
        "color": [float(v) for v in color],
        "collision": bool(collision),
    }


def legacy_boxes(scene: int, half: float, partitions: bool) -> list[dict[str, Any]]:
    """The corridor family built inline by collect_option1 before explicit layouts."""
    origin = scene * SCENE_SPACING_M
    k = scene % 5
    out = [
        box("Floor", (2.0, origin, -0.05), (8.0, 8.0, 0.1), (0.35 + 0.04 * k, 0.4, 0.45)),
        box("WallLeft", (2.0, origin + half, 1.4), (6.0, 0.2, 2.8), (0.65, 0.7 - 0.05 * k, 0.75)),
        box("WallRight", (2.0, origin - half, 1.4), (6.0, 0.2, 2.8), (0.65, 0.7, 0.75 - 0.04 * k)),
        box("EndWall", (5.0, origin, 1.4), (0.2, 2 * half, 2.8), (0.6, 0.65, 0.7)),
        box("Obstacle", (3.5 + 0.1 * k, origin + 1.45, 0.4), (0.45, 0.4, 0.8), (0.1, 0.3, 0.7)),
    ]
    for side in (-1, 1):
        for stripe in range(12):
            color = (0.15, 0.35, 0.65) if stripe % 2 else (0.75, 0.35, 0.12)
            out.append(
                box(
                    f"Stripe{'L' if side > 0 else 'R'}_{stripe}",
                    (-0.4 + stripe * 0.5, origin + side * (half - 0.105), 1.0),
                    (0.15, 0.015, 1.3),
                    color,
                    False,
                )
            )
    for ix in range(8):
        for iy in range(8):
            if (ix + iy) % 2 == 0:
                out.append(
                    box(
                        f"Tile{ix}_{iy}",
                        (-1.5 + ix, origin - 3.5 + iy, 0.002),
                        (1.0, 1.0, 0.002),
                        (0.22, 0.26, 0.30),
                        False,
                    )
                )
    if partitions:
        for side in (-1, 1):
            out.append(
                box(
                    f"DoorPartition{side + 1}",
                    (1.75 + 0.12 * k, origin + side * 1.45, 0.7),
                    (0.16, 0.65 + 0.08 * k, 1.4),
                    (0.35, 0.45, 0.25),
                )
            )
    return out


def layout_boxes(scene: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Boxes of an explicit layout; coordinates are scene-local and shifted by origin."""
    origin = scene["scene_index"] * SCENE_SPACING_M
    return [
        box(
            b["name"],
            (b["xyz"][0], b["xyz"][1] + origin, b["xyz"][2]),
            b["size"],
            b["color"],
            b.get("collision", True),
        )
        for b in scene["boxes"]
    ]


def _rect_distance(p, center, size) -> float:
    dx = max(abs(p[0] - center[0]) - size[0] / 2, 0.0)
    dy = max(abs(p[1] - center[1]) - size[1] / 2, 0.0)
    return math.hypot(dx, dy)


def route_clearance(waypoints: Iterable, boxes: Iterable[Mapping], *, step: float = 0.02):
    """Minimum planar distance from the route polyline to any colliding box above floor."""
    pts = [tuple(map(float, w)) for w in waypoints]
    solid = [b for b in boxes if b["collision"] and b["xyz"][2] - b["size"][2] / 2 > -0.01]
    best, where = math.inf, None
    for (x0, y0), (x1, y1) in pairwise(pts):
        n = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / step))
        for i in range(n + 1):
            p = (x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n)
            for b in solid:
                d = _rect_distance(p, b["xyz"], b["size"])
                if d < best:
                    best, where = d, b["name"]
    return best, where


def digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def teacher_rollout(waypoints, speed: float, *, hz: float = 12.0, max_steps: int = 360):
    """Pose-step rollout of DemonstrationTeacher, as the kinematic collector applies it.

    Returns (reached, steps, poses) with poses as (x, y, yaw) per control frame.
    """
    import numpy as np

    from navfm.collection.demonstrations import DemonstrationTeacher

    pts = np.asarray(waypoints, float)
    teacher = DemonstrationTeacher(pts, speed)
    xy = pts[0].copy()
    yaw = math.atan2(*(pts[1] - pts[0])[::-1])
    poses = [(float(xy[0]), float(xy[1]), yaw)]
    dt = 1.0 / hz
    for step in range(max_steps):
        (vx, _, w), done = teacher.step(xy, yaw)
        if done:
            return True, step, poses
        xy = xy + dt * vx * np.array([math.cos(yaw), math.sin(yaw)])
        yaw += dt * w
        poses.append((float(xy[0]), float(xy[1]), yaw))
    return False, max_steps, poses


def _ray_box(origin, direction, center, size):
    """Distance along a 2D ray to an axis-aligned rectangle, or None."""
    t0, t1 = -math.inf, math.inf
    for o, d, c, s in zip(origin, direction, center, size, strict=True):
        lo, hi = c - s / 2, c + s / 2
        if abs(d) < 1e-12:
            if not lo <= o <= hi:
                return None
            continue
        a, b = (lo - o) / d, (hi - o) / d
        t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
    if t1 < max(t0, 0.0):
        return None
    return max(t0, 0.0)


def goal_view(pose, boxes, *, camera_forward_m=0.2, fov_deg=64.0, columns=65, camera_z=0.55):
    """Nearest box name per image column for a forward camera at pose (planar ray-cast).

    Floor slabs and decals are ignored; only boxes rising 0.3 m or more are hit.
    """
    x, y, yaw = pose
    cam = (x + camera_forward_m * math.cos(yaw), y + camera_forward_m * math.sin(yaw))
    # Visible near the horizon: rises at least 0.3 m and starts below the view's upper band.
    tall = [
        b
        for b in boxes
        if b["xyz"][2] + b["size"][2] / 2 >= 0.3
        and b["xyz"][2] - b["size"][2] / 2 <= camera_z + 0.5
    ]
    hits = []
    for i in range(columns):
        a = yaw + math.radians(fov_deg) * (0.5 - i / (columns - 1))
        d = (math.cos(a), math.sin(a))
        best = (math.inf, None)
        for b in tall:
            t = _ray_box(cam, d, b["xyz"][:2], b["size"][:2])
            if t is not None and t < best[0]:
                best = (t, b["name"])
        hits.append(best[1])
    return hits


SEALED_SPECS = ("configs/splits/heldout_layouts_v1.json",)
# The one unseal ledger. Any other directory is refused, so slots cannot be renewed
# by choosing a fresh path; entries are archived under gates/ after each run.
LEDGER_DIR = "~/navfm-runtime-evidence/heldout_layouts_v1-ledger"
# Checkpoints may be unsealed against held-out only once declared here (sha256 list).
DECLARED_CHECKPOINTS = "configs/splits/heldout_layouts_v1_checkpoints.json"
CHECKPOINT_ROLES = {"policy_episode_run", "goal_swap_control"}
# Scene indices reserved by sealed specs; legacy routes must never use them either,
# because the legacy family would render index 40 with scene 0's appearance.
ROUTE_MATCH_M = 0.1
COLOUR_MATCH = 0.1
SIZE_MATCH_M = 0.05
SCENE_OVERLAP = 0.5


def _sealed_specs(repo):
    from pathlib import Path

    return [json.loads((Path(repo) / rel).read_text()) for rel in SEALED_SPECS]


def _hausdorff(a, b, step=0.02) -> float:
    def dense(line):
        pts = [tuple(map(float, w)) for w in line]
        out = []
        for (x0, y0), (x1, y1) in pairwise(pts):
            n = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / step))
            out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n + 1)]
        return out

    da, db = dense(a), dense(b)

    def directed(p, q):
        return max(min(math.dist(x, y) for y in q) for x in p)

    return max(directed(da, db), directed(db, da))


def _box_key_match(a, b) -> bool:
    return math.dist(a["color"], b["color"]) <= COLOUR_MATCH and all(
        abs(x - y) <= SIZE_MATCH_M for x, y in zip(a["size"], b["size"], strict=True)
    )


def scene_resembles(boxes, sealed_boxes) -> float:
    """Fraction of sealed boxes (above the floor) matched in colour and size by boxes."""
    target = [b for b in sealed_boxes if b["name"] != "Floor"]
    if not target:
        return 0.0
    hit = sum(1 for t in target if any(_box_key_match(t, b) for b in boxes))
    return hit / len(target)


def sealed_matches(routes, repo, scenes=None) -> list[str]:
    """Reasons a selection touches sealed held-out data.

    Routes match by id, scene index or geometry (Hausdorff distance below
    ROUTE_MATCH_M in scene-local coordinates); scenes match by appearance (half
    or more of a sealed scene's boxes reproduced in colour and size).
    """
    reasons = []
    for spec in _sealed_specs(repo):
        sealed_routes = spec["routes"]
        ids = {r["id"] for r in sealed_routes}
        indices = {r["scene_index"] for r in sealed_routes}
        for r in routes:
            name = r.get("id", "?")
            if name in ids:
                reasons.append(f"{name}: sealed route id")
            elif r.get("scene_index") in indices:
                reasons.append(f"{name}: reserved scene index {r.get('scene_index')}")
            elif any(
                _hausdorff(r["waypoints"], s["waypoints"]) < ROUTE_MATCH_M for s in sealed_routes
            ):
                reasons.append(f"{name}: route geometry matches a sealed route")
        for scene in scenes or []:
            for sealed in spec["scenes"]:
                if scene_resembles(scene["boxes"], sealed["boxes"]) >= SCENE_OVERLAP:
                    reasons.append(
                        f"scene {scene.get('scene_index')}: resembles sealed {sealed['group']}"
                    )
    return reasons


def refuse_sealed(routes, repo, scenes=None) -> None:
    reasons = sealed_matches(routes, repo, scenes)
    if reasons:
        raise ValueError(f"sealed held-out data refused: {sorted(set(reasons))}")


def pinned_ledger():
    from pathlib import Path

    return Path(LEDGER_DIR).expanduser().resolve()


def ledger_entries(ledger_dir) -> list[dict]:
    from pathlib import Path

    d = Path(ledger_dir)
    return [json.loads(f.read_text()) for f in sorted(d.glob("run_*.json"))] if d.is_dir() else []


def _started(entry) -> bool:
    """A run counts against its slot once any episode was attempted."""
    from pathlib import Path

    summary = Path(entry["out"]) / "collection.json"
    if not summary.exists():
        return False
    return bool(json.loads(summary.read_text()).get("episodes"))


def claim_unseal_slot(
    ledger_dir, spec, *, out, role, routes, checkpoint_sha256=None, repo=None
) -> dict:
    """Record one unseal run within the spec's pre-declared slots.

    Roles are bound to the run: checkpoint roles need a declared checkpoint, the
    teacher role must have none. A run that never attempted an episode does not
    consume its slot; at most one such retry per role is allowed.
    """
    import time
    from pathlib import Path

    d = Path(ledger_dir)
    entries = ledger_entries(d)
    slots = spec["protocol"]["unseal_slots"]
    if role not in slots:
        raise ValueError(f"unknown unseal role {role!r}; declared: {sorted(slots)}")
    if (role in CHECKPOINT_ROLES) != (checkpoint_sha256 is not None):
        raise ValueError(f"role {role!r} does not match checkpoint presence")
    if checkpoint_sha256 is not None:
        declared_path = Path(repo) / DECLARED_CHECKPOINTS
        declared = (
            set(json.loads(declared_path.read_text())["sha256"])
            if declared_path.exists()
            else set()
        )
        if checkpoint_sha256 not in declared:
            raise ValueError("checkpoint not declared for held-out evaluation")
    same = [e for e in entries if e["role"] == role]
    used = sum(1 for e in same if _started(e))
    if used >= slots[role]:
        raise ValueError(f"unseal slots for {role!r} exhausted ({used}/{slots[role]})")
    if len(same) - used >= 1 and len(same) >= slots[role] + 1:
        raise ValueError(f"retry for {role!r} already used")
    if any(e["out"] == str(out) for e in entries):
        raise ValueError("output already recorded in the unseal ledger")
    d.mkdir(parents=True, exist_ok=True)
    entry = {
        "out": str(out),
        "role": role,
        "routes": routes,
        "checkpoint_sha256": checkpoint_sha256,
        "content_digest": spec["content_digest"],
        "time": time.time(),
    }
    (d / f"run_{len(entries):03d}.json").write_text(json.dumps(entry, indent=2) + "\n")
    return entry


def check_heldout_goals(goal_root, routes, role, ledger_dir) -> None:
    """Held-out goals are teacher-run final frames; goal-swap uses the partner route's."""
    from pathlib import Path

    teacher = [
        e["out"]
        for e in ledger_entries(ledger_dir)
        if e["role"] == "teacher_goal_traversal" and _started(e)
    ]
    if len(teacher) != 1:
        raise ValueError("exactly one completed teacher_goal_traversal run must exist")
    definition = json.loads((Path(goal_root) / "goal_source.json").read_text())["goals"]
    by_scene: dict[int, list[str]] = {}
    for r in routes:
        by_scene.setdefault(r["scene_index"], []).append(r["id"])
    for r in routes:
        partner = [x for x in by_scene[r["scene_index"]] if x != r["id"]]
        expected = partner[0] if role == "goal_swap_control" else r["id"]
        source = Path(definition[r["id"]]["source"]).resolve()
        if not source.is_relative_to(Path(teacher[0]).resolve() / expected):
            raise ValueError(f"{r['id']}: goal must come from the teacher run of {expected}")


def require_scoring_allowed(collection, routes, repo, ledger_dir) -> None:
    """Scoring sealed routes requires the collection to be a recorded unseal run."""
    from pathlib import Path

    if not sealed_matches(routes, repo):
        return
    if ledger_dir is None:
        raise ValueError("sealed held-out routes refused; scoring needs --score-heldout LEDGER")
    if Path(ledger_dir).resolve() != pinned_ledger():
        raise ValueError(f"scoring ledger must be the pinned ledger {pinned_ledger()}")
    recorded = {e["out"] for e in ledger_entries(ledger_dir)}
    if str(collection) not in recorded:
        raise ValueError("collection is not a recorded unseal run")
