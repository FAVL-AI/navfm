import pytest

from navfm.collection.arrival_confirmation import (
    ABSTAINED,
    APPROACH,
    CONFIRMED,
    TRACKING,
    ConfirmationConfig,
    ConfirmationState,
)

CFG = ConfirmationConfig(threshold=7.745, votes=2, window=4, approach_budget=10)


def run(seq, cfg=CFG):
    s = ConfirmationState(cfg)
    return s, [s.update(*x) for x in seq]


def test_no_evidence_before_the_chain_end():
    s, recs = run([(False, 1.0)] * 6)
    assert s.phase == TRACKING
    assert all(r["vote"] is None for r in recs)


def test_alternating_chain_flag_does_not_discard_evidence():
    # The v1 junction pattern: flag true with large distance, flag false with
    # in-region distance. v1 never accepted; the latched approach does.
    seq = [(True, 10.6), (False, 6.1), (True, 11.0), (False, 6.5)]
    s, recs = run(seq)
    assert s.phase == CONFIRMED
    assert recs[1]["phase"] == APPROACH and recs[3]["phase"] == CONFIRMED


def test_far_votes_never_confirm():
    s, _ = run([(True, 9.0)] * 9)
    assert s.phase == APPROACH


def test_votes_expire_outside_the_window():
    # Two votes five decisions apart never share a window of four.
    seq = [(True, 5.0), (True, 9), (True, 9), (True, 9), (True, 5.0), (True, 9)]
    s, _ = run(seq)
    assert s.phase == APPROACH


def test_pause_clears_votes_and_does_not_consume_budget():
    seq = [(True, 5.0), (True, 9.0, True), (True, 5.0)]
    s, recs = run(seq)
    assert recs[1]["paused"] and recs[1]["votes_in_window"] == 0
    assert s.phase == APPROACH and s.approach_decisions == 2


def test_budget_exhaustion_is_abstention_not_arrival():
    s, _ = run([(True, 9.0)] * 10)
    assert s.phase == ABSTAINED and s.terminal


def test_terminal_states_are_final():
    s, _ = run([(True, 5.0), (True, 5.0), (False, 99.0, True), (True, 99.0)])
    assert s.phase == CONFIRMED


@pytest.mark.parametrize(
    "kw",
    [
        {"threshold": 0},
        {"threshold": 1, "votes": 5, "window": 4},
        {"threshold": 1, "votes": 0},
        {"threshold": 1, "window": 4, "approach_budget": 3},
    ],
)
def test_config_validation(kw):
    with pytest.raises(ValueError):
        ConfirmationConfig(**kw)
