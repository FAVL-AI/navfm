from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import static_arrival_post_close_diagnostic_v1 as diagnostic  # noqa: E402


def _config(tmp_path: Path) -> dict:
    config = diagnostic.build_config(ROOT)
    config["evidence"]["root"] = str(tmp_path / "evidence")
    config["evidence"]["registry"] = str(tmp_path / "registry")
    return config


def _run(tmp_path: Path, monkeypatch, mode: str, *, deadline: float = 3.0) -> tuple[dict, Path]:
    config = _config(tmp_path)
    monkeypatch.setattr(diagnostic, "verify_config", lambda _config, _root: None)
    output = Path(config["evidence"]["root"]) / "attempt-01"
    command = [
        sys.executable,
        str(ROOT / "scripts/static_arrival_post_close_bootstrap_v1.py"),
        "--worker",
        str(ROOT / "tests/fixtures/static_arrival_post_close_harmless_worker.py"),
        mode,
    ]
    result = diagnostic.run_once(
        config=config,
        freeze="harmless-child-test",
        output=output,
        registry=Path(config["evidence"]["registry"]),
        command=command,
        root=ROOT,
        child_deadline_seconds=deadline,
        reap_reserve_seconds=1.0,
        trace_interval_seconds=0.1,
    )
    return result, output


def test_config_binds_sources_and_declares_diagnostic_only_scope():
    config = diagnostic.build_config(ROOT)
    diagnostic.verify_config(config, ROOT)
    assert config["observation"]["construct_scene"] is False
    assert config["observation"]["construct_camera"] is False
    assert config["observation"]["worker_deadline_seconds"] == 60.0
    assert config["observation"]["termination_reap_reserve_seconds"] == 10.0
    assert config["observation"]["thread_local_values"] is False
    assert config["observation"]["environment_dump"] is False


def test_harmless_bootstrap_and_worker_exit_are_recorded(tmp_path, monkeypatch):
    result, output = _run(tmp_path, monkeypatch, "success")
    assert result["child_exit_code"] == 0
    assert result["timed_out"] is False and result["child_reaped"] is True
    events = [
        json.loads(line)["event"]
        for line in (output / "lifecycle_events.jsonl").read_text().splitlines()
    ]
    assert "bootstrap_exec_handoff_requested" in events
    assert "bootstrap_handoff_completed_at_harmless_worker" in events
    assert "simulation_app_close_return" in events
    assert "worker_final_report_written" in events
    assert "worker_main_returned" in events
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert terminal["dataset_admission"] is False
    assert terminal["finalization_complete"] is True


def test_abnormal_harmless_child_exit_is_preserved(tmp_path, monkeypatch):
    result, _output = _run(tmp_path, monkeypatch, "failure")
    assert result["child_exit_code"] == 7
    assert result["timed_out"] is False and result["child_reaped"] is True
    assert result["status"] == "PROCESS_EXITED_NONZERO_BEFORE_DEADLINE"


def test_timeout_requests_termination_and_reaps_harmless_child(tmp_path, monkeypatch):
    result, output = _run(tmp_path, monkeypatch, "hang", deadline=0.8)
    assert result["timed_out"] is True
    assert result["child_reaped"] is True
    assert result["child_exit_code"] is not None
    parent_events = [
        json.loads(line)["event"]
        for line in (output / "supervisor_events.jsonl").read_text().splitlines()
    ]
    assert "child_deadline_reached" in parent_events
    assert "termination_requested" in parent_events
    assert "bounded_thread_trace_requested" in parent_events
    snapshots = (output / "thread_snapshots.jsonl").read_text().splitlines()
    assert snapshots
    assert all("daemon" in row and "alive" in row for row in json.loads(snapshots[0])["threads"])


def test_fresh_output_is_required(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setattr(diagnostic, "verify_config", lambda _config, _root: None)
    registry = Path(config["evidence"]["registry"])
    output = Path(config["evidence"]["root"]) / "attempt-01"
    output.mkdir(parents=True)
    with pytest.raises(ValueError, match="fresh external attempt"):
        diagnostic.run_once(
            config=config,
            freeze="harmless-child-test",
            output=output,
            registry=registry,
            command=[sys.executable, "-c", "pass"],
            root=ROOT,
        )


def test_attempt_record_failure_prevents_child_start(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setattr(diagnostic, "verify_config", lambda _config, _root: None)
    monkeypatch.setattr(
        diagnostic, "_atomic_json", lambda *_args: (_ for _ in ()).throw(OSError("disk"))
    )
    output = Path(config["evidence"]["root"]) / "attempt-01"
    with pytest.raises(OSError, match="disk"):
        diagnostic.run_once(
            config=config,
            freeze="harmless-child-test",
            output=output,
            registry=Path(config["evidence"]["registry"]),
            command=[sys.executable, "-c", "pass"],
            root=ROOT,
        )
    assert not (output / "worker.stdout").exists()
