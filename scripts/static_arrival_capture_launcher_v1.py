"""Single-attempt supervisor for static-arrival camera capture.

The checked-in schedule is preparation-only. The production CLI refuses until
a separately reviewed revision explicitly authorizes runtime capture.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from offline_evaluation_contracts_v1 import atomic_snapshot  # noqa: E402
from prospective_data_contracts_v1 import reference_time  # noqa: E402

from navfm.collection.static_arrival_capture import (  # noqa: E402
    canonical_sha256,
    capture_worker_input,
    validate_schedule,
    verify_source_manifest,
)

CONFIG = ROOT / "configs/eval/static_arrival_training_acquisition_v2.json"
CAPTURE_WORKER = ROOT / "scripts/static_arrival_capture_worker_v1.py"
PROPOSED_CAP_S = 600.0
PRE_REAP_ATTEMPT_ALLOWANCE_S = 570.0
REAP_RESERVE_S = 10.0
FINALIZATION_RESERVE_S = 20.0


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_capture_outputs(
    output: Path, family_input: dict, *, allow_fixture: bool = False
) -> dict:
    report_path = output / "capture_report.json"
    if not report_path.is_file():
        raise ValueError("capture report missing")
    report = json.loads(report_path.read_text())
    expected = [frame["image_id"] for frame in family_input["frames"]]
    rows = report.get("frames")
    if report.get("family") != family_input["family"] or report.get("status") != "PASS":
        raise ValueError("capture family or terminal status mismatch")
    expected_hashes = (
        family_input["schedule_sha256"],
        family_input["source_bindings_sha256"],
        canonical_sha256(family_input),
    )
    actual_hashes = (
        report.get("schedule_sha256"),
        report.get("source_bindings_sha256"),
        report.get("family_input_sha256"),
    )
    if actual_hashes != expected_hashes:
        raise ValueError("capture report schedule/source binding mismatch")
    if report.get("fixture_only") is True and not allow_fixture:
        raise ValueError("contract fixture cannot be admitted as camera evidence")
    if report.get("fixture_only") not in (True, False):
        raise ValueError("capture fixture identity missing")
    if report.get("camera_config") != family_input["camera"]:
        raise ValueError("capture camera configuration mismatch")
    if report.get("fixture_only") is True and allow_fixture is not True:
        raise ValueError("fixture result is not runtime qualification")
    if not isinstance(rows, list) or [row.get("image_id") for row in rows] != expected:
        raise ValueError("capture frame identities/order incomplete")
    expected_bindings = {
        frame["image_id"]: (frame["episode_id"], frame["role"]) for frame in family_input["frames"]
    }
    if any(
        row.get("status") != "PASS"
        or (row.get("episode_id"), row.get("role")) != expected_bindings[row["image_id"]]
        for row in rows
    ):
        raise ValueError("capture contains failed frame")
    if any("geometric_proximity_label" in row or "distance_m" in row for row in rows):
        raise ValueError("evaluator labels entered capture/decision report")
    last_time = None
    last_reference = None
    manifest = {}
    for row in rows:
        image_path = (output / row["image_path"]).resolve()
        try:
            image_path.relative_to(output.resolve())
        except ValueError:
            raise ValueError("capture image path escapes attempt output") from None
        if not image_path.is_file() or _file_sha(image_path) != row.get("image_sha256"):
            raise ValueError("capture image missing or hash mismatch")
        if row.get("fixture_only") is True and not allow_fixture:
            raise ValueError("synthetic image cannot be admitted")
        if report["fixture_only"] is False:
            camera = row.get("camera", {})
            rendering_time = camera.get("rendering_time")
            reference = reference_time(camera)
            if (
                isinstance(rendering_time, bool)
                or not isinstance(rendering_time, (int, float))
                or not math.isfinite(rendering_time)
            ):
                raise ValueError("native rendering_time missing")
            if last_time is not None and rendering_time <= last_time:
                raise ValueError("rendering_time is not strictly increasing")
            if last_reference is not None and reference <= last_reference:
                raise ValueError("native rendering_frame is not strictly increasing")
            last_time, last_reference = rendering_time, reference
        manifest[row["image_id"]] = row["image_sha256"]
    label_path = output / "evaluator_only" / "geometric_labels.jsonl"
    if not label_path.is_file():
        raise ValueError("evaluator-only geometric labels missing")
    labels = [json.loads(line) for line in label_path.read_text().splitlines() if line]
    expected_query = {
        frame["image_id"] for frame in family_input["frames"] if frame["role"] == "query"
    }
    if (
        len(labels) != len(expected_query)
        or {row.get("image_id") for row in labels} != expected_query
    ):
        raise ValueError("evaluator label population mismatch")
    if any(row.get("access") != "EVALUATOR_ONLY_NOT_DECISION_INPUT" for row in labels):
        raise ValueError("evaluator channel marker missing")
    if report["fixture_only"] is False:
        frames_by_id = {frame["image_id"]: frame for frame in family_input["frames"]}
        episodes_by_id = {episode["episode_id"]: episode for episode in family_input["episodes"]}
        capture_rows_by_id = {row["image_id"]: row for row in rows}
        metadata_by_id = {}
        for image_id in expected:
            metadata_path = output / "capture_metadata" / f"{image_id}.json"
            if not metadata_path.is_file():
                raise ValueError("capture metadata missing")
            metadata = json.loads(metadata_path.read_text())
            frame = frames_by_id[image_id]
            if (
                metadata.get("image_id") != image_id
                or metadata.get("episode_id") != frame["episode_id"]
                or metadata.get("role") != frame["role"]
            ):
                raise ValueError("capture metadata identity/role mismatch")
            if metadata.get("image_sha256") != manifest[image_id]:
                raise ValueError("capture metadata image hash mismatch")
            if metadata.get("rendering_time") != capture_rows_by_id[image_id].get("camera", {}).get(
                "rendering_time"
            ) or metadata.get("rendering_frame") != capture_rows_by_id[image_id].get(
                "camera", {}
            ).get("rendering_frame"):
                raise ValueError("metadata timestamp is not bound to the capture snapshot")
            position = metadata.get("actual_camera_position")
            if (
                not isinstance(position, list)
                or len(position) != 3
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for value in position
                )
            ):
                raise ValueError("captured camera pose missing or nonfinite")
            metadata_by_id[image_id] = metadata
        for label in labels:
            frame = frames_by_id[label["image_id"]]
            episode = episodes_by_id[frame["episode_id"]]
            query_pose = metadata_by_id[label["image_id"]]["actual_camera_position"]
            goal_pose = metadata_by_id[episode["goal_reference_image_id"]]["actual_camera_position"]
            query_xy = query_pose[:2]
            goal_xy = goal_pose[:2]
            distance = math.dist(query_xy, goal_xy)
            if (
                label.get("episode_id") != episode["episode_id"]
                or label.get("goal_id") != episode["goal_id"]
                or label.get("coordinate_frame") != episode["coordinate_frame"]
                or label.get("stratum") != frame.get("stratum")
                or label.get("query_camera_xy_m") != query_xy
                or label.get("goal_camera_xy_m") != goal_xy
                or not math.isfinite(label.get("distance_m", float("nan")))
                or not math.isclose(label["distance_m"], distance, rel_tol=0.0, abs_tol=1e-9)
                or label.get("geometric_proximity_label") is not (distance <= 0.5)
            ):
                raise ValueError("evaluator label does not match same-snapshot captured poses")
        image_root = output / "policy_inputs" / "images"
        expected_paths = {str((output / row["image_path"]).resolve()) for row in rows}
        if {
            str(path.resolve()) for path in image_root.iterdir() if path.is_file()
        } != expected_paths:
            raise ValueError("policy input directory contains missing or extra files")
        metadata_root = output / "capture_metadata"
        expected_metadata = {f"{image_id}.json" for image_id in expected}
        if {path.name for path in metadata_root.iterdir() if path.is_file()} != expected_metadata:
            raise ValueError("capture metadata directory contains missing or extra files")
    manifest["evaluator_only/geometric_labels.jsonl"] = _file_sha(label_path)
    return {
        "frame_count": len(rows),
        "reference_count": sum(row["role"] == "reference" for row in family_input["frames"]),
        "query_count": len(expected_query),
        "scored_decisions": sum(
            frame.get("scored_decision") is True for frame in family_input["frames"]
        ),
        "artifact_sha256": manifest,
    }


def _write_failure_records(
    output: Path, reservation: Path, record: dict, writer: Callable = atomic_snapshot
) -> None:
    record["status"] = "FAIL"
    record["finalization_status"] = "FAILED"
    record["finalization_complete"] = False
    with contextlib.suppress(OSError):
        (output / "finalization_complete.json").unlink(missing_ok=True)
    for path in (output / "terminal_record.json", reservation.with_suffix(".terminal.json")):
        try:
            writer(path, record)
        except BaseException:
            record["failure_record_write_error"] = True


def finalize_attempt(
    output: Path,
    reservation: Path,
    record: dict,
    writer: Callable = atomic_snapshot,
) -> None:
    """Write terminal records; only a complete measured run receives admission."""

    record["finalization_complete"] = record.get("status") == "PASS"
    record["finalization_status"] = "COMPLETE"
    terminal = output / "terminal_record.json"
    registry_terminal = reservation.with_suffix(".terminal.json")
    try:
        writer(terminal, record)
        writer(registry_terminal, record)
        if record["status"] == "PASS":
            marker = {
                "status": "COMPLETE",
                "freeze": record["freeze"],
                "terminal_sha256": _file_sha(terminal),
                "registry_terminal_sha256": _file_sha(registry_terminal),
                "attempt_start_sha256": _file_sha(output / "attempt_start.json"),
            }
            writer(output / "finalization_complete.json", marker)
        else:
            record["finalization_complete"] = False
    except BaseException as exc:
        record["finalization_error_type"] = type(exc).__name__
        _write_failure_records(output, reservation, record, writer)
        raise


def run_attempt(
    *,
    config: dict,
    family: str,
    output: Path,
    registry: Path,
    freeze: str,
    worker_command: list[str],
    repo_root: Path = ROOT,
    wall_cap_s: float = PROPOSED_CAP_S,
    reap_reserve_s: float = REAP_RESERVE_S,
    finalize_reserve_s: float = FINALIZATION_RESERVE_S,
    process_started_monotonic: float | None = None,
    allow_fixture: bool = False,
    writer: Callable = atomic_snapshot,
) -> dict:
    """Run one process through the same supervisor used by the future CLI."""

    attempt_started = process_started_monotonic or time.monotonic()
    if allow_fixture is not True and config.get("runtime_authorized") is not True:
        raise ValueError("runtime authorization is absent")
    if allow_fixture and config.get("runtime_authorized") is not False:
        raise ValueError("contract-test mode requires a preparation-only schedule")
    validate_schedule(config)
    verify_source_manifest(config, repo_root)
    if wall_cap_s <= reap_reserve_s + finalize_reserve_s:
        raise ValueError("whole-process cap leaves no child execution allowance")
    output = output.expanduser().resolve()
    repo_root = repo_root.resolve()
    if output.exists() or output.is_relative_to(repo_root):
        raise ValueError("output must be new and outside the repository")
    registry = registry.expanduser().resolve()
    registry.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = registry / "lock"
    with lock_path.open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        reservation = registry / f"{family}.reserved.json"
        try:
            descriptor = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError("family attempt already consumed; no retry") from exc
        start = attempt_started
        record = {
            "schema": "static_arrival_family_attempt_v2",
            "family": family,
            "freeze": freeze,
            "status": "STARTED",
            "fixture_only": allow_fixture,
            "wall_cap_seconds": wall_cap_s,
            "pre_reap_attempt_allowance_seconds": wall_cap_s - reap_reserve_s - finalize_reserve_s,
            "reap_reserve_seconds": reap_reserve_s,
            "verification_and_finalization_reserve_seconds": finalize_reserve_s,
            "child_exit_code": None,
            "timeout": False,
            "child_reaped": False,
            "occupied_wall_seconds": 0.0,
        }
        with os.fdopen(descriptor, "w") as stream:
            stream.write(
                json.dumps(
                    {"family": family, "freeze": freeze, "status": "CONSUMED"}, sort_keys=True
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        child = None
        try:
            output.mkdir(parents=True, mode=0o700)
            os.umask(0o077)
            writer(output / "attempt_start.json", record)
            family_input = capture_worker_input(config, family)
            family_input["schedule_sha256"] = canonical_sha256(config)
            family_input["source_bindings_sha256"] = canonical_sha256(config["source_bindings"])
            input_dir = output / "attempt_inputs"
            input_dir.mkdir(mode=0o700)
            writer(input_dir / "family_input.json", family_input)
            writer(input_dir / "schedule.json", config)
            record["schedule_sha256"] = family_input["schedule_sha256"]
            record["source_bindings_sha256"] = family_input["source_bindings_sha256"]
            record["family_input_sha256"] = canonical_sha256(family_input)
            writer(output / "attempt_start.json", record)
            environment = dict(os.environ)
            nonce = hashlib.sha256(os.urandom(32)).hexdigest()
            environment["NAVFM_STATIC_ARRIVAL_PARENT_NONCE"] = nonce
            command = [*worker_command, "--parent-nonce", nonce]
            with (output / "worker.stdout").open("wb") as stdout:
                child = subprocess.Popen(
                    command,
                    cwd=repo_root,
                    env=environment,
                    stdout=stdout,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                record["child_started_monotonic"] = time.monotonic()
                child_deadline = start + wall_cap_s - reap_reserve_s - finalize_reserve_s
                try:
                    record["child_exit_code"] = child.wait(
                        timeout=max(0.0, child_deadline - time.monotonic())
                    )
                except subprocess.TimeoutExpired:
                    record["timeout"] = True
                if child.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(
                            timeout=max(
                                0.0, start + wall_cap_s - finalize_reserve_s - time.monotonic()
                            )
                        )
                    except subprocess.TimeoutExpired:
                        with contextlib.suppress(ProcessLookupError):
                            os.killpg(child.pid, signal.SIGKILL)
                        try:
                            child.wait(
                                timeout=max(
                                    0.0,
                                    start + wall_cap_s - finalize_reserve_s - time.monotonic(),
                                )
                            )
                        except subprocess.TimeoutExpired:
                            raise TimeoutError(
                                "child could not be reaped within the process reserve"
                            ) from None
            record["child_exit_code"] = child.returncode
            record["child_reaped"] = child.returncode is not None
            if record["timeout"]:
                raise TimeoutError("family capture exceeded its single process deadline")
            if child.returncode != 0:
                raise ValueError("capture worker failed")
            verified = verify_capture_outputs(output, family_input, allow_fixture=allow_fixture)
            record.update(verified)
            record["status"] = "CONTRACT_TEST_ONLY_PASS" if allow_fixture else "PASS"
            record["capture_terminal_status"] = "PASS"
            record["worker_report_sha256"] = _file_sha(output / "capture_report.json")
        except BaseException as exc:
            record["status"] = "FAIL"
            record["failure_type"] = type(exc).__name__
            raise
        finally:
            record["occupied_wall_seconds"] = time.monotonic() - start
            if record["status"] == "PASS":
                try:
                    finalize_attempt(output, reservation, record, writer)
                    record["occupied_wall_seconds"] = time.monotonic() - start
                    if record["occupied_wall_seconds"] > wall_cap_s:
                        record["status"] = "FAIL"
                        record["timeout"] = True
                        record["failure_type"] = "WholeProcessDeadlineExceeded"
                        _write_failure_records(output, reservation, record, writer)
                except BaseException:
                    raise
            else:
                for path in (
                    output / "terminal_record.json",
                    reservation.with_suffix(".terminal.json"),
                ):
                    try:
                        writer(path, record)
                    except BaseException:
                        record["failure_record_write_error"] = True
    return record


def main() -> None:
    process_started = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=("F0", "F1", "F2", "F3", "F4"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--execute-approved", action="store_true")
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    if not args.execute_approved or config.get("runtime_authorized") is not True:
        parser.error("preparation-only; a separately reviewed authorized revision is required")
    gate = config.get("runtime_gate", {})
    if any(
        gate.get(name, {}).get("status") != "PASS"
        for name in ("known_fixture_camera", "training_scene_camera")
    ):
        parser.error("camera runtime qualification evidence is incomplete")
    actual_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if args.freeze != actual_head or subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ):
        parser.error("exact clean frozen commit required")
    validate_schedule(config)
    verify_source_manifest(config, ROOT)
    group = next(item for item in config["groups"] if item["family"] == args.family)
    if group["role"] == "descriptive_assessment":
        parser.error("F4 assessment access requires its own later frozen gate")
    registry = Path(config["registry_root"]).expanduser()
    environment_python = config["worker_python"]
    worker_input_path = args.out.expanduser().resolve() / "attempt_inputs/family_input.json"
    command = [
        environment_python,
        str(CAPTURE_WORKER),
        "--config",
        str(CONFIG),
        "--family-input",
        str(worker_input_path),
        "--out",
        str(args.out.expanduser().resolve()),
    ]
    run_attempt(
        config=config,
        family=args.family,
        output=args.out,
        registry=registry,
        freeze=args.freeze,
        worker_command=command,
        process_started_monotonic=process_started,
    )


if __name__ == "__main__":
    main()
