from __future__ import annotations

import os
import signal
import sys

import pytest
from scripts.run_static_arrival_startup_diagnostic_v1 import (
    child_environment,
    supervise,
)


def test_child_environment_pins_hub_without_mutating_parent():
    parent = {"PATH": os.environ.get("PATH", ""), "OMNICLIENT_HUB_MODE": "shared"}
    child = child_environment(parent)
    assert child["OMNICLIENT_HUB_MODE"] == "disabled"
    assert parent["OMNICLIENT_HUB_MODE"] == "shared"


def test_supervisor_records_harmless_child_exit_and_reap(tmp_path):
    output = tmp_path / "normal"
    record = supervise(
        [sys.executable, "-c", "print('harmless child complete')"],
        output,
        env=dict(os.environ),
        cwd=tmp_path,
        execution_limit_s=3,
        cleanup_reserve_s=1,
    )
    assert record["child_exit_code"] == 0
    assert record["child_reaped"] is True
    assert record["timeout"] is False
    assert record["status"] == "FAIL_STARTUP_INCOMPLETE"
    assert record["within_budget"] is True
    assert (output / "terminal.json").is_file()


def test_supervisor_times_out_signals_and_reaps_harmless_child(tmp_path):
    output = tmp_path / "timeout"
    record = supervise(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        output,
        env=dict(os.environ),
        cwd=tmp_path,
        execution_limit_s=0.25,
        cleanup_reserve_s=1,
    )
    assert record["timeout"] is True
    assert record["child_reaped"] is True
    assert record["child_exit_code"] in (-signal.SIGTERM, -signal.SIGKILL)
    assert record["termination_requests"][0]["signal"] == "SIGTERM"
    assert record["status"] == "FAIL_EXECUTION_TIMEOUT"
    assert record["within_budget"] is True


def test_supervisor_refuses_populated_output(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        supervise(
            [sys.executable, "-c", "pass"],
            output,
            env=dict(os.environ),
            cwd=tmp_path,
            execution_limit_s=1,
            cleanup_reserve_s=1,
        )
