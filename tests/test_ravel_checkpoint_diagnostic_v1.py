"""Hermetic structural diagnostics and CPU-only admission guards; no checkpoint load."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from diagnose_ravel_checkpoint_v1 import CONFIG, validate_protocol
from ravel_fixed_graph_v1 import checkpoint_admitted, checkpoint_structure


def test_checkpoint_diagnostics_separate_shapes_parameters_buffers_and_unused_keys():
    report = checkpoint_structure(
        {"learned": [2], "running": [1]},
        {"learned": [2]},
        {"running": [1]},
        {"learned": [3], "unused": [4]},
    )
    assert report["missing_parameters"] == []
    assert report["missing_buffers"] == ["running"]
    assert report["unexpected_keys"] == ["unused"]
    assert report["shape_mismatches"] == {"learned": {"expected": [2], "supplied": [3]}}
    assert not checkpoint_admitted(report["missing_parameters"], report["unexpected_keys"])


def test_diagnostics_preserve_existing_parameter_and_unexpected_key_guard():
    assert not checkpoint_admitted(["learned"], [])
    assert not checkpoint_admitted([], ["unused"])
    assert checkpoint_admitted([], [])


@pytest.mark.parametrize(
    "key", ["forwards", "GPU_calls", "constructor_attempts", "worker_cpu_wall_s"]
)
def test_cpu_checkpoint_budget_rejects_implicit_expansion(key):
    cfg = json.loads(CONFIG.read_text())
    cfg["caps"][key] += 1
    with pytest.raises(ValueError, match="CPU diagnostic budget"):
        validate_protocol(cfg)


def test_superpoint_evidence_cannot_complete_targeted_lightglue_diagnosis():
    from diagnose_ravel_checkpoint_v1 import targeted_diagnostic_complete

    required = [
        {"event": "CONSTRUCTOR_ATTEMPT", "kind": "lightglue"},
        {"event": "STATE_LOAD_DIAGNOSTIC", "kind": "lightglue", "sequence": 1},
        {"event": "STATE_LOAD_RESULT", "kind": "lightglue", "sequence": 1},
        {"event": "STATE_LOAD_DIAGNOSTIC", "kind": "lightglue", "sequence": 2},
        {"event": "STATE_LOAD_RESULT", "kind": "lightglue", "sequence": 2},
        {"event": "FINAL_ADMISSION_DIAGNOSTIC", "kind": "lightglue"},
    ]
    assert targeted_diagnostic_complete(required)
    assert not targeted_diagnostic_complete([dict(row, kind="superpoint") for row in required])
    for omitted in range(len(required)):
        assert not targeted_diagnostic_complete(required[:omitted] + required[omitted + 1 :])
