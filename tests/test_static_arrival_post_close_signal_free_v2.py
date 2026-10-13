from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import static_arrival_post_close_signal_free_v2 as diagnostic  # noqa: E402


def _config(tmp_path: Path) -> dict:
    config = diagnostic.build_config(ROOT)
    config["evidence"]["root"] = str(tmp_path / "evidence")
    config["evidence"]["registry"] = str(tmp_path / "registry")
    return config


def _run(tmp_path: Path, monkeypatch, mode: str, *, deadline: float = 2.0) -> tuple[dict, Path]:
    config = _config(tmp_path)
    monkeypatch.setattr(diagnostic, "verify_config", lambda _config, _root: None)
    output = Path(config["evidence"]["root"]) / "attempt-01"
    command = [
        sys.executable,
        str(ROOT / "scripts/static_arrival_post_close_bootstrap_v1.py"),
        "--worker",
        str(ROOT / "tests/fixtures/static_arrival_post_close_signal_free_harmless_worker.py"),
        mode,
    ]
    result = diagnostic.run_once(
        config=config,
        freeze="signal-free-harmless-test",
        output=output,
        registry=Path(config["evidence"]["registry"]),
        command=command,
        root=ROOT,
        child_deadline_seconds=deadline,
        reap_reserve_seconds=1.0,
    )
    return result, output


def test_v2_config_disables_all_predeadline_instrumentation():
    config = diagnostic.build_config(ROOT)
    diagnostic.verify_config(config, ROOT)
    assert config["observation"]["parent_exit_observation"] == "passive_poll_only"
    assert config["observation"]["trace_signals"] is False
    assert config["observation"]["debugger_attachment"] is False
    assert config["observation"]["background_sampler"] is False
    assert "thread_snapshots.jsonl" not in str(config)
    assert config["observation"]["child_deadline_seconds"] == 60.0
    assert config["observation"]["termination_reap_reserve_seconds"] == 10.0


def test_natural_exit_after_final_marker_is_observed_without_interference(tmp_path, monkeypatch):
    result, output = _run(tmp_path, monkeypatch, "exit_after_marker")
    events = [
        json.loads(line) for line in (output / "lifecycle_events.jsonl").read_text().splitlines()
    ]
    marker_ns = next(
        row["monotonic_ns"] for row in events if row["event"] == "worker_main_returned"
    )
    assert result["natural_zero_exit_before_deadline"] is True
    assert result["timed_out"] is False and result["child_reaped"] is True
    assert result["child_exit_code"] == 0
    assert result["child_exit_observed_monotonic_ns"] - marker_ns >= 250_000_000
    parent_events = (output / "supervisor_events.jsonl").read_text()
    assert "signal" not in parent_events
    assert result["dataset_admission"] is False
    assert not (output / "thread_snapshots.jsonl").exists()


def test_deadline_cleanup_is_not_a_natural_exit(tmp_path, monkeypatch):
    result, output = _run(tmp_path, monkeypatch, "hang_after_marker", deadline=0.6)
    assert result["timed_out"] is True
    assert result["natural_zero_exit_before_deadline"] is False
    assert result["child_reaped"] is True
    assert result["child_exit_code"] != 0
    parent_events = [
        json.loads(line) for line in (output / "supervisor_events.jsonl").read_text().splitlines()
    ]
    assert [
        row.get("signal") for row in parent_events if row["event"] == "cleanup_signal_requested"
    ] == ["SIGTERM"]


def test_abnormal_child_exit_is_not_natural_success(tmp_path, monkeypatch):
    result, _output = _run(tmp_path, monkeypatch, "abnormal_after_marker")
    assert result["child_exit_code"] == 9
    assert result["timed_out"] is False and result["child_reaped"] is True
    assert result["natural_zero_exit_before_deadline"] is False


def test_populated_attempt_directory_is_refused(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setattr(diagnostic, "verify_config", lambda _config, _root: None)
    output = Path(config["evidence"]["root"]) / "attempt-01"
    output.mkdir(parents=True)
    with pytest.raises(ValueError, match="fresh external evidence"):
        diagnostic.run_once(
            config=config,
            freeze="fixture",
            output=output,
            registry=Path(config["evidence"]["registry"]),
            command=[sys.executable, "-c", "pass"],
            root=ROOT,
        )
