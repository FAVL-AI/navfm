"""One explicitly authorized prospective model scorer; no capture/automatic second model."""

import argparse
import fcntl
import json
import os
import signal
import time
from pathlib import Path

from development_qualification_contracts_v1 import (
    ROOT,
    cancel_signal,
    frozen,
    run_bounded,
    sha,
)
from offline_evaluation_contracts_v1 import atomic_snapshot as write
from prospective_scoring_contracts_v2 import finalize_score, verify_prior_scores
from vint_scoring_contracts_v1 import verify_continuation as verify_bound_dataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--model", choices=["vint"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    config = ROOT / "configs/eval/prospective_vint_scoring_v1.json"
    cfg = json.loads(config.read_text())
    frozen(args.freeze, cfg)
    verify_bound_dataset(cfg)
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError("fresh external output required")
    registry = Path(cfg["evaluation_registry"])
    registry.mkdir(parents=True, exist_ok=True)
    lock = (registry / "lock").open("a")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    reservations = registry / "reservations.json"
    prior = json.loads(reservations.read_text()) if reservations.exists() else []
    if any(r["model"] == args.model for r in prior) or len(prior) >= 1:
        raise ValueError("declared model identity consumed; no retry")
    verify_prior_scores(prior, args.freeze)
    started = time.monotonic()
    prior.append(
        dict(model=args.model, freeze=args.freeze, reserved_s=1800, status="STARTED", out=str(out))
    )
    write(reservations, prior)
    signal.signal(signal.SIGTERM, cancel_signal)
    out.mkdir(parents=True)
    ledger = dict(freeze=args.freeze, model=args.model, status="STARTED", config_sha256=sha(config))
    write(out / "ledger.json", ledger)
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
            code = run_bounded(
                [
                    cfg["python"],
                    str(ROOT / "scripts/prospective_vint_score_v1.py"),
                    "--config",
                    str(config),
                    "--model",
                    args.model,
                    "--out",
                    str(out),
                ],
                env,
                ROOT,
                log,
                max(
                    0,
                    cfg["evaluation"]["wall_seconds_per_model"] - (time.monotonic() - started) - 5,
                ),
            )
        if code or json.loads((out / "report.json").read_text())["status"] != "PASS":
            raise ValueError("evaluation incomplete")
        verify_bound_dataset(cfg)
        frozen(args.freeze, cfg)
        ledger.update(status="PASS", child_reaped=True)
    except BaseException as exc:
        ledger.update(status="FAIL", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        try:
            frozen(args.freeze, cfg)
            verify_bound_dataset(cfg)
        except BaseException as exc:
            ledger.update(status="FAIL", postflight_error_type=type(exc).__name__)
        finalize_score(out, reservations, prior, ledger, started)


if __name__ == "__main__":
    main()
