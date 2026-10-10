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


def topomap_baseline(
    distances,
    nodes=4,
    verify_threshold=None,
    confirmation=None,
    bounded=None,
    recovery=None,
    start_lost=False,
    approach_steering=True,
):
    from navfm.collection.topomap import (
        BoundedTopomapState,
        RecoveringTopomapState,
        TopomapConfig,
        TopomapState,
    )

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
    b.bounded = bounded
    b.verify_threshold = verify_threshold
    b.verify_persistence = 2
    b.state_cls = TopomapState if bounded is None else BoundedTopomapState
    if recovery is not None:
        b.state_cls = RecoveringTopomapState
    b.confirmation = confirmation
    b.recovery = recovery
    b.scan_rate = 0.4
    b.approach_steering = approach_steering
    b.initial_node = 0
    b.start_lost = start_lost
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


def chain_then(requested, flag):
    """Chain flag pattern `flag(call)`; requested-goal distance requested[call]."""

    def d(call, n):
        reached = flag(call)
        chain = [2.0 if (reached and i == n - 2) else 9.0 for i in range(n - 1)]
        if reached:
            chain[-1] = 1.0  # goal node is the argmin: reached
        return [*chain, requested[min(call, len(requested) - 1)]]

    return d


def test_v2_confirmation_survives_an_alternating_chain_flag():
    from navfm.collection.arrival_confirmation import ConfirmationConfig

    # v1 pattern: flag true with a far requested goal, flag false with a near one.
    cfg = ConfirmationConfig(threshold=7.745, votes=2, window=4, approach_budget=10)
    req = [9.0, 10.6, 6.1, 11.0, 6.5, 9.0]
    b = topomap_baseline(chain_then(req, lambda c: c in (1, 3)), nodes=2, confirmation=cfg)
    out = [b.step([None] * 6, goal=np.zeros((2, 2, 3))) for _ in range(5)]
    assert [o["confirmation"]["phase"] for o in out] == [
        "tracking",
        "approach",
        "approach",
        "approach",
        "confirmed",
    ]
    assert [o["policy_stop"] for o in out] == [False] * 4 + [True]
    # In the approach phase the robot steers by the requested goal, never back to the chain.
    assert out[2]["waypoint_normalized"][1] == 0.5


def test_v2_confirmation_budget_is_an_abstention_not_a_stop():
    from navfm.collection.arrival_confirmation import ConfirmationConfig

    cfg = ConfirmationConfig(threshold=7.745, votes=2, window=4, approach_budget=4)
    b = topomap_baseline(chain_then([9.0], lambda c: True), nodes=2, confirmation=cfg)
    out = [b.step([None] * 6, goal=np.zeros((2, 2, 3))) for _ in range(6)]
    assert out[3]["policy_abstain"] == "confirmation_budget"
    assert not any(o["policy_stop"] for o in out)
    assert all(o["command"] == [0.0, 0.0, 0.0] for o in out[3:])


def test_v2_recovery_scans_in_place_then_fails_terminally():
    from navfm.collection.topomap import BoundedConfig, RecoveryConfig

    bc = BoundedConfig(max_jump=2, persistence=2, lost_enter=6.0, lost_exit=2.0, lost_patience=3)
    rc = RecoveryConfig(exit=5.0, persistence=2, scan_budget=3, max_attempts=1)
    b = topomap_baseline(
        lambda call, n: [9.0] * n, nodes=4, bounded=bc, recovery=rc, start_lost=True
    )
    out = [b.step([None] * 6) for _ in range(5)]
    assert all(o["scan"] and o["command"] == [0.0, 0.0, 0.4] for o in out[:2])
    assert out[2]["policy_abstain"] == "recovery_failed" and not out[2]["scan"]
    assert all(o["command"] == [0.0, 0.0, 0.0] for o in out[2:])
    assert not any(o["policy_stop"] for o in out)


def test_v2_recovery_relocalises_and_resumes_tracking():
    from navfm.collection.topomap import BoundedConfig, RecoveryConfig

    bc = BoundedConfig(max_jump=2, persistence=2, lost_enter=6.0, lost_exit=2.0, lost_patience=3)
    rc = RecoveryConfig(exit=5.0, persistence=2, scan_budget=10, max_attempts=1)

    def d(call, n):
        return [4.0 if i == 2 else 9.0 for i in range(n)]

    b = topomap_baseline(d, nodes=6, bounded=bc, recovery=rc, start_lost=True)
    out = [b.step([None] * 6) for _ in range(3)]
    assert out[0]["scan"] and out[1]["chain"]["event"] == "relocalised"
    assert out[1]["chain"]["closest_node"] == 2 and not out[2]["scan"]
    assert out[2]["command"][0] > 0


def test_v2_constructor_guards(monkeypatch):
    from navfm.collection.arrival_confirmation import ConfirmationConfig
    from navfm.collection.topomap import BoundedConfig, RecoveryConfig

    def parent_init(self, checkpoint, **kw):
        self.stop_enabled = kw["stop_enabled"]
        self.manifest = {}
        self.limits = rb.BaseLimits(max_v=0.1, max_w=0.4)

    monkeypatch.setattr(rb.RGBBaseline, "__init__", parent_init)
    cc = ConfirmationConfig(threshold=7.745)
    rc = RecoveryConfig(exit=5.0)
    with pytest.raises(ValueError, match="not both"):
        rb.RGBTopomapBaseline("x", verify_threshold=7.7, confirmation=cc, stop_enabled=True)
    with pytest.raises(ValueError, match="needs bounded"):
        rb.RGBTopomapBaseline("x", recovery=rc, stop_enabled=True)
    with pytest.raises(ValueError, match="lost start"):
        rb.RGBTopomapBaseline("x", start_lost=True, stop_enabled=True)
    with pytest.raises(ValueError, match="scan rate"):
        rb.RGBTopomapBaseline(
            "x", bounded=BoundedConfig(), recovery=rc, scan_rate=0.9, stop_enabled=True
        )
    b = rb.RGBTopomapBaseline("x", confirmation=cc, stop_enabled=True)
    assert b.manifest["topomap"]["confirmation"]["threshold"] == 7.745


def test_v2a_steers_as_v1_and_v2b_steers_to_the_requested_goal_in_approach():
    from navfm.collection.arrival_confirmation import ConfirmationConfig

    cfg = ConfirmationConfig(threshold=7.745, votes=2, window=4, approach_budget=10)
    req = [9.0, 10.6, 9.0, 11.0]
    flag = lambda c: c in (1, 3)  # noqa: E731
    outs = {}
    for steering in (False, True):
        b = topomap_baseline(
            chain_then(req, flag), nodes=2, confirmation=cfg, approach_steering=steering
        )
        outs[steering] = [b.step([None] * 6, goal=np.zeros((2, 2, 3))) for _ in range(3)]
    # Decision 2: approach latched, chain flag false.
    assert outs[False][2]["waypoint_normalized"][1] == 0.0
    assert outs[True][2]["waypoint_normalized"][1] == 0.5
    # On a chain-end decision both steer to the requested goal.
    assert (
        outs[False][1]["waypoint_normalized"][1] == outs[True][1]["waypoint_normalized"][1] == 0.5
    )


def test_every_variant_spec_carries_a_lost_start(monkeypatch):
    # Red-team H1: a v1-shaped spec (B1) silently dropped --start-lost.
    def parent_init(self, checkpoint, **kw):
        self.stop_enabled = kw["stop_enabled"]
        self.manifest = {}
        self.limits = rb.BaseLimits(max_v=0.1, max_w=0.4)

    monkeypatch.setattr(rb.RGBBaseline, "__init__", parent_init)
    b1 = {
        "bounded": {
            "max_jump": 2,
            "persistence": 2,
            "lost_enter": 6.752,
            "lost_exit": 2.215,
            "lost_patience": 3,
        },
        "verify_threshold": None,
        "verify_persistence": 2,
    }
    kw = rb.topomap_components(b1, start_lost=True)
    assert kw["start_lost"] is True
    policy = rb.RGBTopomapBaseline("x", stop_enabled=True, **kw)
    policy.set_chain([np.zeros((2, 2, 3))] * 4)
    assert policy.state.lost
    a = rb.topomap_components({**b1, "bounded": None}, start_lost=False)
    assert a["start_lost"] is False and a["bounded"] is None
