"""Calibrate the v2 recovery exit threshold on development recordings (rule declared first).

Rule, declared before computing:
- Population: decisions of the calibration recordings whose argmin node is within
  one node of the pose-true nearest node and whose robot position is within
  0.5 m of a chain node ("correctly localised, on route"), as for the v1 lost
  thresholds (calibrate_components.py). Pose labels are evaluation-only here.
- exit = 90th percentile of that population's window-minimum distance. It must
  be below lost_enter (v1: 95th percentile, 6.752), so relocalisation needs
  evidence that on-route tracking meets nine times in ten, and entry needs
  evidence it meets only one time in twenty.
- Reported, not optimised: the fraction of off-route decisions (> 0.5 m from
  every node) whose window minimum is <= exit, an upper bound on spurious
  relocalisation opportunities for forward-facing views. Rotated (scan) views are
  absent from these recordings; their behaviour is measured in the recovery trials.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--chain-root", type=Path, required=True)
    p.add_argument("--collection", type=Path, action="append", required=True)
    p.add_argument("--lost-enter", type=float, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("output must be new")
    chains = json.loads((a.chain_root / "chain.json").read_text())["routes"]
    on, off, episodes = [], [], []
    for root in a.collection:
        for e in json.loads((root / "collection.json").read_text())["episodes"]:
            if e["status"] != "PASS":
                continue
            m = json.loads((root / e["id"] / "runtime_manifest.json").read_text())
            chain = chains[m["route"]["id"]]
            teach = json.loads((Path(chain["traversal"]) / "runtime_manifest.json").read_text())
            npose = np.array([teach["captures"][n["frame"]]["pose"][:2] for n in chain["nodes"]])
            episodes.append(str(root / e["id"]))
            stop = m.get("policy_stop_frame")
            for r in m["inference"]:
                if stop is not None and r["frame"] > stop:
                    continue  # stationary post-stop decisions are not tracking evidence
                xy = np.array(m["captures"][r["frame"]]["pose"][:2])
                d = np.linalg.norm(npose - xy, axis=1)
                true = int(np.argmin(d))
                dmin = float(min(r["window_distances"]))
                if d.min() > 0.5:
                    off.append(dmin)
                elif abs(r["chain"]["argmin_node"] - true) <= 1:
                    on.append(dmin)
    exit_ = float(np.percentile(on, 90))
    if not exit_ < a.lost_enter:
        raise SystemExit(f"rule violated: exit {exit_} is not below lost_enter {a.lost_enter}")
    result = {
        "scope": "DEVELOPMENT_CALIBRATION",
        "chain_root": str(a.chain_root.resolve()),
        "episodes": episodes,
        "on_route_decisions": len(on),
        "off_route_decisions": len(off),
        "exit": exit_,
        "lost_enter": a.lost_enter,
        "on_route_at_or_below_exit": float(np.mean(np.asarray(on) <= exit_)),
        "off_route_at_or_below_exit": float(np.mean(np.asarray(off) <= exit_)) if off else None,
        "rules": __doc__,
    }
    a.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("rules", "episodes")}, indent=1))


if __name__ == "__main__":
    main()
