"""Prepared one-attempt telemetry launcher; never launched by offline analysis."""

import argparse
import json
import os
import signal
from pathlib import Path

from controller_telemetry_v1 import artifact_hashes
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
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    cfg = json.loads((ROOT / "configs/eval/controller_telemetry_v1.json").read_text())
    frozen(a.freeze, cfg)
    for name, digest in cfg["telemetry_source_sha256"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("telemetry source drift")
    if a.out.resolve().is_relative_to(ROOT):
        raise ValueError("external output required")
    a.out.mkdir(parents=True, exist_ok=False)
    record = {
        "id": "controller-telemetry-v1-0000",
        "freeze": a.freeze,
        "status": "STARTED",
        "scope": "telemetry only",
    }
    write(a.out / "ledger.json", record)
    signal.signal(signal.SIGTERM, cancel_signal)
    try:
        with (a.out / "process.log").open("w") as log:
            rc = run_bounded(
                [
                    cfg["python"],
                    str(ROOT / "scripts/prepare_controller_telemetry_v1.py"),
                    "--out",
                    str(a.out / "attempt"),
                    "--robot",
                    cfg["robot"],
                ],
                dict(
                    os.environ,
                    PYTHONPATH=str(ROOT / "src"),
                    NAVFM_UPSTREAM=cfg["upstream"],
                    OMNICLIENT_HUB_MODE="disabled",
                    PYTHONNOUSERSITE="1",
                ),
                ROOT,
                log,
                120,
            )
        frozen(a.freeze, cfg)
        record.update(status="COMPLETED" if rc == 0 else "FAIL", returncode=rc)
        # Existing coverage FAIL is an observed result, not a reason for another attempt.
        report = a.out / "attempt/imu_qualification.json"
        record["report_sha256"] = sha(report) if report.exists() else None
    except BaseException as error:
        record.update(status="FAIL", exception_type=type(error).__name__)
        raise
    finally:
        record["artifacts_sha256"] = artifact_hashes(a.out)
        write(a.out / "ledger.json", record)


if __name__ == "__main__":
    main()
