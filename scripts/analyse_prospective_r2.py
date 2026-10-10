"""Frozen prospective first-entry recovery scoring on development layouts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import analyse_component_comparison_v2 as v2
import audit_closed_loop_episodes as audit
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
CONFIG = "configs/eval/prospective_r2_recovery_v1.json"
FROZEN_FILES = [
    CONFIG,
    "docs/PROSPECTIVE_R2_PROTOCOL_V1.md",
    "scripts/analyse_prospective_r2.py",
    "scripts/run_prospective_r2.py",
    "tests/test_prospective_r2.py",
    "scripts/collect_option1.py",
    "scripts/analyse_component_comparison_v2.py",
    "scripts/audit_closed_loop_episodes.py",
    "src/navfm/collection/episode_measures.py",
    "configs/eval/arrival_measures_v1.json",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def frozen_config(commit: str) -> dict:
    for rel in FROZEN_FILES:
        blob = subprocess.run(
            ["git", "-C", str(REPO), "show", f"{commit}:{rel}"], capture_output=True, check=True
        ).stdout
        if blob != (REPO / rel).read_bytes():
            raise ValueError(f"Frozen file differs: {rel}")
    cfg = json.loads((REPO / CONFIG).read_text())
    if not cfg["status"].startswith("FROZEN"):
        raise ValueError("Protocol not frozen")
    return cfg


def first_entry(
    inference: list[dict], true: list[int], tolerance: int = 0, terminal_frame: int | None = None
) -> dict:
    """The declared entry precedes decision zero; never select a later entry."""
    relocation = next(
        (
            i
            for i, r in enumerate(inference[:36])
            if not r["chain"]["lost"] and (terminal_frame is None or r["frame"] <= terminal_frame)
        ),
        None,
    )
    if relocation is None:
        abstain = any(r["chain"].get("event") == "recovery_failed" for r in inference)
        return {
            "outcome": "abstention" if abstain else "failure",
            "reason": "no relocation in common horizon",
            "relocation": None,
        }
    delta = abs(inference[relocation]["chain"]["closest_node"] - true[relocation])
    follow = [
        r
        for r in inference[relocation + 1 : relocation + 11]
        if terminal_frame is None or r["frame"] < terminal_frame
    ]
    complete = len(follow) == 10
    reentry = any(r["chain"]["lost"] for r in follow)
    outcome = (
        "wrong_confident"
        if delta > tolerance
        else "correct_confident"
        if complete and not reentry
        else "failure"
    )
    return {
        "outcome": outcome,
        "relocation": relocation,
        "node_error": delta,
        "selected_node": inference[relocation]["chain"]["closest_node"],
        "true_node": true[relocation],
        "followup_complete": complete,
        "lost_reentry": reentry,
        "reason": "wrong node"
        if delta > tolerance
        else "censored durability"
        if not complete
        else "lost reentry"
        if reentry
        else None,
    }


def motion(m: dict) -> dict:
    caps = m["captures"]
    end = m.get("policy_stop_frame")
    if end is None:
        end = m.get("policy_abstain_frame")
    # Predeclared gate window includes exactly24 terminal tail frames.
    end = len(caps) - 1 if end is None else min(end + 24, len(caps) - 1)
    first = m["inference"][0]
    p = np.asarray([first["predecision_pose"], *[c["pose"] for c in caps[: end + 1]]], float)
    dt = np.diff([first["predecision_sim_time"], *[c["simulation_time"] for c in caps[: end + 1]]])
    displacement = np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1)
    rotation = float(np.abs(np.diff(np.unwrap(p[:, 2]))).sum())
    return {
        "translating_s": float(dt[displacement > 1e-4].sum()),
        "absolute_rotation_rad": rotation,
        "initial_pose": m["start_settling"]["pose"],
        "window_end_frame": end,
        "path_length_m": float(displacement.sum()),
        "exposure_s": float(sum(dt)),
        "collision_before_task_end": any(
            c["time"] <= caps[end]["simulation_time"] for c in m.get("contacts", [])
        ),
        "contact_records": sum(
            c["time"] <= caps[end]["simulation_time"] for c in m.get("contacts", [])
        ),
        "extra_tail_s": caps[-1]["simulation_time"] - caps[end]["simulation_time"],
        "extra_tail_contact_records": sum(
            c["time"] > caps[end]["simulation_time"] for c in m.get("contacts", [])
        ),
        "settling_contacts": m["start_settling"]["contacts"],
    }


def ledger_checks(cfg: dict, ledger: list[dict]) -> list:
    """Fail closed on every launch, including entries outside scoring loops."""
    failures = []
    launches = [x for x in ledger if x.get("event") == "launch"]
    names = [x["collection"] for x in launches]
    if len(names) != len(set(names)):
        failures.append("duplicate launch collection")
    digests = {x.get("robot_usd_sha256") for x in launches}
    if len(digests) != 1 or None in digests or "" in digests:
        failures.append("robot digest differs across launches")
    expected = [(t, v) for t, spec in cfg["trials"].items() for v in spec["variants"]]
    initial = []
    for launch in launches:
        t, v = launch.get("trial"), launch.get("variant")
        if t not in cfg["trials"] or v not in cfg["trials"].get(t, {}).get("variants", []):
            failures.append("undeclared trial or variant")
            continue
        routes = launch.get("routes", [])
        if (
            not routes
            or len(routes) != len(set(routes))
            or not set(routes) <= set(cfg["trials"][t]["routes"])
        ):
            failures.append("undeclared or duplicate routes")
        prefix = f"v2-{t}-{v}-"
        if launch["collection"] == prefix + "20261010-01":
            initial.append((t, v))
            if routes != cfg["trials"][t]["routes"]:
                failures.append("initial routes differ from fixed order")
        elif launch["collection"] != prefix + "20261010-02":
            failures.append("undeclared attempt tag")
    if initial != expected[: len(initial)]:
        failures.append("initial launch order differs from frozen order")
    remaining = [
        i
        for i, x in enumerate(ledger)
        if x.get("event") == "launch" and x.get("trial") in list(cfg["trials"])[1:]
    ]
    gates = [i for i, x in enumerate(ledger) if x.get("event") == "pilot_gate"]
    if remaining and (len(gates) != 1 or gates[0] >= min(remaining)):
        failures.append("remaining stage lacks prior unique pilot gate")
    return failures


def aggregate(rows: list[dict]) -> dict:
    ncontact = sum(bool(r.get("collision_before_task_end")) for r in rows)
    path = sum(r.get("path_length_m", 0) for r in rows)
    seconds = sum(r.get("exposure_s", 0) for r in rows)
    return {
        "planned_attempts": len(rows),
        "primary": dict(Counter(r["primary"]["outcome"] for r in rows)),
        "secondary": dict(Counter(r["secondary"]["outcome"] for r in rows)),
        "contact_episodes": ncontact,
        "path_m": path,
        "exposure_s": seconds,
        "contacts_per_m": ncontact / path if path else None,
        "contacts_per_s": ncontact / seconds if seconds else None,
        "correct_arrival_stops": sum(bool(r.get("correct_stop")) for r in rows),
        "wrong_arrival_stops": sum(bool(r.get("wrong_stop")) for r in rows),
        "translating_s": sum(r.get("motion", {}).get("translating_s", 0) for r in rows),
        "absolute_rotation_rad": sum(
            r.get("motion", {}).get("absolute_rotation_rad", 0) for r in rows
        ),
    }


def analyse(commit: str, evidence: Path, stage: str) -> dict:
    cfg = frozen_config(commit)
    trials = list(cfg["trials"])[:1] if stage == "pilot" else list(cfg["trials"])
    ledgerpath = evidence / "prospective-r2-v1-launch-ledger.jsonl"
    ledger = (
        [json.loads(s) for s in ledgerpath.read_text().splitlines()] if ledgerpath.exists() else []
    )
    launches = [x for x in ledger if x["event"] == "launch"]
    completions = [x for x in ledger if x["event"] == "exit"]
    freeze_time = int(git("log", "-1", "--format=%ct", commit))
    ctx = {
        "cfg": cfg,
        "cfg_sha": sha(REPO / CONFIG),
        "freeze_time": freeze_time,
        "qual_sha": sha(Path(cfg["runtime"]["qualification"])),
        "cache": {},
        "nonrepo": [],
        "amendment": None,
        "ledger": None,
    }
    rows, attempt_log, violations = [], [], ledger_checks(cfg, ledger)
    for trial in trials:
        t = cfg["trials"][trial]
        for arm in t["variants"]:
            for route in t["routes"]:
                entries = [
                    x
                    for x in launches
                    if x["trial"] == trial and x["variant"] == arm and route in x["routes"]
                ]
                roots = sorted(evidence.glob(f"v2-{trial}-{arm}-*"))
                declared = {x["collection"] for x in launches}
                for root in roots:
                    if root.is_dir() and root.name not in declared:
                        violations.append([trial, arm, "unledgered collection", root.name])
                attempts = []
                for launch in entries:
                    root = evidence / launch["collection"]
                    cj = (
                        json.loads((root / "collection.json").read_text())
                        if (root / "collection.json").exists()
                        else {}
                    )
                    status = next(
                        (e["status"] for e in cj.get("episodes", []) if e["id"] == route), "MISSING"
                    )
                    if cj.get("status") == "RUNNING":
                        status = "INCOMPLETE_COLLECTION"
                    a = {
                        "trial": trial,
                        "variant": arm,
                        "route": route,
                        "collection": root.name,
                        "status": status,
                        "integrity_ok": False,
                        "primary": {"outcome": "failure", "reason": status},
                        "secondary": {"outcome": "failure", "reason": status},
                    }
                    ends = [x for x in completions if x["collection"] == root.name]
                    checks = {
                        "ledger_complete": len(ends) == 1,
                        "clean_launch": launch["worktree_status"] == "",
                        "launch_head": launch["head"] == commit,
                        "config_digest": launch["config_sha256"] == ctx["cfg_sha"],
                    }
                    if ends:
                        checks["robot_digest"] = (
                            launch["robot_usd_sha256"] == ends[0]["robot_usd_sha256_after"]
                        )
                        checks["frozen_routes_digest"] = (
                            root / "frozen_routes.json"
                        ).exists() and sha(root / "frozen_routes.json") == ends[0][
                            "frozen_routes_sha256"
                        ]
                    if status == "PASS":
                        try:
                            m = json.loads((root / route / "runtime_manifest.json").read_text())
                            checks.update(
                                v2.attempt_checks(
                                    None,
                                    commit,
                                    t,
                                    trial,
                                    cfg["conditions"][t["condition"]],
                                    cfg["variants"][arm],
                                    arm,
                                    m,
                                    root,
                                    ctx,
                                )
                            )
                            goal, identity = audit.goal_xy(
                                Path(cfg["runtime"]["goal_root"]), root / route
                            )
                            checks["goal_identity"] = bool(identity) and all(
                                v for v in identity.values() if isinstance(v, bool)
                            )
                            r = audit.audit(root / route, goal)
                            a.update(r["measures"])
                            a["motion"] = motion(m)
                            for key in ["path_length_m", "exposure_s", "collision_before_task_end"]:
                                a[key] = a["motion"][key]
                            init = m["initial_policy_state"]
                            checks["initial_counters"] = (
                                init["closest_node"] == 0
                                and init["lost"] is True
                                and init["_far"] == 0
                                and init["_pending"] == []
                                and init["attempts"] == (1 if arm == "R2_recover" else None)
                                and init["_scan"] == (0 if arm == "R2_recover" else None)
                                and m["initial_policy_counters"]
                                == dict(
                                    stop_count=0,
                                    stopped=False,
                                    verified_count=0,
                                    chain_reached_decisions=0,
                                )
                            )
                            checks["live_history"] = (
                                len(m["initial_history_sha256"]) == 6
                                and len(set(m["initial_history_sha256"])) == 1
                                and m["initial_history_sha256"][0]
                                == hashlib.sha256(
                                    np.asarray(
                                        Image.open(root / route / "start.png").convert("RGB")
                                    ).tobytes()
                                ).hexdigest()
                            )
                            p0 = np.asarray(m["inference"][0]["predecision_pose"])
                            target = np.asarray(m["start_pose"])
                            tol = cfg["design"]["matching_tolerances"]

                            def yaw_error(x, y):
                                return abs(
                                    float(np.degrees(np.arctan2(np.sin(x - y), np.cos(x - y))))
                                )

                            checks["target_pose"] = (
                                np.linalg.norm(p0[:2] - target[:2]) <= tol["position_m"]
                                and yaw_error(p0[2], target[2]) <= tol["yaw_deg"]
                            )
                            a["motion"]["initial_pose"] = p0.tolist()
                            nodes = v2.node_poses(m)
                            true = [
                                int(
                                    np.argmin(
                                        np.linalg.norm(
                                            nodes - np.asarray(x["predecision_pose"])[:2], axis=1
                                        )
                                    )
                                )
                                for x in m["inference"]
                            ]
                            terminal = m.get("policy_stop_frame")
                            if terminal is None:
                                terminal = m.get("policy_abstain_frame")
                            a["primary"] = first_entry(
                                m["inference"], true, terminal_frame=terminal
                            )
                            a["secondary"] = first_entry(m["inference"], true, 1, terminal)
                            rel = a["primary"].get("relocation")
                            a["followup_exact_correct"] = [
                                x["chain"]["closest_node"] == true[i]
                                for i, x in enumerate(m["inference"])
                                if rel is not None
                                and rel < i <= rel + 10
                                and (terminal is None or x["frame"] < terminal)
                            ]
                            lost = True
                            transitions = []
                            for i, x in enumerate(m["inference"]):
                                if terminal is not None and x["frame"] > terminal:
                                    break
                                if lost and not x["chain"]["lost"]:
                                    transitions.append(
                                        dict(
                                            decision=i,
                                            node_error=abs(x["chain"]["closest_node"] - true[i]),
                                            within_common_horizon=i < 36,
                                        )
                                    )
                                lost = x["chain"]["lost"]
                            a["preterminal_confident_transitions"] = transitions
                            preterminal = [
                                x
                                for x in m["inference"]
                                if terminal is None or x["frame"] <= terminal
                            ]
                            a["lost_entry_indices"] = [0] + [
                                i
                                for i in range(1, len(preterminal))
                                if preterminal[i]["chain"]["lost"]
                                and not preterminal[i - 1]["chain"]["lost"]
                            ]
                        except (KeyError, TypeError, ValueError, IndexError, OSError) as exc:
                            checks["measurement_complete"] = False
                            a["measurement_error"] = str(exc)
                    a["checks"] = checks
                    a["integrity_ok"] = status == "PASS" and all(checks.values())
                    if not a["integrity_ok"]:
                        a["primary"] = a["secondary"] = {
                            "outcome": "failure",
                            "reason": "invalid evidence",
                        }
                    attempts.append(a)
                    attempt_log.append(a)
                if len(entries) > 2 or (len(attempts) > 1 and attempts[0]["status"] == "PASS"):
                    violations.append([trial, arm, route, "retry rule violated"])
                rows.append(
                    attempts[0]
                    if attempts
                    else {
                        "trial": trial,
                        "variant": arm,
                        "route": route,
                        "status": "NOT_RUN",
                        "integrity_ok": False,
                        "primary": {"outcome": "failure", "reason": "NOT_RUN"},
                        "secondary": {"outcome": "failure", "reason": "NOT_RUN"},
                    }
                )
    external = ctx["nonrepo"]
    globally_ok = not violations and bool(external) and all(x == external[0] for x in external)
    if not globally_ok:
        violations.append(["global", "provenance or retry mismatch"])
    arms = {arm: aggregate([r for r in rows if r["variant"] == arm]) for arm in cfg["variants"]}
    hard = {
        arm: aggregate(
            [r for r in rows if r["variant"] == arm and cfg["trials"][r["trial"]]["rear_facing"]]
        )
        for arm in cfg["variants"]
    }
    pairs = []
    for trial in trials:
        for route in cfg["trials"][trial]["routes"]:
            rr = [r for r in rows if r["trial"] == trial and r["route"] == route]
            if len(rr) == 2 and all("motion" in r for r in rr):
                p, q = [np.asarray(r["motion"]["initial_pose"], float) for r in rr]
                images = [
                    np.asarray(
                        Image.open(evidence / r["collection"] / route / "start.png").convert("L"),
                        float,
                    )
                    for r in rr
                ]
                image_error = float(np.abs(images[0] - images[1]).mean())
                pairs.append(
                    {
                        "trial": trial,
                        "route": route,
                        "image_mean_abs_grey": image_error,
                        "start_position_error_m": float(np.linalg.norm(p[:2] - q[:2])),
                        "start_yaw_error_deg": float(
                            abs(np.degrees(np.arctan2(np.sin(p[2] - q[2]), np.cos(p[2] - q[2]))))
                        ),
                    }
                )
    tol = cfg["design"]["matching_tolerances"]
    for pair in pairs:
        pair["integrity_ok"] = (
            pair["start_position_error_m"] <= tol["position_m"]
            and pair["start_yaw_error_deg"] <= tol["yaw_deg"]
            and pair["image_mean_abs_grey"] <= tol["image_mean_abs_grey"]
        )
        if not pair["integrity_ok"]:
            violations.append([pair["trial"], pair["route"], "paired start mismatch"])
    if stage == "all" and len(rows) > 8:
        gates = [x for x in ledger if x.get("event") == "pilot_gate"]
        if len(gates) != 1:
            violations.append("missing unique pilot report")
        else:
            gate = gates[0]
            try:
                reportpath = Path(gate["report_path"])
                report = json.loads(reportpath.read_text())
                pilot_rows = [r for r in rows if r["trial"] == next(iter(cfg["trials"]))]
                pilot_pairs = [r for r in pairs if r["trial"] == next(iter(cfg["trials"]))]
                if (
                    reportpath.resolve().is_relative_to(REPO)
                    or sha(reportpath) != gate["report_sha256"]
                    or report["freeze_commit"] != commit
                    or report["config_sha256"] != ctx["cfg_sha"]
                    or not report["continue_fixed_remaining"]
                    or report["primary_attempts"] != pilot_rows
                    or report["paired_starts"] != pilot_pairs
                ):
                    violations.append("pilot gate report invalid")
            except (OSError, KeyError, ValueError):
                violations.append("pilot gate report missing")
    globally_ok = globally_ok and not violations and len(pairs) == len(rows) // 2
    integrity_ok = globally_ok and all(r["integrity_ok"] for r in rows)

    def count(group, arm, outcome):
        return group[arm]["primary"].get(outcome, 0)

    supported = (
        stage == "all"
        and integrity_ok
        and count(arms, "R2_recover", "correct_confident") >= 12
        and count(arms, "R2_recover", "correct_confident")
        > count(arms, "B1x_exit", "correct_confident")
        and count(hard, "R2_recover", "correct_confident") >= 6
        and count(hard, "R2_recover", "correct_confident")
        > count(hard, "B1x_exit", "correct_confident")
        and count(arms, "R2_recover", "wrong_confident")
        <= count(arms, "B1x_exit", "wrong_confident")
    )
    raw_guard = arms["R2_recover"]["contact_episodes"] <= arms["B1x_exit"]["contact_episodes"]
    rate_r, rate_b = arms["R2_recover"]["contacts_per_m"], arms["B1x_exit"]["contacts_per_m"]
    contact_guard = raw_guard and rate_r is not None and rate_b is not None and rate_r <= rate_b
    return {
        "contact_guard": contact_guard,
        "guarded_retention": stage == "all" and supported and contact_guard,
        "scope": "prospective R2 versus B1x, development only",
        "freeze_commit": commit,
        "config_sha256": ctx["cfg_sha"],
        "stage": stage,
        "integrity_ok": integrity_ok,
        "continue_fixed_remaining": stage == "pilot" and integrity_ok,
        "decision": "PILOT_ONLY"
        if stage == "pilot"
        else "INCONCLUSIVE"
        if not integrity_ok
        else "SUPPORT"
        if supported
        else "NOT_SUPPORTED",
        "primary_attempts": rows,
        "all_attempts": attempt_log,
        "retry_sensitivity": [r for r in attempt_log if r not in rows],
        "violations": violations,
        "arms": arms,
        "hard_subgroup": hard,
        "paired_starts": pairs,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze-commit", required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--stage", choices=["pilot", "all"], required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists() or a.out.resolve().is_relative_to(REPO):
        p.error("Output must be new and outside repository")
    result = analyse(a.freeze_commit, a.evidence, a.stage)
    a.out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({k: result[k] for k in ["stage", "integrity_ok", "decision", "arms"]}, indent=2)
    )


if __name__ == "__main__":
    main()
