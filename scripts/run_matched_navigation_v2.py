"""One explicitly selected launch from a finite development manifest; no retries."""

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

from analyse_matched_navigation_v2 import analyse
from development_qualification_contracts_v1 import (
    ROOT,
    cancel_signal,
    compare_initial,
    frozen,
    run_bounded,
    sha,
    write,
)
from matched_navigation_contracts_v2 import ORDER, admit, verify_recorded_artifacts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", required=True)
    p.add_argument("--launch", choices=ORDER, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    cfg = json.loads((ROOT / "configs/eval/matched_development_v2.json").read_text())
    frozen(a.freeze, cfg)
    if tuple(cfg["order"]) != ORDER or any(Path(x).exists() for x in cfg["cleanup_must_be_absent"]):
        raise ValueError("finite manifest or cleanup mismatch")
    out = a.out.resolve()
    if out.is_relative_to(ROOT):
        raise ValueError("external output required")
    out.mkdir(exist_ok=True)
    ledger = out / "ledger.json"
    records = json.loads(ledger.read_text()) if ledger.exists() else []
    admit(records, a.launch, a.freeze)
    for record in records:
        verify_recorded_artifacts(out / record["id"], record)
        previous = out / record["id"] / "result.json"
        if not previous.exists() or sha(previous) != record.get("report_sha256"):
            raise ValueError("prior result drift")
        result = json.loads(previous.read_text())
        if result.get("integrity") != "PASS":
            raise ValueError("prior integrity not established")
        if record["id"] != ORDER[0]:
            role = "vint-release" if "release" in record["id"] else "vint-adapted"
            if (
                result.get("role") != role
                or result.get("checkpoint_sha256") != cfg["models"][role]["sha256"]
            ):
                raise ValueError("prior role/checkpoint mismatch")
    dest = out / a.launch
    if dest.exists():
        raise ValueError("attempt path exists; no retry")
    dest.mkdir()
    coverage = a.launch == ORDER[0]
    role = None if coverage else ("vint-release" if "release" in a.launch else "vint-adapted")
    if coverage:
        cmd = [
            cfg["python"],
            str(ROOT / "scripts/qualify_imu_coverage_v2.py"),
            "--out",
            str(dest / "attempt"),
            "--robot",
            cfg["robot"],
        ]
        timeout = 120
    else:
        model = cfg["models"][role]
        cmd = [
            cfg["python"],
            str(ROOT / "scripts/collect_matched_navigation_v2.py"),
            "--out",
            str(dest / "episode"),
            "--robot",
            cfg["robot"],
            "--actuation",
            "wheel",
            "--checkpoint",
            model["checkpoint"],
            "--checkpoint-sha256",
            model["sha256"],
            "--qualification",
            cfg["qualification"],
            "--yaw-feedback",
            "--goal-root",
            cfg["goal_root"],
            "--route-id",
            cfg["route"],
            "--max-steps",
            "600",
            "--policy-period-frames",
            "6",
            "--policy-max-v",
            "0.1",
            "--stop-rule",
            "upstream_t3",
            "--topomap-root",
            cfg["topomap_root"],
            "--topomap-radius",
            "4",
            "--topomap-close-threshold",
            "3.0",
        ]
        timeout = 600
    record = dict(
        id=a.launch,
        freeze=a.freeze,
        integrity="STARTED",
        role=role,
        argv=cmd,
        wall_start=time.time(),
    )
    records.append(record)
    write(ledger, records)
    signal.signal(signal.SIGTERM, cancel_signal)
    start = time.monotonic()
    try:
        with (dest / "process.log").open("w") as log:
            rc = run_bounded(
                cmd,
                dict(
                    os.environ,
                    PYTHONPATH=str(ROOT / "src"),
                    NAVFM_UPSTREAM=cfg["upstream"],
                    OMNICLIENT_HUB_MODE="disabled",
                    PYTHONNOUSERSITE="1",
                ),
                ROOT,
                log,
                timeout,
            )
        frozen(a.freeze, cfg)
        if rc != 0:
            raise ValueError("worker failed; no retry")
        if coverage:
            path = dest / "attempt/imu_qualification.json"
            data = json.loads(path.read_text())
            if (
                data.get("status") != "PASS"
                or data.get("simulation_ticks") != 1200
                or len(data.get("plateaux", [])) != 16
            ):
                raise ValueError("fixed coverage failed; navigation not admitted")
            if [r["command"] for r in data["plateaux"]] != cfg["coverage_commands"]:
                raise ValueError("coverage command manifest mismatch")
            result = dict(
                integrity="PASS",
                coverage=data["plateaux"],
                checks=data["checks"],
                source_report_sha256=sha(path),
            )
        else:
            result, episode = analyse(dest / "episode", cfg, role)
            result["checkpoint_sha256"] = cfg["models"][role]["sha256"]
            result["source_manifest_sha256"] = sha(episode / "runtime_manifest.json")
            subprocess.run(
                [
                    cfg["verification_python"],
                    str(ROOT / "scripts/verify_rgb_feasibility.py"),
                    "--manifest",
                    str(episode / "runtime_manifest.json"),
                ],
                check=True,
                timeout=30,
                stdout=subprocess.DEVNULL,
            )
            if a.launch in (ORDER[2], ORDER[4]):
                import numpy as np
                from PIL import Image

                first_id = ORDER[1] if a.launch == ORDER[2] else ORDER[3]
                previous = json.loads((out / first_id / "result.json").read_text())
                if (
                    previous["boundary"]["state"] != result["boundary"]["state"]
                    or previous["boundary"]["goal_rgb_sha256"]
                    != result["boundary"]["goal_rgb_sha256"]
                ):
                    raise ValueError("matched initial state/goal mismatch")
                aa = np.asarray(
                    Image.open(out / first_id / "episode/first_policy_input.png").convert("L"),
                    float,
                )
                bb = np.asarray(
                    Image.open(dest / "episode/first_policy_input.png").convert("L"), float
                )
                match = compare_initial(
                    previous["boundary"], result["boundary"], float(np.abs(aa - bb).mean())
                )
                result["pair_initialization"] = match
                write(dest / "result.json", result)
                if match["status"] != "PASS":
                    raise ValueError("pair initialization integrity failed")
        write(dest / "result.json", result)
        record.update(integrity="PASS", report_sha256=sha(dest / "result.json"))
    except BaseException as error:
        record.update(integrity="FAIL", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        record["wall_s"] = time.monotonic() - start
        record["artifacts"] = {
            str(f.relative_to(dest)): sha(f) for f in dest.rglob("*") if f.is_file()
        }
        write(ledger, records)
    print("Launch complete. STOP; no automatic continuation.")


if __name__ == "__main__":
    main()
