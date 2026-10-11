import numpy as np
import pytest

from navfm.deployment.yahboom import YahboomAdapter


class Policy:
    def step(self, history, goal):
        assert len(history) == 6
        return {"command": [0.1, 0, 0.2]}


def test_adapter_rgb_only_and_cadence():
    sent = []
    a = YahboomAdapter(Policy(), np.zeros((24, 32, 3), np.uint8), sent.append)
    rgb = np.zeros((24, 32, 3), np.uint8)
    assert a.observe(rgb, 1, 1)["command"] == [0.1, 0, 0.2]
    assert a.observe(rgb, 1.1, 1.1) is None
    a.observe(rgb, 1.25, 1.25)
    assert len(sent) == 2


@pytest.mark.parametrize("ts,now", [(1, 1.3), (1, 0), (float("nan"), 1)])
def test_timestamp_failure_stops(ts, now):
    sent = []
    a = YahboomAdapter(Policy(), None, sent.append)
    with pytest.raises(ValueError):
        a.observe(np.zeros((24, 32, 3), np.uint8), ts, now)
    assert sent[-1] == [0, 0, 0]


def test_history_gap_stops():
    sent = []
    a = YahboomAdapter(Policy(), None, sent.append)
    a.observe(np.zeros((24, 32, 3), np.uint8), 1, 1)
    with pytest.raises(ValueError):
        a.observe(np.zeros((24, 32, 3), np.uint8), 2, 2)
    assert sent[-1] == [0, 0, 0]
