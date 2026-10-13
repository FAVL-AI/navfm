"""Startup-and-close-only Isaac worker for the post-close exit diagnostic."""

from __future__ import annotations

import atexit
import json
import os
import signal
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from navfm.isaac.app import IsaacApp, SimConfig  # noqa: E402

OUTPUT = Path(os.environ["NAVFM_POST_CLOSE_DIAGNOSTIC_OUT"]).resolve()
EVENTS = OUTPUT / "lifecycle_events.jsonl"
STACKS = OUTPUT / "thread_snapshots.jsonl"
MAX_THREADS = 128
MAX_STACK_FRAMES = 32
SNAPSHOT_LOCK = threading.Lock()


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


def _thread_snapshot(label: str) -> None:
    if not SNAPSHOT_LOCK.acquire(blocking=False):
        _event("thread_snapshot_skipped", reason="snapshot_already_running", label=label)
        return
    try:
        frames = sys._current_frames()
        threads = threading.enumerate()[:MAX_THREADS]
        rows = []
        for thread in threads:
            frame = frames.get(thread.ident) if thread.ident is not None else None
            stack = (
                traceback.format_list(traceback.extract_stack(frame, limit=MAX_STACK_FRAMES))
                if frame
                else []
            )
            rows.append(
                {
                    "ident": thread.ident,
                    "native_id": getattr(thread, "native_id", None),
                    "name": thread.name[:160],
                    "daemon": thread.daemon,
                    "alive": thread.is_alive(),
                    "stack": stack,
                }
            )
        _append(
            STACKS,
            {
                "label": label,
                "clock": "time.monotonic_ns",
                "monotonic_ns": time.monotonic_ns(),
                "thread_count": len(threads),
                "truncated": len(threading.enumerate()) > MAX_THREADS,
                "threads": rows,
            },
        )
    finally:
        SNAPSHOT_LOCK.release()


def _signal_snapshot(_signum: int, _frame: Any) -> None:
    _thread_snapshot("parent_requested_snapshot")


def _threading_shutdown_marker() -> None:
    # CPython invokes this before joining non-daemon Python threads.
    _event("python_threading_shutdown_hook_enter")
    _thread_snapshot("python_threading_shutdown_hook")


def _atexit_marker() -> None:
    _event("python_atexit_enter_after_threading_shutdown")
    _thread_snapshot("python_atexit")


def _atomic_report(value: dict[str, Any]) -> None:
    temporary = OUTPUT / "worker_final_report.json.pending"
    target = OUTPUT / "worker_final_report.json"
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

    # Kept registered through interpreter shutdown; it creates no helper thread.
    signal.signal(signal.SIGUSR1, _signal_snapshot)
    threading._register_atexit(_threading_shutdown_marker)
    atexit.register(_atexit_marker)
    _event("bootstrap_handoff_completed_at_worker_entry")
    _thread_snapshot("worker_entry")

    app = IsaacApp(SimConfig(headless=True), fast_shutdown=False)
    _event("simulation_app_start_enter")
    app.start()
    _event("simulation_app_start_return")
    _thread_snapshot("after_application_start")

    _event("simulation_app_close_enter")
    app.close()
    _event("simulation_app_close_return")
    _thread_snapshot("after_application_close")

    report = {
        "schema": "static_arrival_post_close_worker_report_v1",
        "status": "STARTUP_AND_CLOSE_RETURNED",
        "scene_constructed": False,
        "camera_constructed": False,
        "frames_captured": 0,
        "fast_shutdown": False,
        "sdk_cleanup_completion": "NOT_INDEPENDENTLY_OBSERVED",
    }
    _event("worker_final_report_write_enter")
    _atomic_report(report)
    _thread_snapshot("before_worker_main_return")
    return 0


if __name__ == "__main__":
    _event("worker_main_enter")
    result = main()
    _event("worker_main_returned", return_code=result)
    sys.exit(result)
