from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import static_arrival_camera_qualification_continuation_v2 as continuation  # noqa: E402
import static_arrival_camera_qualification_worker_v2 as worker_v2  # noqa: E402

from navfm.collection.static_arrival_camera_qualification import build_worker_input  # noqa: E402


def _config(tmp_path: Path) -> dict:
    config = continuation.build_config(ROOT)
    config["evidence"]["root"] = str(tmp_path / "evidence")
    config["evidence"]["registry"] = str(tmp_path / "registry")
    return config


def _worker(mode: str) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts/static_arrival_camera_child_bootstrap_v2.py"),
        "--worker",
        str(ROOT / "tests/fixtures/static_arrival_camera_qualification_worker.py"),
        "--mode",
        mode,
    ]


def _run(tmp_path: Path, mode: str, monkeypatch, cap: float | None = None) -> dict:
    config = _config(tmp_path)
    monkeypatch.setattr(
        continuation,
        "verify_config",
        lambda _config, root: continuation.verify_source_bindings(
            continuation.build_qualification(root), root
        ),
    )
    if cap is not None:
        monkeypatch.setattr(continuation, "CAP_SECONDS", cap)
    return continuation.run_once(
        config=config,
        output=Path(config["evidence"]["root"]) / "attempt-01",
        registry=Path(config["evidence"]["registry"]),
        freeze="fixture-freeze",
        worker_command=_worker(mode),
        root=ROOT,
    )


def test_v2_freeze_preserves_camera_criteria_and_requires_graceful_close():
    config = continuation.build_config(ROOT)
    base = continuation.build_qualification(ROOT)
    assert (
        config["population"]
        == base["population"]
        == {
            "frames": 8,
            "references": 3,
            "queries": 5,
        }
    )
    assert config["camera"] == base["camera"]
    assert config["schedule"] == base["schedule"]
    assert config["budget"] == base["budget"]
    assert config["shutdown_contract"]["fast_shutdown"] is False
    assert config["shutdown_contract"]["close_return_required"] is True
    assert config["shutdown_contract"]["sdk_cleanup_claim"] == "NOT_INDEPENDENTLY_OBSERVED"
    assert config["amendment_status"] == "REVIEW_REQUIRED_NOT_EXECUTED"
    continuation.verify_config(config, ROOT)


def test_v2_harmless_child_capsule_and_full_parent_transaction_pass(tmp_path, monkeypatch):
    result = _run(tmp_path, "success", monkeypatch)
    output = Path(_config(tmp_path)["evidence"]["root"]) / "attempt-01"
    registry_terminal = Path(_config(tmp_path)["evidence"]["registry"]) / (
        "technical-scene0-v2.reserved.terminal.json"
    )
    assert result["status"] == "QUALIFICATION_PASS"
    assert result["child_exit_code"] == 0 and result["child_reaped"] is True
    assert result["timeout"] is False
    assert result["sdk_cleanup_completion"] == "NOT_INDEPENDENTLY_OBSERVED"
    continuation.verify_completion(
        output,
        registry_terminal,
        "fixture-freeze",
        build_worker_input(_config(tmp_path))
        | {"shutdown_contract": _config(tmp_path)["shutdown_contract"]},
    )
    assert json.loads((output / "qualification_complete.json").read_text())[
        "measurement_capsule_sha256"
    ]


def test_complete_capsule_does_not_override_missing_close_return(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="report terminal/schedule"):
        _run(tmp_path, "no_close_return", monkeypatch)
    output = tmp_path / "evidence" / "attempt-01"
    capsule = json.loads((output / "measurement_complete.json").read_text())
    assert capsule["measurement_status"] == "COMPLETE_BEFORE_SHUTDOWN"
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert terminal["status"] == "FAIL"
    assert terminal["child_exit_code"] == 0 and terminal["child_reaped"] is True


def test_missing_measurement_capsule_vetoes_final_admission(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="capsule"):
        _run(tmp_path, "capsule_failure", monkeypatch)
    assert not (tmp_path / "evidence" / "attempt-01" / "qualification_complete.json").exists()
    terminal = json.loads(
        (tmp_path / "evidence" / "attempt-01" / "terminal_record.json").read_text()
    )
    assert terminal["status"] == "FAIL"
    assert terminal["child_exit_code"] == 0 and terminal["child_reaped"] is True


def test_abnormal_harmless_child_is_not_admitted(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="worker failed"):
        _run(tmp_path, "failure", monkeypatch)
    terminal = json.loads(
        (tmp_path / "evidence" / "attempt-01" / "terminal_record.json").read_text()
    )
    assert terminal["status"] == "FAIL"
    assert terminal["child_exit_code"] == 7 and terminal["child_reaped"] is True


def test_timeout_harmless_child_is_not_admitted(tmp_path, monkeypatch):
    with pytest.raises((TimeoutError, ValueError)):
        _run(tmp_path, "hang", monkeypatch, cap=30.1)
    terminal = json.loads(
        (tmp_path / "evidence" / "attempt-01" / "terminal_record.json").read_text()
    )
    assert terminal["status"] == "FAIL"
    assert terminal["timeout"] is True and terminal["child_reaped"] is True


def test_final_marker_failure_revokes_terminal_pass(tmp_path, monkeypatch):
    original = continuation._atomic_json
    fail_once = {"armed": True}

    def failing_marker(path, value):
        if Path(path).name == "qualification_complete.json" and fail_once["armed"]:
            fail_once["armed"] = False
            raise OSError("controlled marker persistence failure")
        return original(path, value)

    monkeypatch.setattr(continuation, "_atomic_json", failing_marker)
    with pytest.raises(OSError, match="controlled marker"):
        _run(tmp_path, "success", monkeypatch)
    output = tmp_path / "evidence" / "attempt-01"
    assert not (output / "qualification_complete.json").exists()
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert terminal["status"] == "FAIL" and terminal["finalization_complete"] is False


def test_deadline_crossed_during_final_verification_revokes_admission(tmp_path, monkeypatch):
    calls = {"count": 0}

    def crossing_elapsed(started):
        calls["count"] += 1
        if calls["count"] < 4:
            return 0.0
        return continuation.CAP_SECONDS + 0.1

    monkeypatch.setattr(continuation, "_elapsed_seconds", crossing_elapsed)
    with pytest.raises(TimeoutError, match="verification exceeded budget"):
        _run(tmp_path, "success", monkeypatch)
    output = tmp_path / "evidence" / "attempt-01"
    assert not (output / "qualification_complete.json").exists()
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert terminal["status"] == "FAIL"
    assert terminal["timeout"] is True
    assert terminal["whole_process_deadline_exceeded"] is True
    assert terminal["occupied_wall_seconds"] > continuation.CAP_SECONDS
    assert calls["count"] >= 4


def test_production_capsule_write_failure_is_not_admitted(tmp_path, monkeypatch):
    config = continuation.build_config(ROOT)
    worker_input = build_worker_input(config) | {"shutdown_contract": config["shutdown_contract"]}
    output = tmp_path / "attempt"
    (output / "capture_metadata").mkdir(parents=True)
    (output / "policy_inputs" / "images").mkdir(parents=True)
    rows = []
    for frame in worker_input["frames"]:
        image_id = frame["image_id"]
        rows.append({"image_id": image_id, "status": "PASS"})
        (output / "capture_metadata" / f"{image_id}.json").write_text("{}")
        (output / "policy_inputs" / "images" / f"{image_id}.jpg").write_bytes(b"fixture")

    def fail_capsule_write(*_args, **_kwargs):
        raise OSError("controlled capsule persistence failure")

    monkeypatch.setattr(worker_v2, "atomic_snapshot", fail_capsule_write)
    with pytest.raises(OSError, match="capsule persistence"):
        worker_v2._persist_measurement_capsule(output, {"frames": rows}, worker_input)
    assert not (output / "measurement_complete.json").exists()
    assert not (output / "qualification_complete.json").exists()


def test_attempt_record_persistence_failure_is_retained_in_registry(tmp_path, monkeypatch):
    original = continuation._atomic_json

    def fail_attempt_record(path, value):
        if Path(path).name == "attempt_start.json":
            raise OSError("controlled attempt record failure")
        return original(path, value)

    monkeypatch.setattr(continuation, "_atomic_json", fail_attempt_record)
    with pytest.raises(OSError, match="controlled attempt record"):
        _run(tmp_path, "success", monkeypatch)
    registry_terminal = tmp_path / "registry" / "technical-scene0-v2.reserved.terminal.json"
    terminal = json.loads(registry_terminal.read_text())
    assert terminal["status"] == "FAIL"
    assert terminal["failure_type"] == "OSError"
    assert terminal["child_exit_code"] is None
