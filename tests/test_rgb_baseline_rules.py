import numpy as np
import pytest

from navfm.collection import rgb_baseline as rb


class FakeTensor:
    def __init__(self, value):
        self.value = np.asarray(value, float)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.value

    def reshape(self, *shape):
        return self.value.reshape(*shape)

    def __getitem__(self, index):
        return FakeTensor(self.value[index])


class FakeModel:
    def __init__(self, distances, waypoint=(2.0, 0.0)):
        self.distances = list(distances)
        self.waypoint = waypoint

    def __call__(self, observation, goal):
        actions = np.zeros((1, 5, 4))
        actions[0, 2, :2] = self.waypoint
        return FakeTensor([self.distances.pop(0)]), FakeTensor(actions)


class FakeTorch:
    class cuda:
        @staticmethod
        def synchronize():
            pass

    class inference_mode:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False


def baseline(distances, *, stop_rule="project", period=0.25, waypoint=(2.0, 0.0)):
    b = rb.RGBBaseline.__new__(rb.RGBBaseline)
    b.torch = FakeTorch
    b.device = "cpu"
    b.tensor = lambda images: None
    b.model = FakeModel(distances, waypoint)
    b.action_scale_m = 0.05
    b.control_period_s = period
    b.stop_rule = stop_rule
    b.stop_enabled = True
    b.stop_count = 0
    b.stopped = False
    b.limits = rb.BaseLimits(max_v=0.2, max_w=0.4)
    return b


def run(b, n):
    return [b.step([None] * 6, None) for _ in range(n)]


def test_project_rule_never_fires_above_one_even_when_close():
    # The historical rule cannot fire at the observed goal-as-current floor (>=1.9).
    out = run(baseline([1.9] * 6), 6)
    assert not any(o["policy_stop"] for o in out)


def test_project_rule_needs_three_consecutive():
    out = run(baseline([0.5, 0.5, 2.0, 0.5, 0.5, 0.5]), 6)
    assert [o["policy_stop"] for o in out] == [False] * 5 + [True]


def test_upstream_rule_latches_at_three():
    out = run(baseline([5.0, 3.0, 9.0], stop_rule="upstream_t3"), 3)
    assert [o["policy_stop"] for o in out] == [False, True, True]
    assert out[2]["command"] == [0.0, 0.0, 0.0]


def test_upstream_rule_does_not_fire_above_three():
    out = run(baseline([3.01, 4.0], stop_rule="upstream_t3"), 2)
    assert not any(o["policy_stop"] for o in out)


def test_control_period_rescales_feedforward_velocity():
    # waypoint 1 unit * 0.05 m; v = dx / dt, below the 0.2 m/s cap at both periods.
    fast = run(baseline([9.0], period=0.25, waypoint=(1.0, 0.0)), 1)[0]["command"][0]
    slow = run(baseline([9.0], period=0.5, waypoint=(1.0, 0.0)), 1)[0]["command"][0]
    assert fast == pytest.approx(0.2) and slow == pytest.approx(0.1)


def test_unknown_rule_and_bad_period_rejected(tmp_path):
    with pytest.raises(ValueError, match="stop rule"):
        rb.RGBBaseline(tmp_path / "x.pth", stop_rule="tuned")
    with pytest.raises(ValueError, match="period"):
        rb.RGBBaseline(tmp_path / "x.pth", control_period_s=0)
