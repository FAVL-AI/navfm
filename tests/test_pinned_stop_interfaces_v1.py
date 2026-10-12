"""Hermetic adapter guards; actual native parity has a separate frozen source-cache probe."""

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pinned_stop_interfaces_v1 import (
    authenticated_module,
    load_config,
    validate_acquisition,
    validate_configuration,
    validate_reference,
)


def inputs():
    ids = ["synthetic0", "synthetic1"]
    hashes = [hashlib.sha256(v.encode()).hexdigest() for v in ids]
    return ids, hashes, np.eye(2), np.array([[0, 0.25], [0, 0]])


def test_supported_and_unsupported_goal_identity_do_not_force_nearest_node():
    ids, hashes, d, g = inputs()
    ok = validate_reference(load_config(), ids, hashes, d, g, ids[1], hashes[1])
    assert ok.goal == 1 and not ok.unsupported_goal
    absent = validate_reference(load_config(), ids, hashes, d, g, "absent", hashes[1])
    assert absent.goal is None and absent.unsupported_goal
    mismatched = validate_reference(load_config(), ids, hashes, d, g, ids[1], hashes[0])
    assert mismatched.unsupported_goal
    ambiguous = validate_reference(load_config(), ids, [hashes[0]] * 2, d, g, ids[0], hashes[0])
    assert ambiguous.unsupported_goal


@pytest.mark.parametrize(
    "mutation",
    [
        "nonfinite",
        "unnormalized",
        "negative_graph",
        "shape",
        "duplicate_id",
        "empty_id",
        "hash_shape",
        "integer_dtype",
    ],
)
def test_invalid_reference_contract_fails(mutation):
    ids, hashes, d, g = inputs()
    if mutation == "nonfinite":
        d[0, 0] = np.nan
    if mutation == "unnormalized":
        d *= 2
    if mutation == "negative_graph":
        g[0, 1] = -1
    if mutation == "shape":
        g = np.zeros((3, 3))
    if mutation == "duplicate_id":
        ids[1] = ids[0]
    if mutation == "empty_id":
        ids[0] = ""
    if mutation == "hash_shape":
        hashes[0] = "short"
    if mutation == "integer_dtype":
        d = d.astype(int)
    with pytest.raises(ValueError):
        validate_reference(load_config(), ids, hashes, d, g, ids[1], hashes[1])


@pytest.mark.parametrize(
    "episode,sequence,clock",
    [
        ("wrong", 1, 0.25),
        ("episode", 0, 0.25),
        ("episode", 2, 0.25),
        ("episode", 1, 0.5),
        ("episode", 1, float("nan")),
        ("episode", True, 0.25),
        ("episode", 1.0, 0.25),
    ],
)
def test_acquisition_order_and_identity_are_not_interchangeable(episode, sequence, clock):
    with pytest.raises(ValueError):
        validate_acquisition(load_config(), "episode", 0, 0.0, episode, sequence, clock)


def test_correct_acquisition_and_budget_exhaustion():
    cfg = load_config()
    validate_acquisition(cfg, "episode", 0, 0.0, "episode", 1, 0.25)
    with pytest.raises(ValueError, match="budget exhausted"):
        validate_acquisition(cfg, "episode", 15, 3.75, "episode", 16, 4.0)


def test_source_tampering_rejected_before_any_ast_execution(tmp_path):
    p = tmp_path / "source.py"
    p.write_text("raise RuntimeError('must not execute')\n")
    spec = load_config()["sources"]["placenav"]["belief"]
    with pytest.raises(ValueError, match="hash/blob identity mismatch"):
        authenticated_module("placenav", p, spec)
    wrong = dict(spec, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="unapproved native source digest"):
        authenticated_module("placenav", p, wrong)


def test_native_constants_cannot_be_silently_tuned():
    cfg = load_config()
    cfg["native_constants"]["placenav"]["delta"] = 5
    with pytest.raises(ValueError, match="configuration drift"):
        validate_configuration(cfg)


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_admitted_native_floating_dtype_is_preserved(dtype):
    ids, hashes, d, g = inputs()
    admitted = validate_reference(load_config(), ids, hashes, d.astype(dtype), g, ids[1], hashes[1])
    assert admitted.descriptors.dtype == dtype


@pytest.mark.parametrize("mode", ["nonzero", "timeout", "launch_error"])
def test_supervisor_preserves_actual_exit_timeout_and_reaping(tmp_path, mode):
    from qualify_pinned_stop_interfaces_v1 import supervise_worker

    command = [sys.executable, "-c", "raise SystemExit(3)"]
    if mode == "timeout":
        command = [sys.executable, "-c", "import time; time.sleep(5)"]
    if mode == "launch_error":
        command = [str(tmp_path / "absent_executable")]
    with (tmp_path / "worker.log").open("w") as log:
        outcome = supervise_worker(command, log, 0.05 if mode == "timeout" else 2)
    if mode == "nonzero":
        assert outcome == {"exit_code": 3, "timeout": False, "reaped": True}
    if mode == "timeout":
        assert outcome["exit_code"] < 0 and outcome["timeout"] is True and outcome["reaped"] is True
    if mode == "launch_error":
        assert outcome["exit_code"] is None and outcome["reaped"] is False
        assert outcome["exception_type"] == "FileNotFoundError"
