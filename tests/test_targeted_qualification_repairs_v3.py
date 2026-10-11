"""Pure v3 lifecycle and authenticated alias checks, without runtime imports."""

import ast
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from imu_lifecycle_v3 import instrument_initialization, instrument_probe, preserve_nonfinite
from nomad_dependency_boundary_v3 import verify_loaded_dependencies


def test_initialization_order_and_preserved_commands():
    source = Path(__file__).resolve().parents[1] / "scripts/qualify_imu_controller_v1.py"
    text = ast.unparse(instrument_initialization(instrument_probe(source.read_text())))
    positions = [
        text.index(x)
        for x in [
            "robot.teleport((-3, 0), 0)",
            "sim.stop()",
            "gyro = ObservedBodyGyro",
            "gyro.sensor.resume()",
            "sim.play()",
            "robot._articulation.initialize()",
        ]
    ]
    assert positions == sorted(positions)
    assert text.count("robot.teleport((-3, 0), 0)") == 1
    assert "range(1200)" in text and "gyro.observe_readiness(tick)" in text
    assert "initial pose changed across sensor restart" in text


def test_changed_initialization_boundary_is_refused():
    with pytest.raises(ValueError):
        instrument_initialization(ast.parse("gyro=ObservedBodyGyro(robot, sim)"))


@pytest.mark.parametrize("failure", [None, "foreign_binary", "altered_binary", "wrong_object"])
def test_alias_requires_exact_object_and_authenticated_binary(tmp_path, failure):
    binary = tmp_path / "_C.so"
    binary.write_bytes(b"approved")
    obj = SimpleNamespace()
    parent = SimpleNamespace(__file__=str(binary), _dynamo=SimpleNamespace(compiled_autograd=obj))
    manifest = {
        "files": [{"path": str(binary), "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}]
    }
    if failure == "foreign_binary":
        other = tmp_path / "foreign.so"
        other.write_bytes(b"approved")
        parent.__file__ = str(other)
    if failure == "altered_binary":
        binary.write_bytes(b"changed")
    modules = {
        "torch._C": parent,
        "torch._C._dynamo.autograd_compiler": obj
        if failure != "wrong_object"
        else SimpleNamespace(),
    }
    if failure:
        with pytest.raises(ImportError):
            verify_loaded_dependencies(manifest, modules)
    else:
        records = verify_loaded_dependencies(manifest, modules)
        assert records[1]["attribute_path"] == "_dynamo.compiled_autograd"


@pytest.mark.parametrize("case", ["early_invalid", "boundary_invalid", "boundary_stale"])
def test_readiness_preserves_early_invalid_but_blocks_boundary(case):
    from imu_controller_boundary_v1 import GyroGuard

    source = Path(__file__).resolve().parents[1] / "scripts/qualify_imu_controller_v3.py"
    tree = ast.parse(source.read_text())
    method = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "observe_readiness"
    )
    events = []
    namespace = {
        "phase_mark": lambda name, **fields: events.append((name, fields)),
        "preserve_nonfinite": preserve_nonfinite,
    }
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
            "readiness-test",
            "exec",
        ),
        namespace,
    )
    value = SimpleNamespace(
        is_valid=case != "boundary_invalid", time=1.0, ang_vel_x=0.0, ang_vel_y=0.0, ang_vel_z=0.0
    )
    obj = SimpleNamespace(
        interface=SimpleNamespace(get_sensor_reading=lambda *a, **k: value),
        path="/imu",
        sim=SimpleNamespace(current_time=1.0),
        readiness_guard=GyroGuard("/imu"),
    )
    if case == "early_invalid":
        value.is_valid = False
        namespace["observe_readiness"](obj, 117)
        assert not obj.readiness_guard.records and events[0][1]["valid"] is False
    else:
        if case == "boundary_stale":
            obj.readiness_guard.last_time = 1.0
        with pytest.raises(ValueError):
            namespace["observe_readiness"](obj, 119)
        assert events[0][0] == "NATIVE_READINESS_OBSERVATION"


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_readiness_evidence_retained_without_validation_relaxation(tmp_path, number):
    import json

    from imu_controller_boundary_v1 import GyroGuard
    from imu_lifecycle_v3 import PhaseLog

    evidence = tmp_path / "phases.jsonl"
    value = SimpleNamespace(is_valid=True, time=1.0, ang_vel_x=0.0, ang_vel_y=0.0, ang_vel_z=number)
    source = Path(__file__).resolve().parents[1] / "scripts/qualify_imu_controller_v3.py"
    method = next(
        n
        for n in ast.walk(ast.parse(source.read_text()))
        if isinstance(n, ast.FunctionDef) and n.name == "observe_readiness"
    )
    namespace = {"phase_mark": PhaseLog(evidence).mark, "preserve_nonfinite": preserve_nonfinite}
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])),
            "readiness-test",
            "exec",
        ),
        namespace,
    )
    obj = SimpleNamespace(
        interface=SimpleNamespace(get_sensor_reading=lambda *a, **k: value),
        path="/imu",
        sim=SimpleNamespace(current_time=1.0),
        readiness_guard=GyroGuard("/imu"),
    )
    namespace["observe_readiness"](obj, 117)
    saved = json.loads(evidence.read_text())
    assert saved["angular_velocity"][2]["nonfinite_numeric"] == repr(number)
    with pytest.raises(ValueError, match="nonfinite"):
        namespace["observe_readiness"](obj, 119)
