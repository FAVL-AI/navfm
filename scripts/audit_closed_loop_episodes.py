"""Audit completed closed-loop RGB episodes: command tracking and event timeline.

Tracking compares each held policy command with the base motion actually
realised over the interval it was held (simulator pose, evaluation only), before
the first contact. The timeline orders goal-region entry, arrival declaration,
post-stop settling, route departure, contact and termination.

Every outcome measure comes from navfm.collection.episode_measures, the single
definition (configs/eval/arrival_measures_v1.json); this script adds timelines
and tracking diagnostics around it.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from navfm.collection.episode_measures import (  # noqa: E402
    ARRIVAL_RADIUS_M,
    DEPARTURE_M,
    SETTLE_MOTION_M,
    SETTLE_WINDOW_S,
    TURN_MIN_RAD_S,
    episode_measures,
    turn_tracking,
)


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


def audit(episode: Path, goal_image_xy=None) -> dict:
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
    measures = episode_measures(m, line, goal_image_xy)
    events = {
        "goal_region_entry_frame": measures["goal_region_entry_frame"],
        "arrival_declared_frame": stop,
        "route_departure_frame": measures["route_departure_frame"],
        "first_contact_frame": measures["first_contact_frame"],
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
    return {
        "route": m["route"]["id"],
        "termination": m["termination"],
        "measures": measures,
        "events": events,
        "event_times_s": {
            k: (None if v is None else round(float(times[v] - times[0]), 2))
            for k, v in events.items()
        },
        "event_order": [k for k, _ in ordered],
        "first_event": ordered[0][0] if ordered else None,
        "contact_with": contact_with,
        "closest_endpoint_m": float(goal_d[closest]),
        "closest_endpoint_frame": closest,
        "lateral_at_closest_endpoint_m": float(lateral[closest]),
        "base_controller": m.get("base_controller"),
        "component_variant": m.get("component_variant"),
        "components": component_trace(m["inference"], times, m),
        "max_lateral_m": float(lateral.max()),
        "tracking": summarise_tracking(track, max_v, max_w),
        "tracking_diagnostic": turn_tracking(
            [r["w_cmd"] for r in track], [r["w_real"] for r in track]
        ),
        "tracking_lag1": summarise_tracking(track_lag, max_v, max_w),
        "control_hz": policy.get("control_hz"),
        "max_v": max_v,
    }


def goal_identity(goal_root: Path, episode: Path, m: dict) -> dict:
    """Verify the goal the episode consumed is the declared source frame.

    Three representations exist and each is checked against its own record:
    the declared source frame (encoded JPEG bytes, sha256 in goal_source.json
    and the episode's goal_source_frame), the goal-root copy (must be the same
    bytes), and the episode's goal.png (a PNG of the decoded RGB uint8 pixels the
    model consumed; sha256 recorded as fixed_goal_sha256). The source and the
    episode copy must decode to identical pixels.
    """
    import hashlib

    from PIL import Image

    route_id = m["route"]["id"]
    if not (goal_root / "goal_source.json").exists():
        raise ValueError(f"{goal_root}: goal root declares no goal_source.json")
    declared = json.loads((goal_root / "goal_source.json").read_text())["goals"][route_id]
    recorded = m.get("goal_source_frame") or {}
    if recorded.get("source") != declared["source"] or recorded.get("frame") != declared["frame"]:
        raise ValueError(f"{episode}: goal root does not match the episode's goal source")
    root_bytes = (goal_root / route_id / "goal.png").read_bytes()
    source_sha = hashlib.sha256(root_bytes).hexdigest()
    if not source_sha == declared["source_sha256"] == recorded.get("source_sha256"):
        raise ValueError(f"{episode}: goal-root bytes differ from the declared source frame")
    episode_bytes = (episode / "goal.png").read_bytes()
    episode_sha = hashlib.sha256(episode_bytes).hexdigest()
    if episode_sha != m.get("fixed_goal_sha256"):
        raise ValueError(f"{episode}: episode goal file differs from its recorded hash")
    source_px = np.asarray(Image.open(goal_root / route_id / "goal.png").convert("RGB"))
    consumed_px = np.asarray(Image.open(episode / "goal.png").convert("RGB"))
    if source_px.shape != consumed_px.shape or not np.array_equal(source_px, consumed_px):
        raise ValueError(f"{episode}: consumed goal pixels differ from the declared source")
    return {
        "source_frame": declared["source"],
        "source_encoded_sha256": source_sha,
        "episode_png_sha256": episode_sha,
        "consumed_pixels_sha256": hashlib.sha256(consumed_px.tobytes()).hexdigest(),
        "consumed_pixels_shape": list(consumed_px.shape),
        "consumed_pixels_dtype": str(consumed_px.dtype),
        "verified": "source bytes == declared; episode file == recorded; decoded pixels equal",
    }


def goal_xy(goal_root, episode: Path):
    """Capture position and verified identity of the goal the episode used."""
    m = json.loads((episode / "runtime_manifest.json").read_text())
    if not m.get("policy"):
        return None, None
    if goal_root is None:
        raise ValueError(f"{episode}: policy episode needs --goal-root to score its goal")
    identity = goal_identity(goal_root, episode, m)
    declared = json.loads((goal_root / "goal_source.json").read_text())["goals"][m["route"]["id"]]
    source = json.loads((goal_root / m["route"]["id"] / "runtime_manifest.json").read_text())
    return source["captures"][declared["frame"]]["pose"][:2], identity


def node_poses(manifest) -> np.ndarray | None:
    """Teacher-traversal positions of the episode's chain nodes (evaluation only)."""
    tm = manifest.get("topomap")
    if not tm:
        return None
    chain = json.loads((Path(tm["root"]) / "chain.json").read_text())["routes"][
        manifest["route"]["id"]
    ]
    teach = json.loads((Path(chain["traversal"]) / "runtime_manifest.json").read_text())
    return np.array([teach["captures"][n["frame"]]["pose"][:2] for n in chain["nodes"]])


def component_trace(inference, times, manifest) -> dict:
    """Localisation errors against the pose-true node, lost decisions, verification delay.

    Primary localisation measure: decisions whose current or followed node is
    more than one node from the chain node nearest the robot's true position.
    The pose-true node is evaluation-only. Jump counts are reported too, but a
    bounded variant lowers them partly by construction.
    """
    chain = [r.get("chain") for r in inference]
    if not any(chain):
        return None
    poses = node_poses(manifest)
    caps = manifest["captures"]
    wrong_closest = wrong_followed = 0
    for r, c in zip(inference, chain, strict=True):
        true = int(
            np.argmin(np.linalg.norm(poses - np.array(caps[r["frame"]]["pose"][:2]), axis=1))
        )
        wrong_closest += int(abs(c["closest_node"] - true) > 1)
        wrong_followed += int(abs(c["followed_node"] - true) > 1)
    prev, jumps, lost, events = 0, 0, 0, {}
    first_reached = stop = None
    for k, (r, c) in enumerate(zip(inference, chain, strict=True)):
        cur = c["closest_node"]
        jumps += int(cur - prev > 1 or cur < prev)
        prev = cur
        lost += int(bool(c.get("lost")))
        events[c.get("event", "upstream")] = events.get(c.get("event", "upstream"), 0) + 1
        if c["reached_goal"] and first_reached is None:
            first_reached = k
        if r["policy_stop"] and stop is None:
            stop = k
    delay = None
    if first_reached is not None and stop is not None:
        a, b = inference[first_reached]["frame"], inference[stop]["frame"]
        delay = {"decisions": stop - first_reached, "seconds": float(times[b] - times[a])}
    verifying = any(r.get("verification") is not None for r in inference)
    return {
        "decisions": len(inference),
        "decisions_closest_off_true_node": wrong_closest,
        "decisions_followed_off_true_node": wrong_followed,
        "localisation_jumps": jumps,
        "lost_decisions": lost,
        "events": events,
        "chain_reached_first_decision": first_reached,
        "verification_delay": delay if verifying else "NOT_APPLICABLE",
        "verification_rejected_decisions": sum(
            1 for r in inference if r.get("verification") == "pending"
        ),
    }


def scorer_provenance() -> dict:
    import hashlib
    import subprocess

    files = [
        "scripts/audit_closed_loop_episodes.py",
        "src/navfm/collection/episode_measures.py",
        "configs/eval/arrival_measures_v1.json",
    ]
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain", *files], capture_output=True, text=True
    ).stdout.strip()
    return {
        "measures_version": json.loads((REPO / files[2]).read_text())["name"],
        "git_head": head,
        "scorer_files_modified_since_head": bool(dirty),
        "sha256": {f: hashlib.sha256((REPO / f).read_bytes()).hexdigest() for f in files},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--collection", type=Path, action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--goal-root", type=Path, help="score distance to the goal image's capture pose")
    p.add_argument(
        "--score-heldout",
        type=Path,
        metavar="LEDGER_DIR",
        help="unseal ledger; sealed routes are scored only for collections recorded in it",
    )
    a = p.parse_args()
    if a.out.exists():
        p.error("output must be new")
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
            xy_goal, identity = goal_xy(a.goal_root, root / e["id"])
            rows.append(
                {
                    "collection": root.name,
                    **audit(root / e["id"], xy_goal),
                    "goal_identity": identity,
                }
            )
    a.out.write_text(
        json.dumps(
            {
                "scope": "ENGINEERING_DIAGNOSIS",
                "scorer": scorer_provenance(),
                "thresholds": {
                    "goal_radius_m": ARRIVAL_RADIUS_M,
                    "route_departure_m": DEPARTURE_M,
                    "settle_window_s": SETTLE_WINDOW_S,
                    "settle_m": SETTLE_MOTION_M,
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
