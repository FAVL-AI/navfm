"""Calibrate localisation-repair and arrival-verification thresholds on development recordings.

Evaluation-only labels (simulator pose) define on-route/lost decisions and
near/far goal frames; they are used here to choose thresholds and never enter a
policy decision. The recordings used here must not be the evaluation episodes.

Rules, declared before computing:
- lost_enter = 95th percentile of the window-minimum distance on correctly
  localised decisions (argmin within one node of the true nearest node);
  lost_exit = median of the same distribution.
- verify_threshold: the largest threshold whose false-accept rate on far frames
  (> 0.75 m from the goal-image pose) is <= 2 %; frames 0.5-0.75 m are a margin
  band excluded from both classes; true-accept rate on near frames (<= 0.5 m)
  is reported, not optimised.
- pixel control: normalised cross-correlation of 80x60 grayscale current frame
  and goal image; threshold by the same rule (accept when NCC >= threshold).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
NEAR_M, FAR_M, MAX_FAR_ACCEPT = 0.5, 0.75, 0.02


def ncc(a, b) -> float:
    def prep(x):
        g = np.asarray(Image.fromarray(x).convert("L").resize((80, 60)), float)
        g -= g.mean()
        return g / (np.linalg.norm(g) + 1e-9)

    return float((prep(a) * prep(b)).sum())


def threshold_low_accept(near, far):
    """Largest t with mean(far <= t) <= MAX_FAR_ACCEPT (accept when value <= t)."""
    far = np.sort(np.asarray(far, float))
    k = int(math.floor(MAX_FAR_ACCEPT * len(far)))
    t = float(far[k] - 1e-6) if k < len(far) else float(far[-1])
    return t, float(np.mean(np.asarray(near) <= t)), float(np.mean(far <= t))


def threshold_high_accept(near, far):
    """Smallest t with mean(far >= t) <= MAX_FAR_ACCEPT (accept when value >= t)."""
    far = np.sort(np.asarray(far, float))[::-1]
    k = int(math.floor(MAX_FAR_ACCEPT * len(far)))
    t = float(far[k] + 1e-6) if k < len(far) else float(far[-1])
    return t, float(np.mean(np.asarray(near) >= t)), float(np.mean(far >= t))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--goal-root", type=Path, required=True)
    p.add_argument(
        "--chain-root", type=Path, required=True, help="true chains of the lost calibration runs"
    )
    p.add_argument("--lost-collection", type=Path, action="append", required=True)
    p.add_argument("--verify-collection", type=Path, action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("output must be new")
    import sys

    sys.path.insert(0, str(REPO / "src"))
    from navfm.collection.rgb_baseline import RGBBaseline

    goals = json.loads((a.goal_root / "goal_source.json").read_text())["goals"]
    chains = json.loads((a.chain_root / "chain.json").read_text())["routes"]

    # Lost thresholds from logged window distances on true-chain runs.
    on_route, off_route = [], []
    for root in a.lost_collection:
        for e in json.loads((root / "collection.json").read_text())["episodes"]:
            m = json.loads((root / e["id"] / "runtime_manifest.json").read_text())
            nodes = chains[e["id"]]["nodes"]
            teach = json.loads(
                (Path(chains[e["id"]]["traversal"]) / "runtime_manifest.json").read_text()
            )
            npose = np.array([teach["captures"][n["frame"]]["pose"][:2] for n in nodes])
            for r in m["inference"]:
                xy = np.array(m["captures"][r["frame"]]["pose"][:2])
                d_nodes = np.linalg.norm(npose - xy, axis=1)
                true = int(np.argmin(d_nodes))
                dmin = float(min(r["window_distances"]))
                if d_nodes.min() > 0.5:
                    off_route.append(dmin)
                elif abs(r["chain"]["argmin_node"] - true) <= 1:
                    on_route.append(dmin)
    lost_enter = float(np.percentile(on_route, 95))
    lost_exit = float(np.median(on_route))

    # Verification thresholds by replaying requested-goal distance on decision histories.
    policy = RGBBaseline(
        a.checkpoint, action_scale_m=0.05, stop_enabled=False, max_v=0.1, control_period_s=0.5
    )
    learned_near, learned_far, pix_near, pix_far, sources = [], [], [], [], []
    for root in a.verify_collection:
        for e in json.loads((root / "collection.json").read_text())["episodes"]:
            ep = root / e["id"]
            m = json.loads((ep / "runtime_manifest.json").read_text())
            rid = m["route"]["id"]
            src = json.loads((a.goal_root / rid / "runtime_manifest.json").read_text())
            gx, gy = src["captures"][goals[rid]["frame"]]["pose"][:2]
            goal = np.asarray(Image.open(a.goal_root / rid / "goal.png").convert("RGB"))
            inf = m["inference"]
            sources.append(str(ep))
            for k, r in enumerate(inf):
                x, y = m["captures"][r["frame"]]["pose"][:2]
                dist = math.hypot(x - gx, y - gy)
                if NEAR_M < dist <= FAR_M:
                    continue
                frames = [inf[j]["frame"] for j in range(max(0, k - 5), k + 1)]
                frames = [frames[0]] * (6 - len(frames)) + frames
                hist = [
                    np.asarray(Image.open(ep / "trajectory" / f"{q}.jpg").convert("RGB"))
                    for q in frames
                ]
                learned = policy.step(hist, goal)["predicted_distance"]
                pix = ncc(hist[-1], goal)
                (learned_near if dist <= NEAR_M else learned_far).append(learned)
                (pix_near if dist <= NEAR_M else pix_far).append(pix)
    t_learned, tar_l, far_l = threshold_low_accept(learned_near, learned_far)
    t_pix, tar_p, far_p = threshold_high_accept(pix_near, pix_far)
    result = {
        "scope": "DEVELOPMENT_CALIBRATION",
        "checkpoint_sha256": hashlib.sha256(a.checkpoint.read_bytes()).hexdigest(),
        "lost": {
            "collections": [str(c) for c in a.lost_collection],
            "on_route_decisions": len(on_route),
            "off_route_decisions": len(off_route),
            "lost_enter": lost_enter,
            "lost_exit": lost_exit,
            "off_route_window_min_median": float(np.median(off_route)) if off_route else None,
            "on_route_above_enter": float(np.mean(np.asarray(on_route) > lost_enter)),
            "off_route_above_enter": float(np.mean(np.asarray(off_route) > lost_enter))
            if off_route
            else None,
        },
        "verification": {
            "episodes": sources,
            "near_frames": len(learned_near),
            "far_frames": len(learned_far),
            "learned": {"threshold": t_learned, "true_accept": tar_l, "false_accept": far_l},
            "pixel_ncc": {"threshold": t_pix, "true_accept": tar_p, "false_accept": far_p},
        },
        "rules": __doc__,
    }
    a.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rules"}, indent=1))


if __name__ == "__main__":
    main()
