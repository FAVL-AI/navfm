"""One known-fixture timing diagnostic only; never admits a dataset."""

import argparse
import fcntl
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from development_qualification_contracts_v1 import ROOT, cancel_signal, frozen, sha
from offline_evaluation_contracts_v1 import atomic_snapshot as write
from prospective_collection_contracts_v1 import admission, validate_capsule
from prospective_data_contracts_v1 import specification
from prospective_timing_contracts_v1 import Events, wait_child


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    config = ROOT / "configs/eval/prospective_timing_v1.json"
    cfg = json.loads(config.read_text())
    frozen(args.freeze, cfg)
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError("fresh external output required")
    registry = Path(cfg["timing"]["registry"])
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
    events = Events(out / "parent_events.jsonl", "parent_monotonic_v1")
    events.emit("PARENT_START", execution_deadline_ns=int((start + 115) * 1e9), process_cap_s=120)
    child = None
    signal.signal(signal.SIGTERM, cancel_signal)
    try:
        spec = specification([0, 1])
        for li, layout in enumerate(spec["layouts"]):
            for ri, route in enumerate(layout["routes"]):
                route["id"] = f"timing_fixture_layout{li}_route{ri}"
        write(out / "specification.json", spec)
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
            events.emit("LAUNCH_REQUEST")
            child = subprocess.Popen(
                [
                    cfg["python"],
                    str(ROOT / "scripts/prospective_capture_timing_v1.py"),
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
            wait_child(child, record, start, events)
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
    except BaseException as exc:
        record.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        try:
            events.emit("PARENT_FINALIZE", event_logging_ns=events.logging_ns)
        except OSError:
            record.update(status="FAIL", finalization_logging_error=True)
        record["occupied_wall_s"] = time.monotonic() - start
        record["artifacts"] = {
            str(f.relative_to(out)): sha(f)
            for f in out.rglob("*")
            if f.is_file() and f.name != "ledger.json"
        }
        write(out / "ledger.json", record)
        write(slot, record)
    if record["status"] != "PASS":
        raise ValueError("timing diagnostic process incomplete")


if __name__ == "__main__":
    main()
