"""One-shot supervisor for the static-arrival startup-only diagnostic."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/eval/static_arrival_startup_diagnostic_v1.json"
WORKER_PATH = ROOT / "scripts/static_arrival_startup_worker_v1.py"
EXECUTION_LIMIT_S = 30.0
CLEANUP_RESERVE_S = 10.0


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".pending")
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _append_event(path: Path, event: str, **fields: Any) -> None:
    row = {
        "event": event,
        "utc": datetime.now(timezone.utc).isoformat(),
        "monotonic_ns": time.monotonic_ns(),
        **fields,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read_events(path: Path) -> tuple[list[dict[str, Any]], bool]:
    if not path.is_file():
        return [], False
    rows: list[dict[str, Any]] = []
    valid = True
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            valid = False
            continue
        if isinstance(row, dict) and isinstance(row.get("event"), str):
            rows.append(row)
        else:
            valid = False
    return rows, valid


def _signal_group(
    child: subprocess.Popen, sig: signal.Signals, journal: Path, attempts: list
) -> None:
    entry: dict[str, Any] = {
        "signal": sig.name,
        "utc": datetime.now(timezone.utc).isoformat(),
        "monotonic_ns": time.monotonic_ns(),
    }
    try:
        os.killpg(child.pid, sig)
        entry["request_result"] = "sent"
    except ProcessLookupError:
        entry["request_result"] = "process_group_absent"
    except OSError as exc:
        entry["request_result"] = "error"
        entry["error_type"] = type(exc).__name__
    attempts.append(entry)
    _append_event(journal, "termination_signal_requested", **entry)


def child_environment(parent: dict[str, str]) -> dict[str, str]:
    """Copy the parent environment and pin Hub mode for this child only."""
    child = dict(parent)
    child["OMNICLIENT_HUB_MODE"] = "disabled"
    return child


def supervise(
    command: list[str],
    output: Path,
    *,
    env: dict[str, str],
    cwd: Path,
    execution_limit_s: float = EXECUTION_LIMIT_S,
    cleanup_reserve_s: float = CLEANUP_RESERVE_S,
    record_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one child with a hard execution deadline and bounded cleanup wait."""
    if execution_limit_s <= 0 or cleanup_reserve_s < 0 or cleanup_reserve_s > CLEANUP_RESERVE_S:
        raise ValueError("invalid diagnostic deadline")
    if output.exists():
        raise FileExistsError("diagnostic output already exists")
    output.mkdir(parents=True, mode=0o700)
    parent_events = output / "parent_events.jsonl"
    child_events = output / "child_events.jsonl"
    stdout_path = output / "worker.stdout"
    started = time.monotonic()
    execution_deadline = started + execution_limit_s
    cleanup_deadline = execution_deadline + cleanup_reserve_s
    record: dict[str, Any] = {
        "schema": "static_arrival_startup_diagnostic_terminal_v1",
        "status": "STARTED",
        "execution_limit_seconds": execution_limit_s,
        "cleanup_reserve_seconds": cleanup_reserve_s,
        "child_exit_code": None,
        "timeout": False,
        "child_reaped": False,
        "termination_requests": [],
        "startup_completed": False,
        "close_returned": False,
    }
    if record_context:
        record.update(record_context)
    child = None
    execution_ended = started
    try:
        _append_event(parent_events, "before_spawn", cwd=str(cwd), command=command)
        with stdout_path.open("xb") as log:
            child = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            record["child_pid"] = child.pid
            record["child_started_monotonic_ns"] = time.monotonic_ns()
            _append_event(parent_events, "child_spawned", pid=child.pid)
            try:
                child.wait(timeout=max(0.0, execution_deadline - time.monotonic()))
                execution_ended = time.monotonic()
            except subprocess.TimeoutExpired:
                record["timeout"] = True
                execution_ended = execution_deadline
            cleanup_deadline = min(
                started + execution_limit_s + cleanup_reserve_s,
                execution_ended + cleanup_reserve_s,
            )
            if child.poll() is None:
                _signal_group(child, signal.SIGTERM, parent_events, record["termination_requests"])
                try:
                    child.wait(timeout=min(5.0, max(0.0, cleanup_deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    _signal_group(
                        child, signal.SIGKILL, parent_events, record["termination_requests"]
                    )
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        child.wait(timeout=max(0.0, cleanup_deadline - time.monotonic()))
            record["child_exit_code"] = child.poll()
            record["child_reaped"] = child.returncode is not None
            _append_event(
                parent_events,
                "child_wait_complete",
                child_exit_code=record["child_exit_code"],
                child_reaped=record["child_reaped"],
                timeout=record["timeout"],
            )
    except BaseException as exc:
        record["supervisor_error_type"] = type(exc).__name__
        execution_ended = min(time.monotonic(), execution_deadline)
        if child is not None and child.poll() is None and time.monotonic() < cleanup_deadline:
            _signal_group(child, signal.SIGTERM, parent_events, record["termination_requests"])
            try:
                child.wait(timeout=max(0.0, cleanup_deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                _signal_group(child, signal.SIGKILL, parent_events, record["termination_requests"])
        if child is not None:
            record["child_exit_code"] = child.poll()
            record["child_reaped"] = child.returncode is not None
    finally:
        if execution_ended > execution_deadline:
            record["timeout"] = True
        record["execution_elapsed_seconds"] = max(0.0, execution_ended - started)
        record["cleanup_deadline_monotonic_ns"] = int(cleanup_deadline * 1_000_000_000)
        rows, journal_valid = _read_events(child_events)
        names = [row["event"] for row in rows]
        record["child_events_valid_jsonl"] = journal_valid
        record["observed_child_events"] = names
        record["startup_completed"] = (
            "after_simulation_app_constructor" in names and "application_start_returned" in names
        )
        record["close_returned"] = "close_returned" in names
        record["child_event_sha256"] = _sha(child_events) if child_events.is_file() else None
        record["stdout_sha256"] = _sha(stdout_path) if stdout_path.is_file() else None
        record["occupied_wall_seconds"] = time.monotonic() - started
        record["cleanup_elapsed_seconds"] = max(
            0.0, record["occupied_wall_seconds"] - record["execution_elapsed_seconds"]
        )
        record["cleanup_within_reserve"] = record["cleanup_elapsed_seconds"] <= cleanup_reserve_s
        if record["timeout"]:
            record["status"] = "FAIL_EXECUTION_TIMEOUT"
        elif record.get("supervisor_error_type"):
            record["status"] = "FAIL_SUPERVISOR"
        elif record["child_exit_code"] != 0 or not record["child_reaped"]:
            record["status"] = "FAIL_CHILD_EXIT_OR_REAP"
        elif not journal_valid or not record["startup_completed"]:
            record["status"] = "FAIL_STARTUP_INCOMPLETE"
        elif not record["close_returned"]:
            record["status"] = "STARTUP_PASSED_CLOSE_RETURN_UNOBSERVED"
        else:
            record["status"] = "PASS_STARTUP_AND_CLOSE_RETURNED"
        record["within_budget"] = (
            record["execution_elapsed_seconds"] <= execution_limit_s
            and record["cleanup_within_reserve"]
            and record["occupied_wall_seconds"] <= execution_limit_s + cleanup_reserve_s
        )
        if not record["within_budget"] and not record["timeout"]:
            record["status"] = "FAIL_CLEANUP_RESERVE_EXCEEDED"
        record["terminal_written_monotonic_ns"] = time.monotonic_ns()
        _atomic_json(output / "terminal.json", record)
    return record


def _verify_freeze(freeze: str, root: Path, cfg: dict[str, Any]) -> None:
    if (
        cfg["runtime"]["hub_mode"] != "disabled"
        or cfg["runtime"]["cwd"] != str(root)
        or cfg["budget"]
        != {
            "child_execution_seconds": 30.0,
            "cleanup_reserve_seconds": 10.0,
            "total_seconds": 40.0,
            "deadline_includes": "spawn through normal close and child exit",
            "cleanup_includes": "termination requests, child reap, evidence verification and terminal record",
        }
    ):
        raise ValueError("startup diagnostic contract mismatch")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
    if head != freeze or dirty:
        raise ValueError("exact clean diagnostic freeze required")
    for binding in cfg["source_bindings"]:
        if _sha(root / binding["path"]) != binding["sha256"]:
            raise ValueError(f"diagnostic source binding mismatch: {binding['path']}")
    python_path = Path(cfg["runtime"]["python"])
    if not python_path.is_file() or _sha(python_path) != cfg["runtime"]["python_sha256"]:
        raise ValueError("bound worker interpreter identity mismatch")
    check = subprocess.run(
        [
            str(python_path),
            "-c",
            "from importlib.metadata import version; print(version('isaacsim'))",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=root,
        timeout=10,
    )
    if check.stdout.strip() != cfg["runtime"]["isaacsim_distribution_version"]:
        raise ValueError("bound Isaac Sim distribution version mismatch")


def run_one(freeze: str, *, execute_approved: bool) -> dict[str, Any]:
    if not execute_approved:
        raise ValueError("--execute-approved is required")
    raw = CONFIG_PATH.read_bytes()
    expected_config_sha = "20da7f7dcadd17f30eeb7ab21742f947c1b584c56fe79e7b1ae1fdfb303dd8da"
    if hashlib.sha256(raw).hexdigest() != expected_config_sha:
        raise ValueError("startup diagnostic config hash mismatch")
    cfg = json.loads(raw)
    _verify_freeze(freeze, ROOT, cfg)
    root = Path(cfg["evidence"]["root"])
    output = root / cfg["evidence"]["attempt"]
    registry = Path(cfg["evidence"]["registry"])
    if output.exists():
        raise FileExistsError("fresh external evidence directory required")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    registry.mkdir(parents=True, exist_ok=True, mode=0o700)
    reservation = registry / "startup-diagnostic-attempt-01.reserved.json"
    with (registry / "lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        descriptor = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"status": "CONSUMED", "freeze": freeze}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        output.mkdir(mode=0o700)
        launch_cfg = {
            "schema": cfg["schema"],
            "freeze": freeze,
            "worker_python": cfg["runtime"]["python"],
            "worker_python_sha256": cfg["runtime"]["python_sha256"],
            "isaacsim_distribution_version": cfg["runtime"]["isaacsim_distribution_version"],
            "hub_mode": cfg["runtime"]["hub_mode"],
            "cwd": str(ROOT),
            "launch_arguments": {
                "headless": cfg["application"]["headless"],
                "renderer": cfg["application"]["renderer"],
                "width": cfg["application"]["resolution"][0],
                "height": cfg["application"]["resolution"][1],
            },
            "application_settings": cfg["application"],
            "budget": cfg["budget"],
            "source_bindings": cfg["source_bindings"],
            "config_sha256": expected_config_sha,
        }
        _atomic_json(output / "attempt.json", launch_cfg)
        env = child_environment(dict(os.environ))
        command = [
            cfg["runtime"]["python"],
            str(WORKER_PATH),
            "--out",
            str(output / "supervised"),
            "--config",
            str(CONFIG_PATH),
        ]
        record = supervise(
            command,
            output / "supervised",
            env=env,
            cwd=ROOT,
            execution_limit_s=cfg["budget"]["child_execution_seconds"],
            cleanup_reserve_s=cfg["budget"]["cleanup_reserve_seconds"],
            record_context={
                "freeze": freeze,
                "attempt_directory": str(output),
                "registry_reservation": str(reservation),
                "source_bindings": cfg["source_bindings"],
                "config_sha256": expected_config_sha,
            },
        )
        return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--execute-approved", action="store_true")
    args = parser.parse_args()
    try:
        record = run_one(args.freeze, execute_approved=args.execute_approved)
    except BaseException as exc:
        print(f"STARTUP_DIAGNOSTIC_NOT_ADMITTED: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(
        json.dumps(
            {
                "status": record["status"],
                "startup_completed": record["startup_completed"],
                "close_returned": record["close_returned"],
                "timeout": record["timeout"],
                "child_exit_code": record["child_exit_code"],
                "child_reaped": record["child_reaped"],
                "within_budget": record["within_budget"],
                "attempt_directory": record["attempt_directory"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
