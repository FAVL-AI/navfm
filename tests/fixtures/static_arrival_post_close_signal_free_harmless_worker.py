"""Harmless worker fixture for passive exit-observation tests."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

output = Path(os.environ["NAVFM_POST_CLOSE_DIAGNOSTIC_OUT"])
events = output / "lifecycle_events.jsonl"


def event(name: str) -> None:
    with events.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                {"event": name, "clock": "time.monotonic_ns", "monotonic_ns": time.monotonic_ns()}
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())


event("bootstrap_handoff_completed_at_worker_entry")
event("simulation_app_start_enter")
event("simulation_app_start_return")
event("simulation_app_close_enter")
event("simulation_app_close_return")
event("worker_final_report_write_enter")
(output / "worker_final_report.json").write_text('{"status":"fixture_final_marker"}\n')
event("worker_final_report_written")
event("worker_main_returned")

mode = sys.argv[1] if len(sys.argv) > 1 else "exit_after_marker"
if mode == "exit_after_marker":
    time.sleep(0.3)
elif mode == "hang_after_marker":
    time.sleep(20)
elif mode == "abnormal_after_marker":
    raise SystemExit(9)
else:
    raise ValueError("unknown fixture mode")
