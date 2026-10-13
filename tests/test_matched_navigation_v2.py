"""Pure negative controls for finite admission, native input and scoring."""

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from matched_navigation_contracts_v2 import ORDER, admit, classify, contact_counts, score_command
from navigation_imu_boundary_v2 import bind


def test_source_binding_uses_native_sensor_after_selected_start():
    text = ast.unparse(
        bind((Path(__file__).resolve().parents[1] / "scripts/collect_option1.py").read_text())
    )
    assert "measured = body_gyro.read()" in text
    assert "measured = float(np.asarray(robot._articulation.get_velocities())" not in text
    assert text.count("body_gyro = initialize(robot, sim, start_xy, start_yaw, episode)") == 1
    assert "body_gyro = None" in text and "navigation_active = False" in text
    assert "record_tracking(robot, sim, held" in text


@pytest.mark.parametrize("bad", ["wrong_freeze", "failed", "duplicate", "unknown"])
def test_admission_rejects_invalid_prior(bad):
    prior = dict(id=ORDER[0], freeze="freeze", integrity="PASS")
    if bad == "wrong_freeze":
        prior["freeze"] = "other"
    if bad == "failed":
        prior["integrity"] = "FAIL"
    if bad == "duplicate":
        prior["id"] = ORDER[1]
    if bad == "unknown":
        prior["id"] = "unknown"
    with pytest.raises(ValueError):
        admit([prior], ORDER[1], "freeze")


def test_admission_keeps_fixed_abba_order():
    prior = [dict(id=x, freeze="freeze", integrity="PASS") for x in ORDER[:3]]
    admit(prior, ORDER[3], "freeze")
    with pytest.raises(ValueError):
        admit(prior, ORDER[4], "freeze")


@pytest.mark.parametrize("response", [0, -0.005])
def test_small_yaw_zero_or_wrong_sign_cannot_pass(response):
    rows = [dict(evaluation_v=0.05, evaluation_w=response, dt=1 / 120) for _ in range(60)]
    assert not score_command(rows, (0.05, 0.005))["passed"]


def test_small_yaw_exact_response_and_uncovered_exposure():
    rows = [dict(evaluation_v=0.05, evaluation_w=0.005, dt=1 / 120) for _ in range(60)]
    result = score_command(rows, (0.05, 0.005))
    assert result["passed"] and not result["near_zero_uncovered"]
    result = score_command(rows, (0.001, 0.0001))
    assert result["near_zero_uncovered"] and result["exposure_s"] == pytest.approx(0.5)


def test_nonfinite_tracking_rejected():
    with pytest.raises(ValueError):
        score_command([dict(evaluation_v=0.1, evaluation_w=float("nan"), dt=0.5)], (0.1, 0.1))


def test_stop_uses_predecision_pose_not_postcapture():
    manifest = dict(
        route=dict(waypoints=[[0, 0], [1, 0]], scene_index=0),
        captures=[dict(distance_to_goal_m=0.1)],
        policy_stop_frame=0,
        inference=[dict(frame=0, predecision_pose=[0, 0, 0], predecision_sim_time=0.0)],
    )
    result = classify(manifest)
    assert result["outcome"] == "wrong_stop" and not result["goal_visited"]


def test_contacts_support_fixture_and_unknown():
    result = contact_counts(
        [
            dict(paths=["/World/Robot/fl_wheel", "/World/Fixture/Scene0/Floor"]),
            dict(paths=["/World/Robot/base_link", "/World/Fixture/Scene0/Wall"]),
        ]
    )
    assert result["support"] == 1 and result["fixture"] == 1
    with pytest.raises(ValueError):
        contact_counts([dict(paths=["/World/Robot/base_link", "/Unknown"])])


def test_native_startup_order_and_no_live_teleport():
    text = (
        Path(__file__).resolve().parents[1] / "scripts/navigation_imu_boundary_v2.py"
    ).read_text()
    fn = next(
        n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == "initialize"
    )
    text = ast.unparse(fn)
    assert (
        text.index("sim.stop()")
        < text.index("authored.set_world_poses")
        < text.index("gyro = BodyGyro")
        < text.index("sim.play()")
    )
    assert "teleport" not in text and "range(120)" in text and "tick in (118, 119)" in text


def test_zero_command_reads_native_sensor_once_without_pi_update():
    from types import SimpleNamespace

    tree = bind((Path(__file__).resolve().parents[1] / "scripts/collect_option1.py").read_text())
    callback = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "on_physics_step"
    )
    events = []
    gyro = SimpleNamespace(
        raise_if_failed=lambda: None, read=lambda: events.append("read") or 0.0, fail=lambda e: None
    )
    tracker = SimpleNamespace(
        reset=lambda: events.append("reset"), update=lambda *a: pytest.fail("PI must remain reset")
    )
    held = dict(command=(0.0, 0.0, 0.0), idle=0, updates=0)
    ns = dict(
        body_gyro=gyro, tracker=tracker, held=held, wheel_targets=lambda *args: events.append(args)
    )
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[callback], type_ignores=[])),
            "callback",
            "exec",
        ),
        ns,
    )
    ns["on_physics_step"](1 / 120)
    assert events == ["read", "reset", (0.0, 0.0, 0.0)] and held["idle"] == 1


def test_first_decision_stop_does_not_receive_tail_goal_visit_or_tracking():
    from matched_navigation_contracts_v2 import tracking_summary

    manifest = dict(
        route=dict(waypoints=[[0, 0], [1, 0]], scene_index=0),
        captures=[dict(distance_to_goal_m=0.1, simulation_time=0.1)],
        policy_stop_frame=0,
        inference=[dict(frame=0, predecision_pose=[0, 0, 0], predecision_sim_time=0.0)],
    )
    result = classify(manifest)
    assert not result["goal_visited"] and result["tail_goal_visited"]
    assert result["first_stop_distance_m"] == 1 and result["first_stop_signed_margin_m"] == -0.5
    assert result["task_capture_count"] == 0
    tracking = tracking_summary([dict(frame=0, passed=True)], result["terminal_index"])
    assert tracking["task_holds"] == 0 and tracking["task_pass_fraction"] is None


def test_prior_png_gate_artifact_mutation_rejected(tmp_path):
    from development_qualification_contracts_v1 import sha
    from matched_navigation_contracts_v2 import verify_recorded_artifacts

    names = [
        "result.json",
        "episode/first_policy_input.png",
        "episode/first_policy_input.json",
        "episode/first_policy_tensors.json",
    ]
    for name in names:
        p = tmp_path / name
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(b"original")
    record = dict(id=ORDER[1], artifacts={name: sha(tmp_path / name) for name in names})
    verify_recorded_artifacts(tmp_path, record)
    (tmp_path / names[1]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact drift"):
        verify_recorded_artifacts(tmp_path, record)
