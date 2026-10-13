"""Harmless child used to exercise the diagnostic bootstrap/supervisor."""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from pathlib import Path


def event(name: str) -> None:
    output = Path(os.environ["NAVFM_POST_CLOSE_DIAGNOSTIC_OUT"])
    with (output / "lifecycle_events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {"event": name, "clock": "time.monotonic_ns", "monotonic_ns": time.monotonic_ns()}
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())


def snapshot(_signum: int, _frame: object) -> None:
    output = Path(os.environ["NAVFM_POST_CLOSE_DIAGNOSTIC_OUT"])
    rows = [
        {"ident": t.ident, "name": t.name, "daemon": t.daemon, "alive": t.is_alive()}
        for t in threading.enumerate()
    ]
    with (output / "thread_snapshots.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"threads": rows}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


signal.signal(signal.SIGUSR1, snapshot)
event("bootstrap_handoff_completed_at_harmless_worker")
event("simulation_app_start_enter")
event("simulation_app_start_return")
event("simulation_app_close_enter")
event("simulation_app_close_return")
event("worker_final_report_write_enter")
event("worker_final_report_written")
event("worker_main_returned")

mode = sys.argv[1] if len(sys.argv) > 1 else "success"
if mode == "failure":
    raise SystemExit(7)
if mode == "hang":
    while True:
        time.sleep(0.1)
