"""Audit completed closed-loop RGB episodes: command tracking and event timeline.

Tracking compares each held policy command with the base motion actually
realised over the interval it was held (simulator pose, evaluation only), before
the first contact. The timeline orders goal-region entry, arrival declaration,
post-stop settling, route departure, contact and termination.

Thresholds are declared here, before reading results: goal region 0.5 m
(arrival radius), route departure 0.5 m from the route polyline, settled when
the base moves <0.01 m over the last 1 s after a stop, tracking judged only on
held turn commands with |w| >= 0.1 rad/s.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

GOAL_RADIUS_M = 0.5
DEPARTURE_M = 0.5
SETTLE_WINDOW_S = 1.0
SETTLE_M = 0.01
TURN_MIN_RAD_S = 0.1


def point_to_polyline(p, line):
    a, b = line[:-1], line[1:]
    ab = b - a
    t = np.clip(np.einsum("ij,ij->i", p - a, ab) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
    return float(np.min(np.linalg.norm(p - (a + t[:, None] * ab), axis=1)))


def first(mask):
    idx = np.flatnonzero(mask)
    return int(idx[0]) if len(idx) else None


def tracking(times, xy, yaw, inference, stop_frame, contact_frame, lag=0):
    """Per held command: commanded (v, w) vs realised forward speed and yaw rate.

    lag shifts the realised interval by whole decisions to expose actuation delay.
    """
    rows = []
    frames = [r["frame"] for r in inference]
    end = min(x for x in (contact_frame, stop_frame, len(times) - 1) if x is not None)
    for i in range(len(inference) - 1 - lag):
        a, b = frames[i + lag], frames[i + lag + 1]
        if b > end:
            break
        v_cmd, _, w_cmd = inference[i]["command"]
        dt = times[b] - times[a]
        heading = yaw[a] + 0.5 * (yaw[b] - yaw[a])
        d = xy[b] - xy[a]
        rows.append(
            {
                "v_cmd": v_cmd,
                "w_cmd": w_cmd,
                "v_real": float((d[0] * math.cos(heading) + d[1] * math.sin(heading)) / dt),
                "w_real": float((yaw[b] - yaw[a]) / dt),
                "waypoint": inference[i]["waypoint_normalized"][:2],
            }
        )
    return rows


def summarise_tracking(rows, max_v, max_w):
    if not rows:
        return {"held_commands": 0}
    v_cmd = np.array([r["v_cmd"] for r in rows])
    w_cmd = np.array([r["w_cmd"] for r in rows])
    v_real = np.array([r["v_real"] for r in rows])
    w_real = np.array([r["w_real"] for r in rows])
    turning = np.abs(w_cmd) >= TURN_MIN_RAD_S
    moving = v_cmd > 1e-6
    wp = np.array([r["waypoint"] for r in rows], float)
    # Curvature of the circle through the origin, tangent to x, passing the waypoint.
    kappa_wp = 2 * wp[:, 1] / np.maximum((wp**2).sum(1), 1e-12)
    out = {
        "held_commands": len(rows),
        "v_saturated_fraction": float(np.mean(np.isclose(v_cmd, max_v))),
        "w_saturated_fraction": float(np.mean(np.isclose(np.abs(w_cmd), max_w))),
        "v_real_over_cmd_median": float(np.median(v_real[moving] / v_cmd[moving]))
        if moving.any()
        else None,
        "turn_commands": int(turning.sum()),
        "w_real_over_cmd_median": float(np.median(w_real[turning] / w_cmd[turning]))
        if turning.any()
        else None,
        "w_abs_error_median": float(np.median(np.abs(w_real - w_cmd)[turning]))
        if turning.any()
        else None,
        "w_sign_agreement": float(np.mean(np.sign(w_real[turning]) == np.sign(w_cmd[turning])))
        if turning.any()
        else None,
    }
    sel = moving & turning & (np.abs(kappa_wp) > 1e-6)
    if sel.any():
        # Waypoints are in normalised units; convert curvature to 1/m with 0.05 m/unit.
        out["commanded_over_waypoint_curvature_median"] = float(
            np.median((w_cmd[sel] / v_cmd[sel]) / (kappa_wp[sel] / 0.05))
        )
        out["realised_over_waypoint_curvature_median"] = float(
            np.median((w_real[sel] / np.maximum(v_real[sel], 1e-3)) / (kappa_wp[sel] / 0.05))
        )
    return out


def audit(episode: Path) -> dict:
    m = json.loads((episode / "runtime_manifest.json").read_text())
    line = np.asarray(m["route"]["waypoints"], float)
    line[:, 1] += m["route"]["scene_index"] * 20.0
    caps = m["captures"]
    times = np.array([c["simulation_time"] for c in caps])
    xy = np.array([c["pose"][:2] for c in caps], float)
    yaw = np.unwrap(np.array([c["pose"][2] for c in caps], float))
    goal_d = np.array([c["distance_to_goal_m"] for c in caps])
    if not np.allclose(goal_d, np.linalg.norm(xy - line[-1], axis=1), atol=1e-6):
        raise ValueError(f"{episode}: recorded goal distance disagrees with route endpoint")
    lateral = np.array([point_to_polyline(p, line) for p in xy])
    contacts = sorted(m.get("contacts", []), key=lambda c: c["time"])
    contact_frame = int(np.searchsorted(times, contacts[0]["time"])) if contacts else None
    contact_with = (
        sorted({p for p in contacts[0]["paths"] if not p.startswith("/World/Robot")})
        if contacts
        else None
    )
    stop = m.get("policy_stop_frame")
    policy = m.get("policy") or {}
    max_v, max_w = policy.get("max_v", 0.1), policy.get("max_w", 0.4)
    settle = None
    if stop is not None:
        after = times >= times[stop]
        tail = (times >= times[-1] - SETTLE_WINDOW_S) & after
        moved_after = float(np.max(np.linalg.norm(xy[after] - xy[stop], axis=1)))
        tail_motion = (
            float(np.max(np.linalg.norm(xy[tail] - xy[tail][0], axis=1))) if tail.any() else None
        )
        settle = {
            "displacement_after_stop_m": moved_after,
            "final_window_motion_m": tail_motion,
            "settled": tail_motion is not None and tail_motion < SETTLE_M,
            "stop_goal_distance_m": float(goal_d[stop]),
            "final_goal_distance_m": float(goal_d[-1]),
        }
    events = {
        "goal_region_entry_frame": first(goal_d <= GOAL_RADIUS_M),
        "arrival_declared_frame": stop,
        "route_departure_frame": first(lateral > DEPARTURE_M),
        "first_contact_frame": contact_frame,
        "termination_frame": len(caps) - 1,
    }
    ordered = sorted(
        ((k.removesuffix("_frame"), v) for k, v in events.items() if v is not None),
        key=lambda kv: kv[1],
    )
    closest = int(np.argmin(goal_d))
    inference = m["inference"]
    track = tracking(times, xy, yaw, inference, stop, contact_frame)
    track_lag = tracking(times, xy, yaw, inference, stop, contact_frame, lag=1)
    stop_distance = float(goal_d[stop]) if stop is not None else None
    outcome = {
        "arrival": bool((goal_d <= GOAL_RADIUS_M).any()),
        "correct_stop": stop_distance is not None and stop_distance <= GOAL_RADIUS_M,
        "wrong_stop": stop_distance is not None and stop_distance > GOAL_RADIUS_M,
        "collision": contact_frame is not None,
        "timeout": stop is None,
    }
    outcome["completion"] = outcome["correct_stop"] and not outcome["collision"]
    return {
        "route": m["route"]["id"],
        "termination": m["termination"],
        "outcome": outcome,
        "events": events,
        "event_times_s": {
            k: (None if v is None else round(float(times[v] - times[0]), 2))
            for k, v in events.items()
        },
        "event_order": [k for k, _ in ordered],
        "first_event": ordered[0][0] if ordered else None,
        "contact_with": contact_with,
        "closest_goal_m": float(goal_d[closest]),
        "closest_frame": closest,
        "lateral_at_closest_m": float(lateral[closest]),
        "max_lateral_m": float(lateral.max()),
        "settle": settle,
        "tracking": summarise_tracking(track, max_v, max_w),
        "tracking_lag1": summarise_tracking(track_lag, max_v, max_w),
        "control_hz": policy.get("control_hz"),
        "max_v": max_v,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--collection", type=Path, action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--score-heldout",
        type=Path,
        metavar="LEDGER_DIR",
        help="unseal ledger; sealed routes are scored only for collections recorded in it",
    )
    a = p.parse_args()
    if a.out.exists():
        p.error("output must be new")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from navfm.collection.scene_layouts import require_scoring_allowed

    for root in a.collection:
        routes = json.loads((root / "frozen_routes.json").read_text())
        try:
            require_scoring_allowed(
                root.resolve(), routes, Path(__file__).resolve().parents[1], a.score_heldout
            )
        except ValueError as exc:
            p.error(f"{root.name}: {exc}")
    rows = []
    for root in a.collection:
        summary = json.loads((root / "collection.json").read_text())
        for e in summary["episodes"]:
            if e["status"] != "PASS":
                rows.append({"collection": root.name, "route": e["id"], "status": e["status"]})
                continue
            rows.append({"collection": root.name, **audit(root / e["id"])})
    a.out.write_text(
        json.dumps(
            {
                "scope": "ENGINEERING_DIAGNOSIS",
                "thresholds": {
                    "goal_radius_m": GOAL_RADIUS_M,
                    "route_departure_m": DEPARTURE_M,
                    "settle_window_s": SETTLE_WINDOW_S,
                    "settle_m": SETTLE_M,
                    "turn_min_rad_s": TURN_MIN_RAD_S,
                },
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    for r in rows:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
