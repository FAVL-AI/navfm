"""One-shot supervisor and freeze contract for post-close exit diagnosis."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKER_PYTHON = Path(
    "/home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python"
)
SIMAPP_SOURCE = Path(
    "/home/favl/miniforge3/envs/isaac/lib/python3.11/site-packages/"
    "isaacsim/exts/isaacsim.simulation_app/isaacsim/simulation_app/simulation_app.py"
)
THREADING_SOURCE = Path("/home/favl/miniforge3/envs/isaac/lib/python3.11/threading.py")
SOURCE_PATHS = (
    "scripts/static_arrival_post_close_diagnostic_v1.py",
    "scripts/static_arrival_post_close_bootstrap_v1.py",
    "scripts/static_arrival_post_close_worker_v1.py",
    "src/navfm/isaac/app.py",
)
REGISTRY_NAME = "post-close-diagnostic-v1.reserved.json"
CHILD_DEADLINE_SECONDS = 60.0
REAP_RESERVE_SECONDS = 10.0
TRACE_INTERVAL_SECONDS = 10.0


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def build_config(root: Path = ROOT) -> dict[str, Any]:
    return {
        "schema": "static_arrival_post_close_diagnostic_v1",
        "purpose": "startup_and_close_process_exit_diagnosis_only",
        "runtime": {
            "python": str(WORKER_PYTHON),
            "python_sha256": _sha(WORKER_PYTHON),
            "python_version": "3.11.15",
            "threading_source": str(THREADING_SOURCE),
            "threading_source_sha256": _sha(THREADING_SOURCE),
            "isaacsim_version": "5.1.0.0",
            "simulation_app_source": str(SIMAPP_SOURCE),
            "simulation_app_source_sha256": _sha(SIMAPP_SOURCE),
            "fast_shutdown": False,
            "child_working_directory": str(root.resolve()),
            "child_hub_mode": "disabled",
        },
        "source_bindings": [{"path": name, "sha256": _sha(root / name)} for name in SOURCE_PATHS],
        "observation": {
            "construct_scene": False,
            "construct_camera": False,
            "capture_frames": False,
            "worker_deadline_seconds": CHILD_DEADLINE_SECONDS,
            "termination_reap_reserve_seconds": REAP_RESERVE_SECONDS,
            "trace_signal": "SIGUSR1",
            "trace_interval_seconds": TRACE_INTERVAL_SECONDS,
            "maximum_parent_trace_requests": 6,
            "stack_frames_per_thread": 32,
            "maximum_threads_per_snapshot": 128,
            "thread_local_values": False,
            "environment_dump": False,
            "dataset_admission": False,
        },
        "evidence": {
            "root": "/home/favl/navfm-runtime-evidence/static-arrival-post-close-diagnostic-v1",
            "attempt": "attempt-01",
            "registry": "/home/favl/navfm-runtime-evidence/static-arrival-post-close-diagnostic-v1/registry",
        },
    }


def verify_config(config: dict[str, Any], root: Path = ROOT) -> None:
    expected = build_config(root)
    if config != expected:
        raise ValueError("post-close diagnostic freeze/config/source binding mismatch")


def runtime_preflight(config: dict[str, Any]) -> None:
    import sys
    import threading

    if Path(sys.executable).resolve() != WORKER_PYTHON.resolve():
        raise RuntimeError("diagnostic configuration must use the bound worker interpreter")
    if Path(threading.__file__).resolve() != THREADING_SOURCE.resolve():
        raise RuntimeError("bound CPython threading source path mismatch")
    if sys.version.split()[0] != config["runtime"]["python_version"]:
        raise RuntimeError("bound CPython version mismatch")


def _event(output: Path, name: str, **fields: Any) -> None:
    _append_event(
        output / "supervisor_events.jsonl",
        {
            "event": name,
            "clock": "time.monotonic_ns",
            "monotonic_ns": time.monotonic_ns(),
            **fields,
        },
    )


def run_once(
    *,
    config: dict[str, Any],
    freeze: str,
    output: Path,
    registry: Path,
    command: list[str],
    root: Path = ROOT,
    child_deadline_seconds: float = CHILD_DEADLINE_SECONDS,
    reap_reserve_seconds: float = REAP_RESERVE_SECONDS,
    trace_interval_seconds: float = TRACE_INTERVAL_SECONDS,
) -> dict[str, Any]:
    verify_config(config, root)
    output = output.expanduser().resolve()
    registry = registry.expanduser().resolve()
    allowed_root = Path(config["evidence"]["root"]).resolve()
    allowed_registry = Path(config["evidence"]["registry"]).resolve()
    if (
        output.exists()
        or not output.is_relative_to(allowed_root)
        or not registry.is_relative_to(allowed_registry)
        or child_deadline_seconds <= 0
        or reap_reserve_seconds <= 0
        or trace_interval_seconds <= 0
    ):
        raise ValueError("diagnostic requires a fresh external attempt and positive bounds")
    registry.mkdir(parents=True, exist_ok=True, mode=0o700)
    reservation = registry / REGISTRY_NAME
    with (registry / "lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fd = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError("post-close diagnostic attempt already consumed") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"status": "CONSUMED", "freeze": freeze}, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    output.mkdir(parents=True, mode=0o700)
    started = time.monotonic()
    child: subprocess.Popen | None = None
    record: dict[str, Any] = {
        "schema": "static_arrival_post_close_diagnostic_result_v1",
        "freeze": freeze,
        "status": "STARTED",
        "worker_deadline_seconds": child_deadline_seconds,
        "reap_reserve_seconds": reap_reserve_seconds,
        "child_exit_code": None,
        "child_reaped": False,
        "timed_out": False,
        "dataset_admission": False,
    }
    _atomic_json(
        output / "attempt_start.json",
        {"schema": "static_arrival_post_close_attempt_v1", "freeze": freeze, "status": "STARTED"},
    )
    try:
        env = dict(os.environ)
        env["NAVFM_POST_CLOSE_PARENT_NONCE"] = hashlib.sha256(os.urandom(32)).hexdigest()
        env["NAVFM_POST_CLOSE_DIAGNOSTIC_OUT"] = str(output)
        with (output / "worker.stdout").open("wb") as stdout:
            child = subprocess.Popen(
                command,
                cwd=root,
                env=env,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        record["child_pid"] = child.pid
        _event(output, "child_started", pid=child.pid)
        deadline = started + child_deadline_seconds
        next_trace = time.monotonic() + trace_interval_seconds
        trace_requests = 0
        while True:
            now = time.monotonic()
            return_code = child.poll()
            if return_code is not None:
                record["child_exit_observed_monotonic_ns"] = time.monotonic_ns()
                if now >= deadline:
                    record["timed_out"] = True
                    record["status"] = "PROCESS_EXITED_AFTER_CHILD_DEADLINE"
                else:
                    record["status"] = (
                        "PROCESS_EXITED_ZERO_BEFORE_DEADLINE"
                        if return_code == 0
                        else "PROCESS_EXITED_NONZERO_BEFORE_DEADLINE"
                    )
                break
            if now >= deadline:
                record["timed_out"] = True
                record["status"] = "PROCESS_ALIVE_AT_CHILD_DEADLINE"
                _event(output, "child_deadline_reached", deadline_seconds=child_deadline_seconds)
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                    _event(output, "termination_requested", signal="SIGTERM")
                except ProcessLookupError:
                    _event(output, "termination_target_gone", signal="SIGTERM")
                reap_deadline = time.monotonic() + reap_reserve_seconds
                term_deadline = min(
                    reap_deadline, time.monotonic() + min(5.0, reap_reserve_seconds / 2)
                )
                try:
                    child.wait(timeout=max(0.0, term_deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    if child.poll() is None:
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                            _event(output, "termination_requested", signal="SIGKILL")
                        except ProcessLookupError:
                            _event(output, "termination_target_gone", signal="SIGKILL")
                    try:
                        child.wait(timeout=max(0.0, reap_deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        record["reap_deadline_exceeded"] = True
                break
            if (
                now >= next_trace
                and trace_requests < config["observation"]["maximum_parent_trace_requests"]
            ):
                try:
                    os.kill(child.pid, signal.SIGUSR1)
                    _event(output, "bounded_thread_trace_requested", signal="SIGUSR1")
                    trace_requests += 1
                except ProcessLookupError:
                    _event(output, "trace_signal_target_gone")
                next_trace += trace_interval_seconds
            time.sleep(min(0.1, max(0.0, deadline - now)))
        if child.returncode is None:
            child.poll()
        record["child_exit_code"] = child.poll()
        record["child_reaped"] = child.returncode is not None
        _event(
            output,
            "child_reaped" if record["child_reaped"] else "child_not_reaped",
            exit_code=record["child_exit_code"],
            reaped=record["child_reaped"],
        )
    except BaseException as exc:
        record.update(status="SUPERVISOR_FAILURE", supervisor_error_type=type(exc).__name__)
        if child is not None and child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
                _event(output, "supervisor_failure_termination_requested", signal="SIGTERM")
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=reap_reserve_seconds)
            except subprocess.TimeoutExpired:
                record["reap_deadline_exceeded"] = True
        if child is not None:
            record["child_exit_code"] = child.poll()
            record["child_reaped"] = child.returncode is not None
        raise
    finally:
        record["occupied_wall_seconds"] = time.monotonic() - started
        record["dataset_admission"] = False
        record["finalization_complete"] = True
        _atomic_json(output / "terminal_record.json", record)
        _atomic_json(reservation.with_suffix(".terminal.json"), record)
    return record


def main() -> None:
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--execute-approved", action="store_true")
    args = parser.parse_args()
    if not args.execute_approved:
        parser.error("PREPARATION ONLY: --execute-approved requires explicit approval")
    config_path = ROOT / "configs/eval/static_arrival_post_close_diagnostic_v1.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        verify_config(config, ROOT)
        runtime_preflight(config)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    except (OSError, subprocess.CalledProcessError, ValueError, RuntimeError) as exc:
        parser.error(f"cannot verify diagnostic freeze: {type(exc).__name__}")
    if args.freeze != head or dirty:
        parser.error("exact clean approved commit required")
    command = [
        str(WORKER_PYTHON),
        str(ROOT / "scripts/static_arrival_post_close_bootstrap_v1.py"),
    ]
    try:
        record = run_once(
            config=config,
            freeze=args.freeze,
            output=args.out,
            registry=Path(config["evidence"]["registry"]),
            command=command,
        )
    except BaseException as exc:
        print(f"POST_CLOSE_DIAGNOSTIC_FAILURE: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(record, sort_keys=True))


if __name__ == "__main__":
    main()
