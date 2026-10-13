import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.controller_telemetry_v1 import (
    artifact_hashes,
    checked_array,
    derived_clipping,
    instrument,
)


def test_transform_preserves_native_read_and_schedule():
    source = Path("scripts/imu_coverage_base_v2.py").read_text()
    transformed = instrument(source)
    ast.parse(transformed)
    assert (
        transformed.count("measured = gyro.read()") == source.count("measured = gyro.read()") == 1
    )
    assert "range(1200)" in transformed and "tracker.update(w, measured, 1 / 120)" in transformed
    assert (
        transformed.index("TELEMETRY_REQUESTED_TARGET")
        < transformed.index("set_joint_velocity_targets(target)")
        < transformed.index("TELEMETRY_ACCEPTED_TARGET")
    )
    assert transformed.index("sim.step(render=False)") < transformed.index("TELEMETRY_POST_PHYSICS")


def test_boundary_drift_rejected():
    with pytest.raises(ValueError):
        instrument("changed")


def test_schema_and_nonfinite_rejected():
    assert checked_array([[1.0, 2.0]], 2) == [1.0, 2.0]
    for v in [[1.0], [float("nan"), 2], None, [True, 2.0]]:
        with pytest.raises(ValueError):
            checked_array(v, 2)


def test_derived_flags_not_state_mutation():
    g = SimpleNamespace(feedforward=1.0, kp=1.0, ki=4.0, integral_limit=0.5, output_limit=1.5)
    d = derived_clipping(0.5, 0.5, 1.0, -1.0, g, 1.5)
    assert d["derived_integral_clipped"] and d["derived_output_clipped"]
    assert g.ki == 4


def test_partial_failure_artifacts_bound(tmp_path):
    import hashlib

    (tmp_path / "attempt").mkdir()
    (tmp_path / "attempt/lifecycle.jsonl").write_text('{"phase":"partial"}\n')
    (tmp_path / "process.log").write_text("timeout")
    hashes = artifact_hashes(tmp_path)
    assert (
        hashes["attempt/lifecycle.jsonl"]
        == hashlib.sha256((tmp_path / "attempt/lifecycle.jsonl").read_bytes()).hexdigest()
    )
    assert "process.log" in hashes and "attempt/imu_qualification.json" not in hashes
