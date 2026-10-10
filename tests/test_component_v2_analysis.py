"""Definitions computed by scripts/analyse_component_comparison_v2.py (frozen in the v2 config)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyse_component_comparison_v2 as v2


def rec(argmin, closest, followed, dist=5.0, lost=False, stop=False):
    return {
        "chain": {
            "argmin_node": argmin,
            "argmin_distance": dist,
            "closest_node": closest,
            "followed_node": followed,
            "lost": lost,
        },
        "policy_stop": stop,
        "frame": 0,
    }


def manifest(records):
    for k, r in enumerate(records):
        r["frame"] = 6 * k
    return {"inference": records}


def lateral(n):
    return np.zeros(6 * n + 1)


def test_decision_zero_encounter_uses_the_resumed_initial_node():
    # Red-team H2: the d22 start meets the look-alike on its first decision.
    recs = [rec(10, 10, 10)] + [rec(11, 11, 11) for _ in range(12)]
    out = v2.ambiguity(manifest(recs), [5] * 13, lateral(13), initial_node=5, close=3.0)
    assert out["encountered"] and out["encounters"][0]["decision"] == 0
    assert out["followed"] == 1
    missed = v2.ambiguity(manifest(recs), [5] * 13, lateral(13), initial_node=0, close=3.0)
    assert not missed["encountered"]


def test_correction_needs_the_full_horizon_before_the_task_end():
    held = [rec(10, 5, 6)] + [rec(5, 5, 6) for _ in range(10)]
    out = v2.ambiguity(manifest(held), [5] * 11, lateral(11), initial_node=5, close=3.0)
    assert out["corrected"] == 1
    short = [rec(10, 5, 6)] + [rec(5, 5, 6) for _ in range(4)] + [rec(5, 5, 6, stop=True)]
    out = v2.ambiguity(manifest(short), [5] * 6, lateral(6), initial_node=5, close=3.0)
    assert out["NOT_EVALUABLE"] == 1 and out["corrected"] == 0


def test_lost_following_of_the_aliased_node_counts_as_followed():
    recs = [rec(10, 5, 10, lost=True)] + [rec(10, 5, 10, lost=True) for _ in range(11)]
    out = v2.ambiguity(manifest(recs), [5] * 12, lateral(12), initial_node=5, close=3.0)
    assert out["followed"] >= 1


def test_decisions_after_the_task_end_are_ignored():
    recs = [rec(5, 5, 6, stop=True)] + [rec(10, 5, 10) for _ in range(5)]
    out = v2.ambiguity(manifest(recs), [5] * 6, lateral(6), initial_node=5, close=3.0)
    assert not out["encountered"]


def test_withheld_then_lost_track():
    recs = [rec(10, 5, 6)] + [rec(9, 9, 9) for _ in range(10)]
    out = v2.ambiguity(manifest(recs), [5] * 11, lateral(11), initial_node=5, close=3.0)
    assert out["withheld_then_lost_track"] == 1


def test_backward_proposals_are_tallied_with_correctness():
    # Previous node 4; argmin 3 at distance 4.1 (> close) proposes node 3: backward.
    recs = [rec(3, 3, 3, dist=4.1), rec(3, 3, 4, dist=2.0)]
    out = v2.ambiguity(manifest(recs), [4, 4], lateral(2), initial_node=4, close=3.0)
    b = out["backward_proposals"]
    assert len(b) == 1 and b[0]["accepted"] and not b[0]["proposal_closer_to_true"]
