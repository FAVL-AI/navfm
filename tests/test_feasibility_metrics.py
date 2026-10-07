import pytest

from navfm.collection.feasibility_metrics import summarize


def fixture(stops):
    return {
        "captures": [
            {
                "distance_to_goal_m": 1.0,
                "aabb_clearance_m": 0.2,
                "step_duration_s": 0.1,
                "wall_loop_ms": 10,
            },
            {
                "distance_to_goal_m": 0.4,
                "aabb_clearance_m": 0.3,
                "step_duration_s": 0.1,
                "wall_loop_ms": 20,
            },
        ],
        "inference": [
            {"physics_frame": i, "policy_stop": stop, "latency_ms": 10}
            for i, stop in enumerate(stops)
        ],
        "fixture": {"goal_radius_m": 0.5, "safety_clearance_m": 0.3},
        "contacts": [],
        "metrics": {"termination": "policy_stop" if any(stops) else "timeout"},
    }


def transitions():
    return [
        {"pose_before": [0, 0, 0], "pose_after": [0.1, 0, 0]},
        {"pose_before": [0.1, 0, 0], "pose_after": [0.2, 0, 0]},
    ]


def test_goal_proximity_without_stop_is_not_success():
    result = summarize(fixture([False, False]), transitions())
    assert result["navigation_success_episodes"] == 0
    assert result["final_position_in_goal_episodes"] == 1
    assert result["correct_stop_rate"] is None
    assert result["premature_stop_rate"] is None
    assert result["path_length_m"] == pytest.approx(0.2)
    assert result["envelope_violation_duration_s"] == pytest.approx(0.1)


def test_stop_classification_and_collision_disqualification():
    data = fixture([True, True])
    result = summarize(data, transitions())
    assert result["correct_stop_events"] == result["premature_stop_events"] == 1
    assert result["navigation_success_episodes"] == 1
    data["contacts"] = [{"sim_time": 0.1}]
    assert summarize(data, transitions())["navigation_success_episodes"] == 0
    data["contacts"] = []
    data["metrics"]["termination"] = "timeout"
    assert summarize(data, transitions())["navigation_success_episodes"] == 0


def test_missing_recording_is_rejected():
    with pytest.raises(ValueError):
        summarize(fixture([False, False]), transitions()[:1])
