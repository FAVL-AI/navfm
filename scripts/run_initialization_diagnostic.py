"""Execute fixed bounded stages and report all frozen state/history guards."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

from initialization_diagnostic import REPO, compare, frozen, sha

PYTHON = "/home/favl/miniforge3/envs/isaac/bin/python"


def analyse(root: Path, cfg: dict) -> dict:
    comparisons = []
    chronological = []
    traces = {}
    for repetition in cfg["repetitions"]:
        for case in cfg["cases"]:
            for role in ["reference", "replay"]:
                path = root / f"{case}-r{repetition}-{role}" / "trace.json"
                if not path.exists():
                    continue
                t = json.loads(path.read_text())
                traces[(case, repetition, role)] = t
            ref = traces.get((case, repetition, "reference"))
            replay = traces.get((case, repetition, "replay"))
            if not ref or ref["status"] != "PASS":
                continue
            if replay and replay["status"] == "PASS":
                reference_frames = [
                    ref["initial"],
                    *[x for x in ref["captures"] if x["image"].startswith("script_")],
                ]
                replay_frames = [
                    replay["initial"],
                    *[x for x in replay["captures"] if x["image"].startswith("script_")],
                ]
                if len(reference_frames) != 37 or len(replay_frames) != 37:
                    raise ValueError("Missing chronological captures")
                for index, (av, bv) in enumerate(zip(reference_frames, replay_frames, strict=True)):
                    states = []
                    for role, value in [("reference", av), ("replay", bv)]:
                        state = json.loads(json.dumps(value))
                        state["image"] = f"{case}-r{repetition}-{role}/" + state["image"]
                        state["history"] = [json.loads(json.dumps(state)) for _ in range(6)]
                        states.append(state)
                    result = compare(states[0], states[1], root, cfg["bounds"])
                    chronological.append(
                        dict(case=case, repetition=repetition, physical_step=index, **result)
                    )
            for method in ["direct_root", "direct_full", "command_replay"]:
                other = replay if method == "command_replay" else ref
                if not other or other["status"] != "PASS":
                    continue

                # Compare paths from separate process directories using root-relative names.
                def relative(state, role, case=case, repetition=repetition):
                    s = json.loads(json.dumps(state))
                    prefix = f"{case}-r{repetition}-{role}/"
                    s["image"] = prefix + s["image"]
                    for h in s["history"]:
                        h["image"] = prefix + h["image"]
                    return s

                result = compare(
                    relative(ref["methods"]["continuous"], "reference"),
                    relative(
                        other["methods"][method],
                        "replay" if method == "command_replay" else "reference",
                    ),
                    root,
                    cfg["bounds"],
                )
                comparisons.append(
                    dict(
                        case=case,
                        repetition=repetition,
                        comparison="within",
                        method=method,
                        **result,
                    )
                )
    for case in cfg["cases"]:
        for method in cfg["methods"]:
            role = "replay" if method == "command_replay" else "reference"
            a, b = traces.get((case, 1, role)), traces.get((case, 2, role))
            if not a or not b or a["status"] != "PASS" or b["status"] != "PASS":
                continue
            states = []
            for repetition, t in [(1, a), (2, b)]:
                s = json.loads(json.dumps(t["methods"][method]))
                prefix = f"{case}-r{repetition}-{role}/"
                s["image"] = prefix + s["image"]
                for h in s["history"]:
                    h["image"] = prefix + h["image"]
                states.append(s)
            comparisons.append(
                dict(
                    case=case,
                    comparison="cross_repetition",
                    method=method,
                    **compare(states[0], states[1], root, cfg["bounds"]),
                )
            )
    ledger_path = root / "ledger.jsonl"
    ledger = (
        [json.loads(line) for line in ledger_path.read_text().splitlines()]
        if ledger_path.exists()
        else []
    )
    expected = [
        f"{case}-r{repetition}-{role}"
        for repetition in cfg["repetitions"]
        for case in cfg["cases"]
        for role in ["reference", "replay"]
    ]
    launches = [
        event["label"]
        for event in ledger
        if event["event"] == "launch" and event["label"] != "retrospective"
    ]
    exits = [
        event for event in ledger if event["event"] == "exit" and event["label"] != "retrospective"
    ]
    ledger_ok = (
        launches == expected
        and [event["label"] for event in exits] == expected
        and all(
            event.get("returncode") == 0
            and not event.get("timeout")
            and event.get("postflight_drift") is None
            for event in exits
        )
    )
    complete = (
        ledger_ok
        and len(traces) == 8
        and all(
            t["status"] == "PASS" and t.get("source_asset_preflight_and_postflight_match") is True
            for t in traces.values()
        )
    )
    verified = []
    for method in ["command_replay", "direct_full"]:
        relevant = [c for c in comparisons if c["method"] in [method, "continuous"]]
        if complete and len(relevant) == 8 and all(c["passed"] for c in relevant):
            verified.append(method)
    return dict(
        mechanically_complete=complete,
        ledger_order_and_exit_integrity=ledger_ok,
        traces=[
            dict(
                case=k[0], repetition=k[1], role=k[2], status=v["status"], failure=v.get("failure")
            )
            for k, v in traces.items()
        ],
        comparisons=comparisons,
        chronological=chronological,
        verified_reproducible_methods=verified,
        decision="VERIFIED_ON_TWO_CASES" if verified else "BOUNDED_UNRESOLVED",
        efficacy_claim=False,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze-commit", required=True)
    p.add_argument("--stage", choices=["retrospective", "probes", "analyse"], required=True)
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

    if a.stage == "retrospective":
        launch(
            [
                str(REPO / ".venv/bin/python"),
                str(REPO / "scripts/reconstruct_initial_policy.py"),
                "--freeze-commit",
                a.freeze_commit,
                "--out",
                str(root / "retrospective.json"),
            ],
            root / "retrospective.log",
            "retrospective",
        )
        return
    if any(root.glob("*-reference")) or any(root.glob("*-replay")):
        p.error("probes already attempted; no retries")
    for repetition in cfg["repetitions"]:
        for case in cfg["cases"]:
            reference = root / f"{case}-r{repetition}-reference"
            for role in ["reference", "replay"]:
                out = root / f"{case}-r{repetition}-{role}"
                args = [
                    PYTHON,
                    str(REPO / "scripts/collect_initialization_diagnostic.py"),
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
                if not ok or t.get("status") != "PASS":
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
