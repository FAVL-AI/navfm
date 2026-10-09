"""Write the held-out layout family heldout_layouts_v1 (boxes, routes, protocol fields).

Route starts (x = 1.0) and lengths (2.15-2.22 m) are matched to training. Scene
appearance (palettes, obstacles, end-wall landmarks) is new. The final approach
(lateral offset 0.6-0.7 m, heading +x, ending at x = 2.9) is near some training
endpoints but at larger offsets, so held-out mainly tests unseen scenes with a
modestly shifted final pose. Each group has two routes whose goal poses are at
least twice the arrival radius apart and whose goal views centre on landmarks
of different shape and colour.

Usage: make_heldout_layouts_v1.py OUT.json  (refuses to write if any check fails)
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from navfm.collection.scene_layouts import box

FIRST_SCENE = 40
GROUPS = [
    # name, half width, floor, wall, end wall, obstacles, panels, start y, endpoint dy
    (
        "heldout_layout_A",
        1.6,
        (0.62, 0.55, 0.42),
        (0.85, 0.82, 0.60),
        (0.80, 0.78, 0.58),
        [("Crate", (2.6, 0.0, 0.3), (0.35, 0.35, 0.6), (0.45, 0.25, 0.10))],
        [(0.80, 0.10, 0.10), (0.10, 0.60, 0.20)],
        0.0,
        0.65,
    ),
    (
        "heldout_layout_B",
        2.2,
        (0.15, 0.42, 0.20),
        (0.45, 0.50, 0.62),
        (0.30, 0.30, 0.75),
        [("Drum", (2.5, 1.55, 0.35), (0.45, 0.45, 0.7), (0.85, 0.65, 0.10))],
        [(0.95, 0.50, 0.05), (0.55, 0.10, 0.65)],
        0.2,
        0.6,
    ),
    (
        "heldout_layout_C",
        1.8,
        (0.55, 0.33, 0.27),
        (0.90, 0.90, 0.88),
        (0.88, 0.88, 0.86),
        [("Pillar", (2.5, 0.0, 1.4), (0.3, 0.3, 2.8), (0.30, 0.10, 0.35))],
        [(0.10, 0.10, 0.45), (0.95, 0.85, 0.20)],
        0.0,
        0.7,
    ),
    (
        "heldout_layout_D",
        1.9,
        (0.12, 0.10, 0.10),
        (0.70, 0.55, 0.50),
        (0.65, 0.50, 0.45),
        [("Bench", (2.4, -1.45, 0.25), (0.9, 0.35, 0.5), (0.20, 0.45, 0.30))],
        [(0.05, 0.55, 0.60), (0.90, 0.30, 0.55)],
        -0.2,
        0.6,
    ),
    (
        "heldout_layout_E",
        1.7,
        (0.70, 0.55, 0.20),
        (0.40, 0.75, 0.40),
        (0.50, 0.60, 0.45),
        [("Cabinet", (2.5, 0.0, 0.5), (0.35, 0.45, 1.0), (0.85, 0.20, 0.40))],
        [(0.15, 0.15, 0.15), (0.95, 0.95, 0.30)],
        0.0,
        0.6,
    ),
    (
        "heldout_layout_F",
        2.0,
        (0.40, 0.22, 0.20),
        (0.80, 0.75, 0.85),
        (0.95, 0.80, 0.95),
        [("Planter", (2.3, 1.6, 0.3), (0.5, 0.5, 0.6), (0.25, 0.55, 0.15))],
        [(0.20, 0.35, 0.90), (0.95, 0.55, 0.45)],
        -0.1,
        0.65,
    ),
]
PROTOCOL = {
    "teacher_speed_m_s": 0.2,
    "teacher_max_steps": 360,
    "policy_max_v_m_s": 0.1,
    "policy_max_steps": 600,
    "control_hz": 12.0,
    "arrival_radius_m": 0.5,
    "min_endpoint_separation_m": 1.0,
    "clearance_requirement_m": 0.34,
    "min_goal_landmark_fraction": 0.3,
    "unseal_slots": {
        "teacher_goal_traversal": 1,
        "policy_episode_run": 4,
        "goal_swap_control": 2,
    },
    "unseal_slot_reason": "one teacher traversal for goal frames; policy runs for at most four pre-declared checkpoints; goal-swap control for two of them",
    "contact_scoring": "any robot contact with a non-floor fixture prim marks the episode a collision episode; completion requires a correct stop and no contact",
}


def shell(half, floor, wall, end):
    return [
        box("Floor", (2.0, 0, -0.05), (8.0, 8.0, 0.1), floor),
        box("WallLeft", (2.0, half, 1.4), (6.0, 0.2, 2.8), wall),
        box("WallRight", (2.0, -half, 1.4), (6.0, 0.2, 2.8), wall),
        box("EndWall", (5.0, 0, 1.4), (0.2, 2 * half, 2.8), end),
    ]


def build():
    scenes, routes = [], []
    for k, (group, half, floor, wall, end, obstacles, panels, y0, dy) in enumerate(GROUPS):
        index = FIRST_SCENE + k
        boxes = shell(half, floor, wall, end)
        boxes += [box(*o) for o in obstacles]
        # One end-wall landmark centred on each route's final heading line. The two
        # differ in shape as well as colour: a solid block versus three vertical bars.
        (lc, rc) = panels
        boxes.append(box("PanelEndL", (4.885, y0 + dy, 1.0), (0.03, 0.9, 1.2), lc, False))
        for bar in (-1, 0, 1):
            boxes.append(
                box(
                    f"PanelEndR{bar + 1}",
                    (4.885, y0 - dy + 0.35 * bar, 1.0),
                    (0.03, 0.2, 1.2),
                    rc,
                    False,
                )
            )
        scenes.append(
            {"scene_index": index, "group": group, "wall_half_width": half, "boxes": boxes}
        )
        for j, side in enumerate((1, -1)):
            ye = y0 + side * dy
            wp = [[1.0, y0], [1.6, y0], [2.2, ye], [2.9, ye]]
            routes.append(
                {
                    "id": f"{group[-1].lower()}_route_{j}",
                    "scene": group,
                    "split": "heldout",
                    "route_id": f"{group}_route_{j}",
                    "scene_index": index,
                    "seed": 4000 + 2 * index + j,
                    "waypoints": wp,
                    "speed": PROTOCOL["teacher_speed_m_s"],
                    "start_yaw": math.atan2(wp[1][1] - wp[0][1], wp[1][0] - wp[0][0]),
                    "wall_half_width": half,
                }
            )
    return {"protocol": PROTOCOL, "scenes": scenes, "routes": routes}


def dominant(view):
    """Most frequent end-wall landmark family in a view (bars count together)."""
    names = [h.rstrip("0123456789") for h in view if h and h.startswith("PanelEnd")]
    return max(set(names), key=names.count) if names else None


def verify(spec):
    """Per-route teacher completion, clearance and goal-view landmark checks."""
    from navfm.collection.scene_layouts import (
        _rect_distance,
        goal_view,
        route_clearance,
        teacher_rollout,
    )

    p = spec["protocol"]
    out, failures = {}, []
    for scene in spec["scenes"]:
        solid = [
            b for b in scene["boxes"] if b["collision"] and b["xyz"][2] - b["size"][2] / 2 > -0.01
        ]
        routes = [r for r in spec["routes"] if r["scene_index"] == scene["scene_index"]]
        ends = []
        for r in routes:
            reached, steps, poses = teacher_rollout(
                r["waypoints"], r["speed"], hz=p["control_hz"], max_steps=p["teacher_max_steps"]
            )
            line, _ = route_clearance(r["waypoints"], scene["boxes"])
            body = min(_rect_distance(q[:2], b["xyz"], b["size"]) for q in poses for b in solid)
            # The collector photographs the goal at the last waypoint, facing the last segment.
            (gx, gy), (px, py) = r["waypoints"][-1], r["waypoints"][-2]
            photo = (gx, gy, math.atan2(gy - py, gx - px))
            view = goal_view(photo, scene["boxes"])
            # The goal image is the teacher run's final recorded frame (0.12 m short).
            final_view = goal_view(poses[-1], scene["boxes"])
            landmark = sum(1 for h in view if h not in (None, "WallLeft", "WallRight", "EndWall"))
            start, goal = r["waypoints"][0], r["waypoints"][-1]
            out[r["id"]] = {
                "teacher_reached": reached,
                "teacher_steps": steps,
                "teacher_final_pose": [round(v, 4) for v in poses[-1]],
                "polyline_clearance_m": round(line, 3),
                "teacher_body_clearance_m": round(body, 3),
                "goal_photo_pose": [round(v, 4) for v in photo],
                "goal_landmark_fraction": round(landmark / len(view), 3),
                "goal_view_dominant": dominant(view),
                "final_frame_landmark_fraction": round(
                    sum(
                        1 for h in final_view if h not in (None, "WallLeft", "WallRight", "EndWall")
                    )
                    / len(final_view),
                    3,
                ),
                "final_frame_view_dominant": dominant(final_view),
                "straight_line_null_min_goal_distance_m": round(abs(goal[1] - start[1]), 3),
            }
            ends.append(photo[:2])
            v = out[r["id"]]
            if not reached:
                failures.append(f"{r['id']}: teacher did not reach goal")
            if min(line, body) < p["clearance_requirement_m"]:
                failures.append(f"{r['id']}: clearance")
            if (
                min(v["goal_landmark_fraction"], v["final_frame_landmark_fraction"])
                < p["min_goal_landmark_fraction"]
            ):
                failures.append(f"{r['id']}: goal view lacks landmarks")
            if v["straight_line_null_min_goal_distance_m"] <= p["arrival_radius_m"]:
                failures.append(f"{r['id']}: reachable by driving straight")
        sep = math.dist(*ends)
        out[scene["group"]] = {"goal_photo_separation_m": round(sep, 3)}
        if sep < p["min_endpoint_separation_m"]:
            failures.append(f"{scene['group']}: endpoints too close")
        own = {0: "PanelEndL", 1: "PanelEndR"}
        for j, r in enumerate(routes):
            v = out[r["id"]]
            if not v["goal_view_dominant"] == v["final_frame_view_dominant"] == own[j]:
                failures.append(f"{r['id']}: goal view not dominated by its own landmark")
    return out, failures


ANALYSIS_PLAN = {
    "unit_of_analysis": "route (12 routes in 6 scene groups); episodes are nested within routes",
    "episodes_per_route": 1,
    "primary_endpoint": "completion: correct stop within arrival radius and no contact",
    "secondary_endpoints": [
        "arrival: any frame within arrival radius",
        "correct stop, wrong stop (>radius), collision episode, timeout",
    ],
    "goal_blind_nulls": "always-left and always-right policies would complete about 6/12 because each group pairs a left and a right goal",
    "decision_rule": "a checkpoint is called competent on held-out only if completion >= 10/12 (one-sided exact binomial against the goal-blind p = 0.5: P(X >= 10) = 0.019); below that the result is reported as not established",
    "goal_swap_control": "each route run with its partner route's goal image (teacher final frame of the partner); goal-conditioning is supported only if the episode ends nearer the partner goal than the route's own goal in >= 10/12 routes and completion against the route's own goal is <= 2/12",
    "retry_rule": "a run that attempted no episode (collector refusal or crash before the first episode) does not consume its slot; one such retry per role, recorded in the ledger; any run that attempted an episode is final and reported",
    "post_render_check": "before scoring, the image distance between the two goal photographs of a group must exceed the distance between repeated renders of one goal; otherwise the group is excluded and reported",
    "reporting": "counts with route denominators per checkpoint; Wilson 95% intervals; per-group table; paired route-level differences between checkpoints",
    "null_baseline": "straight-line drive from the start never comes within the arrival radius (recorded per route; in groups A, C, E it collides with the central obstacle)",
    "interpretation_limit": "descriptive engineering evidence; with 12 routes a Wilson interval spans about +/-0.25 and 6 groups cannot estimate between-group variance; not confirmatory of any scientific claim",
}


if __name__ == "__main__":
    import hashlib

    from navfm.collection.scene_layouts import digest

    repo = Path(__file__).resolve().parents[1]
    spec = build()
    verification, failures = verify(spec)
    if failures:
        sys.exit("refusing to write: " + "; ".join(failures))
    frozen = {
        "name": "heldout_layouts_v1",
        "frozen": "2026-10-09",
        "sealed": True,
        "status": "FROZEN_SPECIFICATION; NOT COLLECTED; NOT SCORED",
        "realises": "configs/splits/arrival_split_v2.json held_out groups",
        "split_v2_sha256": hashlib.sha256(
            (repo / "configs/splits/arrival_split_v2.json").read_bytes()
        ).hexdigest(),
        "generator": "scripts/make_heldout_layouts_v1.py",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scene_layouts_sha256": hashlib.sha256(
            (repo / "src/navfm/collection/scene_layouts.py").read_bytes()
        ).hexdigest(),
        "design": "explicit boxes, never scene_index % 5; new palettes, obstacles and end-wall landmarks. Route starts (x=1.0) and lengths (2.15-2.22 m) are matched to training. The final approach (lateral offset 0.6-0.7 m from the start line, heading +x, ending at x=2.9) is near training endpoints such as straight_run_0001 (2.8, 0.25, heading 0) and layout7-9 behavior4 (2.8, 0.20-0.28, heading -12 deg) but at larger offsets; held-out therefore tests unseen scenes with a modestly shifted final pose, not novel route shapes.",
        "residual_resemblance": "obstacles are plain boxes like the training Obstacle; lighting is the shared normal-light Sun 1500 / Dome 800",
        "policy_clearance_note": "teacher body clearance >= 0.46 m on every route except group E (0.348 m to the central Cabinet); a policy deviating ~0.1-0.2 m toward a central obstacle (groups A, C, E) can contact it, which scores as a collision episode",
        "reserved_scene_indices": sorted({r["scene_index"] for r in spec["routes"]}),
        "ray_cast_limit": "goal_view is a planar ray-cast for boxes rising >=0.3 m; valid for these box scenes only",
        "protocol": spec["protocol"],
        "analysis_plan": ANALYSIS_PLAN,
        "verification": verification,
        "forbidden_uses": [
            "recovery or training collection",
            "stop-rule or threshold calibration",
            "checkpoint selection",
            "controller tuning",
            "pilot, debugging or diagnostic runs",
        ],
        "enforcement": "collect, admission, replay, summary, decompose and audit scripts refuse routes matching a sealed id, reserved scene index or route geometry (Hausdorff <0.1 m) and scenes reproducing half of a sealed scene's boxes; collection needs --unseal-heldout LEDGER_DIR --unseal-role ROLE within the declared slots, all routes, and the frozen protocol budget; scoring needs the collection recorded in that ledger",
        "unseal_rule": "only after the confirmatory protocol is frozen and red-teamed and the evaluated checkpoint sha256 values are declared in configs/splits/heldout_layouts_v1_checkpoints.json; one teacher_goal_traversal run first; policy goals are that run's final recorded frames (goal_source.json sources must lie in it; goal-swap uses the partner route's frame); the pinned ledger ~/navfm-runtime-evidence/heldout_layouts_v1-ledger is archived under gates/ after each run",
        "accepted_residuals": "the seal guards against accidental use by project tooling, not a determined operator: deleting the ledger, shifting a route by >= 0.1 m, a uniform colour tint, copying fewer than half of a scene's boxes, or reusing only the final approach pose evade it",
        "scenes": spec["scenes"],
        "routes": spec["routes"],
    }
    frozen["content_digest"] = digest({"scenes": spec["scenes"], "routes": spec["routes"]})
    Path(sys.argv[1]).write_text(json.dumps(frozen, indent=1) + "\n")
    print(json.dumps(verification, indent=1))
