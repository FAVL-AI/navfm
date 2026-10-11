"""One bounded controller probe; halt and preserve evidence on any failure."""

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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    cfg = json.loads((ROOT / "configs/eval/imu_controller_qualification_v1.json").read_text())
    frozen(a.freeze, cfg)
    if any(Path(path).exists() for path in cfg["cleanup_must_be_absent"]):
        raise ValueError("isolated CI runner cleanup required")
    out = a.out.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError("new external evidence required")
    out.mkdir(parents=True)
    signal.signal(signal.SIGTERM, cancel_signal)
    ledger = out / "ledger.json"
    write(ledger, {"id": "imu-controller-v1-0000", "freeze": a.freeze, "status": "STARTED"})
    try:
        with (out / "process.log").open("w") as log:
            rc = run_bounded(
                [
                    cfg["python"],
                    str(ROOT / "scripts/qualify_imu_controller_v1.py"),
                    "--out",
                    str(out / "attempt"),
                    "--robot",
                    cfg["robot"],
                ],
                dict(os.environ, PYTHONPATH=str(ROOT / "src")),
                ROOT,
                log,
                cfg["wall_seconds"],
            )
        frozen(a.freeze, cfg)
        report = out / "attempt/imu_qualification.json"
        data = json.loads(report.read_text())
        if rc != 0 or data["status"] != "PASS":
            raise ValueError("controller probe failed; no continuation")
        write(
            ledger,
            {
                "id": "imu-controller-v1-0000",
                "freeze": a.freeze,
                "status": "PASS",
                "report_sha256": sha(report),
            },
        )
    except BaseException as error:
        write(
            ledger,
            {
                "id": "imu-controller-v1-0000",
                "freeze": a.freeze,
                "status": "FAIL",
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise


if __name__ == "__main__":
    main()
