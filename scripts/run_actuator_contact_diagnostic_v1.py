"""Two fresh arms, one attempt per arm; no motion qualification admission."""

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


def validate_completed(out, condition):
    report = json.loads((out / "attempt/imu_qualification.json").read_text())
    events = [
        json.loads(line) for line in (out / "attempt/lifecycle.jsonl").read_text().splitlines()
    ]
    samples = [e for e in events if e.get("phase") == "PASSIVE_PLANT_SAMPLE"]
    if (
        report.get("error")
        or len(samples) != 960
        or [e["tick"] for e in samples] != list(range(960))
    ):
        raise ValueError("complete diagnostic samples required")
    if any(e["contact_observation"] != "IMMEDIATE_QUERY_COMPLETED" for e in samples):
        raise ValueError("contact observation missing")
    if condition == "airborne" and any(e["contacts"] or e["clearance_m"] <= 0.1 for e in samples):
        raise ValueError("unloaded condition failed")
    if condition == "grounded" and not any(e["contacts"] for e in samples):
        raise ValueError("grounded contact observer not demonstrated")
    return {
        "ticks": len(samples),
        "scientific_status": report.get("status"),
        "scope": "diagnostic, not qualification",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads((ROOT / "configs/eval/actuator_contact_diagnostic_v1.json").read_text())
    frozen(args.freeze, cfg)
    for path, digest in cfg["diagnostic_source_sha256"].items():
        if sha(ROOT / path) != digest:
            raise ValueError("diagnostic source drift")
    if args.out.resolve().is_relative_to(ROOT):
        raise ValueError("external output required")
    args.out.mkdir(parents=True, exist_ok=False)
    records = [
        {
            "id": f"actuator-contact-v1-{arm}",
            "condition": arm,
            "status": "NOTRUN",
            "freeze": args.freeze,
        }
        for arm in ("grounded", "airborne")
    ]
    signal.signal(signal.SIGTERM, cancel_signal)
    try:
        for record in records:
            out = args.out / record["condition"]
            out.mkdir()
            record["status"] = "STARTED"
            write(args.out / "ledger.json", records)
            try:
                with (out / "process.log").open("w") as log:
                    rc = run_bounded(
                        [
                            cfg["python"],
                            str(ROOT / "scripts/prepare_actuator_contact_diagnostic_v1.py"),
                            "--out",
                            str(out / "attempt"),
                            "--robot",
                            cfg["robot"],
                        ],
                        dict(
                            os.environ,
                            PYTHONPATH=str(ROOT / "src"),
                            NAVFM_UPSTREAM=cfg["upstream"],
                            NAVFM_DIAGNOSTIC_CONDITION=record["condition"],
                            OMNICLIENT_HUB_MODE="disabled",
                            PYTHONNOUSERSITE="1",
                        ),
                        ROOT,
                        log,
                        120,
                    )
                frozen(args.freeze, cfg)
                if rc != 0:
                    raise ValueError(f"worker exit {rc}")
                record.update(
                    status="COMPLETED", integrity=validate_completed(out, record["condition"])
                )
            except BaseException as error:
                record.update(status="FAIL", exception_type=type(error).__name__)
                raise
            finally:
                record["artifacts_sha256"] = artifact_hashes(out)
                write(args.out / "ledger.json", records)
    finally:
        write(args.out / "ledger.json", records)


if __name__ == "__main__":
    main()
