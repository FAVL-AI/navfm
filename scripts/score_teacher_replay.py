"""Open-loop ViNT arrival-signal diagnostic on admitted teacher recordings.

Each recording is replayed at 4 Hz (every third 12 Hz frame) through the same
RGBBaseline preprocessing, model and reference stop rule used live. Inputs are
RGB history and goal RGB only; simulator distance is evaluation-only.

Conditions per recording:
  own_goal         - the recording's own goal image (positive)
  wrong_goal       - another route's goal image (negative control)
  goal_as_current  - the goal image repeated as the whole history (floor control)
Test-split routes are excluded; with --admission only admitted recordings are used.

Label units: upstream ViNT labels are step counts, (goal_time - curr_time) //
waypoint_spacing, positives 1..max_dist_cat and negatives max_dist_cat. In this
corpus one step is `--step-m` metres of teacher motion, so true distance in label
units is distance_to_goal_m / step_m. Predicted distance is never read as metres.

Stop rules reported (neither fitted to these recordings):
  project_rule  - three consecutive predictions <=1 and waypoint <=0.15 m (rgb_baseline)
  upstream_t3   - first prediction <= 3, the pinned deployment close_threshold default
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


def fit_slope(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or np.ptp(x) == 0:
        return None
    slope, intercept = np.polyfit(x, y, 1)
    return {"slope": float(slope), "intercept": float(intercept)}


def replay(policy, frames, goal):
    policy.stop_count, policy.stopped = 0, False
    history, rows = [], []
    for i in range(0, len(frames), 3):
        history = [*history, frames[i]][-6:]
        padded = [history[0]] * (6 - len(history)) + history
        p = policy.step(padded, goal)
        rows.append((i, p["predicted_distance"], p["policy_stop"], p["waypoint_normalized"]))
    return rows


def admitted_set(path):
    if path is None:
        return None
    admission = json.loads(path.read_text())
    return {
        (Path(t["collection"]).name, t["id"]) for t in admission["trajectories"] if not t["errors"]
    }


def condition(policy, frames, goal, true, step_m):
    r = replay(policy, frames, goal)
    idx = [x[0] for x in r]
    pred = np.asarray([x[1] for x in r])
    t = true[idx]
    near = t <= 0.5
    stop = next((i for i, _, s, _ in r if s), None)
    t3 = next((i for i, d, _, _ in r if d <= 3.0), None)
    labels = np.minimum(t / step_m, 20.0)
    return {
        "goal_sha256": hashlib.sha256(goal.tobytes()).hexdigest()[:16],
        "inferences": len(r),
        "spearman_pred_vs_true": spearman(pred, t),
        "fit_pred_vs_label_units": fit_slope(labels, pred),
        "pred_first": float(pred[0]),
        "pred_last": float(pred[-1]),
        "pred_min": float(pred.min()),
        "pred_mean_within_0p5m": float(pred[near].mean()) if near.any() else None,
        "label_units_mean_within_0p5m": float(labels[near].mean()) if near.any() else None,
        "pred_mean_beyond_1m": float(pred[t > 1.0].mean()) if (t > 1.0).any() else None,
        "project_rule_stop_frame": stop,
        "true_distance_at_project_stop_m": float(true[stop]) if stop is not None else None,
        "upstream_t3_frame": t3,
        "true_distance_at_upstream_t3_m": float(true[t3]) if t3 is not None else None,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", type=Path, action="append", required=True)
    ap.add_argument("--collection", type=Path, action="append", required=True)
    ap.add_argument("--admission", type=Path, help="admission.json; restrict to admitted")
    ap.add_argument("--step-m", type=float, default=0.049994826316833496)
    ap.add_argument(
        "--goal-override-root",
        type=Path,
        help="score own_goal against <root>/<route>/goal.png (pose-identical recapture)",
    )
    ap.add_argument(
        "--include-retired-test",
        action="store_true",
        help="diagnostic only: include retired corpus-test routes",
    )
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        ap.error("output must be new")
    from navfm.collection.rgb_baseline import RGBBaseline

    admitted = admitted_set(a.admission)
    episodes = []
    for root in a.collection:
        from navfm.collection.scene_layouts import refuse_sealed

        try:
            # Held-out routes never enter training, replay diagnostics or summaries.
            refuse_sealed(
                json.loads((root / "frozen_routes.json").read_text()),
                Path(__file__).resolve().parents[1],
            )
        except ValueError as exc:
            ap.error(f"{root.name}: {exc}")
        for e in json.loads((root / "collection.json").read_text())["episodes"]:
            path = root / e["id"]
            m = json.loads((path / "runtime_manifest.json").read_text())
            if e["status"] != "PASS" or (
                m["route"]["split"] == "test" and not a.include_retired_test
            ):
                continue
            if admitted is not None and (root.name, e["id"]) not in admitted:
                continue
            episodes.append((root.name, e["id"], path, m))
    loaded = []
    for k, (coll, rid, path, m) in enumerate(episodes):
        captures = m["captures"]
        frames = [
            np.asarray(Image.open(path / "trajectory" / f"{i}.jpg").convert("RGB"))
            for i in range(len(captures))
        ]
        true = np.asarray([c["distance_to_goal_m"] for c in captures], float)
        goal_dir = a.goal_override_root / rid if a.goal_override_root else path
        own = np.asarray(Image.open(goal_dir / "goal.png").convert("RGB"))
        # Negatives come from a different scene: same-scene route variants end
        # 0.25 m apart, so their goals are not wrong places.
        other = next(
            (
                x
                for x in episodes[k + 1 :] + episodes[:k]
                if x[3]["route"]["scene_index"] != m["route"]["scene_index"]
            ),
            None,
        )
        if other is None:
            raise ValueError(f"no cross-scene negative available for {rid}")
        # The negative control uses the same goal type as the positive.
        wrong_dir = a.goal_override_root / other[1] if a.goal_override_root else other[2]
        wrong = np.asarray(Image.open(wrong_dir / "goal.png").convert("RGB"))
        loaded.append((coll, rid, m, frames, true, own, wrong, other))
    report = {
        "scope": "ENGINEERING_DIAGNOSIS_OPEN_LOOP_TEACHER_REPLAY",
        "step_m": a.step_m,
        "goal_override_root": str(a.goal_override_root) if a.goal_override_root else None,
        "includes_retired_test": a.include_retired_test,
        "recordings": [[c, r] for c, r, *_ in loaded],
        "checkpoints": [],
    }
    for checkpoint in a.checkpoint:
        policy = RGBBaseline(checkpoint, action_scale_m=a.step_m, stop_enabled=True, max_v=0.1)
        rows = []
        for coll, rid, m, frames, true, own, wrong, other in loaded:
            result = {"collection": coll, "route": rid, "split": m["route"]["split"]}
            result["own_goal"] = condition(policy, frames, own, true, a.step_m)
            result["wrong_goal"] = condition(policy, frames, wrong, true, a.step_m)
            policy.stop_count, policy.stopped = 0, False
            floor = policy.step([own] * 6, own)
            result["goal_as_current_pred"] = floor["predicted_distance"]
            result["wrong_goal_source"] = other[1]
            result["wrong_goal_scene_index"] = other[3]["route"]["scene_index"]
            rows.append(result)
            print(json.dumps({"checkpoint": policy.digest[:12], **result}))
        report["checkpoints"].append(
            {
                "path": str(checkpoint),
                "sha256": policy.digest,
                "stop_rule": policy.manifest["stop_rule"],
                "rows": rows,
            }
        )
        del policy
    a.out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
