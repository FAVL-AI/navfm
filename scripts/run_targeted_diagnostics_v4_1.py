"""Two separately admitted diagnostic stages; never retries or tracks commands."""

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
    p.add_argument("--stage", choices=["imports", "initialization"], required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    cfg = json.loads((ROOT / "configs/eval/targeted_diagnostics_v4_1.json").read_text())
    frozen(a.freeze, cfg)
    if any(Path(x).exists() for x in cfg["cleanup_must_be_absent"]):
        raise ValueError("CI cleanup required")
    out = a.out.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError("new external evidence required")
    out.mkdir(parents=True)
    signal.signal(signal.SIGTERM, cancel_signal)
    record = {"freeze": a.freeze, "stage": a.stage, "status": "STARTED"}
    write(out / "ledger.json", record)
    try:
        if a.stage == "imports":
            cmd = [
                cfg["python"],
                str(ROOT / "scripts/dependency_import_audit_v4.py"),
                "--manifest",
                cfg["manifest"],
                "--out",
                str(out / "audit.json"),
            ]
            env = dict(
                os.environ,
                PYTHONPATH=str(ROOT / "src"),
                PYTHONNOUSERSITE="1",
                CUDA_VISIBLE_DEVICES="",
            )
            limit = 60
        else:
            cmd = [
                cfg["python"],
                str(ROOT / "scripts/diagnose_imu_initialization_v4.py"),
                "--out",
                str(out / "attempt"),
                "--robot",
                cfg["robot"],
            ]
            env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), OMNICLIENT_HUB_MODE="disabled")
            limit = 120
        with (out / "process.log").open("w") as log:
            rc = run_bounded(cmd, env, ROOT, log, limit)
        frozen(a.freeze, cfg)
        record.update(status="COMPLETED" if rc == 0 else "FAIL", exit_code=rc)
    except BaseException as error:
        record.update(status="FAIL", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        record["artifacts"] = {
            str(f.relative_to(out)): sha(f)
            for f in out.rglob("*")
            if f.is_file() and f.name != "ledger.json"
        }
        write(out / "ledger.json", record)


if __name__ == "__main__":
    main()
