import ast
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
from controller_plant_diagnostic_v1 import TRIALS, command, info, prepare, target_onset


def test_finite_balanced_schedule_and_conditioning():
    assert len(TRIALS) == 12 and Counter(x[0] for x in TRIALS) == {
        "reset": 4,
        "carry": 4,
        "direct": 4,
    }
    for k, (mode, v, w) in enumerate(TRIALS):
        assert command(120 + 240 * k) == (0, 0)
        assert command(240 + 240 * k) == (
            (0.0, 0.0) if mode == "direct" else (v, -(0.4 if w > 0 else -0.4))
        )
        assert command(300 + 240 * k) == (v, w)
    assert info(2999)["stage"] == "target" and command(3000) == (0, 0)
    assert Counter((v, w) for _, v, w in TRIALS) == {
        (0.05, 0.005): 3,
        (0.05, -0.005): 3,
        (0, 0.4): 3,
        (0, -0.4): 3,
    }


def test_transform_native_read_and_shared_conditioning():
    source = prepare(Path("scripts/imu_coverage_base_v2.py").read_text())
    ast.parse(source)
    assert source.count("measured = gyro.read()") == 1
    assert "range(3120)" in source and "gyro.guard.records) == 3000" in source
    assert (
        'diagnostic_info(tick)["stage"] == "target" and diagnostic_info(tick)["mode"] == "direct"'
        in source
    )
    assert "for start in [300 + 240*k for k in range(12)]" in source
    assert "NOT_APPLICABLE" in source


def test_drift_failclosed():
    with pytest.raises(ValueError):
        prepare("def command(tick):\n pass\ndef main():\n pass")


def test_reset_only_at_target_and_observed_before_after():
    from types import SimpleNamespace

    class Array:
        def __init__(self, value):
            self.value = value

        def tolist(self):
            return self.value

    tracker = SimpleNamespace(integral=0.1)
    tracker.reset = lambda: setattr(tracker, "integral", 0.0)
    articulation = SimpleNamespace(
        get_world_poses=lambda: (None, Array([[1, 0, 0, 0]])),
        get_velocities=lambda: Array([[0] * 6]),
        get_joint_velocities=lambda: Array([[0] * 4]),
    )
    robot = SimpleNamespace(pose=lambda: (Array([0, 0]), 0), _articulation=articulation)
    events = []

    def mark(phase, **fields):
        events.append((phase, fields))

    target_onset(299, tracker, robot, SimpleNamespace(current_time=0), mark, lambda x: x)
    assert tracker.integral == 0.1 and events == []
    target_onset(300, tracker, robot, SimpleNamespace(current_time=0), mark, lambda x: x)
    assert (
        events[-1][1]["integral_before_reset"] == 0.1 and events[-1][1]["integral_after_reset"] == 0
    )
    tracker.integral = 0.2
    target_onset(540, tracker, robot, SimpleNamespace(current_time=0), mark, lambda x: x)
    assert tracker.integral == 0.2  # carry target retains prior state
