"""Descriptive concordance of the re-collected kidnap block with the superseded attempts.

Declared in component_comparison_v2 amendment 2 before the re-collection. DESCRIPTIVE
ONLY: no gate reads it, and no further amendment of the recovery block follows from
its result, whatever it is. For each (trial, variant, route) of the replaced cells it
compares the superseded attempt (collection tag 20261010-01) with the re-collected
attempt the analysis counts (block tag, or its rerun tag) on:
  (i)  termination class: "ended" (a stop or halt before the frame budget) or "timeout";
  (ii) stopped_within_0_5m: ended, with final distance to the goal image's capture
       position <= 0.5 m.
Both are computed the same way for both draws, from the saved transitions (commands and
poses), so the 14 superseded attempts that have no manifest outcome are included. A
stop and an abstain halt are both "ended"; recovery success by the frozen definition
needs decisions and is not part of this comparison.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

E = Path("/home/favl/navfm-runtime-evidence")


def outcome(episode: Path, goal: np.ndarray, budget: int) -> dict:
    records = json.loads((episode / "trajectory" / "transitions.json").read_text())["records"]
    final = float(np.linalg.norm(np.asarray(records[-1]["pose_after"][:2]) - goal))
    ended = len(records) < budget
    return {
        "frames": len(records),
        "termination_class": "ended" if ended else "timeout",
        "final_goal_distance_m": final,
        "stopped_within_0_5m": bool(ended and final <= 0.5),
    }


def goal_xy(goal_root: Path, route: str) -> np.ndarray:
    goals = json.loads((goal_root / "goal_source.json").read_text())["goals"]
    src = json.loads((goal_root / route / "runtime_manifest.json").read_text())
    return np.asarray(src["captures"][goals[route]["frame"]]["pose"][:2])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--amendment", type=Path, required=True)
    p.add_argument("--analysis", type=Path, required=True, help="amended stage-2 analysis output")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("output must be new")
    cfg = json.loads(a.config.read_text())
    am = json.loads(a.amendment.read_text())
    an = json.loads(a.analysis.read_text())
    goal_root = Path(cfg["runtime"]["goal_root"])
    counted = {(x["trial"], x["variant"], x["route"]): x.get("collection") for x in an["attempts"]}
    rows = []
    for trial, variant in am["replaced_cells"]:
        t = cfg["trials"][trial]
        budget = t.get("budget_frames", cfg["runtime"]["budget_frames"])
        for route in t["routes"]:
            g = goal_xy(goal_root, route)
            old = E / f"v2-{trial}-{variant}-{am['superseded_tag']}" / route
            new_coll = counted.get((trial, variant, route))
            row = {"trial": trial, "variant": variant, "route": route, "re_collected": new_coll}
            row["superseded"] = outcome(old, g, budget)
            row["re_collected_outcome"] = (
                None if new_coll is None else outcome(E / new_coll / route, g, budget)
            )
            if row["re_collected_outcome"] is not None:
                for k in ("termination_class", "stopped_within_0_5m"):
                    row[f"agree_{k}"] = row["superseded"][k] == row["re_collected_outcome"][k]
            rows.append(row)
    summary: dict = {}
    for r in rows:
        s = summary.setdefault(
            r["variant"],
            {
                "pairs": 0,
                "missing": 0,
                "agree_termination_class": 0,
                "agree_stopped_within_0_5m": 0,
            },
        )
        if r["re_collected_outcome"] is None:
            s["missing"] += 1
            continue
        s["pairs"] += 1
        s["agree_termination_class"] += r["agree_termination_class"]
        s["agree_stopped_within_0_5m"] += r["agree_stopped_within_0_5m"]
    result = {
        "scope": "DESCRIPTIVE ONLY (amendment 2 concordance rule); no gate reads this",
        "summary": summary,
        "rows": rows,
        "rules": __doc__,
    }
    a.out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
