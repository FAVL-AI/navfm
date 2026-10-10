"""Integrity, outcomes, mechanism measures and gates for component_comparison_v2 (stages 2-3).

Definitions and gates are those frozen in configs/eval/component_comparison_v2.json
("definitions", "gates_to_stage_3"); this file is their computation. Pose is used
only for evaluation. Collections are named v2-<trial>-<variant>-<tag>.

Usage: analyse_component_comparison_v2.py --config CFG --freeze-commit SHA
       --audit AUDIT.json --tag TAG --trial NAME [--trial ...] --out OUT.json
       [--negative-control]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

E = Path("/home/favl/navfm-runtime-evidence")
REPO = Path(__file__).resolve().parents[1]
PERIOD = 6
AFTER = 10  # decisions examined after an encounter or a relocalisation


def git_blob_sha(commit: str, rel: str, cache: dict) -> str:
    if (commit, rel) not in cache:
        r = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{rel}"], capture_output=True)
        cache[commit, rel] = hashlib.sha256(r.stdout).hexdigest()
    return cache[commit, rel]


def influencing(m: dict) -> dict:
    stack = [m]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if x.get("name") == "influencing_file_digests" and isinstance(x.get("observed"), dict):
                return x["observed"]
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return {}


def to_polyline(p: np.ndarray, line: np.ndarray) -> float:
    a, b = line[:-1], line[1:]
    ab = b - a
    t = np.clip(np.einsum("ij,ij->i", p - a, ab) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
    return float(np.min(np.linalg.norm(p - (a + t[:, None] * ab), axis=1)))


def node_poses(m: dict) -> np.ndarray:
    tm = m["topomap"]
    chain = json.loads((Path(tm["root"]) / "chain.json").read_text())["routes"][m["route"]["id"]]
    teach = json.loads((Path(chain["traversal"]) / "runtime_manifest.json").read_text())
    return np.array([teach["captures"][n["frame"]]["pose"][:2] for n in chain["nodes"]])


def true_nodes(m: dict, npose: np.ndarray) -> list[int]:
    return [
        int(
            np.argmin(
                np.linalg.norm(npose - np.array(m["captures"][r["frame"]]["pose"][:2]), axis=1)
            )
        )
        for r in m["inference"]
    ]


def task_end_decision(inf: list) -> int:
    """Last decision of the task: the stop or abstention decision, else the last decision."""
    return next(
        (k for k, r in enumerate(inf) if r["policy_stop"] or r.get("policy_abstain")),
        len(inf) - 1,
    )


def ambiguity(
    m: dict, true: list[int], lateral: np.ndarray, initial_node: int, close: float
) -> dict:
    """Encounter / correction / followed / avoidance (frozen definitions).

    Lost-state decisions count (a lost policy following an aliased node is
    following it). Only decisions up to the task end count. "corrected" needs
    the full AFTER-decision horizon before the task end, else NOT_EVALUABLE.
    """
    inf = m["inference"]
    k_end = task_end_decision(inf)
    encounters, backward = [], []
    for k in range(k_end + 1):
        c = inf[k]["chain"]
        prev = inf[k - 1]["chain"]["closest_node"] if k else initial_node
        if "argmin_node" not in c:
            continue
        if abs(c["argmin_node"] - true[k]) >= 3 and abs(prev - true[k]) <= 1:
            followed = abs(c["followed_node"] - true[k]) > 1
            if followed:
                outcome = "followed"
            elif k + AFTER > k_end:
                outcome = "NOT_EVALUABLE"
            elif all(
                abs(inf[j]["chain"]["closest_node"] - true[j]) <= 1
                for j in range(k + 1, k + 1 + AFTER)
            ):
                outcome = "corrected"
            else:
                outcome = "withheld_then_lost_track"
            encounters.append(
                {
                    "decision": k,
                    "true": true[k],
                    "prev_current": prev,
                    "argmin": c["argmin_node"],
                    "argmin_distance": c["argmin_distance"],
                    "event": c.get("event", "upstream"),
                    "lost": bool(c.get("lost")),
                    "followed_node": c["followed_node"],
                    "outcome": outcome,
                }
            )
        if not c.get("lost"):
            close_hit = c["argmin_distance"] <= close
            proposal = c["argmin_node"] + (1 if close_hit else 0)
            if proposal < prev:
                backward.append(
                    {
                        "decision": k,
                        "prev_current": prev,
                        "proposal": proposal,
                        "true": true[k],
                        "accepted": c["closest_node"] < prev,
                        "proposal_closer_to_true": abs(proposal - true[k]) < abs(prev - true[k]),
                    }
                )
    first = inf[encounters[0]["decision"]]["frame"] if encounters else 0
    after = lateral[first:]
    count = {
        o: sum(e["outcome"] == o for e in encounters)
        for o in ("followed", "corrected", "withheld_then_lost_track", "NOT_EVALUABLE")
    }
    return {
        "encountered": bool(encounters),
        "encounters": encounters,
        **count,
        "status": "NOT_TESTED (avoidance)" if not encounters else "TESTED",
        "departure_after_first": bool((after > 0.5).any()),
        "max_lateral_after_first_m": float(after.max()) if len(after) else None,
        "backward_proposals": backward,
    }


def recovery(m: dict, true: list[int], start_lost: bool) -> dict:
    """Recovery per lost entry (frozen definition): relocalised within 1 node, no re-entry in 10."""
    inf = m["inference"]
    lost = [bool(r["chain"].get("lost")) for r in inf]
    entries = [0] if (start_lost and lost and lost[0]) else []
    entries += [k for k in range(1, len(inf)) if lost[k] and not lost[k - 1]]
    out = []
    for k0 in entries:
        reloc = next((k for k in range(k0 + 1, len(inf)) if not lost[k]), None)
        if reloc is None:
            out.append(
                {"entry": k0, "relocalised": None, "success": False, "reason": "never relocalised"}
            )
            continue
        node = inf[reloc]["chain"]["closest_node"]
        correct = abs(node - true[reloc]) <= 1
        yaw = np.unwrap([m["captures"][inf[q]["frame"]]["pose"][2] for q in range(k0, reloc + 1)])
        reentry = any(lost[j] for j in range(reloc + 1, min(reloc + 1 + AFTER, len(inf))))
        out.append(
            {
                "entry": k0,
                "relocalised": reloc,
                "node": node,
                "true": true[reloc],
                "event": inf[reloc]["chain"].get("event"),
                "decisions_lost": reloc - k0,
                "heading_rotated_deg": float(np.degrees(abs(yaw[-1] - yaw[0]))),
                "success": bool(correct and not reentry),
                "reason": None
                if correct and not reentry
                else ("wrong node" if not correct else "re-entered"),
            }
        )
    return {
        "lost_entries": len(out),
        "entries": out,
        "first_entry_success": bool(out and out[0]["success"]),
        "successes": sum(e["success"] for e in out),
    }


NEGATIVE_MODES = ("variant", "chain", "resume", "start_lost")


def attempt_checks(a, t, cond, spec, v, m, root, coll, route, ctx) -> dict:
    """Integrity checks for one attempt; every expected value comes from the frozen config."""
    neg = a.negative_control
    pt = m["policy"]["topomap"]
    tm = m["topomap"]
    want_lost = bool(t.get("start_lost")) != (neg == "start_lost")
    checks = {
        "variant": m["component_variant"]["variant"] == v,
        "config_sha": m["component_variant"]["comparison_config_sha256"] == ctx["cfg_sha"],
        "checkpoint": m["policy"]["sha256"] == ctx["cfg"]["checkpoint"]["sha256"],
        "chain_root": str(Path(tm["root"]).resolve()) == str(Path(cond["root"]).resolve()),
        "chain_sha": tm["chain_json_sha256"]
        == ("0" * 64 if neg == "chain" else cond["chain_json_sha256"]),
        "bounded": pt["bounded"] == spec["bounded"],
        "verify": pt["verify_threshold"] == spec["verify_threshold"],
        "confirmation": pt.get("confirmation") == spec.get("confirmation"),
        "approach_steering": pt.get("approach_steering")
        == (spec.get("approach_steering", True) if spec.get("confirmation") else None),
        "recovery": pt.get("recovery") == spec.get("recovery"),
        "start_lost": bool(pt.get("start_lost")) == want_lost
        and bool(tm.get("start_lost")) == want_lost,
        "radius": pt["radius"] == ctx["cfg"]["runtime"]["radius"],
        "close_threshold": pt["close_threshold"] == ctx["cfg"]["runtime"]["close_threshold"],
        "budget": m.get("max_steps")
        == t.get("budget_frames", ctx["cfg"]["runtime"]["budget_frames"]),
        "qualification": m.get("qualification_sha256") == ctx["qual_sha"],
        "launched_after_freeze": (root / "frozen_routes.json").stat().st_mtime > ctx["freeze_time"],
        "perturbation": [
            m["start_perturbation"][k] for k in ("arc_fraction", "lateral_m", "yaw_deg")
        ]
        == t.get("perturbation", [0.0, 0.0, 0.0]),
    }
    obs = influencing(m)
    rf = {
        q.split(str(REPO) + "/", 1)[1]: d for q, d in obs.items() if q.startswith(str(REPO) + "/")
    }
    checks["source_at_freeze"] = bool(rf) and all(
        git_blob_sha(a.freeze_commit, r, ctx["cache"]) == d for r, d in rf.items()
    )
    ctx["nonrepo"].append({q: d for q, d in obs.items() if not q.startswith(str(REPO) + "/")})
    frames = [r["frame"] for r in m["inference"]]
    end = m.get("policy_stop_frame")
    end = end if end is not None else m.get("policy_abstain_frame")
    checks["inference_complete"] = frames == list(range(0, PERIOD * len(frames), PERIOD)) and (
        end is not None or frames[-1] >= m["max_steps"] - PERIOD
    )
    resume = m.get("resume")
    if t.get("resume_from"):
        rm_path = Path(t["resume_from"])
        rm = json.loads((rm_path / "runtime_manifest.json").read_text())
        K = t["resume_decision"] + (1 if neg == "resume" else 0)
        node = rm["inference"][K - 1]["chain"]["closest_node"]
        checks["resume"] = (
            resume is not None
            and resume["episode"] == str(rm_path.resolve())
            and resume["decision"] == K
            and resume["initial_node"] == node
            and tm.get("initial_node") == node
            and resume["source_checkpoint_sha256"] == ctx["cfg"]["checkpoint"]["sha256"]
            and resume["history_sha256"]
            == [
                hashlib.sha256((rm_path / "trajectory" / f"{q}.jpg").read_bytes()).hexdigest()
                for q in resume["history_frames"]
            ]
        )
    else:
        checks["resume"] = resume is None and tm.get("initial_node") == 0
    r = ctx["audit"].get((coll, route))
    checks["audited"] = r is not None and "measures" in r
    gi = (r or {}).get("goal_identity") or {}
    checks["goal_identity"] = bool(gi) and all(x for x in gi.values() if isinstance(x, bool))
    return checks


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--freeze-commit", required=True)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--trial", action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--negative-control", choices=NEGATIVE_MODES)
    a = p.parse_args()
    if a.out.exists():
        p.error("output must be new")
    cfg_bytes = subprocess.run(
        [
            "git",
            "-C",
            str(REPO),
            "show",
            f"{a.freeze_commit}:configs/eval/component_comparison_v2.json",
        ],
        capture_output=True,
    ).stdout
    cfg = json.loads(cfg_bytes)
    if cfg != json.loads(a.config.read_text()):
        p.error("--config differs from the frozen commit's protocol")
    ctx = {
        "cfg": cfg,
        "cfg_sha": hashlib.sha256(a.config.read_bytes()).hexdigest(),
        "freeze_time": int(
            subprocess.run(
                ["git", "-C", str(REPO), "log", "-1", "--format=%ct", a.freeze_commit],
                capture_output=True,
                text=True,
            ).stdout
        ),
        "audit": {
            (r["collection"], r["route"]): r for r in json.loads(a.audit.read_text())["rows"]
        },
        "qual_sha": hashlib.sha256(Path(cfg["runtime"]["qualification"]).read_bytes()).hexdigest(),
        "cache": {},
        "nonrepo": [],
    }
    variants = list(cfg["variants"])
    close = cfg["runtime"]["close_threshold"]
    attempts, failures = [], []
    for trial in a.trial:
        t = cfg["trials"][trial]
        cond = cfg["conditions"][t["condition"]]
        for v in t["variants"]:
            coll = f"v2-{trial}-{v}-{a.tag}"
            root = E / coll
            shifted = variants[(variants.index(v) + 1) % len(variants)]
            spec = cfg["variants"][shifted if a.negative_control == "variant" else v]
            cj = (
                json.loads((root / "collection.json").read_text())
                if (root / "collection.json").exists()
                else {"episodes": []}
            )
            eps = {e["id"]: e for e in cj["episodes"]}
            for route in t["routes"]:
                att = {"trial": trial, "variant": v, "route": route, "collection": coll}
                e = eps.get(route)
                if e is None or e["status"] != "PASS":
                    att["status"] = "NEVER_RUN" if e is None else e["status"]
                    failures.append((coll, route, [att["status"]]))
                    attempts.append(att)
                    continue
                att["status"] = "PASS"
                m = json.loads((root / route / "runtime_manifest.json").read_text())
                checks = attempt_checks(a, t, cond, spec, v, m, root, coll, route, ctx)
                att["checks"] = checks
                att["integrity_ok"] = all(checks.values())
                if not att["integrity_ok"]:
                    failures.append((coll, route, sorted(k for k, ok in checks.items() if not ok)))
                r = ctx["audit"].get((coll, route))
                if r is None:
                    attempts.append(att)
                    continue
                ms = r["measures"]
                inf = m["inference"]
                k_end = task_end_decision(inf)
                first_end = next(
                    (k for k, x in enumerate(inf) if x["chain"].get("reached_goal")), None
                )
                stop_k = next((k for k, x in enumerate(inf) if x["policy_stop"]), None)
                att.update(
                    {
                        k: ms[k]
                        for k in (
                            "correct_stop",
                            "wrong_stop",
                            "timeout",
                            "navigation_success",
                            "collision_before_task_end",
                            "stop_goal_distance_m",
                            "min_goal_distance_m",
                            "final_goal_distance_m",
                            "exposure_s",
                            "elapsed_s",
                            "path_length_m",
                        )
                    }
                )
                att["abstained"] = m.get("policy_abstain_reason")
                att["termination"] = m["termination"]
                att["added_stopping_delay"] = (
                    {"decisions": stop_k - first_end, "seconds": 0.5 * (stop_k - first_end)}
                    if ms["correct_stop"] and first_end is not None and stop_k is not None
                    else None
                )
                if t["condition"] != "wrong_chain_swap":
                    npose = node_poses(m)
                    true = true_nodes(m, npose)
                    att["current_off_true"] = sum(
                        abs(inf[k]["chain"]["closest_node"] - true[k]) > 1 for k in range(k_end + 1)
                    )
                    goal_node = len(npose) - 1
                    latch = next(
                        (
                            k
                            for k, x in enumerate(inf)
                            if (x.get("confirmation") or {}).get("phase") == "approach"
                        ),
                        None,
                    )
                    att["approach_latch"] = (
                        None
                        if latch is None
                        else {
                            "decision": latch,
                            "true_node": true[latch],
                            "premature": true[latch] <= goal_node - 3,
                        }
                    )
                    exit_ = (spec.get("recovery") or {}).get("exit") or (
                        (spec.get("bounded") or {}).get("lost_exit")
                    )
                    lost_ks = [k for k in range(k_end + 1) if inf[k]["chain"].get("lost")]
                    att["lost_decisions"] = len(lost_ks)
                    att["lost_false_global_matches"] = (
                        None
                        if exit_ is None
                        else sum(
                            inf[k]["chain"]["argmin_distance"] <= exit_
                            and abs(inf[k]["chain"]["argmin_node"] - true[k]) > 1
                            for k in lost_ks
                        )
                    )
                    caps = m["captures"]
                    line = np.asarray(m["route"]["waypoints"], float)
                    line[:, 1] += m["route"]["scene_index"] * 20.0
                    lateral = np.array([to_polyline(np.array(c["pose"][:2]), line) for c in caps])
                    if t["question"] == "look-alike":
                        att["ambiguity"] = ambiguity(
                            m, true, lateral, m["topomap"].get("initial_node", 0), close
                        )
                    att["recovery"] = recovery(m, true, bool(t.get("start_lost")))
                attempts.append(att)
    nonrepo = ctx["nonrepo"]
    if nonrepo and not all(n == nonrepo[0] for n in nonrepo):
        failures.append(("all", "all", ["nonrepo_influencing_files"]))
    per_check: dict = {}
    for _, _, ks in failures:
        for k in ks:
            per_check[k] = per_check.get(k, 0) + 1

    def rows(trial_names, variant):
        return [
            x
            for x in attempts
            if x["trial"] in trial_names and x["variant"] == variant and "correct_stop" in x
        ]

    def planned(trial_names, variant):
        return sum(
            len(cfg["trials"][tn]["routes"])
            for tn in trial_names
            if variant in cfg["trials"][tn]["variants"]
        )

    def complete(trial_names, variants_):
        rs = [x for v in variants_ for x in rows(trial_names, v)]
        return all(x.get("integrity_ok") for x in rs) and all(
            len(rows(trial_names, v)) == planned(trial_names, v) for v in variants_
        )

    def contacts(rs):
        return sum(bool(x["collision_before_task_end"]) for x in rs)

    def exposure(rs):
        secs = sum(x["exposure_s"] for x in rs)
        path = sum(x["path_length_m"] for x in rs)
        n = contacts(rs)
        return {
            "contacts": n,
            "exposure_s": secs,
            "path_m": path,
            "contacts_per_min": 60 * n / secs if secs else None,
            "contacts_per_m": n / path if path else None,
        }

    gates = {}
    ran = set(a.trial)
    amb = sorted(tn for tn in ran if cfg["trials"][tn]["question"] == "look-alike")
    if amb:
        ra, rb = rows(amb, "A_baseline"), rows(amb, "B1_bounded")
        b_enc = [e for x in rb for e in x["ambiguity"]["encounters"]]
        evaluable = [e for e in b_enc if e["outcome"] != "NOT_EVALUABLE"]
        g = {
            "complete": complete(amb, ["A_baseline", "B1_bounded"]),
            "A_follows_in_some_trial": any(x["ambiguity"]["followed"] for x in ra),
            "B1_encounters": bool(b_enc),
            "B1_corrects_every_evaluable_encounter": bool(evaluable)
            and all(e["outcome"] == "corrected" for e in evaluable),
            "B1_contacts_le_A": contacts(rb) <= contacts(ra),
        }
        g["pass"] = all(g.values())
        g["status"] = "NOT_TESTED" if not b_enc else ("PASS" if g["pass"] else "FAIL")
        g["exposure"] = {"A_baseline": exposure(ra), "B1_bounded": exposure(rb)}
        gates["B1_bounded (look-alike)"] = g
    kid = sorted(tn for tn in ran if cfg["trials"][tn]["question"] == "recovery")
    if kid:
        uninf = [tn for tn in kid if cfg["trials"][tn].get("uninformative_view")]
        arms = ("B1_bounded", "B1x_exit", "R2_recover")

        def succ(tns, v):
            return sum(x["recovery"]["first_entry_success"] for x in rows(tns, v))

        g = {
            "complete": complete(kid, list(arms)),
            "R2_uninformative_successes": succ(uninf, "R2_recover"),
            "B1x_uninformative_successes": succ(uninf, "B1x_exit"),
            "R2_all_successes": succ(kid, "R2_recover"),
            "B1x_all_successes": succ(kid, "B1x_exit"),
            "B1_all_successes": succ(kid, "B1_bounded"),
            "uninformative_trials": planned(uninf, "R2_recover"),
        }
        g["pass"] = (
            g["complete"]
            and g["R2_uninformative_successes"] >= 6
            and g["R2_uninformative_successes"] > g["B1x_uninformative_successes"]
            and g["R2_all_successes"] >= g["B1x_all_successes"]
            and contacts(rows(kid, "R2_recover")) <= contacts(rows(kid, "B1x_exit"))
        )
        g["exposure"] = {v: exposure(rows(kid, v)) for v in arms}
        gates["R2_recover"] = g
    arr = sorted(tn for tn in ran if cfg["trials"][tn]["question"] == "arrival recognition")
    if arr:
        vs = cfg["trials"][arr[0]]["variants"]
        g = {
            v: {
                "correct": sum(x["correct_stop"] for x in rows(arr, v)),
                "wrong": sum(x["wrong_stop"] for x in rows(arr, v)),
                "abstained": sum(bool(x["abstained"]) for x in rows(arr, v)),
                "timeouts": sum(x["timeout"] and not x["abstained"] for x in rows(arr, v)),
                "premature_latches": sum(
                    bool((x.get("approach_latch") or {}).get("premature")) for x in rows(arr, v)
                ),
                **exposure(rows(arr, v)),
                "n": len(rows(arr, v)),
            }
            for v in vs
        }
        g["complete"] = complete(arr, vs)
        for v in ("V2a_confirm", "V2b_confirm_steer"):
            if v in g:
                g[f"{v}_pass"] = (
                    g["complete"]
                    and g[v]["correct"] >= 3
                    and g[v]["wrong"] == 0
                    and g[v]["contacts"] <= g["A_baseline"]["contacts"]
                    and g[v]["correct"] > g["C1_verify"]["correct"]
                )
        gates["V2 (arrival recognition)"] = g
    out = {
        "scope": "component_comparison_v2 development",
        "freeze_commit": a.freeze_commit,
        "config_sha256": ctx["cfg_sha"],
        "negative_control": a.negative_control,
        "attempts": attempts,
        "integrity_failures": failures,
        "integrity_failures_per_check": per_check,
        "gates": gates,
    }
    a.out.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(
        json.dumps(
            {
                "attempts": len(attempts),
                "integrity_failures_per_check": per_check,
                "gates": gates,
            },
            indent=1,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
