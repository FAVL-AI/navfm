"""Decompose completed live RGB episodes into progress, route deviation, heading
error and distance-head agreement with true goal distance.

Simulator pose is evaluation-only here; nothing in this script feeds a policy.
"""

from __future__ import annotations

import argparse
import json
import math
from itertools import pairwise
from pathlib import Path

import numpy as np


def ranks(x):
    order = np.argsort(x, kind="stable")
    r = np.empty(len(x))
    r[order] = np.arange(len(x))
    # average ties
    for v in np.unique(x):
        idx = np.where(x == v)[0]
        if len(idx) > 1:
            r[idx] = r[idx].mean()
    return r


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    return float(np.corrcoef(ranks(a), ranks(b))[0, 1])


def point_to_polyline(p, line):
    best = math.inf
    for a, b in pairwise(line):
        ab = b - a
        t = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-12), 0.0, 1.0)
        best = min(best, float(np.linalg.norm(p - (a + t * ab))))
    return best


def wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def decompose(episode: Path) -> dict:
    m = json.loads((episode / "runtime_manifest.json").read_text())
    line = np.asarray(m["route"]["waypoints"], float)
    line[:, 1] += m["route"]["scene_index"] * 20.0
    goal = line[-1]
    captures = m["captures"]
    xy = np.asarray([c["pose"][:2] for c in captures], float)
    yaw = np.asarray([c["pose"][2] for c in captures], float)
    true = np.asarray([c["distance_to_goal_m"] for c in captures], float)
    if not np.allclose(true, np.linalg.norm(xy - goal, axis=1), atol=1e-6):
        raise ValueError(f"{episode}: recorded goal distance disagrees with route endpoint")
    start = line[0]
    lateral = np.asarray([point_to_polyline(p, line) for p in xy])
    bearing = math.atan2(*(goal - xy[-1])[::-1])
    inference = m["inference"]
    frames = [x["frame"] for x in inference]
    predicted = np.asarray([x["predicted_distance"] for x in inference], float)
    true_at_inference = true[np.clip(frames, 0, len(true) - 1)]
    closest = int(np.argmin(true))
    nearest_inference = int(np.argmin(np.abs(np.asarray(frames) - closest)))
    return {
        "route": m["route"].get("id", episode.name),
        "frames": len(captures),
        "termination": m["termination"],
        "policy_stop_frame": m.get("policy_stop_frame"),
        "start_goal_m": float(np.linalg.norm(start - goal)),
        "min_goal_distance_m": float(true[closest]),
        "min_goal_distance_frame": closest,
        "final_goal_distance_m": float(true[-1]),
        "net_progress_m": float(np.linalg.norm(start - goal) - true[-1]),
        "max_lateral_deviation_m": float(lateral.max()),
        "final_lateral_deviation_m": float(lateral[-1]),
        "final_heading_error_rad": float(wrap(bearing - yaw[-1])),
        "arrival_any_frame": bool((true <= 0.5).any()),
        "predicted_distance_min": float(predicted.min()),
        "predicted_distance_at_closest_approach": float(predicted[nearest_inference]),
        "predicted_vs_true_spearman": spearman(predicted, true_at_inference),
        "inferences": len(inference),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--collection", type=Path, action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("output must be new")
    rows = []
    for root in a.collection:
        summary = json.loads((root / "collection.json").read_text())
        for e in summary["episodes"]:
            if e["status"] != "PASS":
                rows.append({"collection": root.name, "route": e["id"], "status": e["status"]})
                continue
            rows.append({"collection": root.name, **decompose(root / e["id"])})
    a.out.write_text(json.dumps({"scope": "ENGINEERING_DIAGNOSIS", "rows": rows}, indent=2) + "\n")
    for r in rows:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
