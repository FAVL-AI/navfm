import pytest

from navfm.collection.topomap import TopomapConfig, TopomapState

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
