"""Frozen technical-camera qualification schedule and admission checks.

The qualification uses a documented training-scene fixture but creates no
training episode, prediction, fitted value, or calibration label.
"""

from __future__ import annotations

import contextlib
import fcntl
import functools
import hashlib
import json
import math
import os
import signal
import subprocess
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

from navfm.collection.static_arrival_capture import (
    CAMERA_SETTINGS,
    LIGHTING_SETTINGS,
    canonical_sha256,
    source_sha256,
    training_scene_boxes,
)

SCENE_INDEX = 0
SCENE_HALF_WIDTH_M = 2.0
SCENE_PARTITIONS = False
EPISODE_ID = "camera_qualification_v1_legacy_corridor_scene_0"
REFERENCE_POSES = ([1.03, 0.33, 0.07], [1.37, 0.33, 0.07], [1.71, 0.33, 0.07])
QUERY_POSES = (
    [2.05, 0.33, 0.07],
    [2.39, 0.33, 0.17],
    [2.73, 0.33, 0.27],
    [3.07, 0.33, -0.03],
    [3.41, 0.33, 0.07],
)
FRAME_COUNT = len(REFERENCE_POSES) + len(QUERY_POSES)
CAP_SECONDS = 120.0
REAP_RESERVE_SECONDS = 10.0
FINALIZE_RESERVE_SECONDS = 20.0
TERM_GRACE_SECONDS = 5.0
BOUND_PATHS = (
    "src/navfm/collection/scene_layouts.py",
    "src/navfm/isaac/app.py",
    "src/navfm/collection/static_arrival_capture.py",
    "src/navfm/collection/static_arrival_camera_qualification.py",
    "scripts/static_arrival_capture_worker_v1.py",
    "scripts/static_arrival_camera_qualification_worker_v1.py",
    "scripts/static_arrival_camera_qualification_v1.py",
    "scripts/prospective_data_contracts_v1.py",
    "scripts/development_qualification_contracts_v1.py",
    "scripts/offline_evaluation_contracts_v1.py",
    "configs/eval/static_arrival_training_acquisition_v2.json",
)


def _sha(path: Path) -> str:
    return source_sha256(path)


@functools.lru_cache(maxsize=4)
def _isaacsim_distribution_version(worker_python: str) -> str:
    return subprocess.check_output(
        [
            worker_python,
            "-c",
            "from importlib.metadata import version; print(version('isaacsim'))",
        ],
        text=True,
        timeout=10,
    ).strip()


def _frame(role: str, index: int, pose: list[float]) -> dict[str, Any]:
    return {
        "image_id": f"camera_qualification_v1_{role}_{index:02d}",
        "episode_id": EPISODE_ID,
        "role": role,
        "body_pose_xy_yaw_rad": pose,
    }


def build_qualification(root: Path) -> dict[str, Any]:
    geometry = training_scene_boxes(SCENE_INDEX, SCENE_HALF_WIDTH_M, SCENE_PARTITIONS)
    acquisition_config = json.loads(
        (root / "configs/eval/static_arrival_training_acquisition_v2.json").read_text()
    )
    worker_python = Path(acquisition_config["worker_python"])
    if not worker_python.is_file():
        raise ValueError("bound Isaac worker interpreter is unavailable")
    isaacsim_version = _isaacsim_distribution_version(str(worker_python))
    scheduled_poses = {
        tuple(float(value) for value in frame["body_pose_xy_yaw_rad"])
        for episode in acquisition_config["episodes"]
        if episode["scene_index"] == SCENE_INDEX
        for frame in episode["reference_frames"] + episode["query_frames"]
    }
    qualification_frames = [
        _frame("reference", index, pose) for index, pose in enumerate(REFERENCE_POSES)
    ] + [_frame("query", index, pose) for index, pose in enumerate(QUERY_POSES)]
    pose_overlap = sorted(
        set(
            tuple(float(value) for value in frame["body_pose_xy_yaw_rad"])
            for frame in qualification_frames
        )
        & scheduled_poses
    )
    if pose_overlap or EPISODE_ID in {
        episode["episode_id"] for episode in acquisition_config["episodes"]
    }:
        raise ValueError("technical qualification overlaps a planned episode or exact pose")
    return {
        "schema_version": 1,
        "status": "PREPARED_FOR_APPROVAL",
        "purpose": "technical_camera_path_qualification_only",
        "fixture": {
            "identity": "legacy_corridor_scene_0",
            "source": "the explicitly bound F0 scene geometry in the already-published v2 schedule",
            "scene_index": SCENE_INDEX,
            "wall_half_width_m": SCENE_HALF_WIDTH_M,
            "partitions": SCENE_PARTITIONS,
            "geometry_sha256": canonical_sha256(geometry),
            "exposure_note": "scene specification is already exposed; this qualification creates new technical captures which are excluded from all scheduled fit, threshold-selection, and assessment episodes",
        },
        "camera": dict(CAMERA_SETTINGS),
        "lighting": dict(LIGHTING_SETTINGS),
        "runtime": {
            "worker_python": str(worker_python),
            "worker_python_sha256": _sha(worker_python),
            "isaacsim_distribution_version": isaacsim_version,
            "bootstrap_compatibility_branch": [5, 0],
        },
        "warmup_sim_steps": CAMERA_SETTINGS["warmup_sim_steps"],
        "held_sim_steps_per_capture": CAMERA_SETTINGS["held_sim_steps_per_capture"],
        "schedule": {
            "episode_id": EPISODE_ID,
            "references": [
                _frame("reference", index, pose) for index, pose in enumerate(REFERENCE_POSES)
            ],
            "queries": [_frame("query", index, pose) for index, pose in enumerate(QUERY_POSES)],
            "capture_order": "all three reference views, then five query views",
            "pose_semantics": "eight separately authored static camera poses; transitions are not a continuous-motion trajectory",
            "labels": "none; no evaluator labels or query ground truth are written or supplied to capture code",
        },
        "overlap_audit": {
            "planned_episode_identity_overlap": [],
            "exact_body_pose_overlap": [],
            "scene_specification_overlap": ["legacy_corridor_scene_0/F0"],
        },
        "population": {
            "frames": FRAME_COUNT,
            "references": len(REFERENCE_POSES),
            "queries": len(QUERY_POSES),
        },
        "budget": {
            "status": "PROPOSED_FOR_APPROVAL_NOT_MEASURED",
            "scope": "one complete qualification process, from runner entry through capture, child shutdown, reap, verification, and qualification finalization",
            "whole_process_cap_seconds": CAP_SECONDS,
            "capture_and_child_exit_allowance_seconds": CAP_SECONDS
            - REAP_RESERVE_SECONDS
            - FINALIZE_RESERVE_SECONDS,
            "reap_reserve_seconds": REAP_RESERVE_SECONDS,
            "verification_and_finalization_reserve_seconds": FINALIZE_RESERVE_SECONDS,
            "deadline_clock": "parent monotonic clock; starts at runner entry and is checked again after finalization",
            "measured": False,
            "does_not_establish_full_family_feasibility": True,
        },
        "evidence": {
            "root": "~/navfm-runtime-evidence/static-arrival-camera-qualification-v1",
            "registry": "~/navfm-runtime-evidence/static-arrival-camera-qualification-v1/registry",
            "one_attempt_only": True,
            "dataset_admission": False,
            "retain_partial_frames_and_readbacks": True,
        },
        "source_bindings": [{"path": name, "sha256": _sha(root / name)} for name in BOUND_PATHS],
    }


def build_worker_input(config: dict[str, Any]) -> dict[str, Any]:
    scene = config["fixture"]
    frames = config["schedule"]["references"] + config["schedule"]["queries"]
    return {
        "mode": "technical_camera_qualification_only",
        "qualification_id": "static-arrival-camera-qualification-v1-scene0",
        "family": "TECHNICAL",
        "camera": config["camera"],
        "lighting": config["lighting"],
        "warmup_sim_steps": config["warmup_sim_steps"],
        "held_sim_steps_per_capture": config["held_sim_steps_per_capture"],
        "expected_isaacsim_version": config["runtime"]["isaacsim_distribution_version"],
        "episodes": [
            {
                "episode_id": EPISODE_ID,
                "scene_index": scene["scene_index"],
                "wall_half_width_m": scene["wall_half_width_m"],
                "partitions": scene["partitions"],
                "geometry_sha256": scene["geometry_sha256"],
            }
        ],
        "frames": frames,
        "schedule_sha256": canonical_sha256(config),
        "bound_schedule_sha256": canonical_sha256(config),
        "source_bindings_sha256": canonical_sha256(config["source_bindings"]),
    }


def verify_source_bindings(config: dict[str, Any], root: Path) -> None:
    rows = config.get("source_bindings")
    if not isinstance(rows, list) or [row.get("path") for row in rows] != list(BOUND_PATHS):
        raise ValueError("qualification source binding set/order mismatch")
    for row in rows:
        if row.get("sha256") != _sha(root / row["path"]):
            raise ValueError(f"qualification source hash mismatch: {row['path']}")


def _number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def verify_capture(output: Path, worker_input: dict[str, Any]) -> dict[str, Any]:
    report_path = output / "capture_report.json"
    report = json.loads(report_path.read_text())
    expected_frames = worker_input["frames"]
    expected_ids = [frame["image_id"] for frame in expected_frames]
    if (
        report.get("schema") != "static_arrival_camera_qualification_v1"
        or report.get("status") != "PASS"
        or report.get("shutdown_returned") is not True
        or report.get("bootstrap_compatibility_branch") != [5, 0]
        or report.get("isaacsim_distribution_version") != worker_input["expected_isaacsim_version"]
        or report.get("qualification_only") is not True
        or report.get("schedule_sha256") != worker_input["schedule_sha256"]
        or report.get("source_bindings_sha256") != worker_input["source_bindings_sha256"]
        or report.get("worker_input_sha256") != canonical_sha256(worker_input)
        or report.get("family") != "TECHNICAL"
        or report.get("camera_config") != worker_input["camera"]
    ):
        raise ValueError("qualification report terminal/schedule binding mismatch")
    rows = report.get("frames")
    if not isinstance(rows, list) or [row.get("image_id") for row in rows] != expected_ids:
        raise ValueError("qualification frame population/order mismatch")
    frame_by_id = {frame["image_id"]: frame for frame in expected_frames}
    previous_time: float | None = None
    previous_frame: Fraction | None = None
    hashes = {}
    for row in rows:
        image_id = row["image_id"]
        expected = frame_by_id[image_id]
        if (
            row.get("status") != "PASS"
            or row.get("episode_id") != EPISODE_ID
            or row.get("role") != expected["role"]
            or any(key in row for key in ("distance_m", "geometric_proximity_label", "stratum"))
        ):
            raise ValueError("failed frame or evaluator-only data in capture report")
        camera = row.get("camera", {})
        rendering_time = camera.get("rendering_time")
        reference = camera.get("rendering_frame", {})
        if not _number(rendering_time):
            raise ValueError("native rendering_time missing/nonfinite")
        numerator, denominator = (
            reference.get("referenceTimeNumerator"),
            reference.get("referenceTimeDenominator"),
        )
        if (
            isinstance(numerator, bool)
            or not isinstance(numerator, int)
            or isinstance(denominator, bool)
            or not isinstance(denominator, int)
            or denominator <= 0
        ):
            raise ValueError("native rational rendering frame missing")
        current_frame = Fraction(numerator, denominator)
        if previous_time is not None and rendering_time <= previous_time:
            raise ValueError("native rendering_time is not strictly ordered")
        if previous_frame is not None and current_frame <= previous_frame:
            raise ValueError("native rational rendering frame is not strictly ordered")
        previous_time, previous_frame = float(rendering_time), current_frame
        author, held = row.get("pose_author_time"), row.get("hold_end_time")
        if not _number(author) or not _number(held):
            raise ValueError("pose hold timestamps missing/nonfinite")
        duration = float(held) - float(author)
        expected_duration = (
            worker_input["held_sim_steps_per_capture"] / worker_input["camera"]["sim_hz"]
        )
        if not math.isclose(duration, expected_duration, rel_tol=0.0, abs_tol=1e-5):
            raise ValueError("held-pose duration differs from frozen step schedule")
        if not (float(author) < float(rendering_time) <= float(held) + 1e-6):
            raise ValueError("RGB timestamp falls outside held-pose interval")
        if row.get("rgb_shape") != [240, 320, 4]:
            raise ValueError("RGB shape criterion failed")
        if not _number(row.get("rgb_std")) or row["rgb_std"] < 5.0:
            raise ValueError("raw RGB usability criterion failed")
        actual = row.get("actual_camera_position")
        represented = row.get("represented_float32_position")
        if (
            not isinstance(actual, list)
            or not isinstance(represented, list)
            or len(actual) != 3
            or len(represented) != 3
            or any(not _number(item) for item in actual + represented)
            or any(
                abs(float(a) - float(b)) > 1e-6 for a, b in zip(actual, represented, strict=True)
            )
        ):
            raise ValueError("camera pose does not match float32-aware readback")
        expected_position = row.get("requested_camera_position")
        if not isinstance(expected_position, list) or len(expected_position) != 3:
            raise ValueError("requested camera pose missing")
        from prospective_data_contracts_v1 import float32_position

        expected_float32 = float32_position(expected_position)
        if represented != expected_float32:
            raise ValueError("float32 pose representation does not match requested pose")
        body_pose = expected["body_pose_xy_yaw_rad"]
        expected_camera_pose = [
            body_pose[0] + worker_input["camera"]["forward_offset_m"] * math.cos(body_pose[2]),
            body_pose[1] + worker_input["camera"]["forward_offset_m"] * math.sin(body_pose[2]),
            worker_input["camera"]["camera_height_m"],
        ]
        if any(
            abs(float(a) - float(b)) > 1e-9
            for a, b in zip(expected_position, expected_camera_pose, strict=True)
        ):
            raise ValueError("requested camera pose does not match bound body pose")
        yaw = float(body_pose[2])
        expected_quaternion = [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]
        actual_quaternion = row.get("actual_camera_quaternion")
        if (
            not isinstance(actual_quaternion, list)
            or len(actual_quaternion) != 4
            or any(not _number(item) for item in actual_quaternion)
            or not any(
                all(
                    abs(float(a) - float(b)) <= 1e-6
                    for a, b in zip(actual_quaternion, target, strict=True)
                )
                for target in (expected_quaternion, [-item for item in expected_quaternion])
            )
        ):
            raise ValueError("camera quaternion does not match bound pose")
        image = (output / row["image_path"]).resolve()
        image.relative_to(output.resolve())
        metadata_path = output / "capture_metadata" / f"{image_id}.json"
        metadata = json.loads(metadata_path.read_text())
        if (
            metadata.get("image_id") != image_id
            or metadata.get("episode_id") != EPISODE_ID
            or metadata.get("role") != expected["role"]
            or metadata.get("image_sha256") != row.get("image_sha256")
            or metadata.get("rendering_time") != rendering_time
            or metadata.get("rendering_frame") != reference
            or metadata.get("actual_camera_position") != actual
            or metadata.get("actual_camera_quaternion") != actual_quaternion
            or any(
                key in metadata for key in ("distance_m", "geometric_proximity_label", "stratum")
            )
        ):
            raise ValueError("same-snapshot metadata binding or label isolation failed")
        if not image.is_file() or _sha(image) != row.get("image_sha256"):
            raise ValueError("captured RGB image missing or hash mismatch")
        import numpy as np
        from PIL import Image

        with Image.open(image) as rendered:
            rgb = np.asarray(rendered.convert("RGB"))
        if rgb.shape != (240, 320, 3) or not np.isfinite(rgb).all():
            raise ValueError("saved RGB image is unusable")
        hashes[image_id] = row["image_sha256"]
    expected_metadata = {f"{image_id}.json" for image_id in expected_ids}
    metadata_root = output / "capture_metadata"
    if {path.name for path in metadata_root.iterdir()} != expected_metadata:
        raise ValueError("capture metadata inventory mismatch")
    if (output / "evaluator_only").exists():
        raise ValueError("qualification output must not contain evaluator labels")
    image_root = output / "policy_inputs" / "images"
    if {path.name for path in image_root.iterdir()} != {
        f"{image_id}.jpg" for image_id in expected_ids
    }:
        raise ValueError("captured RGB inventory mismatch")
    return {
        "frame_count": len(rows),
        "reference_count": 3,
        "query_count": 5,
        "image_sha256": hashes,
        "capture_artifacts": {
            "capture_report.json": _sha(report_path),
            **{
                f"capture_metadata/{image_id}.json": _sha(
                    output / "capture_metadata" / f"{image_id}.json"
                )
                for image_id in expected_ids
            },
            **{
                f"policy_inputs/images/{image_id}.jpg": hashes[image_id]
                for image_id in expected_ids
            },
        },
    }


def verify_completion_marker(output: Path, registry_terminal: Path, freeze: str) -> None:
    """Recheck terminal records and every captured artifact bound by admission."""
    marker_path = output / "qualification_complete.json"
    terminal_path = output / "terminal_record.json"
    attempt_path = output / "attempt_start.json"
    marker = json.loads(marker_path.read_text())
    terminal = json.loads(terminal_path.read_text())
    registry_record = json.loads(registry_terminal.read_text())
    if (
        marker.get("status") != "QUALIFICATION_COMPLETE"
        or marker.get("freeze") != freeze
        or set(marker)
        != {
            "status",
            "freeze",
            "terminal_sha256",
            "registry_terminal_sha256",
            "attempt_start_sha256",
        }
        or marker.get("terminal_sha256") != _sha(terminal_path)
        or marker.get("registry_terminal_sha256") != _sha(registry_terminal)
        or marker.get("attempt_start_sha256") != _sha(attempt_path)
        or registry_record != terminal
        or terminal.get("status") != "QUALIFICATION_PASS"
        or terminal.get("freeze") != freeze
        or terminal.get("finalization_complete") is not True
        or terminal.get("dataset_admission") is not False
        or terminal.get("timeout") is not False
        or terminal.get("child_exit_code") != 0
        or terminal.get("child_reaped") is not True
    ):
        raise ValueError("qualification marker/terminal record binding mismatch")
    image_ids = terminal.get("image_sha256")
    if not isinstance(image_ids, dict) or len(image_ids) != FRAME_COUNT:
        raise ValueError("qualification terminal image inventory is incomplete")
    expected_paths = {
        "capture_report.json",
        *{f"capture_metadata/{image_id}.json" for image_id in image_ids},
        *{f"policy_inputs/images/{image_id}.jpg" for image_id in image_ids},
    }
    artifacts = terminal.get("capture_artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != expected_paths:
        raise ValueError("qualification terminal artifact inventory mismatch")
    for relative, expected_hash in artifacts.items():
        artifact_path = (output / relative).resolve()
        artifact_path.relative_to(output.resolve())
        if not artifact_path.is_file() or _sha(artifact_path) != expected_hash:
            raise ValueError("qualification artifact changed after admission")
    if (output / "evaluator_only").exists():
        raise ValueError("qualification output contains evaluator-only data")


def _emergency_reap(child, record: dict[str, Any], deadline: float) -> None:
    """Best-effort TERM/KILL cleanup on every exceptional supervisor exit."""

    def alive() -> bool:
        try:
            return child.poll() is None
        except BaseException as exc:
            record["cleanup_poll_error_type"] = type(exc).__name__
            return True

    def signal_group(sig: int, fallback_name: str) -> None:
        fallback_needed = False
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            fallback_needed = True
        except BaseException as exc:
            record[f"{fallback_name}_group_error_type"] = type(exc).__name__
            fallback_needed = True
        if fallback_needed and alive():
            try:
                getattr(child, "terminate" if sig == signal.SIGTERM else "kill")()
            except ProcessLookupError:
                pass
            except BaseException as fallback_exc:
                record[f"{fallback_name}_child_error_type"] = type(fallback_exc).__name__

    if alive():
        signal_group(signal.SIGTERM, "cleanup_term")
        try:
            child.wait(timeout=max(0.0, min(TERM_GRACE_SECONDS, deadline - time.monotonic())))
        except BaseException as exc:
            record["cleanup_term_wait_error_type"] = type(exc).__name__
    if alive():
        signal_group(signal.SIGKILL, "cleanup_kill")
        try:
            child.wait(
                timeout=max(
                    0.0,
                    min(REAP_RESERVE_SECONDS - TERM_GRACE_SECONDS, deadline - time.monotonic()),
                )
            )
        except BaseException as exc:
            record["cleanup_kill_wait_error_type"] = type(exc).__name__
    try:
        record["child_exit_code"] = child.poll()
        record["child_reaped"] = child.returncode is not None
    except BaseException as exc:
        record["cleanup_final_poll_error_type"] = type(exc).__name__
        record["child_reaped"] = False


def run_supervised_worker(
    *,
    command: list[str],
    output: Path,
    worker_input: dict[str, Any],
    cap_seconds: float = CAP_SECONDS,
    freeze: str,
    process_started_monotonic: float | None = None,
) -> dict[str, Any]:
    """Bounded subprocess lifecycle used by the approval-gated CLI and tests."""
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    input_path = output / "qualification_input.json"
    _atomic_json(input_path, worker_input)
    nonce = hashlib.sha256(os.urandom(32)).hexdigest()
    env = dict(os.environ, NAVFM_STATIC_ARRIVAL_PARENT_NONCE=nonce)
    started = (
        process_started_monotonic if process_started_monotonic is not None else time.monotonic()
    )
    record: dict[str, Any] = {
        "schema": "static_arrival_camera_qualification_attempt_v1",
        "status": "STARTED",
        "freeze": freeze,
        "child_exit_code": None,
        "timeout": False,
        "child_reaped": False,
        "wall_cap_seconds": cap_seconds,
        "capture_allowance_seconds": cap_seconds - REAP_RESERVE_SECONDS - FINALIZE_RESERVE_SECONDS,
    }
    command = [*command, "--input", str(input_path), "--out", str(output), "--parent-nonce", nonce]
    child = None
    try:
        with (output / "worker.stdout").open("wb") as stdout:
            child = subprocess.Popen(
                command, env=env, stdout=stdout, stderr=subprocess.STDOUT, start_new_session=True
            )
            record["child_started_monotonic"] = time.monotonic()
            deadline = started + cap_seconds - REAP_RESERVE_SECONDS - FINALIZE_RESERVE_SECONDS
            try:
                child.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                record["timeout"] = True
            if child.poll() is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(
                        timeout=max(
                            0.0,
                            started
                            + cap_seconds
                            - FINALIZE_RESERVE_SECONDS
                            - (REAP_RESERVE_SECONDS - TERM_GRACE_SECONDS)
                            - time.monotonic(),
                        )
                    )
                except subprocess.TimeoutExpired:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait(
                        timeout=max(
                            0.0,
                            started + cap_seconds - FINALIZE_RESERVE_SECONDS - time.monotonic(),
                        )
                    )
        record["child_exit_code"] = child.returncode
        record["child_reaped"] = child.returncode is not None
        record["timeout"] = record["timeout"] or time.monotonic() > deadline
        if record["timeout"]:
            raise TimeoutError("camera qualification exceeded its single deadline")
        if child.returncode != 0 or not record["child_reaped"]:
            raise ValueError("camera qualification worker failed or was not reaped")
        if json.loads(input_path.read_text()) != worker_input:
            raise ValueError("qualification input changed during worker execution")
        verified = verify_capture(output, worker_input)
        record.update(verified)
        record["status"] = "QUALIFICATION_PASS"
    except BaseException as exc:
        record["status"] = "FAIL"
        record["failure_type"] = type(exc).__name__
        if child is not None:
            _emergency_reap(
                child,
                record,
                started + cap_seconds - FINALIZE_RESERVE_SECONDS,
            )
        raise
    finally:
        record["occupied_wall_seconds"] = time.monotonic() - started
        if record["occupied_wall_seconds"] > cap_seconds:
            record.update(status="FAIL", timeout=True, failure_type="WholeProcessDeadlineExceeded")
        record["finalization_complete"] = False
        record["dataset_admission"] = False
        terminal_path = output / "terminal_record.json"
        try:
            _atomic_json(terminal_path, record)
        except BaseException as exc:
            record.update(
                status="FAIL",
                failure_type="FinalizationFailure",
                finalization_error_type=type(exc).__name__,
            )
            with contextlib.suppress(BaseException):
                _atomic_json(terminal_path, record)
            raise
    return record


def run_one_shot(
    *,
    config: dict[str, Any],
    output: Path,
    registry: Path,
    freeze: str,
    worker_command: list[str],
    root: Path,
    process_started_monotonic: float | None = None,
) -> dict[str, Any]:
    """Consume the qualification identity once and supervise one worker."""
    process_started = (
        process_started_monotonic if process_started_monotonic is not None else time.monotonic()
    )
    verify_source_bindings(config, root)
    output = output.expanduser().resolve()
    root = root.resolve()
    if output.exists() or output.is_relative_to(root):
        raise ValueError("qualification output must be new and external")
    registry = registry.expanduser().resolve()
    registry.mkdir(parents=True, exist_ok=True, mode=0o700)
    reservation = registry / "technical-scene0.reserved.json"
    with (registry / "lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            descriptor = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError("qualification attempt already consumed; no retry") from exc
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
                    "worker_input_sha256": canonical_sha256(build_worker_input(config)),
                },
            )
        except BaseException as exc:
            terminal = {
                "schema": "static_arrival_camera_qualification_attempt_v1",
                "status": "FAIL",
                "freeze": freeze,
                "failure_type": "ParentInitializationFailure",
                "failure_detail_type": type(exc).__name__,
                "child_exit_code": None,
                "timeout": False,
                "child_reaped": False,
                "finalization_complete": False,
                "dataset_admission": False,
            }
            if output.is_dir():
                with contextlib.suppress(BaseException):
                    _atomic_json(output / "terminal_record.json", terminal)
            with contextlib.suppress(BaseException):
                _atomic_json(reservation.with_suffix(".terminal.json"), terminal)
            raise
        result = None
        try:
            result = run_supervised_worker(
                command=worker_command,
                output=output,
                worker_input=build_worker_input(config),
                cap_seconds=float(config["budget"]["whole_process_cap_seconds"]),
                freeze=freeze,
                process_started_monotonic=process_started,
            )
        except BaseException:
            terminal_path = output / "terminal_record.json"
            if terminal_path.is_file():
                terminal = json.loads(terminal_path.read_text())
                _atomic_json(reservation.with_suffix(".terminal.json"), terminal)
            raise
        terminal = json.loads((output / "terminal_record.json").read_text())
        marker_path = output / "qualification_complete.json"
        marker_path.unlink(missing_ok=True)
        try:
            _atomic_json(reservation.with_suffix(".terminal.json"), terminal)
        except BaseException as exc:
            marker_path.unlink(missing_ok=True)
            terminal.update(
                status="FAIL",
                finalization_complete=False,
                failure_type="RegistryFinalizationFailure",
                finalization_error_type=type(exc).__name__,
            )
            _atomic_json(output / "terminal_record.json", terminal)
            raise
        if result["status"] == "QUALIFICATION_PASS":
            terminal["finalization_complete"] = True
            terminal["occupied_wall_seconds"] = time.monotonic() - process_started
            try:
                _atomic_json(output / "terminal_record.json", terminal)
                _atomic_json(reservation.with_suffix(".terminal.json"), terminal)
                marker = {
                    "status": "QUALIFICATION_COMPLETE",
                    "freeze": freeze,
                    "terminal_sha256": _sha(output / "terminal_record.json"),
                    "registry_terminal_sha256": _sha(reservation.with_suffix(".terminal.json")),
                    "attempt_start_sha256": _sha(output / "attempt_start.json"),
                }
                _atomic_json(marker_path, marker)
                saved_marker = json.loads(marker_path.read_text())
                if saved_marker != marker:
                    raise ValueError("qualification finalization marker mismatch")
                verify_completion_marker(output, reservation.with_suffix(".terminal.json"), freeze)
                elapsed = time.monotonic() - process_started
                if elapsed > float(config["budget"]["whole_process_cap_seconds"]):
                    raise TimeoutError("whole qualification process exceeded its deadline")
            except BaseException as exc:
                marker_path.unlink(missing_ok=True)
                terminal.update(
                    status="FAIL",
                    timeout=isinstance(exc, TimeoutError),
                    occupied_wall_seconds=time.monotonic() - process_started,
                    finalization_complete=False,
                    failure_type=(
                        "WholeProcessDeadlineExceeded"
                        if isinstance(exc, TimeoutError)
                        else "FinalizationFailure"
                    ),
                    finalization_error_type=type(exc).__name__,
                )
                _atomic_json(output / "terminal_record.json", terminal)
                _atomic_json(reservation.with_suffix(".terminal.json"), terminal)
                raise
            result["whole_process_wall_seconds"] = elapsed
        return result


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".pending")
    with temporary.open("w") as stream:
        stream.write(json.dumps(value, allow_nan=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
