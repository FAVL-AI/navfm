"""One150-second NoMaD process; no retry or other model launch."""

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
    cfg = json.loads((ROOT / "configs/eval/nomad_compatibility_v3.json").read_text())
    frozen(a.freeze, cfg)
    dependencies = json.loads(Path(cfg["installed_dependency_manifest"]).read_text())
    for item in dependencies["files"]:
        if sha(Path(item["path"])) != item["sha256"]:
            raise ValueError("installed dependency drift")
    if any(Path(x).exists() for x in cfg["cleanup_must_be_absent"]):
        raise ValueError("CI-runner cleanup required")
    out = a.out.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError("new external output required")
    out.mkdir(parents=True)
    signal.signal(signal.SIGTERM, cancel_signal)
    record = {"id": "nomad-compat-v3-0000", "freeze": a.freeze, "status": "STARTED"}
    write(out / "ledger.json", record)
    try:
        env = dict(
            os.environ,
            PYTHONPATH=str(ROOT / "src"),
            NAVFM_UPSTREAM=cfg["upstream"],
            PYTHONNOUSERSITE="1",
        )
        with (out / "process.log").open("w") as log:
            rc = run_bounded(
                [
                    cfg["python"],
                    str(ROOT / "scripts/development_nomad_compatibility_v3.py"),
                    "--config",
                    str(ROOT / "configs/eval/nomad_compatibility_v3.json"),
                    "--role",
                    "nomad-release",
                    "--out",
                    str(out / "nomad.json"),
                ],
                env,
                ROOT,
                log,
                150,
            )
        frozen(a.freeze, cfg)
        for item in dependencies["files"]:
            if sha(Path(item["path"])) != item["sha256"]:
                raise ValueError("installed dependency postflight drift")
        provenance = json.loads((out / "import-resolution.json").read_text())
        if provenance["status"] != "PASS":
            raise ValueError("dependency provenance failed")
        report = json.loads((out / "nomad.json").read_text())
        if rc != 0 or report["status"] != "PASS" or report.get("device_type") != "cuda":
            raise ValueError("native NoMaD check failed")
        record.update(status="PASS", report_sha256=sha(out / "nomad.json"))
    except BaseException as error:
        record.update(status="FAIL", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        provenance_path = out / "import-resolution.json"
        if provenance_path.exists():
            record["provenance_sha256"] = sha(provenance_path)
        write(out / "ledger.json", record)


if __name__ == "__main__":
    main()
