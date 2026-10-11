"""Run one declared native smoke; independent results require shared integrity and reaping."""

from __future__ import annotations

import argparse
import json
import os
import signal
from pathlib import Path

from development_qualification_contracts_v1 import (
    ROOT,
    cancel_signal,
    frozen,
    run_bounded,
    sha,
    write,
)
from native_dependency_closure_v2 import contract_digest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", required=True)
    p.add_argument("--model", choices=["nomad"], required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    config = ROOT / "configs/train/native_adaptation_smoke_v3.json"
    cfg = json.loads(config.read_text())
    frozen(a.freeze, cfg)
    dependencies = json.loads(Path(cfg["installed_dependency_manifest"]).read_text())
    for item in dependencies["files"]:
        if sha(Path(item["path"])) != item["sha256"]:
            raise ValueError("installed dependency drift")
    proof = json.loads(Path(cfg["cpu_preflight_report"]).read_text())
    if (
        proof["status"] != "PASS"
        or proof["python"] != cfg["python"]
        or proof["models"] != ["nomad"]
        or proof["configuration_digest"] != contract_digest(cfg)
    ):
        raise ValueError("complete native CPU preflight required")
    out = a.out.resolve()
    if out.is_relative_to(ROOT):
        raise ValueError("external output required")
    if out.exists():
        raise ValueError("fresh v3 output required; no retry")
    out.mkdir(parents=True)
    records = []
    attempt = out / a.model
    if attempt.exists():
        raise ValueError("attempt already exists; no retry")
    attempt.mkdir()
    record = {
        "model": a.model,
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
                    str(ROOT / "scripts/native_adaptation_worker_v3.py"),
                    "--config",
                    str(config),
                    "--model",
                    a.model,
                    "--out",
                    str(attempt),
                ],
                env,
                ROOT,
                log,
                150,
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
            or report["optimizer_updates"] != 6
            or report["completed_transactions"] != 6
            or report["final_ema_counter"] != 6
            or any(
                t["phase"] != "COMPLETE"
                or not all(t[k] for k in ("optimizer_applied", "scheduler_applied", "ema_applied"))
                for t in report["transactions"]
            )
        ):
            raise ValueError("native training smoke failed")
        record.update(status="PASS", optimizer_updates=6, device_type=report["device_type"])
    except BaseException as exc:
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
                shared_integrity="FAIL",
                postflight_error_type=type(exc).__name__,
                postflight_error=str(exc),
            )
        record["artifacts"] = {f.name: sha(f) for f in attempt.iterdir() if f.is_file()}
        write(out / "ledger.json", records)


if __name__ == "__main__":
    main()
