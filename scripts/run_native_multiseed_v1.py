"""Run one declared native smoke; independent results require shared integrity and reaping."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
from pathlib import Path

from development_qualification_contracts_v1 import (
    ROOT,
    cancel_signal,
    frozen,
    run_bounded,
    sha,
    write,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", required=True)
    p.add_argument("--model", choices=["gnm", "nomad"], required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, choices=[0, 11, 22], required=True)
    a = p.parse_args()
    config = ROOT / "configs/train/native_multiseed_adaptation_v1.json"
    cfg = json.loads(config.read_text())
    frozen(a.freeze, cfg)
    dependencies = json.loads(Path(cfg["installed_dependency_manifest"]).read_text())
    for item in dependencies["files"]:
        if sha(Path(item["path"])) != item["sha256"]:
            raise ValueError("installed dependency drift")
    from native_multiseed_contracts_v1 import reserve_run, validate_schedule

    validate_schedule(cfg)
    out = a.out.resolve()
    if out.is_relative_to(ROOT):
        raise ValueError("external output required")
    if out.exists():
        raise ValueError("fresh v3 output required; no retry")
    import fcntl
    import time

    registry = Path(cfg["registry"])
    registry.mkdir(parents=True, exist_ok=True)
    lock = (registry / "lock").open("a")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    slots = registry / "reservations.json"
    reserved = json.loads(slots.read_text()) if slots.exists() else []
    reserved = reserve_run(cfg, reserved, a.model, a.seed, a.freeze)
    write(slots, reserved)
    started = time.monotonic()
    out.mkdir(parents=True)
    records = []
    attempt = out / a.model
    if attempt.exists():
        raise ValueError("attempt already exists; no retry")
    attempt.mkdir()
    record = {
        "model": a.model,
        "seed": a.seed,
        "freeze": a.freeze,
        "config_sha256": sha(config),
        "status": "STARTED",
        "child_reaped": False,
        "shared_integrity": "NOT_ESTABLISHED",
    }
    records.append(record)
    write(out / "ledger.json", records)
    signal.signal(signal.SIGTERM, cancel_signal)
    try:
        env = dict(
            os.environ,
            PYTHONPATH=str(ROOT / "src"),
            NAVFM_UPSTREAM=cfg["upstream"],
            PYTHONNOUSERSITE="1",
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            WANDB_MODE="disabled",
        )
        with (attempt / "process.log").open("w") as log:
            rc = run_bounded(
                [
                    cfg["python"],
                    str(ROOT / "scripts/native_multiseed_worker_v1.py"),
                    "--config",
                    str(config),
                    "--model",
                    a.model,
                    "--seed",
                    str(a.seed),
                    "--out",
                    str(attempt),
                ],
                env,
                ROOT,
                log,
                max(0.0, cfg["caps"]["wall_seconds"] - (time.monotonic() - started) - 5),
            )
        record["child_reaped"] = True
        frozen(a.freeze, cfg)
        for item in dependencies["files"]:
            if sha(Path(item["path"])) != item["sha256"]:
                raise ValueError("installed dependency postflight drift")
        report = json.loads((attempt / "report.json").read_text())
        prov = json.loads((attempt / "provenance.json").read_text())
        record["shared_integrity"] = prov.get("shared_integrity", "FAIL")
        if (
            rc != 0
            or report["status"] != "PASS"
            or prov["status"] != "PASS"
            or report["optimizer_updates"] != 4720
            or report["completed_transactions"] != 4720
            or (a.model == "nomad" and report["final_ema_counter"] != 4720)
            or any(
                t["phase"] != "COMPLETE"
                or not all(t[k] for k in ("optimizer_applied", "scheduler_applied"))
                or (a.model == "nomad" and not t["ema_applied"])
                for t in report["transactions"]
            )
        ):
            raise ValueError("native adaptation run incomplete or failed")
        record.update(status="PASS", optimizer_updates=4720, device_type=report["device_type"])
    except BaseException as exc:
        if isinstance(exc, (subprocess.TimeoutExpired, KeyboardInterrupt, InterruptedError)):
            record["child_reaped"] = True  # reviewed run_bounded finally kills/reaps the child
        record["incomplete_endpoint"] = isinstance(exc, subprocess.TimeoutExpired)
        record.update(status="FAIL", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        try:
            frozen(a.freeze, cfg)
            for item in dependencies["files"]:
                if sha(Path(item["path"])) != item["sha256"]:
                    raise ValueError("installed dependency postflight drift")
        except BaseException as exc:
            record.update(
                status="FAIL",
                shared_integrity="FAIL",
                postflight_error_type=type(exc).__name__,
                postflight_error=str(exc),
            )
        record["artifacts"] = {
            str(f.relative_to(out)): sha(f) for f in attempt.rglob("*") if f.is_file()
        }
        record["reserved_wall_seconds"] = 3600
        record["actual_occupied_wall_seconds"] = time.monotonic() - started
        reserved[-1].update(
            status=record["status"],
            shared_integrity=record["shared_integrity"],
            actual_occupied_wall_seconds=record["actual_occupied_wall_seconds"],
        )
        write(slots, reserved)
        write(out / "ledger.json", records)


if __name__ == "__main__":
    main()
