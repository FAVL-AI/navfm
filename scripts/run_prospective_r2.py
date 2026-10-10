"""Launch only the reviewed, frozen development R2 versus B1x experiment."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

from analyse_prospective_r2 import CONFIG, REPO, analyse, frozen_config, git, sha

E = Path("/home/favl/navfm-runtime-evidence")
ROBOT = Path("/home/favl/projects/navfm/assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd")
PYTHON = "/home/favl/miniforge3/envs/isaac/bin/python"
CHECKPOINT = (
    "/home/favl/navfm-training-evidence/option1-arrival-n31-e20-seed0-20261009-01/epoch_020.pth"
)


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def append(path: Path, record: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze-commit", required=True)
    p.add_argument("--stage", choices=["pilot", "remaining", "retry"], required=True)
    p.add_argument("--trial", help="retry only: declared trial")
    p.add_argument("--variant", help="retry only: declared variant")
    a = p.parse_args()
    commit = git("rev-parse", a.freeze_commit)
    if git("status", "--porcelain") or git("rev-parse", "HEAD") != commit:
        p.error("Launch requires a clean worktree at the exact freeze commit")
    cfg = frozen_config(commit)
    ledger = E / "prospective-r2-v1-launch-ledger.jsonl"
    cells = []
    if a.stage == "retry":
        if a.trial not in cfg["trials"] or a.variant not in cfg["trials"][a.trial]["variants"]:
            p.error("Retry requires a declared trial and arm")
        cells = [(a.trial, a.variant)]
    else:
        if a.trial or a.variant:
            p.error("trial/variant apply only to retry")
        if a.stage == "remaining":
            pilot = analyse(commit, E, "pilot")
            if not pilot["continue_fixed_remaining"]:
                p.error("Pilot integrity has not passed; expansion refused")
            report = E / "prospective-r2-v1-pilot-gate-20261010-01.json"
            if report.exists():
                p.error("Pilot gate already recorded")
            report.write_text(json.dumps(pilot, indent=2) + "\n")
            append(
                ledger,
                dict(
                    event="pilot_gate",
                    gate_utc=utc(),
                    report_path=str(report),
                    report_sha256=sha(report),
                ),
            )
        trials = list(cfg["trials"])[:1] if a.stage == "pilot" else list(cfg["trials"])[1:]
        cells = [(trial, v) for trial in trials for v in cfg["trials"][trial]["variants"]]
    for trial, variant in cells:
        if git("status", "--porcelain") or git("rev-parse", "HEAD") != commit:
            p.error("Worktree drift during collection")
        frozen_config(commit)
        t = cfg["trials"][trial]
        tag = "20261010-02" if a.stage == "retry" else "20261010-01"
        out = E / f"v2-{trial}-{variant}-{tag}"
        if out.exists() or out.with_suffix(".log").exists():
            p.error(f"Output already exists: {out}")
        routes = t["routes"]
        if a.stage == "retry":
            first = E / f"v2-{trial}-{variant}-20261010-01"
            if not ledger.exists():
                p.error("No initial launch ledger")
            launch = [json.loads(s) for s in ledger.read_text().splitlines()]
            if (
                len([x for x in launch if x["event"] == "launch" and x["collection"] == first.name])
                != 1
            ):
                p.error("No unique initial launch")
            summary = (
                json.loads((first / "collection.json").read_text())
                if (first / "collection.json").exists()
                else {}
            )
            seen = {x["id"]: x["status"] for x in summary.get("episodes", [])}
            routes = [r for r in routes if seen.get(r) != "PASS"]
            if not routes:
                p.error("No infrastructure-failed routes to retry")
        args = [
            PYTHON,
            "scripts/collect_option1.py",
            "--out",
            str(out),
            "--policy-period-frames",
            "6",
            "--topomap-root",
            cfg["conditions"]["true_chain"]["root"],
            "--max-steps",
            str(cfg["runtime"]["budget_frames"]),
            "--start-lost",
            "--start-arc-fraction",
            str(t["perturbation"][0]),
            "--start-lateral-m",
            str(t["perturbation"][1]),
            "--start-yaw-deg",
            str(t["perturbation"][2]),
            "--robot",
            str(ROBOT),
            "--actuation",
            "wheel",
            "--checkpoint",
            CHECKPOINT,
            "--checkpoint-sha256",
            cfg["checkpoint"]["sha256"],
            "--qualification",
            cfg["runtime"]["qualification"],
            "--yaw-feedback",
            "--goal-root",
            cfg["runtime"]["goal_root"],
            "--comparison-config",
            CONFIG,
            "--variant",
            variant,
            "--trial",
            trial,
        ]
        for route in routes:
            args += ["--route-id", route]
        append(
            ledger,
            {
                "event": "launch",
                "collection": out.name,
                "head": commit,
                "worktree_status": "",
                "launch_utc": utc(),
                "trial": trial,
                "variant": variant,
                "routes": routes,
                "config_sha256": sha(REPO / CONFIG),
                "robot_usd_sha256": sha(ROBOT),
                "args": args,
            },
        )
        env = dict(
            os.environ,
            OMNICLIENT_HUB_MODE="disabled",
            NAVFM_UPSTREAM=str(E / "option1-admitted-20261007-02/upstream"),
        )
        with out.with_suffix(".log").open("x") as log:
            try:
                rc = subprocess.run(
                    args, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=5400
                ).returncode
            except subprocess.TimeoutExpired:
                rc = 124
        append(
            ledger,
            {
                "event": "exit",
                "collection": out.name,
                "exit_utc": utc(),
                "exit": rc,
                "frozen_routes_sha256": sha(out / "frozen_routes.json")
                if (out / "frozen_routes.json").exists()
                else None,
                "robot_usd_sha256_after": sha(ROBOT),
            },
        )
        print(f"{trial} {variant} exit {rc}", flush=True)
        if rc != 0:
            break


if __name__ == "__main__":
    main()
