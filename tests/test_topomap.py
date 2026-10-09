import pytest

from navfm.collection.topomap import (
    BoundedConfig,
    BoundedTopomapState,
    TopomapConfig,
    TopomapState,
)

CFG = TopomapConfig(radius=2, close_threshold=3.0)


def test_window_is_upstream_start_end():
    s = TopomapState(goal_node=10, closest_node=0)
    assert s.window(CFG) == (0, 3)
    s.closest_node = 9
    assert s.window(CFG) == (7, 10)


def test_far_argmin_localises_without_advancing():
    s = TopomapState(goal_node=10)
    follow = s.update([9.0, 6.0, 8.0, 12.0], CFG)
    assert follow == 1 and s.closest_node == 1 and not s.reached_goal


def test_close_argmin_advances_to_next_node():
    s = TopomapState(goal_node=10, closest_node=4)
    assert s.window(CFG) == (2, 7)
    follow = s.update([9.0, 7.0, 2.5, 6.0, 8.0, 9.0], CFG)  # argmin node 4, close
    assert follow == 3 and s.closest_node == 5


def test_goal_reached_only_at_goal_node():
    s = TopomapState(goal_node=3, closest_node=2)
    assert s.window(CFG) == (0, 3)
    s.update([9.0, 8.0, 2.0, 5.0], CFG)  # close to node 2 -> advance to node 3 = goal
    assert s.closest_node == 3 and s.reached_goal
    s2 = TopomapState(goal_node=3, closest_node=1)
    s2.update([9.0, 8.0, 4.0, 5.0], CFG)  # node 2 argmin but not close
    assert s2.closest_node == 2 and not s2.reached_goal
    assert s2.history[-1]["closest_node"] == 2


def test_rejects_wrong_window_size_and_bad_config():
    s = TopomapState(goal_node=5)
    with pytest.raises(ValueError):
        s.update([1.0, 2.0], CFG)
    with pytest.raises(ValueError):
        TopomapConfig(radius=-1)


BC = BoundedConfig(max_jump=2, persistence=2, lost_enter=12.0, lost_exit=8.0, lost_patience=3)


def bounded(goal_node=14, closest=5):
    return BoundedTopomapState(goal_node=goal_node, closest_node=closest, bounded=BC)


def far_except(n_window, best_idx, best=5.0, rest=9.0):
    return [best if i == best_idx else rest for i in range(n_window)]


def test_single_aliased_jump_is_withheld():
    # The fine-tuned s_bend_0 case: node 10 scores slightly below node 5 once.
    s2 = bounded(goal_node=14, closest=5)
    cfg4 = TopomapConfig(radius=4, close_threshold=3.0)
    start, end = s2.window(cfg4)  # (1, 10)
    follow = s2.update(far_except(end - start + 1, 10 - start, best=5.3), cfg4)
    assert s2.closest_node == 5 and s2.history[-1]["event"] == "jump_withheld"
    assert start + follow == 6


def test_persistent_jump_is_accepted_but_capped():
    cfg4 = TopomapConfig(radius=4, close_threshold=3.0)
    s = bounded(closest=5)
    for _ in range(2):
        start, end = s.window(cfg4)
        s.update(far_except(end - start + 1, 10 - start, best=5.3), cfg4)
    assert s.closest_node == 7 and s.history[-1]["event"] == "bounded_jump"


def test_lost_entry_global_window_and_no_goal_while_lost():
    cfg4 = TopomapConfig(radius=4, close_threshold=3.0)
    s = bounded(goal_node=6, closest=5)
    for _ in range(3):
        start, end = s.window(cfg4)
        s.update([20.0] * (end - start + 1), cfg4)
    assert s.lost and s.history[-1]["event"] == "lost_entered"
    assert s.window(cfg4) == (0, 6)
    # Even a "close" goal node while lost does not reach the goal on the first decision.
    s.update([20.0] * 6 + [1.0], cfg4)
    assert s.lost and not s.reached_goal


def test_recovery_needs_persistent_global_match():
    cfg4 = TopomapConfig(radius=4, close_threshold=3.0)
    s = bounded(goal_node=14, closest=5)
    for _ in range(3):
        start, end = s.window(cfg4)
        s.update([20.0] * (end - start + 1), cfg4)
    s.update(far_except(15, 9, best=7.0, rest=15.0), cfg4)
    assert s.lost
    s.update(far_except(15, 10, best=7.5, rest=15.0), cfg4)
    assert not s.lost and s.closest_node == 10 and s.history[-1]["event"] == "recovered"


def test_bounded_config_validation():
    with pytest.raises(ValueError):
        BoundedConfig(lost_exit=13.0, lost_enter=12.0)
    with pytest.raises(ValueError):
        BoundedConfig(max_jump=0)
