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


class FakeBatchModel:
    """Distances per node from a callable of (call index, batch size)."""

    def __init__(self, distances):
        self.distances = distances
        self.calls = 0

    def __call__(self, observation, goals):
        n = goals.value.shape[0]
        d = self.distances(self.calls, n)
        self.calls += 1
        actions = np.zeros((n, 5, 4))
        actions[:, 2, 0] = 2.0
        actions[-1, 2, 1] = 0.5  # last batch entry (the requested goal, if any) turns left
        return FakeTensor(np.asarray(d, float)), FakeTensor(actions)


class FakeTorchBatch(FakeTorch):
    @staticmethod
    def cat(items, dim=0):
        return FakeTensor(np.concatenate([i.value for i in items], axis=dim))


class Batchable(FakeTensor):
    def repeat(self, n, *rest):
        return FakeTensor(np.repeat(self.value, n, axis=0))


def topomap_baseline(distances, nodes=4, verify_threshold=None):
    from navfm.collection.topomap import TopomapConfig, TopomapState

    b = rb.RGBTopomapBaseline.__new__(rb.RGBTopomapBaseline)
    b.torch = FakeTorchBatch
    b.device = "cpu"
    b.tensor = lambda images: Batchable(np.zeros((len(images), 1)))
    b.model = FakeBatchModel(distances)
    b.action_scale_m = 0.05
    b.control_period_s = 0.5
    b.stop_enabled = True
    b.limits = rb.BaseLimits(max_v=0.1, max_w=0.4)
    b.topomap_cfg = TopomapConfig(radius=4, close_threshold=3.0)
    b.bounded = None
    b.verify_threshold = verify_threshold
    b.verify_persistence = 2
    b.state_cls = TopomapState
    b.set_chain([np.zeros((2, 2, 3))] * nodes)
    return b


def test_chain_progress_does_not_stop_until_goal_node():
    # Node k is "close" at call k: the robot advances one node per decision.
    def d(call, n):
        return [2.0 if i == call else 9.0 for i in range(n)]

    b = topomap_baseline(d, nodes=4)
    out = [b.step([None] * 6) for _ in range(3)]
    assert [o["chain"]["closest_node"] for o in out] == [1, 2, 3]
    assert [o["policy_stop"] for o in out] == [False, False, True]
    assert out[1]["command"][0] > 0 and out[2]["command"] == [0.0, 0.0, 0.0]


def test_far_from_every_node_never_stops():
    b = topomap_baseline(lambda call, n: [9.0] * n, nodes=4)
    out = [b.step([None] * 6) for _ in range(5)]
    assert not any(o["policy_stop"] for o in out)
    assert all(o["chain"]["closest_node"] == 0 for o in out)


def test_topomap_constructor_takes_the_collector_arguments(monkeypatch):
    # Exercise the real constructor with the collector's call; the parent loads no model.
    def parent_init(self, checkpoint, **kw):
        self.stop_enabled = kw["stop_enabled"]
        self.manifest = {}

    monkeypatch.setattr(rb.RGBBaseline, "__init__", parent_init)
    b = rb.RGBTopomapBaseline(
        "x.pth",
        radius=4,
        close_threshold=3.0,
        action_scale_m=0.05,
        stop_enabled=True,
        max_v=0.1,
        control_period_s=0.5,
    )
    assert b.chain == [] and b.manifest["topomap"]["radius"] == 4
    with pytest.raises(ValueError, match="two nodes"):
        b.set_chain([np.zeros((2, 2, 3))])


def test_verification_holds_stop_until_requested_goal_is_close():
    # Chain completes at decision 3; requested-goal distance (last entry) is far,
    # then close twice. Arrival must wait for two consecutive close verdicts.
    requested = [9.0, 9.0, 9.0, 9.0, 2.0, 2.0]

    def d(call, n):
        chain = [2.0 if i == min(call, n - 2) else 9.0 for i in range(n - 1)]
        return [*chain, requested[min(call, len(requested) - 1)]]

    b = topomap_baseline(d, nodes=4, verify_threshold=3.0)
    out = [b.step([None] * 6, goal=np.zeros((2, 2, 3))) for _ in range(6)]
    assert [o["chain"]["reached_goal"] for o in out][2:] == [True] * 4
    assert [o["verification"] for o in out][2:] == ["pending", "pending", "pending", "accepted"]
    assert [o["policy_stop"] for o in out] == [False] * 5 + [True]
    # While pending, the robot steers by the requested goal's waypoint.
    assert out[2]["waypoint_normalized"][1] == 0.5
    assert out[5]["chain_reached_decisions"] == 4


def test_verification_without_requested_goal_is_refused():
    b = topomap_baseline(lambda call, n: [2.0] * n, nodes=2, verify_threshold=3.0)
    with pytest.raises(ValueError, match="requested goal"):
        b.step([None] * 6)
