"""The single definition of episode measures for closed-loop arrival evaluation.

configs/eval/arrival_measures_v1.json describes these in prose; this module is
the computation every report must call. Collector `metrics` blocks are not
authoritative. Inputs are the runtime manifest (simulator pose is used only for
evaluation) and the scoring goal positions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

ARRIVAL_RADIUS_M = 0.5
SETTLE_WINDOW_S = 1.0
SETTLE_MOTION_M = 0.01
DEPARTURE_M = 0.5
TURN_MIN_RAD_S = 0.1
MIN_TURN_COMMANDS = 20


def _first(mask) -> int | None:
    idx = np.flatnonzero(mask)
    return int(idx[0]) if len(idx) else None


def _to_polyline(p, line) -> float:
    a, b = line[:-1], line[1:]
    ab = b - a
    t = np.clip(np.einsum("ij,ij->i", p - a, ab) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
    return float(np.min(np.linalg.norm(p - (a + t[:, None] * ab), axis=1)))


def contact_frame(manifest: Mapping, times: np.ndarray) -> int | None:
    """First capture frame at or after the first contact report (searchsorted, left)."""
    contacts = manifest.get("contacts") or []
    if not contacts:
        return None
    return int(np.searchsorted(times, min(c["time"] for c in contacts), side="left"))


def episode_measures(
    manifest: Mapping,
    route_line: Sequence,
    goal_image_xy: Sequence[float] | None,
) -> dict:
    """Per-episode measures.

    The scoring goal is the goal image's capture position when known, else the
    route endpoint; both distances are reported. The stop is the latched policy
    decision frame. Settling needs SETTLE_WINDOW_S of frames after the stop,
    otherwise it is UNMEASURABLE and the stop cannot count as correct.
    """
    caps = manifest["captures"]
    times = np.array([c["simulation_time"] for c in caps], float)
    xy = np.array([c["pose"][:2] for c in caps], float)
    line = np.asarray(route_line, float)
    endpoint = line[-1]
    goal = np.asarray(goal_image_xy if goal_image_xy is not None else endpoint, float)
    d_goal = np.linalg.norm(xy - goal, axis=1)
    d_end = np.linalg.norm(xy - endpoint, axis=1)
    lateral = np.array([_to_polyline(p, line) for p in xy])
    stop = manifest.get("policy_stop_frame")
    contact = contact_frame(manifest, times)
    task_end = stop if stop is not None else len(caps) - 1
    contact_before_end = contact is not None and contact <= task_end
    contact_after_stop = stop is not None and any(
        int(np.searchsorted(times, c["time"], side="left")) > stop
        for c in manifest.get("contacts") or []
    )
    entry = _first(d_goal <= ARRIVAL_RADIUS_M)
    navigation_success = entry is not None and (contact is None or entry < contact)
    # Region time counts frames up to the task end and before any contact.
    horizon = min(task_end, contact - 1 if contact is not None else task_end)
    in_region_s = float(
        np.sum(d_goal[: horizon + 1] <= ARRIVAL_RADIUS_M) * np.median(np.diff(times))
    )
    settle = "NO_STOP"
    stop_distance = final_distance = displacement_after_stop = None
    if stop is not None:
        stop_distance = float(d_goal[stop])
        final_distance = float(d_goal[-1])
        if times[-1] - times[stop] < SETTLE_WINDOW_S:
            settle = "UNMEASURABLE"
        else:
            tail = times >= times[-1] - SETTLE_WINDOW_S
            motion = float(np.max(np.linalg.norm(xy[tail] - xy[tail][0], axis=1)))
            settle = "SETTLED" if motion < SETTLE_MOTION_M else "MOVING"
        displacement_after_stop = float(np.max(np.linalg.norm(xy[stop:] - xy[stop], axis=1)))
    correct_stop = (
        stop_distance is not None
        and final_distance is not None
        and stop_distance <= ARRIVAL_RADIUS_M
        and settle == "SETTLED"
        and final_distance <= ARRIVAL_RADIUS_M
    )
    wrong_stop = stop is not None and not correct_stop
    departure = _first(lateral > DEPARTURE_M)
    return {
        "scoring_goal": "goal_image_capture" if goal_image_xy is not None else "route_endpoint",
        "goal_offset_from_endpoint_m": float(np.linalg.norm(goal - endpoint)),
        "min_goal_distance_m": float(d_goal.min()),
        "min_endpoint_distance_m": float(d_end.min()),
        "final_goal_distance_m": float(d_goal[-1]),
        "goal_region_entry_frame": entry,
        "time_in_goal_region_s": in_region_s,
        "navigation_success": bool(navigation_success),
        "stop_frame": stop,
        "stop_goal_distance_m": stop_distance,
        "settle": settle,
        "displacement_after_stop_m": displacement_after_stop,
        "correct_stop": bool(correct_stop),
        "wrong_stop": bool(wrong_stop),
        "timeout": stop is None,
        "first_contact_frame": contact,
        "collision_before_task_end": bool(contact_before_end),
        "contact_after_stop": bool(contact_after_stop),
        "completion": bool(correct_stop and not contact_before_end),
        "route_departure_frame": departure,
        "max_lateral_m": float(lateral.max()),
        "elapsed_s": float(times[task_end] - times[0]),
        "exposure_s": float(times[-1] - times[0]),
        "path_length_m": float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()),
        "stop_rule": (manifest.get("policy") or {}).get("stop_rule"),
        "frames_recorded": len(caps),
        "max_steps_budget": manifest.get("max_steps"),
    }


def turn_tracking(setpoints: Sequence[float], realised: Sequence[float]) -> dict:
    """In-episode diagnostic: realised-on-setpoint slope over held turn commands.

    The setpoint is the yaw rate the base controller is asked to realise (policy
    output, before any open-loop gain). Fewer than MIN_TURN_COMMANDS usable
    commands is reported as INSUFFICIENT rather than as a number.
    """
    w = np.asarray(setpoints, float)
    r = np.asarray(realised, float)
    use = np.abs(w) >= TURN_MIN_RAD_S
    if use.sum() < MIN_TURN_COMMANDS:
        return {"status": "INSUFFICIENT", "turn_commands": int(use.sum())}
    slope = float(w[use] @ r[use] / (w[use] @ w[use]))
    return {
        # A diagnostic band, never a qualification (that is the free-space replay).
        "status": "WITHIN_BAND" if 0.8 <= slope <= 1.2 else "OUTSIDE_BAND",
        "turn_commands": int(use.sum()),
        "slope": slope,
    }


def admitted_rate(frozen_routes, collection: Mapping, admission: Mapping | None) -> dict:
    """Admitted trajectories over planned episodes, counted from artefacts.

    planned = the collection's frozen routes (one run each); every planned route
    is classified exactly once: never_run, failed, refused, rejected or admitted.
    """
    episodes = {e["id"]: e for e in collection.get("episodes", [])}
    verdicts = {}
    if admission is not None:
        verdicts = {t["id"]: bool(t["admitted"]) for t in admission["trajectories"]}
    counts = {"never_run": 0, "failed": 0, "refused": 0, "rejected": 0, "admitted": 0}
    for route in frozen_routes:
        e = episodes.get(route["id"])
        if e is None:
            counts["never_run"] += 1
        elif str(e["status"]).startswith("REFUSED"):
            counts["refused"] += 1
        elif e["status"] != "PASS":
            counts["failed"] += 1
        elif verdicts.get(route["id"]):
            counts["admitted"] += 1
        else:
            counts["rejected"] += 1
    planned = len(frozen_routes)
    if planned == 0:
        raise ValueError("no planned routes")
    return {"planned": planned, **counts, "rate": counts["admitted"] / planned}
