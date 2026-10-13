"""Prospective v2 lifecycle contract for static camera qualification."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any

from navfm.collection.static_arrival_camera_qualification import (
    CAP_SECONDS,
    _atomic_json,
    _sha,
    build_qualification,
    build_worker_input,
    run_supervised_worker,
    verify_capture,
    verify_source_bindings,
)
from navfm.collection.static_arrival_capture import canonical_sha256

SIMAPP_SOURCE = Path(
    "/home/favl/miniforge3/envs/isaac/lib/python3.11/site-packages/"
    "isaacsim/exts/isaacsim.simulation_app/isaacsim/simulation_app/simulation_app.py"
)
CONTINUATION_SOURCES = (
    "scripts/static_arrival_camera_qualification_v2.py",
    "scripts/static_arrival_camera_child_bootstrap_v2.py",
    "scripts/static_arrival_camera_qualification_worker_v2.py",
    "scripts/static_arrival_camera_qualification_continuation_v2.py",
)
TERMINAL_NAME = "technical-scene0-v2.reserved.json"


def _elapsed_seconds(started: float) -> float:
    return time.monotonic() - started


def build_config(root: Path) -> dict[str, Any]:
    config = build_qualification(root)
    config["schema"] = "static_arrival_camera_qualification_v2"
    config["amendment_status"] = "REVIEW_REQUIRED_NOT_EXECUTED"
    config["shutdown_contract"] = {
        "isaacsim_distribution_version": "5.1.0.0",
        "child_cwd": str(root.resolve()),
        "child_hub_mode": "disabled",
        "simulation_app_source": str(SIMAPP_SOURCE),
        "simulation_app_source_sha256": _sha(SIMAPP_SOURCE),
        "fast_shutdown": False,
        "close_return_required": True,
        "sdk_cleanup_claim": "NOT_INDEPENDENTLY_OBSERVED",
        "measurement_capsule_required": True,
        "measurement_capsule_schema": "static_arrival_camera_measurement_capsule_v2",
    }
    config["continuation_source_bindings"] = [
        {"path": path, "sha256": _sha(root / path)} for path in CONTINUATION_SOURCES
    ]
    config["evidence"]["root"] = "~/navfm-runtime-evidence/static-arrival-camera-qualification-v2"
    config["evidence"]["registry"] = (
        "~/navfm-runtime-evidence/static-arrival-camera-qualification-v2/registry"
    )
    config["evidence"]["attempt"] = "attempt-01"
    config["evidence"]["one_attempt_only"] = True
    return config


def verify_config(config: dict[str, Any], root: Path) -> None:
    expected = build_config(root)
    if config != expected:
        raise ValueError("camera continuation v2 freeze/config/source mismatch")
    verify_source_bindings(build_qualification(root), root)
    rows = config.get("continuation_source_bindings")
    if not isinstance(rows, list) or [row.get("path") for row in rows] != list(
        CONTINUATION_SOURCES
    ):
        raise ValueError("camera continuation source binding set/order mismatch")
    for row in rows:
        if row.get("sha256") != _sha(root / row["path"]):
            raise ValueError(f"camera continuation source hash mismatch: {row['path']}")


def verify_measurement_capsule(output: Path, worker_input: dict[str, Any]) -> dict[str, Any]:
    capsule_path = output / "measurement_complete.json"
    try:
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("pre-shutdown measurement capsule missing/unreadable") from exc
    report = json.loads((output / "capture_report.json").read_text(encoding="utf-8"))
    expected_launch = {
        "child_cwd": worker_input["shutdown_contract"]["child_cwd"],
        "child_hub_mode": "disabled",
        "simulation_app_fast_shutdown": False,
    }
    expected_ids = [frame["image_id"] for frame in worker_input["frames"]]
    rows = capsule.get("frames")
    artifacts = capsule.get("artifacts")
    expected_paths = {
        *{f"capture_metadata/{image_id}.json" for image_id in expected_ids},
        *{f"policy_inputs/images/{image_id}.jpg" for image_id in expected_ids},
    }
    if (
        capsule.get("schema") != "static_arrival_camera_measurement_capsule_v2"
        or capsule.get("measurement_status") != "COMPLETE_BEFORE_SHUTDOWN"
        or capsule.get("schedule_sha256") != worker_input["schedule_sha256"]
        or capsule.get("source_bindings_sha256") != worker_input["source_bindings_sha256"]
        or capsule.get("worker_input_sha256") != canonical_sha256(worker_input)
        or not isinstance(rows, list)
        or [row.get("image_id") for row in rows] != expected_ids
        or any(row.get("status") != "PASS" for row in rows)
        or capsule.get("frames_sha256") != canonical_sha256(rows)
        or rows != report.get("frames")
        or report.get("shutdown_contract") != worker_input["shutdown_contract"]
        or report.get("launch_observation") != expected_launch
        or not isinstance(artifacts, dict)
        or set(artifacts) != expected_paths
    ):
        raise ValueError("pre-shutdown measurement capsule identity/inventory mismatch")
    for relative, expected_hash in artifacts.items():
        path = (output / relative).resolve()
        path.relative_to(output.resolve())
        if not path.is_file() or _sha(path) != expected_hash:
            raise ValueError("pre-shutdown measurement artifact hash mismatch")
    return {
        "measurement_status": capsule["measurement_status"],
        "measurement_capsule_sha256": _sha(capsule_path),
        "measurement_artifacts": artifacts,
    }


def verify_completion(
    output: Path, registry_terminal: Path, freeze: str, worker_input: dict[str, Any]
) -> None:
    marker = json.loads((output / "qualification_complete.json").read_text())
    terminal_path = output / "terminal_record.json"
    terminal = json.loads(terminal_path.read_text())
    registry_record = json.loads(registry_terminal.read_text())
    if (
        marker.get("schema") != "static_arrival_camera_qualification_completion_v2"
        or set(marker)
        != {
            "schema",
            "freeze",
            "terminal_sha256",
            "registry_terminal_sha256",
            "measurement_capsule_sha256",
        }
        or marker.get("freeze") != freeze
        or marker.get("terminal_sha256") != _sha(terminal_path)
        or marker.get("registry_terminal_sha256") != _sha(registry_terminal)
        or marker.get("measurement_capsule_sha256") != _sha(output / "measurement_complete.json")
        or marker.get("measurement_capsule_sha256") != terminal.get("measurement_capsule_sha256")
        or registry_record != terminal
        or terminal.get("status") != "QUALIFICATION_PASS"
        or terminal.get("freeze") != freeze
        or terminal.get("finalization_complete") is not True
        or terminal.get("dataset_admission") is not False
        or terminal.get("timeout") is not False
        or terminal.get("child_exit_code") != 0
        or terminal.get("child_reaped") is not True
        or terminal.get("sdk_cleanup_completion") != "NOT_INDEPENDENTLY_OBSERVED"
    ):
        raise ValueError("camera qualification v2 completion transaction mismatch")
    verify_capture(output, worker_input)
    verify_measurement_capsule(output, worker_input)
    for relative, expected_hash in terminal["capture_artifacts"].items():
        artifact = (output / relative).resolve()
        artifact.relative_to(output.resolve())
        if not artifact.is_file() or _sha(artifact) != expected_hash:
            raise ValueError("camera qualification v2 artifact changed after admission")


def run_once(
    *,
    config: dict[str, Any],
    output: Path,
    registry: Path,
    freeze: str,
    worker_command: list[str],
    root: Path,
    process_started_monotonic: float | None = None,
) -> dict[str, Any]:
    started = process_started_monotonic or time.monotonic()
    verify_config(config, root)
    root = root.resolve()
    output = output.expanduser().resolve()
    registry = registry.expanduser().resolve()
    allowed = Path(config["evidence"]["root"]).expanduser().resolve()
    registry_allowed = Path(config["evidence"]["registry"]).expanduser().resolve()
    if (
        output.exists()
        or not output.is_relative_to(allowed)
        or not registry.is_relative_to(registry_allowed)
    ):
        raise ValueError("camera qualification v2 requires new external output/registry paths")
    registry.mkdir(parents=True, exist_ok=True, mode=0o700)
    reservation = registry / TERMINAL_NAME
    with (registry / "lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            descriptor = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError("camera qualification v2 attempt already consumed") from exc
        with os.fdopen(descriptor, "w") as stream:
            stream.write(json.dumps({"status": "CONSUMED", "freeze": freeze}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            output.mkdir(parents=True, mode=0o700)
            _atomic_json(
                output / "attempt_start.json",
                {
                    "status": "STARTED",
                    "freeze": freeze,
                    "config_sha256": canonical_sha256(config),
                },
            )
            worker_input = build_worker_input(config)
            worker_input["shutdown_contract"] = config["shutdown_contract"]
            result = run_supervised_worker(
                command=worker_command,
                output=output,
                worker_input=worker_input,
                cap_seconds=CAP_SECONDS,
                freeze=freeze,
                process_started_monotonic=started,
            )
            result.update(verify_measurement_capsule(output, worker_input))
            result["occupied_wall_seconds"] = _elapsed_seconds(started)
            result["whole_process_deadline_exceeded"] = False
            if _elapsed_seconds(started) > CAP_SECONDS:
                raise TimeoutError("camera qualification v2 whole-process budget exceeded")
            result["sdk_cleanup_completion"] = "NOT_INDEPENDENTLY_OBSERVED"
            result["finalization_complete"] = True
            _atomic_json(output / "terminal_record.json", result)
            registry_terminal = reservation.with_suffix(".terminal.json")
            _atomic_json(registry_terminal, result)
            marker = {
                "schema": "static_arrival_camera_qualification_completion_v2",
                "freeze": freeze,
                "terminal_sha256": _sha(output / "terminal_record.json"),
                "registry_terminal_sha256": _sha(registry_terminal),
                "measurement_capsule_sha256": _sha(output / "measurement_complete.json"),
            }
            _atomic_json(output / "qualification_complete.json", marker)
            if _elapsed_seconds(started) > CAP_SECONDS:
                raise TimeoutError("camera qualification v2 finalization exceeded budget")
            verify_completion(output, registry_terminal, freeze, worker_input)
            result["occupied_wall_seconds"] = _elapsed_seconds(started)
            if result["occupied_wall_seconds"] > CAP_SECONDS:
                raise TimeoutError("camera qualification v2 verification exceeded budget")
            _atomic_json(output / "terminal_record.json", result)
            _atomic_json(registry_terminal, result)
            marker.update(
                terminal_sha256=_sha(output / "terminal_record.json"),
                registry_terminal_sha256=_sha(registry_terminal),
            )
            _atomic_json(output / "qualification_complete.json", marker)
            if _elapsed_seconds(started) > CAP_SECONDS:
                raise TimeoutError("camera qualification v2 final admission exceeded budget")
            if json.loads(registry_terminal.read_text()) != result or marker != json.loads(
                (output / "qualification_complete.json").read_text()
            ):
                raise ValueError("camera qualification v2 final transaction mismatch")
            return result
        except BaseException as exc:
            (output / "qualification_complete.json").unlink(missing_ok=True)
            with contextlib.suppress(BaseException):
                terminal_path = output / "terminal_record.json"
                terminal = (
                    json.loads(terminal_path.read_text())
                    if terminal_path.exists()
                    else {
                        "schema": "static_arrival_camera_qualification_attempt_v1",
                        "freeze": freeze,
                        "child_exit_code": None,
                        "timeout": False,
                        "child_reaped": False,
                        "occupied_wall_seconds": _elapsed_seconds(started),
                    }
                )
                terminal.update(
                    status="FAIL",
                    failure_type=type(exc).__name__,
                    occupied_wall_seconds=_elapsed_seconds(started),
                    finalization_complete=False,
                    dataset_admission=False,
                )
                whole_process_timeout = terminal["occupied_wall_seconds"] > CAP_SECONDS
                terminal["whole_process_deadline_exceeded"] = whole_process_timeout
                if whole_process_timeout:
                    terminal["timeout"] = True
                if output.is_dir():
                    _atomic_json(terminal_path, terminal)
                _atomic_json(reservation.with_suffix(".terminal.json"), terminal)
            raise
