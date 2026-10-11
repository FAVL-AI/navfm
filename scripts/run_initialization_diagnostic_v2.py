"""Run the separately frozen v2 bootstrap eligibility and technical contrasts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

from initialization_diagnostic import REPO, sha
from initialization_diagnostic_v2 import bootstrap_ok, eligibility_ok, frozen
from run_initialization_diagnostic import PYTHON
from run_initialization_diagnostic import analyse as analyse_v1


def analyse(root: Path, cfg: dict) -> dict:
    for trace in root.glob("*-reference/trace.json"):
        value = json.loads(trace.read_text())
        if value["status"] == "PASS":
            bootstrap_ok(value["bootstrap"])
            eligibility_ok(value["eligibility"], value["startup_dlss_mode"])
            if value.get("eligibility_passed") is not True:
                raise ValueError("Missing eligibility gate")
    for trace in root.glob("*-replay/trace.json"):
        value = json.loads(trace.read_text())
        if value["status"] == "PASS":
            bootstrap_ok(value["bootstrap"])
            eligibility_ok(value["eligibility"], value["startup_dlss_mode"])
            if value.get("eligibility_passed") is not True:
                raise ValueError("Missing eligibility gate")
    return analyse_v1(root, cfg)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze-commit", required=True)
    p.add_argument("--stage", choices=["probes", "analyse"], required=True)
    a = p.parse_args()
    cfg = frozen(a.freeze_commit, launch=a.stage != "analyse")
    root = Path(cfg["evidence_root"]) / cfg["probe_prefix"]
    if a.stage == "analyse":
        out = root / "analysis.json"
        if out.exists():
            p.error("analysis output exists")
        out.write_text(json.dumps(analyse(root, cfg), indent=2) + "\n")
        return
    root.mkdir(exist_ok=True)
    ledger = root / "ledger.jsonl"

    def append(record):
        record["utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        with ledger.open("a") as f:
            f.write(json.dumps(record) + "\n")

    def launch(args, log, label):
        frozen(a.freeze_commit, launch=True)
        if log.exists():
            p.error("no retries or overwrite")
        append(dict(event="launch", label=label, command=args, freeze_commit=a.freeze_commit))
        with log.open("w") as f:
            try:
                result = subprocess.run(
                    args,
                    cwd=REPO,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    timeout=cfg["watchdog_s"],
                    check=False,
                )
                code = result.returncode
                timeout = False
            except subprocess.TimeoutExpired:
                code = None
                timeout = True
        drift = None
        try:
            frozen(a.freeze_commit, launch=True)
        except Exception as exc:
            drift = str(exc)
        append(
            dict(
                event="exit",
                label=label,
                returncode=code,
                timeout=timeout,
                log_sha256=sha(log),
                postflight_drift=drift,
            )
        )
        return code == 0 and not timeout and drift is None

    if any(root.glob("*-reference")) or any(root.glob("*-replay")):
        p.error("probes already attempted; no retries")
    for repetition in cfg["repetitions"]:
        for case in cfg["cases"]:
            reference = root / f"{case}-r{repetition}-reference"
            for role in ["reference", "replay"]:
                out = root / f"{case}-r{repetition}-{role}"
                args = [
                    PYTHON,
                    str(REPO / "scripts/collect_initialization_diagnostic_v2.py"),
                    "--freeze-commit",
                    a.freeze_commit,
                    "--case",
                    case,
                    "--role",
                    role,
                    "--out",
                    str(out),
                ]
                if role == "replay":
                    args += ["--reference", str(reference)]
                ok = launch(args, out.with_suffix(".log"), out.name)
                t = (
                    json.loads((out / "trace.json").read_text())
                    if (out / "trace.json").exists()
                    else {}
                )
                if not ok or t.get("status") != "PASS" or t.get("eligibility_passed") is not True:
                    append(dict(event="halt", reason="mechanical_failure", label=out.name))
                    return
        append(
            dict(
                event="mechanical_stage_gate", repetition=repetition, continue_next=repetition == 1
            )
        )
    (root / "analysis.json").write_text(json.dumps(analyse(root, cfg), indent=2) + "\n")


if __name__ == "__main__":
    main()
