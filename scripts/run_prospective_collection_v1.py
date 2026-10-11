"""One sealed fresh collection only; no later stage is launched."""

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
from prospective_collection_contracts_v1 import admission, validate_capsule, verify_qualification
from prospective_data_contracts_v1 import validate_seal


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    config = ROOT / "configs/eval/prospective_collection_v1.json"
    cfg = json.loads(config.read_text())
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
    record = dict(
        freeze=args.freeze,
        status="STARTED",
        measurement_complete=False,
        child_exit_code=None,
        timeout=False,
        child_reaped=False,
        sdk_cleanup_completion="NOT_ESTABLISHED",
    )
    write(slot, record)
    write(out / "ledger.json", record)
    start = time.monotonic()
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
                    timeout=max(0, 120 - (time.monotonic() - start) - 5)
                )
            except subprocess.TimeoutExpired:
                record["timeout"] = True
            finally:
                if child.poll() is None:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
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
            write(
                out / "admission.json",
                dict(
                    status="PASS",
                    scope="fresh kinematic offline pilot; not independently sealed benchmark",
                    source_freeze=args.freeze,
                    qualification_freeze="3954fb8daf1de1d2a991a7df20a1effe93bdcba1",
                    splits={"train": [], "dev": names, "test": []},
                    trajectories=[dict(id=n, processed_frames=36) for n in names],
                    dataset_file_sha256={
                        str(f.relative_to(out / "data")): sha(f)
                        for f in (out / "data").rglob("*")
                        if f.is_file()
                    },
                ),
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
        write(out / "ledger.json", record)
        write(slot, record)
    if record["status"] != "PASS":
        raise ValueError("fresh collection admission failed")


if __name__ == "__main__":
    main()
