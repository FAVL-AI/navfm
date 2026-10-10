"""Execute only the frozen first R2 reference/replay validation pair; always stop."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

from initialization_diagnostic import REPO, sha
from replay_recovery_contracts import compare_pair, frozen, trace_ok
from run_initialization_diagnostic import PYTHON


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-commit", required=True)
    a = parser.parse_args()
    cfg = frozen(a.freeze_commit, launch=True)
    root = Path(cfg["evidence_root"]) / cfg["probe_prefix"]
    if root.exists():
        parser.error("Attempt directory already exists; no retries")
    root.mkdir()
    ledger = root / "ledger.jsonl"

    def append(value):
        value["utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        with ledger.open("a") as f:
            f.write(json.dumps(value) + "\n")

    traces = []
    report = dict(decision="HALTED", efficacy_claim=False, further_launches_authorized=False)
    for index, label in enumerate(cfg["authorized_processes"]):
        role = ["reference", "replay"][index]
        out = root / label
        args = [
            PYTHON,
            str(REPO / "scripts/collect_replay_recovery_validation.py"),
            "--freeze-commit",
            a.freeze_commit,
            "--case",
            cfg["first_case"],
            "--role",
            role,
            "--out",
            str(out),
        ]
        if role == "replay":
            args += ["--reference", str(root / cfg["authorized_processes"][0])]
        frozen(a.freeze_commit, launch=True)
        append(dict(event="launch", label=label, command=args, freeze_commit=a.freeze_commit))
        log = out.with_suffix(".log")
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
                code, timeout = result.returncode, False
            except subprocess.TimeoutExpired:
                code, timeout = None, True
        failure = None
        try:
            frozen(a.freeze_commit, launch=True)
            if code != 0 or timeout:
                raise ValueError("Process failure/timeout")
            t = json.loads((out / "trace.json").read_text())
            trace_ok(t, cfg, out)
            traces.append(t)
        except Exception as exc:
            failure = str(exc)
        append(
            dict(
                event="exit",
                label=label,
                returncode=code,
                timeout=timeout,
                log_sha256=sha(log),
                failure=failure,
            )
        )
        if failure:
            report.update(failure=failure, failed_label=label)
            append(dict(event="halt", label=label, reason=failure))
            break
    if len(traces) == 2:
        report = compare_pair(traces[0], traces[1], root, cfg)
        append(dict(event="first_pair_gate", passed=report["passed"], continue_next=False))
    report["attempted_processes"] = len(
        [
            json.loads(x)
            for x in ledger.read_text().splitlines()
            if json.loads(x)["event"] == "launch"
        ]
    )
    report["freeze_commit"] = a.freeze_commit
    (root / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
