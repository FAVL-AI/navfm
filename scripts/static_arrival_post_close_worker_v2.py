"""Signal-free startup-and-close worker for the reduced exit observation."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from navfm.isaac.app import IsaacApp, SimConfig  # noqa: E402

OUTPUT = Path(os.environ["NAVFM_POST_CLOSE_DIAGNOSTIC_OUT"]).resolve()
EVENTS = OUTPUT / "lifecycle_events.jsonl"


def _append(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _event(name: str, **fields: Any) -> None:
    _append(
        EVENTS,
        {
            "event": name,
            "clock": "time.monotonic_ns",
            "monotonic_ns": time.monotonic_ns(),
            **fields,
        },
    )


def _atomic_report(value: dict[str, Any]) -> None:
    target = OUTPUT / "worker_final_report.json"
    temporary = OUTPUT / (target.name + ".pending")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    _event("worker_final_report_written")


def main() -> int:
    parent_nonce = os.environ.get("NAVFM_POST_CLOSE_PARENT_NONCE")
    child_nonce = os.environ.get("NAVFM_POST_CLOSE_CHILD_NONCE")
    if not parent_nonce or parent_nonce != child_nonce:
        raise RuntimeError("bootstrap nonce mismatch")
    if Path.cwd().resolve() != ROOT or os.environ.get("OMNICLIENT_HUB_MODE") != "disabled":
        raise RuntimeError("bound child environment mismatch")

    _event("bootstrap_handoff_completed_at_worker_entry")
    _event("simulation_app_constructor_enter")
    app = IsaacApp(SimConfig(headless=True), fast_shutdown=False)
    _event("simulation_app_constructor_return")
    _event("simulation_app_start_enter")
    app.start()
    _event("simulation_app_start_return")

    _event("simulation_app_close_enter")
    app.close()
    _event("simulation_app_close_return")

    _event("worker_final_report_write_enter")
    _atomic_report(
        {
            "schema": "static_arrival_post_close_signal_free_v2_worker_report",
            "status": "STARTUP_AND_CLOSE_RETURNED",
            "scene_constructed": False,
            "camera_constructed": False,
            "frames_captured": 0,
            "fast_shutdown": False,
            "sdk_cleanup_completion": "NOT_INDEPENDENTLY_OBSERVED",
        }
    )
    return 0


if __name__ == "__main__":
    _event("worker_main_enter")
    result = main()
    _event("worker_main_returned", return_code=result)
    sys.exit(result)
