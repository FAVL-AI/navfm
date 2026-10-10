"""The current topomap code reproduces recorded v1 comparator decisions exactly.

v2 reruns of A_baseline and B1_bounded run new source blobs (topomap.py gained
RecoveringTopomapState). Replaying the logged window distances of v1 episodes
through the current TopomapState / BoundedTopomapState must reproduce every
logged chain record, including decisions after the stop.
"""

import json
from pathlib import Path

import pytest

from navfm.collection.topomap import (
    BoundedConfig,
    BoundedTopomapState,
    TopomapConfig,
    TopomapState,
)

FIXTURE = Path(__file__).parent / "fixtures" / "v1_chain_decisions.json"
EPISODES = json.loads(FIXTURE.read_text())["episodes"]


@pytest.mark.parametrize("ep", EPISODES, ids=lambda e: f"{e['collection']}:{e['route']}")
def test_replayed_v1_decisions_match_the_recording(ep):
    tm = ep["topomap"]
    cfg = TopomapConfig(radius=tm["radius"], close_threshold=tm["close_threshold"])
    if tm["bounded"]:
        state = BoundedTopomapState(
            goal_node=ep["goal_node"], bounded=BoundedConfig(**tm["bounded"])
        )
    else:
        state = TopomapState(goal_node=ep["goal_node"])
    assert len(ep["decisions"]) > 20
    for k, rec in enumerate(ep["decisions"]):
        start, end = state.window(cfg)
        assert [start, end] == rec["chain"]["window"], k
        state.update(rec["d"], cfg)
        got = state.history[-1]
        for key, want in rec["chain"].items():
            assert got[key] == want, (k, key, got[key], want)


def test_the_fixture_exercises_both_comparators_and_the_lost_state():
    events = {r["chain"].get("event") for ep in EPISODES for r in ep["decisions"]}
    assert {"jump_withheld", "lost_entered", "lost"} <= events
    assert any(not ep["topomap"]["bounded"] for ep in EPISODES)


def test_a_perturbed_decision_is_detected():
    # Negative control: change one logged distance and the replay must diverge.
    ep = json.loads(json.dumps(EPISODES[0]))
    k = 22
    d = ep["decisions"][k]["d"]
    i = d.index(min(d))
    d[i] += 50.0
    cfg = TopomapConfig(
        radius=ep["topomap"]["radius"], close_threshold=ep["topomap"]["close_threshold"]
    )
    state = TopomapState(goal_node=ep["goal_node"])
    diverged = False
    for rec in ep["decisions"][: k + 1]:
        state.update(rec["d"], cfg)
        diverged |= any(state.history[-1][key] != v for key, v in rec["chain"].items())
    assert diverged
