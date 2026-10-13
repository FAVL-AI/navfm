import ast
import json
import sys
from itertools import pairwise
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from prospective_timing_contracts_v1 import Events, TimedContext, timing_capture


def test_actual_transform_reverses_to_unchanged_capture():
    original = (Path(__file__).parents[1] / "scripts/prospective_capture_v1.py").read_text()
    tree = timing_capture(original)

    class Reverse(ast.NodeTransformer):
        def visit_Call(self, node):
            if ast.unparse(node.func) == "events.call":
                return self.visit(
                    ast.Call(func=node.args[1], args=node.args[2:], keywords=node.keywords)
                )
            if ast.unparse(node.func) == "TimedContext":
                return self.visit(node.args[0])
            return self.generic_visit(node)

        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call) and ast.unparse(node.value.func) in (
                "events.frame",
                "events.emit",
            ):
                return None
            if (
                isinstance(node.value, ast.Call)
                and ast.unparse(node.value.func) == "events.call"
                and node.value.args[0].value == "CAPSULE_PERSIST"
            ):
                return None
            return self.generic_visit(node)

    assert ast.dump(Reverse().visit(tree), include_attributes=False) == ast.dump(
        ast.parse(original), include_attributes=False
    )


def test_native_call_executes_once_and_failure_event_survives(tmp_path):
    events = Events(tmp_path / "events.jsonl", "test")
    calls = []

    def step():
        calls.append(True)
        raise ValueError("controlled")

    with pytest.raises(ValueError):
        events.call("APP_STEP", step)
    rows = [json.loads(x) for x in events.path.read_text().splitlines()]
    assert calls == [True]
    assert [x["event"] for x in rows] == ["APP_STEP_BEGIN", "APP_STEP_ERROR"]
    assert rows[-1]["interval_end_ns"] >= rows[-1]["interval_start_ns"]


def test_shutdown_nonreturn_retains_close_entry(tmp_path):
    events = Events(tmp_path / "events.jsonl", "test")

    class SDK:
        def __enter__(self):
            return self

        def __exit__(self, *values):
            raise SystemExit(0)

    with pytest.raises(SystemExit), TimedContext(SDK(), events):
        events.emit("CAPSULE_ALREADY_PERSISTED")
    names = [json.loads(x)["event"] for x in events.path.read_text().splitlines()]
    assert names == [
        "SDK_ENTER_BEGIN",
        "SDK_ENTER_END",
        "CAPSULE_ALREADY_PERSISTED",
        "SDK_CLOSE_BEGIN",
        "SDK_CLOSE_ERROR",
    ]
    assert "SDK_CLOSE_END" not in names


def test_append_order_and_clock_anchors(tmp_path):
    events = Events(tmp_path / "events.jsonl", "test")
    events.frame("technical", 0)
    events.call("FRAME_READ", lambda: 5)
    rows = [json.loads(x) for x in events.path.read_text().splitlines()]
    assert [x["sequence"] for x in rows] == list(range(3))
    assert all(x["clock_id"] == "test" and x["wall_ns"] > 0 for x in rows)
    assert all(b["monotonic_ns"] >= a["monotonic_ns"] for a, b in pairwise(rows))
    assert all(x["route"] == "technical" and x["tick"] == 0 for x in rows)


def test_source_drift_rejected():
    original = (Path(__file__).parents[1] / "scripts/prospective_capture_v1.py").read_text()
    with pytest.raises(ValueError, match="boundary"):
        timing_capture(original.replace("sim.step()", "sim.other_step()"))


def test_launcher_is_known_only_and_never_admits_dataset():
    source = (Path(__file__).parents[1] / "scripts/run_prospective_timing_v1.py").read_text()
    assert "specification([0, 1])" in source
    assert "seal" not in source and "admission.json" not in source
    assert "process_cap_s=120" in source and "start + 115" in source
    assert "wait_child(child, record, start, events)" in source


@pytest.mark.parametrize("failed_event", ["LAUNCH_RETURN", "POLL_RETURN", "SIGKILL_REQUEST"])
def test_parent_logging_failure_cannot_orphan_child(tmp_path, monkeypatch, failed_event):
    import time

    import prospective_timing_contracts_v1 as contracts

    killed = []

    class Child:
        pid = 123
        returncode = None

        def __init__(self):
            self.waits = []

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            self.waits.append(timeout)
            if not killed:
                import subprocess

                raise subprocess.TimeoutExpired("fake", timeout)
            self.returncode = -9
            return -9

    class BrokenEvents:
        def emit(self, name, **fields):
            if name == failed_event:
                raise OSError("controlled logging failure")

    monkeypatch.setattr(contracts.os, "killpg", lambda pid, sig: killed.append(pid))
    child = Child()
    record = dict(status="STARTED", timeout=False, child_reaped=False)
    with pytest.raises(OSError):
        contracts.wait_child(child, record, time.monotonic(), BrokenEvents())
    assert killed == [123] and child.waits[-1] == 5
    assert record["child_reaped"] is True and record["child_exit_code"] == -9
    assert record["status"] == "FAIL"
