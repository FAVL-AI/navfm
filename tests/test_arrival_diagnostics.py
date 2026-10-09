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
            "simulation_time": 10.0 + i / 12,
        }
        for i, p in enumerate(poses)
    ]
    inference = [
        {"frame": i, "predicted_distance": 10.0 - i, "sensor_time": 10.0 + i / 12} for i in range(4)
    ]
    m = {
        "route": route,
        "captures": captures,
        "inference": inference,
        "termination": "timeout",
        "policy_stop_frame": None,
        "contacts": [{"time": 10.0 + 2.5 / 12}],
    }
    (tmp_path / "runtime_manifest.json").write_text(json.dumps(m))
    return tmp_path


def test_decompose_recovers_geometry(tmp_path):
    r = decompose.decompose(episode(tmp_path))
    assert r["start_goal_m"] == pytest.approx(2.0)
    assert r["final_lateral_deviation_m"] == pytest.approx(0.1)
    assert r["predicted_vs_true_spearman"] == pytest.approx(1.0)
    assert not r["arrival_any_frame"]
    assert r["displacement_per_decision_m_median"] == pytest.approx(0.5, abs=0.02)
    assert r["decision_period_s_median"] == pytest.approx(1 / 12)
    assert r["first_contact_frame"] == 3


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


audit = load("audit_closed_loop_episodes")


def closed_loop_episode(tmp_path, *, turn_fraction, stop_frame=None, contact_time=None):
    """Straight route along x; commands w=0.2 held per decision, realised at a fraction."""
    route = {"id": "r", "waypoints": [[0, 0], [3, 0]], "scene_index": 0}
    dt, w = 1 / 12, 0.2
    xy, yaw, captures = [0.0, 0.0], 0.0, []
    for i in range(48):
        captures.append(
            {
                "pose": [xy[0], xy[1], yaw],
                "distance_to_goal_m": float(((xy[0] - 3) ** 2 + xy[1] ** 2) ** 0.5),
                "simulation_time": i * dt,
            }
        )
        moving = stop_frame is None or i < stop_frame
        if moving:
            yaw += turn_fraction * w * dt
            xy = [xy[0] + 0.1 * dt * math.cos(yaw), xy[1] + 0.1 * dt * math.sin(yaw)]
    inference = [
        {
            "frame": f,
            "command": [0.1, 0.0, w],
            "waypoint_normalized": [3.0, 0.3],
            "sensor_time": f * dt,
        }
        for f in range(0, 48, 6)
    ]
    m = {
        "route": route,
        "captures": captures,
        "inference": inference,
        "termination": "policy_stop" if stop_frame else "timeout",
        "policy_stop_frame": stop_frame,
        "contacts": []
        if contact_time is None
        else [
            {
                "time": contact_time,
                "paths": ["/World/Robot/base_link", "/World/Fixture/Scene0/Wall"],
            }
        ],
        "policy": {"max_v": 0.1, "max_w": 0.4, "control_hz": 2.0},
    }
    (tmp_path / "runtime_manifest.json").write_text(json.dumps(m))
    return tmp_path


def test_audit_measures_turn_deficit_and_full_tracking(tmp_path):
    weak = audit.audit(closed_loop_episode(tmp_path, turn_fraction=0.2))["tracking"]
    assert weak["w_real_over_cmd_median"] == pytest.approx(0.2, abs=0.02)
    full = audit.audit(closed_loop_episode(tmp_path, turn_fraction=1.0))["tracking"]
    assert full["w_real_over_cmd_median"] == pytest.approx(1.0, abs=0.02)
    assert full["v_real_over_cmd_median"] == pytest.approx(1.0, abs=0.02)


def test_audit_timeline_orders_contact_and_excludes_post_contact_tracking(tmp_path):
    r = audit.audit(closed_loop_episode(tmp_path, turn_fraction=1.0, contact_time=2.0))
    assert r["events"]["first_contact_frame"] == 24
    assert r["contact_with"] == ["/World/Fixture/Scene0/Wall"]
    assert r["event_order"][-1] == "termination"
    assert r["tracking"]["held_commands"] == 4


def test_audit_settle_after_stop(tmp_path):
    r = audit.audit(closed_loop_episode(tmp_path, turn_fraction=1.0, stop_frame=30))
    assert r["measures"]["settle"] == "SETTLED" and r["events"]["arrival_declared_frame"] == 30
    # Stops far from the end of a 3 m route after 30 frames at 0.1 m/s: a wrong stop.
    assert r["measures"]["wrong_stop"] and not r["measures"]["completion"]


def goal_fixture(tmp_path):
    """Goal root holding JPEG source bytes; episode holding the PNG of decoded pixels."""
    import hashlib

    from PIL import Image

    rng = np.random.default_rng(0)
    pixels = (rng.random((24, 32, 3)) * 255).astype(np.uint8)
    teacher = tmp_path / "teacher" / "r" / "trajectory"
    teacher.mkdir(parents=True)
    Image.fromarray(pixels).save(teacher / "9.jpg", format="JPEG", quality=90)
    source_bytes = (teacher / "9.jpg").read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    root = tmp_path / "goals"
    (root / "r").mkdir(parents=True)
    (root / "r" / "goal.png").write_bytes(source_bytes)
    declared = {"source": str(teacher / "9.jpg"), "frame": 0, "source_sha256": source_sha}
    (root / "goal_source.json").write_text(json.dumps({"goals": {"r": declared}}))
    ep = tmp_path / "ep"
    ep.mkdir()
    consumed = np.asarray(Image.open(root / "r" / "goal.png").convert("RGB"))
    Image.fromarray(consumed).save(ep / "goal.png")
    m = {
        "route": {"id": "r"},
        "policy": {"stop_rule": "x"},
        "goal_source_frame": declared,
        "fixed_goal_sha256": hashlib.sha256((ep / "goal.png").read_bytes()).hexdigest(),
    }
    return root, ep, m


def test_goal_identity_accepts_jpeg_source_and_png_episode_copy(tmp_path):
    root, ep, m = goal_fixture(tmp_path)
    identity = audit.goal_identity(root, ep, m)
    assert identity["source_encoded_sha256"] != identity["episode_png_sha256"]
    assert identity["consumed_pixels_shape"] == [24, 32, 3]


def test_goal_identity_rejects_genuinely_changed_goals(tmp_path):
    import hashlib

    from PIL import Image

    root, ep, m = goal_fixture(tmp_path)
    # Changed consumed pixels, with the recorded hash updated to match: still refused.
    px = np.asarray(Image.open(ep / "goal.png")).copy()
    px[0, 0] ^= 1
    Image.fromarray(px).save(ep / "goal.png")
    changed = {**m, "fixed_goal_sha256": hashlib.sha256((ep / "goal.png").read_bytes()).hexdigest()}
    with pytest.raises(ValueError, match="pixels differ"):
        audit.goal_identity(root, ep, changed)
    # Episode file no longer matching its recorded hash.
    with pytest.raises(ValueError, match="recorded hash"):
        audit.goal_identity(root, ep, m)
    # Goal-root bytes no longer the declared source frame.
    root2, ep2, m2 = goal_fixture(tmp_path / "b")
    (root2 / "r" / "goal.png").write_bytes((root2 / "r" / "goal.png").read_bytes() + b"x")
    with pytest.raises(ValueError, match="declared source frame"):
        audit.goal_identity(root2, ep2, m2)


def test_audit_refuses_policy_episode_without_matching_goal_root(tmp_path):
    (tmp_path / "ep").mkdir()
    ep = closed_loop_episode(tmp_path / "ep", turn_fraction=1.0)
    m = json.loads((ep / "runtime_manifest.json").read_text())
    m["goal_source_frame"] = {"source": "/teacher/r/trajectory/9.jpg", "frame": 9}
    m["policy"] = {"stop_rule": "x"}
    m["fixed_goal_sha256"] = "0" * 64
    (ep / "runtime_manifest.json").write_text(json.dumps(m))
    with pytest.raises(ValueError, match="needs --goal-root"):
        audit.goal_xy(None, ep)
    root = tmp_path / "goals"
    (root / "r").mkdir(parents=True)
    (root / "goal_source.json").write_text(
        json.dumps({"goals": {"r": {"source": "/other/9.jpg", "frame": 0}}})
    )
    with pytest.raises(ValueError, match="does not match"):
        audit.goal_xy(root, ep)
