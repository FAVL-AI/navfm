"""Pending-approval accessed-layout collection continuation; no scoring."""

import argparse
import contextlib
import fcntl
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from development_qualification_contracts_v1 import ROOT, cancel_signal, frozen, sha
from offline_evaluation_contracts_v1 import atomic_snapshot as write
from prospective_collection_budget_v2 import (
    cleanup_remaining,
    execution_remaining,
    finalize_transaction,
)
from prospective_collection_contracts_v1 import admission, validate_capsule, verify_qualification
from prospective_data_contracts_v1 import validate_seal


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--execute-approved-amendment", action="store_true")
    args = p.parse_args()
    if not args.execute_approved_amendment:
        raise ValueError("user approval must precede explicit execution opt-in")
    config = ROOT / "configs/eval/prospective_collection_v2.json"
    cfg = json.loads(config.read_text())
    proposal = json.loads(Path(cfg["budget_amendment"]["proposal"]).read_text())
    frozen(args.freeze, cfg)
    verify_qualification(cfg)
    binding = json.loads(Path(cfg["finalization"]["seal_binding"]).read_text())
    if binding["generation_freeze"] != "cfdb4033a88265f8d143a40a38a98ca2ccc09003":
        raise ValueError("seal generation identity drift")
    for path, digest in binding["opaque_original_artifacts"].items():
        if sha(Path(path)) != digest:
            raise ValueError("original opaque seal/failure evidence drift")
    for path, digest in binding["repaired_source_files"].items():
        if sha(Path(path)) != digest:
            raise ValueError("amended source identity drift")
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError("fresh external output required")
    registry = Path(cfg["collection"]["registry"])
    registry.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (registry / "lock").open("a")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    slot = registry / "reservation.json"
    if slot.exists():
        raise ValueError("amended attempt consumed; no retry")
    out.mkdir(parents=True, mode=0o700)
    os.umask(0o077)
    start = time.monotonic()
    dataset_admission = None
    record = dict(
        freeze=args.freeze,
        status="STARTED",
        approved_amendment_invocation=True,
        hard_total_seconds=190,
        execution_deadline_monotonic=start + 185,
        total_deadline_monotonic=start + 190,
        prior_layout_exposure="ACCESSED_NOT_UNINSPECTED",
        measurement_complete=False,
        child_exit_code=None,
        timeout=False,
        child_reaped=False,
        sdk_cleanup_completion="NOT_ESTABLISHED",
    )
    write(slot, record)
    write(out / "ledger.json", record)
    child = None
    signal.signal(signal.SIGTERM, cancel_signal)
    try:
        seal = json.loads(Path(cfg["collection"]["seal"]).read_text())
        spec = validate_seal(
            seal,
            cfg["prospective"]["known_trajectory_ids"],
            "cfdb4033a88265f8d143a40a38a98ca2ccc09003",
        )
        write(out / "specification.json", spec)
        record["specification_access"] = "AUTHORIZED_COLLECTION_ONLY"
        env = dict(
            os.environ,
            PYTHONPATH=str(ROOT / "src"),
            NAVFM_UPSTREAM=cfg["upstream"],
            PYTHONNOUSERSITE="1",
            OMNICLIENT_HUB_MODE="disabled",
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
        )
        with (out / "process.log").open("w") as log:
            child = subprocess.Popen(
                [
                    cfg["python"],
                    str(ROOT / "scripts/prospective_capture_collection_v1.py"),
                    "--config",
                    str(config),
                    "--spec",
                    str(out / "specification.json"),
                    "--out",
                    str(out),
                ],
                env=env,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                record["child_exit_code"] = child.wait(
                    timeout=execution_remaining(
                        proposal, args.execute_approved_amendment, start, time.monotonic()
                    )
                )
            except subprocess.TimeoutExpired:
                record["timeout"] = True
            finally:
                if child.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    try:
                        child.wait(timeout=cleanup_remaining(start, time.monotonic()))
                    except subprocess.TimeoutExpired:
                        record["cleanup_timeout"] = True
                        record["child_exit_code"] = child.poll()
                        record["child_reaped"] = child.returncode is not None
                        raise ValueError("cleanup reached total process deadline") from None
                record["child_exit_code"] = child.returncode
                record["child_reaped"] = True
        capsule_path = out / "measurement_complete.json"
        capsule = json.loads(capsule_path.read_text()) if capsule_path.exists() else None
        verified = False
        if capsule:
            validate_capsule(capsule, out, spec)
            verified = True
        capture = (
            json.loads((out / "capture.json").read_text())
            if (out / "capture.json").exists()
            else {}
        )
        record.update(
            admission(
                capsule,
                record["child_exit_code"],
                record["timeout"],
                record["child_reaped"],
                verified,
                capture.get("status"),
            )
        )
        record["python_post_shutdown_report_written"] = capture.get("status") == "PASS"
        record["capture_terminal_status"] = capture.get("status", "MISSING")
        frozen(args.freeze, cfg)
        if record["status"] == "PASS":
            names = [r["id"] for layout in spec["layouts"] for r in layout["routes"]]
            dataset_admission = dict(
                status="PASS",
                scope="previously accessed kinematic pilot; not independently sealed benchmark",
                source_freeze=args.freeze,
                qualification_freeze="3954fb8daf1de1d2a991a7df20a1effe93bdcba1",
                splits={"train": [], "dev": names, "test": []},
                trajectories=[dict(id=n, processed_frames=36) for n in names],
                dataset_file_sha256={
                    str(f.relative_to(out / "data")): sha(f)
                    for f in (out / "data").rglob("*")
                    if f.is_file()
                },
            )
    except BaseException as exc:
        record.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        record["occupied_wall_s"] = time.monotonic() - start
        record["artifacts"] = {
            str(f.relative_to(out)): sha(f)
            for f in out.rglob("*")
            if f.is_file() and f.name != "ledger.json"
        }
        finalize_transaction(out, slot, record, dataset_admission, start)
    if record["status"] != "PASS":
        raise ValueError("fresh collection admission failed")


if __name__ == "__main__":
    main()
