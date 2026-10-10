"""Stage 1 of component_comparison_v2: replay the v2 confirmation state on recorded decisions.

Open loop: the recorded v1 runs supply, per decision, the chain's reached flag,
the requested-goal distance and the lost flag (D's lost flags enter as pauses, which
V2a/V2b, having no lost state, would not have); the v2 state is replayed on them
up to and including the recorded stop (later decisions are stationary repeats
selected by the v1 rule). v2 steering is not replayed, so this checks the
accumulate / expire / reset / abstain logic, not closed-loop arrival. Pose is
used only to score where a replayed confirmation would have happened.

IN-SAMPLE CONSISTENCY CHECK: the v2 parameters were chosen after reading these
episodes. Distances are scored at frame f-1, the image the decision saw.

Criteria (frozen in configs/eval/component_comparison_v2.json, stages.1_logic_replay):
- S1a: no replayed confirmation at a decision > 0.5 m (the arrival radius) from the goal.
  Vacuous on sequences with fewer than two approach decisions; those are counted.
- S1b: on the C1 truncated junction sequences, a replayed confirmation <= 0.5 m.
- S1c: on true-chain and repeat sequences that continued past the chain end
  (C_verify, D_both) and ended in a v1 correct stop, a replayed confirmation
  <= 0.5 m within 2 decisions of the first chain-end decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from navfm.collection.arrival_confirmation import (
    ConfirmationConfig,
    ConfirmationState,
)
from navfm.collection.episode_measures import episode_measures


def goal_xy(goal_root: Path, route: str):
    goals = json.loads((goal_root / "goal_source.json").read_text())["goals"]
    src = json.loads((goal_root / route / "runtime_manifest.json").read_text())
    return np.array(src["captures"][goals[route]["frame"]]["pose"][:2])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--collection", type=Path, action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("output must be new")
    cfg = json.loads(a.config.read_text())
    cc = ConfirmationConfig(**cfg["variants"]["V2a_confirm"]["confirmation"])
    goal_root = Path(cfg["runtime"]["goal_root"])
    rows = []
    for root in a.collection:
        for e in json.loads((root / "collection.json").read_text())["episodes"]:
            if e["status"] != "PASS":
                continue
            m = json.loads((root / e["id"] / "runtime_manifest.json").read_text())
            g = goal_xy(goal_root, m["route"]["id"])
            line = np.asarray(m["route"]["waypoints"], float)
            line[:, 1] += m["route"]["scene_index"] * 20.0
            v1 = episode_measures(m, line, g)
            stop = m.get("policy_stop_frame")
            seq = [r for r in m["inference"] if stop is None or r["frame"] <= stop]
            s = ConfirmationState(cc)
            first_end = confirm = abstain = None
            for k, r in enumerate(seq):
                chain = r["chain"]
                if chain["reached_goal"] and first_end is None:
                    first_end = k
                rec = s.update(
                    chain["reached_goal"], r["requested_goal_distance"], bool(chain.get("lost"))
                )
                if rec["phase"] == "confirmed" and confirm is None:
                    confirm = k
                if rec["phase"] == "abstained" and abstain is None:
                    abstain = k

            dists = [
                float(
                    np.linalg.norm(np.array(m["captures"][max(r["frame"] - 1, 0)]["pose"][:2]) - g)
                )
                for r in seq
            ]
            rows.append(
                {
                    "collection": root.name,
                    "route": m["route"]["id"],
                    "variant": (m.get("component_variant") or {}).get("variant"),
                    "decisions_replayed": len(seq),
                    "v1_correct_stop": v1["correct_stop"],
                    "v1_wrong_stop": v1["wrong_stop"],
                    "first_chain_end_decision": first_end,
                    "confirm_decision": confirm,
                    "confirm_goal_distance_m": None if confirm is None else dists[confirm],
                    "confirm_delay_decisions": None
                    if confirm is None or first_end is None
                    else confirm - first_end,
                    "abstain_decision": abstain,
                    "approach_decisions": s.approach_decisions,
                    "min_goal_distance_replayed_m": min(dists),
                }
            )
    s1a = [
        r for r in rows if r["confirm_decision"] is not None and r["confirm_goal_distance_m"] > 0.5
    ]
    s1b_rows = [
        r
        for r in rows
        if r["variant"] == "C_verify"
        and "-trunc-" in r["collection"]
        and r["route"].startswith("junction")
    ]
    s1c_rows = [
        r
        for r in rows
        if r["variant"] in ("C_verify", "D_both")
        and ("-true-" in r["collection"] or "-rep-" in r["collection"])
        and r["v1_correct_stop"]
    ]

    def ok_c(r):
        return (
            r["confirm_decision"] is not None
            and r["confirm_goal_distance_m"] <= 0.5
            and r["confirm_delay_decisions"] <= 2
        )

    result = {
        "scope": "STAGE_1_LOGIC_REPLAY (open loop, development, in-sample consistency check)",
        "confirmation": cfg["variants"]["V2a_confirm"]["confirmation"],
        "sequences": len(rows),
        "S1a_false_confirmations": [
            (r["collection"], r["route"], r["confirm_goal_distance_m"]) for r in s1a
        ],
        "S1a_pass": not s1a,
        "S1a_sequences_where_confirmation_possible": sum(
            r["approach_decisions"] >= 2 for r in rows
        ),
        "S1b": [(r["collection"], r["route"], r["confirm_goal_distance_m"]) for r in s1b_rows],
        "S1b_pass": bool(s1b_rows)
        and all(
            r["confirm_decision"] is not None and r["confirm_goal_distance_m"] <= 0.5
            for r in s1b_rows
        ),
        "S1c_sequences": len(s1c_rows),
        "S1c_failures": [(r["collection"], r["route"]) for r in s1c_rows if not ok_c(r)],
        "S1c_pass": bool(s1c_rows) and all(ok_c(r) for r in s1c_rows),
        "rows": rows,
        "rules": __doc__,
    }
    result["gate_V2a_V2b_to_stage_2"] = result["S1a_pass"] and result["S1c_pass"]
    a.out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "rules")}, indent=1))


if __name__ == "__main__":
    main()
