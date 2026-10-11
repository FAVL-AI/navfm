"""Pure sensor-boundary controls; no simulator/model imports."""

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from imu_controller_boundary_v1 import GyroGuard, bind_collector_source
from qualify_imu_controller_v1 import command, setup_prefix


def reading(time=1.0, valid=True, rate=0.2):
    return SimpleNamespace(time=time, is_valid=valid, ang_vel_x=0.0, ang_vel_y=0.0, ang_vel_z=rate)


def test_valid_local_gyro():
    guard = GyroGuard("/body/imu")
    assert guard.accept(reading(), 1.0, "/body/imu") == 0.2


@pytest.mark.parametrize(
    "value,now,source",
    [
        (reading(valid=False), 1.0, "/body/imu"),
        (reading(), 1.0, "/wrong/imu"),
        (reading(time=0.9), 1.0, "/body/imu"),
        (reading(time=1.1), 1.0, "/body/imu"),
        (reading(rate=float("nan")), 1.0, "/body/imu"),
        (reading(), float("inf"), "/body/imu"),
    ],
)
def test_invalid_guard_keeps_evidence(value, now, source):
    guard = GyroGuard("/body/imu")
    with pytest.raises(ValueError):
        guard.accept(value, now, source)
    assert len(guard.records) == 1


def test_duplicate_time_refused():
    guard = GyroGuard("/body/imu")
    guard.accept(reading(), 1.0, "/body/imu")
    with pytest.raises(ValueError, match="stale"):
        guard.accept(reading(), 1.005, "/body/imu")


def test_collector_replaces_only_controller_measurement():
    path = Path(__file__).resolve().parents[1] / "scripts/collect_option1.py"
    source = path.read_text()
    tree = bind_collector_source(source)
    text = ast.unparse(tree)
    assert text.count("body_gyro.read()") == 1
    assert "get_velocities()" not in text
    assert "robot.pose()" in text  # evaluation pose remains
    assert source == path.read_text()
    with pytest.raises(ValueError):
        bind_collector_source(source.replace("def on_physics_step", "def renamed_step"))


def test_probe_finite_fixed_schedule_and_setup():
    values = [command(i) for i in range(1200)]
    assert values[:120] == [(0.0, 0.0)] * 120
    assert values[960:] == [(0.0, 0.0)] * 240
    assert set(w for _, w in values) == {0.0, 0.1, 0.2, 0.4, -0.1, -0.2, -0.4}
    path = Path(__file__).resolve().parents[1] / "scripts/qualify_articulated_control.py"
    prefix = ast.unparse(setup_prefix(path.read_text()))
    assert "SimulationContext" in prefix
    assert "YawRateTracker" not in prefix


def test_launcher_supplies_cwd_and_preserves_failure(tmp_path, monkeypatch):
    import json

    import run_imu_controller_v1 as runner

    config = tmp_path / "configs/eval/imu_controller_qualification_v1.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {"cleanup_must_be_absent": [], "python": "fixed", "robot": "robot", "wall_seconds": 120}
        )
    )
    output = tmp_path.parent / (tmp_path.name + "-evidence")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "frozen", lambda *args: None)

    def invoke(cmd, env, cwd, log, timeout):
        assert cwd == tmp_path and timeout == 120
        raise ValueError("controlled child failure")

    monkeypatch.setattr(runner, "run_bounded", invoke)
    monkeypatch.setattr(sys, "argv", ["runner", "--freeze", "fixed", "--out", str(output)])
    with pytest.raises(ValueError, match="controlled child failure"):
        runner.main()
    assert json.loads((output / "ledger.json").read_text())["status"] == "FAIL"


def test_callback_latches_stops_and_raises_outside_native_boundary():
    from imu_controller_boundary_v1 import BodyGyro

    source = (Path(__file__).resolve().parents[1] / "scripts/collect_option1.py").read_text()
    tree = bind_collector_source(source)
    callback = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "on_physics_step"
    )
    step = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "step")
    sensor = object.__new__(BodyGyro)
    sensor.failure = None
    sensor.evidence_path = None
    sensor.read = lambda: (_ for _ in ()).throw(ValueError("invalid gyro"))
    targets = []
    ns = {
        "body_gyro": sensor,
        "held": {"command": (0.1, 0.0, 0.2), "updates": 0},
        "tracker": SimpleNamespace(update=lambda *args: 99),
        "wheel_targets": lambda *args: targets.append(args),
    }
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[callback], type_ignores=[])),
            "callback",
            "exec",
        ),
        ns,
    )
    ns["on_physics_step"](1 / 120)
    assert targets == [(0.0, 0.0, 0.0)]
    assert ns["held"]["command"] == (0.0, 0.0, 0.0)
    assert sensor.failure is not None
    # The main-thread pre-step check propagates before any new simulator advance.
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[step], type_ignores=[])), "step", "exec"
        ),
        ns,
    )
    with pytest.raises(RuntimeError, match="latched"):
        ns["step"]()


def test_probe_stopped_tail_has_zero_wheels_not_active_braking():
    source = (
        Path(__file__).resolve().parents[1] / "scripts/qualify_imu_controller_v1.py"
    ).read_text()
    tree = ast.parse(source)
    branch = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.If) and ast.unparse(n.test) == "v == 0 and w == 0"
    )
    calls = []
    ns = {
        "v": 0.0,
        "w": 0.0,
        "measured": 0.5,
        "tracker": SimpleNamespace(
            reset=lambda: calls.append("reset"),
            update=lambda *args: pytest.fail("stop must not brake"),
        ),
    }
    exec(compile(ast.Module(body=[branch], type_ignores=[]), "stop", "exec"), ns)
    assert calls == ["reset"] and ns["output"] == 0.0


@pytest.mark.parametrize("index", [0, 1199])
def test_invalid_evaluation_outside_scoring_window_is_refused(index):
    from imu_controller_boundary_v1 import validate_evaluation

    rows = [
        {
            "time": i / 120,
            "evaluation_w": 0.0,
            "orientation": [1.0, 0.0, 0.0, 0.0],
            "xy": [0.0, 0.0],
        }
        for i in range(1200)
    ]
    rows[index]["evaluation_w"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        validate_evaluation(rows)
    assert len(rows) == 1200  # Invalid passive evidence is not discarded.
