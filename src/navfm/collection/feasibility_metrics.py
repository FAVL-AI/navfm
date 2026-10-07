"""Offline evaluation only. Never import this module in a deployed policy."""

from __future__ import annotations

import math

import numpy as np


def summarize(manifest, transitions):
    frames = manifest["captures"]
    predictions = manifest["inference"]
    if not frames or len(transitions) != len(frames):
        raise ValueError("nonempty aligned captures and transitions required")
    stop_frames = [r["physics_frame"] for r in predictions if r["policy_stop"]]
    distances = [frames[i]["distance_to_goal_m"] for i in stop_frames]
    radius = manifest["fixture"]["goal_radius_m"]
    correct = sum(distance <= radius for distance in distances)
    premature = len(distances) - correct
    contacts = manifest["contacts"]
    final_in_goal = frames[-1]["distance_to_goal_m"] <= radius
    successful_stop = bool(
        distances
        and distances[-1] <= radius
        and not contacts
        and manifest["metrics"]["termination"] == "policy_stop"
    )
    return {
        "episodes": 1,
        "stop_events": len(distances),
        "correct_stop_events": correct,
        "premature_stop_events": premature,
        "correct_stop_rate": correct / len(distances) if distances else None,
        "premature_stop_rate": premature / len(distances) if distances else None,
        "navigation_success_episodes": int(successful_stop),
        "final_position_in_goal_episodes": int(final_in_goal),
        "reported_collision_episodes": int(bool(contacts)),
        "collision_monitor_positive_control_verified": False,
        "envelope_violation_duration_s": sum(
            f["step_duration_s"]
            for f in frames
            if f["aabb_clearance_m"] < manifest["fixture"]["safety_clearance_m"]
        ),
        "path_length_m": sum(
            math.dist(t["pose_before"][:2], t["pose_after"][:2]) for t in transitions
        ),
        "final_goal_distance_m": frames[-1]["distance_to_goal_m"],
        "policy_latency_p95_ms": float(np.percentile([r["latency_ms"] for r in predictions], 95)),
        "policy_latency_max_ms": max(r["latency_ms"] for r in predictions),
        "recording_loop_p95_ms": float(np.percentile([f["wall_loop_ms"] for f in frames], 95)),
        "simulation_duration_s": sum(f["step_duration_s"] for f in frames),
        "missing_frames": 0,
        "termination": manifest["metrics"]["termination"],
    }
