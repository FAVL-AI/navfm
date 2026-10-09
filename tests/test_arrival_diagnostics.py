import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


decompose = load("decompose_live_episodes")
replay = load("score_teacher_replay")


def test_spearman_detects_monotone_and_inverted_and_flat():
    a = [1, 2, 3, 4, 5]
    assert decompose.spearman(a, [2, 4, 6, 8, 10]) == pytest.approx(1.0)
    assert decompose.spearman(a, [5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    assert decompose.spearman(a, [3, 3, 3, 3, 3]) is None
    assert replay.spearman(a, [5, 4, 3, 2, 1]) == pytest.approx(-1.0)


def test_point_to_polyline_and_wrap():
    line = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0]])
    assert decompose.point_to_polyline(np.array([1.0, 0.5]), line) == pytest.approx(0.5)
    assert decompose.point_to_polyline(np.array([3.0, 1.0]), line) == pytest.approx(1.0)
    assert decompose.wrap(3 * math.pi / 2) == pytest.approx(-math.pi / 2)


def episode(tmp_path, goal_offset=0.0):
    route = {"id": "r", "waypoints": [[0, 0], [1, 0], [2, 0]], "scene_index": 1}
    goal = np.array([2.0, 20.0])
    poses = [[0.5 * i, 20.0 + 0.1 * (i == 3), 0.0] for i in range(4)]
    captures = [
        {
            "pose": p,
            "distance_to_goal_m": float(np.linalg.norm(np.array(p[:2]) - goal)) + goal_offset,
        }
        for p in poses
    ]
    inference = [{"frame": i, "predicted_distance": 10.0 - i} for i in range(4)]
    m = {
        "route": route,
        "captures": captures,
        "inference": inference,
        "termination": "timeout",
        "policy_stop_frame": None,
    }
    (tmp_path / "runtime_manifest.json").write_text(json.dumps(m))
    return tmp_path


def test_decompose_recovers_geometry(tmp_path):
    r = decompose.decompose(episode(tmp_path))
    assert r["start_goal_m"] == pytest.approx(2.0)
    assert r["final_lateral_deviation_m"] == pytest.approx(0.1)
    assert r["predicted_vs_true_spearman"] == pytest.approx(1.0)
    assert not r["arrival_any_frame"]


def test_decompose_rejects_inconsistent_goal(tmp_path):
    # Negative control: recorded goal distances that disagree with the route endpoint fail.
    with pytest.raises(ValueError, match="disagrees"):
        decompose.decompose(episode(tmp_path, goal_offset=0.2))


class FakePolicy:
    stop_count = 0
    stopped = False

    def __init__(self):
        self.calls = []

    def step(self, history, goal):
        assert len(history) == 6
        self.calls.append(len(self.calls))
        self.stopped = len(self.calls) >= 2
        return {
            "predicted_distance": 5.0 - len(self.calls),
            "policy_stop": self.stopped,
            "waypoint_normalized": [0.0, 0.0],
        }


def test_replay_uses_4hz_frames_and_resets_stop_state():
    p = FakePolicy()
    p.stopped = True
    frames = [np.zeros((2, 2, 3), np.uint8)] * 9
    rows = replay.replay(p, frames, frames[0])
    assert [r[0] for r in rows] == [0, 3, 6]
    assert rows[0][2] is False
