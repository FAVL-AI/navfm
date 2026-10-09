"""Open-loop ViNT arrival-signal diagnostic on admitted teacher recordings.

Each recording is replayed at 4 Hz (every third 12 Hz frame) through the same
RGBBaseline preprocessing, model and reference stop rule used live. Inputs are
RGB history and goal RGB only; simulator distance is evaluation-only.

Conditions per recording:
  own_goal    - the recording's own goal image (positive)
  wrong_goal  - another route's goal image (negative control)
Test-split routes are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def replay(policy, frames, goal):
    policy.stop_count, policy.stopped = 0, False
    history, rows = [], []
    for i in range(0, len(frames), 3):
        history = [*history, frames[i]][-6:]
        padded = [history[0]] * (6 - len(history)) + history
        p = policy.step(padded, goal)
        rows.append((i, p["predicted_distance"], p["policy_stop"], p["waypoint_normalized"]))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--collection", type=Path, action="append", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        ap.error("output must be new")
    from navfm.collection.rgb_baseline import RGBBaseline

    policy = RGBBaseline(
        a.checkpoint, action_scale_m=0.049994826316833496, stop_enabled=True, max_v=0.1
    )
    episodes = []
    for root in a.collection:
        for e in json.loads((root / "collection.json").read_text())["episodes"]:
            path = root / e["id"]
            m = json.loads((path / "runtime_manifest.json").read_text())
            if e["status"] != "PASS" or m["route"]["split"] == "test":
                continue
            episodes.append((root.name, e["id"], path, m))
    rows = []
    for k, (coll, rid, path, m) in enumerate(episodes):
        captures = m["captures"]
        frames = [
            np.asarray(Image.open(path / "trajectory" / f"{i}.jpg").convert("RGB"))
            for i in range(len(captures))
        ]
        true = np.asarray([c["distance_to_goal_m"] for c in captures], float)
        own = np.asarray(Image.open(path / "goal.png").convert("RGB"))
        other = next(x for x in episodes[k + 1 :] + episodes[:k] if x[1] != rid)
        wrong = np.asarray(Image.open(other[2] / "goal.png").convert("RGB"))
        result = {"collection": coll, "route": rid, "split": m["route"]["split"]}
        for name, goal in (("own_goal", own), ("wrong_goal", wrong)):
            r = replay(policy, frames, goal)
            idx = [x[0] for x in r]
            pred = np.asarray([x[1] for x in r])
            t = true[idx]
            near = t <= 0.5
            stop = next((i for i, _, s, _ in r if s), None)
            result[name] = {
                "goal_sha256": hashlib.sha256(goal.tobytes()).hexdigest()[:16],
                "inferences": len(r),
                "spearman_pred_vs_true": spearman(pred, t),
                "pred_first": float(pred[0]),
                "pred_last": float(pred[-1]),
                "pred_min": float(pred.min()),
                "pred_mean_within_0p5m": float(pred[near].mean()) if near.any() else None,
                "pred_mean_beyond_1m": float(pred[t > 1.0].mean()) if (t > 1.0).any() else None,
                "stop_frame": stop,
                "true_distance_at_stop_m": float(true[stop]) if stop is not None else None,
            }
        result["wrong_goal_source"] = other[1]
        rows.append(result)
        print(json.dumps(result))
    a.out.write_text(
        json.dumps(
            {
                "scope": "ENGINEERING_DIAGNOSIS_OPEN_LOOP_TEACHER_REPLAY",
                "checkpoint_sha256": policy.digest,
                "stop_rule": policy.manifest["stop_rule"],
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
