"""One 150-second synthetic component qualification; never pair scoring."""

import argparse
import fcntl
import json
import os
import signal
import time
from pathlib import Path

from development_qualification_contracts_v1 import ROOT, cancel_signal, frozen
from native_provenance_diagnostic_v1 import run_observed, validate_rejection_path
from offline_evaluation_contracts_v1 import atomic_snapshot
from vint_interface_v1 import finalize_component


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cfgpath = ROOT / "configs/eval/vint_provenance_diagnostic_v1.json"
    cfg = json.loads(cfgpath.read_text())
    frozen(args.freeze, cfg)
    out = args.out.resolve()
    validate_rejection_path(cfg, out)
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError("fresh external component output required")
    registry = Path(cfg["qualification_registry"])
    registry.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (registry / "lock").open("a")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    slot = registry / "reservation.json"
    if slot.exists():
        raise ValueError("component attempt consumed; no retry")
    started = time.monotonic()
    prior = [
        dict(
            model="vint-interface",
            freeze=args.freeze,
            status="STARTED",
            reserved_s=150,
            out=str(out),
        )
    ]
    atomic_snapshot(slot, prior)
    out.mkdir(mode=0o700)
    ledger = dict(
        status="STARTED",
        model="vint-interface",
        freeze=args.freeze,
        scope="SYNTHETIC_COMPONENT_DIAGNOSTIC_ONLY",
        child_exit_code=None,
        timeout=None,
        child_reaped=None,
    )
    atomic_snapshot(out / "ledger.json", ledger)
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
        with (out / "process.log").open("w") as log:
            code = run_observed(
                [
                    cfg["python"],
                    str(ROOT / "scripts/qualify_vint_provenance_diagnostic_v1.py"),
                    "--config",
                    str(cfgpath),
                    "--out",
                    str(out),
                ],
                env,
                ROOT,
                log,
                max(0, 145 - (time.monotonic() - started)),
                ledger,
            )
        report = json.loads((out / "report.json").read_text())
        if (
            code
            or report["status"] != "PASS"
            or len(report["roles"]) != 4
            or any(row["status"] != "PASS" for row in report["roles"])
        ):
            raise ValueError("component qualification incomplete")
        frozen(args.freeze, cfg)
        ledger.update(status="PASS", child_reaped=True, child_exit_code=code)
    except BaseException as exc:
        ledger.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        try:
            frozen(args.freeze, cfg)
        except BaseException as exc:
            ledger.update(status="FAIL", postflight_error_type=type(exc).__name__)
        finalize_component(out, slot, prior, ledger, started)
    if ledger["status"] != "PASS":
        raise ValueError("component finalization failed")


if __name__ == "__main__":
    main()
