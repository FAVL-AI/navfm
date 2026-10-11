"""Guard boundaries that prevent false history/state reproducibility claims."""

import copy
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "initialization_diagnostic", ROOT / "scripts/initialization_diagnostic.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def state(tmp_path):
    Image.fromarray(np.zeros((240, 320, 3), dtype=np.uint8)).save(tmp_path / "live.png")
    s = dict(
        root=dict(position=[0, 0, 0.06], quaternion=[1, 0, 0, 0]),
        camera_world=dict(position=[0.2, 0, 0.61], quaternion=[1, 0, 0, 0]),
        camera_local=dict(position=[0.2, 0, 0.55], quaternion=[1, 0, 0, 0]),
        root_velocity=[0] * 6,
        joint_positions=[0] * 4,
        joint_velocities=[0] * 4,
        joint_position_targets=[0] * 4,
        joint_velocity_targets=[0] * 4,
        held_command=[0] * 3,
        controller_integral=0.0,
        settings={"dlss": 2},
        dof_names=["fl", "fr", "rl", "rr"],
        proxy_policy={"lost": True},
        asset_sha256={"fixture": "fixed"},
        image="live.png",
        sim_time=3.0,
        sensor_time=3.0,
        unknown=[],
        mechanical_ok=True,
        history=[
            dict(image="live.png", physical_step=i, sensor_time=i / 12)
            for i in [6, 12, 18, 24, 30, 36]
        ],
    )
    b = dict(
        xy_m=0.02,
        yaw_deg=2,
        z_m=0.002,
        quaternion_deg=0.2,
        joint_position=0.001,
        joint_velocity=0.01,
        root_velocity=0.01,
        controller=1e-6,
        gray_mad=2.5,
        history_age_s=1e-6,
        capture_clock_s=1e-8,
    )
    return s, b, tmp_path


def test_same_and_quaternion_sign(state):
    s, b, p = state
    t = copy.deepcopy(s)
    t["root"]["quaternion"] = [-1, 0, 0, 0]
    assert module.compare(s, t, p, b)["passed"]


@pytest.mark.parametrize(
    "key,value,failure",
    [
        ("root_velocity", [0.010001, 0, 0, 0, 0, 0], "root_velocity"),
        ("controller_integral", 0.000002, "controller_integral"),
        ("sensor_time", 3.000001, "b_capture_clock_s"),
        ("unknown", ["exposure"], "b_unverified_state"),
        ("mechanical_ok", False, "b_unverified_state"),
        ("settings", {"dlss": 0}, "settings"),
    ],
)
def test_state_fail_closed(state, key, value, failure):
    s, b, p = state
    t = copy.deepcopy(s)
    t[key] = value
    assert failure in module.compare(s, t, p, b)["failures"]


def test_full_restore_changed_ages_cannot_pass(state):
    s, b, p = state
    t = copy.deepcopy(s)
    t["sim_time"] += 8 / 12
    t["sensor_time"] += 8 / 12
    t["history"][-1]["sensor_time"] += 8 / 12
    assert "history_0_relative_age_s" in module.compare(s, t, p, b)["failures"]


def test_stale_current_image_cannot_pass(state):
    s, b, p = state
    t = copy.deepcopy(s)
    t["image"] = "different.png"
    assert "b_stale_live_history" in module.compare(s, t, p, b)["failures"]


def test_history_uses_handover_live_not_last_policy_decision():
    frames = [dict(physical_step=i + 1) for i in range(36)]
    assert [x["physical_step"] for x in module.history(frames)] == [6, 12, 18, 24, 30, 36]
    with pytest.raises(ValueError):
        module.history(frames[:-1])


def test_raw_bound_no_brightness_normalisation(state):
    s, b, p = state
    Image.fromarray(np.full((240, 320, 3), 3, dtype=np.uint8)).save(p / "changed.png")
    t = copy.deepcopy(s)
    t["image"] = "changed.png"
    for h in t["history"]:
        h["image"] = "changed.png"
    assert "history_5_gray_mad" in module.compare(s, t, p, b)["failures"]


def test_frozen_imported_contract_list():
    assert "src/navfm/collection/rgb_baseline.py" in module.FILES
    assert "src/navfm/collection/yaw_rate_tracker.py" in module.FILES
    assert "src/navfm/isaac/robot.py" in module.FILES


def test_raw_rgb_digest_is_not_encoded_png_digest(state):
    import hashlib

    _s, _b, p = state
    assert (
        module.raw_rgb_sha(p / "live.png")
        == hashlib.sha256(np.zeros((240, 320, 3), dtype=np.uint8).tobytes()).hexdigest()
    )
    assert module.raw_rgb_sha(p / "live.png") != module.sha(p / "live.png")


def test_legacy_and_recovery_schema_normalisation():
    legacy = dict(
        window_distances=[1.0],
        requested_goal_distance=1.0,
        waypoint_normalized=[0, 0],
        command=[0, 0, 0],
        predicted_distance=1.0,
        chain={"window": [0, 0]},
        policy_stop=False,
    )
    assert module.normalized_prediction(legacy)["policy_abstain"] is None
    recovery = dict(legacy, policy_abstain="scan_budget")
    assert module.normalized_prediction(recovery)["policy_abstain"] == "scan_budget"


@pytest.mark.parametrize(
    "delta,after,updates",
    [(0.0, 1.0, 1), (0.0, 1.01, 0), (1 / 12, 1 + 1 / 12, 9), (1 / 12, 1.1, 10)],
)
def test_render_interval_rejects_hidden_physics_or_missing_feedback(delta, after, updates):
    with pytest.raises(ValueError):
        module.validate_render_interval(1.0, after, delta, updates)


def test_render_interval_accepts_fixed_schedule():
    module.validate_render_interval(1.0, 1.0, 0.0, 0)
    module.validate_render_interval(1.0, 1 + 1 / 12, 1 / 12, 10)


def test_bounded_state_optional_recovery_fields_are_none():
    from navfm.collection.topomap import BoundedConfig, BoundedTopomapState

    state = BoundedTopomapState(goal_node=4, closest_node=0, bounded=BoundedConfig())
    state.lost = True
    actual = module.recorded_state_fields(
        state, ["closest_node", "lost", "_far", "_pending", "attempts", "_scan"]
    )
    assert actual == dict(closest_node=0, lost=True, _far=0, _pending=[], attempts=None, _scan=None)
