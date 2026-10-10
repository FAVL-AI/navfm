"""Integrity, outcomes, mechanism measures, stage-2 gates and stage-3 decisions (component_comparison_v2).

Definitions, gates and criteria are those frozen in configs/eval/component_comparison_v2.json
("definitions", "gates_to_stage_3", "stage_3_criteria", "retry_rule"); this file is their
computation. Pose is used only for evaluation. Collections are named
v2-<trial>-<variant>-<tag>; every tag found is reported (retry rule).

Usage: analyse_component_comparison_v2.py --config CFG --freeze-commit SHA --audit AUDIT.json
       --trial NAME [--trial ...] --out OUT.json
       [--stage2-commit SHA --stage2-path gates/v2/<record>.json] [--negative-control MODE]

Stage 3 is admitted only from a stage-2 gate record committed to the repository:
its freeze commit, config hash, negative-control flag and trial coverage are
checked and its gates are recomputed from its recorded attempts; stage-3
collections must be launched after that commit.
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
                np.linalg.norm(
                    npose - np.array(m["captures"][max(r["frame"] - 1, 0)]["pose"][:2]), axis=1
                )
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
    # Route following from the first encounter, else from the first decision (the
    # handover frame for a resumed trial, so replay frames never count).
    first = inf[encounters[0]["decision"]]["frame"] if encounters else inf[0]["frame"]
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


NEGATIVE_MODES = ("variant", "chain", "resume", "start_lost", "trial")
COUNTERPART = {
    "B1_bounded": "A_baseline",
    "V2a_confirm": "C1_verify",
    "V2b_confirm_steer": "C1_verify",
    "R2_recover": "B1x_exit",
}


def attempt_checks(neg, freeze_commit, t, trial, cond, spec, v, m, root, ctx) -> dict:
    """Integrity checks for one attempt; every expected value comes from the frozen config."""
    pt = m["policy"]["topomap"]
    tm = m["topomap"]
    cv = m["component_variant"]
    want_lost = bool(t.get("start_lost")) != (neg == "start_lost")
    checks = {
        "variant": cv["variant"] == v,
        "trial": cv.get("trial") == (trial + "_x" if neg == "trial" else trial)
        and cv.get("stage") == t["stage"],
        "config_sha": cv["comparison_config_sha256"] == ctx["cfg_sha"],
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
        "scan_rate": pt.get("scan_rate")
        == (spec.get("scan_rate", 0.4) if spec.get("recovery") else None),
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
        git_blob_sha(freeze_commit, r, ctx["cache"]) == d for r, d in rf.items()
    )
    ctx["nonrepo"].append({q: d for q, d in obs.items() if not q.startswith(str(REPO) + "/")})
    frames = [r["frame"] for r in m["inference"]]
    end = m.get("policy_stop_frame")
    end = end if end is not None else m.get("policy_abstain_frame")
    h = (m.get("resume") or {}).get("handover_frame", 0)
    checks["inference_complete"] = frames == list(range(h, h + PERIOD * len(frames), PERIOD)) and (
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
            and resume.get("mode") == "replay_to_handover"
            and resume["episode"] == str(rm_path.resolve())
            and resume["decision"] == K
            and resume["handover_frame"] == K * PERIOD
            and resume["initial_node"] == node
            and tm.get("initial_node") == node
            and resume["source_checkpoint_sha256"] == ctx["cfg"]["checkpoint"]["sha256"]
            and resume["replayed_commands"] == [rm["inference"][k]["command"] for k in range(K)]
            and resume["recorded_start_pose"] == rm["start_pose"]
            and np.allclose(m["start_pose"], rm["start_pose"], atol=1e-9)
            and resume.get("manifest_sha256")
            == hashlib.sha256((rm_path / "runtime_manifest.json").read_bytes()).hexdigest()
        )
        # The replayed commands were applied, frame by frame (not just recorded).
        tr_path = root / m["route"]["id"] / "trajectory" / "transitions.json"
        records = json.loads(tr_path.read_text())["records"] if tr_path.exists() else []
        h = K * PERIOD
        checks["replay_applied"] = (
            resume is not None
            and len(records) >= h
            and all(
                records[i]["command_requested"] == resume["replayed_commands"][i // PERIOD]
                for i in range(h)
            )
        )
        times = [c["simulation_time"] for c in m["captures"]]
        first_contact = (
            int(np.searchsorted(times, min(c["time"] for c in m["contacts"]), side="left"))
            if m.get("contacts")
            else None
        )
        checks["no_contact_before_handover"] = first_contact is None or first_contact >= h
        fid = ctx["cfg"]["replay_fidelity"]
        checks["replay_fidelity"] = (
            resume is not None
            and resume.get("handover_position_error_m", 1e9) <= fid["position_m"]
            and resume.get("handover_yaw_error_deg", 1e9) <= fid["yaw_deg"]
            and resume.get("handover_image_mean_abs_grey", 1e9) <= fid["image_mean_abs_grey"]
            and resume.get("handover_window_matches") is True
            and resume.get("handover_max_distance_diff") is not None
            and resume["handover_max_distance_diff"] <= fid["max_distance_diff"]
        )
    else:
        checks["resume"] = resume is None and tm.get("initial_node") == 0
    return checks


def discover(
    trial: str, variant: str, routes: list[str], base: Path = E
) -> tuple[dict, list, list]:
    """Apply the retry rule over every v2-<trial>-<variant>-* collection.

    Every planned route of every collection is an attempt: its episode status, or
    CRASHED when the collection planned it but recorded no episode (also when the
    collection is still RUNNING). Only a route's first two attempts can count; the
    counted attempt is the first PASS among them, and only if the attempt before it
    (if any) was not a PASS. A third attempt or an attempt after a PASS is a
    violation: the route then has no counted attempt.
    """
    roots = sorted(
        (d for d in base.glob(f"v2-{trial}-{variant}-*") if (d / "frozen_routes.json").exists()),
        key=lambda d: (d / "frozen_routes.json").stat().st_mtime,
    )
    log, counted, violations = [], {}, []
    for root in roots:
        planned_ids = [r["id"] for r in json.loads((root / "frozen_routes.json").read_text())]
        cj = (
            json.loads((root / "collection.json").read_text())
            if (root / "collection.json").exists()
            else {"episodes": [], "status": "MISSING"}
        )
        seen = {e["id"]: e["status"] for e in cj.get("episodes", [])}
        for rid in planned_ids:
            status = seen.get(rid, "CRASHED")
            if cj.get("status") == "RUNNING" and status == "PASS":
                status = "PASS_IN_RUNNING_COLLECTION"
            log.append({"collection": root.name, "route": rid, "status": status})
    for route in routes:
        tries = [x for x in log if x["route"] == route]
        if len(tries) > 2:
            violations.append((route, "more than one rerun"))
        first_pass = next((k for k, x in enumerate(tries) if x["status"] == "PASS"), None)
        if first_pass is not None and first_pass < len(tries) - 1:
            violations.append((route, "attempt after a PASS"))
        if any(r == route for r, _ in violations):
            continue
        if first_pass is not None and first_pass < 2:
            x = tries[first_pass]
            counted[route] = (base / x["collection"], x)
    return counted, log, violations


def measures(m: dict, r: dict, t: dict, spec: dict, close: float, goal) -> dict:
    ms = r["measures"]
    inf = m["inference"]
    k_end = task_end_decision(inf)
    first_end = next((k for k, x in enumerate(inf) if x["chain"].get("reached_goal")), None)
    stop_k = next((k for k, x in enumerate(inf) if x["policy_stop"]), None)
    out = {
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
    out["abstained"] = m.get("policy_abstain_reason")
    out["termination"] = m["termination"]
    out["added_stopping_delay"] = (
        {"decisions": stop_k - first_end, "seconds": 0.5 * (stop_k - first_end)}
        if ms["correct_stop"] and first_end is not None and stop_k is not None
        else None
    )
    latch = next(
        (k for k, x in enumerate(inf) if (x.get("confirmation") or {}).get("phase") == "approach"),
        None,
    )
    if latch is not None and goal is not None:
        d = float(
            np.linalg.norm(
                np.array(m["captures"][max(inf[latch]["frame"] - 1, 0)]["pose"][:2]) - goal
            )
        )
        out["approach_latch"] = {"decision": latch, "goal_distance_m": d, "premature": d > 0.5}
    else:
        out["approach_latch"] = None
    if t["condition"] == "wrong_chain_swap":
        return out
    npose = node_poses(m)
    true = true_nodes(m, npose)
    out["current_off_true"] = sum(
        abs(inf[k]["chain"]["closest_node"] - true[k]) > 1 for k in range(k_end + 1)
    )
    exit_ = (spec.get("recovery") or {}).get("exit") or (spec.get("bounded") or {}).get("lost_exit")
    lost_ks = [k for k in range(k_end + 1) if inf[k]["chain"].get("lost")]
    out["lost_decisions"] = len(lost_ks)
    out["lost_false_global_matches"] = (
        None
        if exit_ is None
        else sum(
            inf[k]["chain"]["argmin_distance"] <= exit_
            and abs(inf[k]["chain"]["argmin_node"] - true[k]) > 1
            for k in lost_ks
        )
    )
    line = np.asarray(m["route"]["waypoints"], float)
    line[:, 1] += m["route"]["scene_index"] * 20.0
    lateral = np.array([to_polyline(np.array(c["pose"][:2]), line) for c in m["captures"]])
    if t["question"] == "look-alike":
        out["ambiguity"] = ambiguity(m, true, lateral, m["topomap"].get("initial_node", 0), close)
    out["recovery"] = recovery(m, true, bool(t.get("start_lost")))
    return out


def goal_xy(cfg: dict, route: str) -> np.ndarray:
    """Scoring goal: the goal image's capture position (evaluation only)."""
    root = Path(cfg["runtime"]["goal_root"])
    goals = json.loads((root / "goal_source.json").read_text())["goals"]
    src = json.loads((root / route / "runtime_manifest.json").read_text())
    return np.array(src["captures"][goals[route]["frame"]]["pose"][:2])


def contacts(rs):
    return sum(bool(x["collision_before_task_end"]) for x in rs)


def exposure(rs):
    path = sum(x["path_length_m"] for x in rs)
    n = contacts(rs)
    return {
        "contacts": n,
        "path_m": path,
        "exposure_s": sum(x["exposure_s"] for x in rs),
        "contacts_per_m": n / path if path else (0.0 if n == 0 else None),
    }


def per_m_le(a_rows, b_rows) -> bool:
    a, b = exposure(a_rows)["contacts_per_m"], exposure(b_rows)["contacts_per_m"]
    return a is not None and (b is None or a <= b)


def compute_gates(cfg: dict, attempts: list, ran: set, globally_ok: bool) -> dict:
    """Stage-2 gates (config gates_to_stage_3)."""

    def rows(tns, v):
        return [
            x for x in attempts if x["trial"] in tns and x["variant"] == v and "correct_stop" in x
        ]

    def planned(tns, v):
        return sum(
            len(cfg["trials"][tn]["routes"]) for tn in tns if v in cfg["trials"][tn]["variants"]
        )

    def complete(tns, vs):
        rs = [x for x in attempts if x["trial"] in tns and x["variant"] in vs]
        return (
            globally_ok
            and all(tn in ran for tn in tns)  # every declared trial of the question analysed
            and all(x.get("integrity_ok") for x in rs)
            and all(len(rows(tns, v)) == planned(tns, v) for v in vs)
        )

    def q(question):
        # All declared trials of the question, never only those named on the command line.
        tns = sorted(tn for tn in cfg["trials"] if cfg["trials"][tn]["question"] == question)
        return tns if set(tns) & ran else []

    gates = {}
    amb = q("look-alike")
    if amb:
        ra, rb = rows(amb, "A_baseline"), rows(amb, "B1_bounded")
        b_enc = [e for x in rb for e in x["ambiguity"]["encounters"]]
        evaluable = [e for e in b_enc if e["outcome"] != "NOT_EVALUABLE"]
        g = {
            "complete": complete(amb, ["A_baseline", "B1_bounded"]),
            "A_follows_in_some_trial": any(x["ambiguity"]["followed"] for x in ra),
            "B1_evaluable_encounters": len(evaluable),
            "B1_corrects_every_evaluable_encounter": bool(evaluable)
            and all(e["outcome"] == "corrected" for e in evaluable),
            "B1_contacts_le_A": contacts(rb) <= contacts(ra),
            "exposure": {"A_baseline": exposure(ra), "B1_bounded": exposure(rb)},
        }
        if not g["complete"]:
            g["status"] = "INCOMPLETE"
        elif not g["A_follows_in_some_trial"] or not evaluable:
            g["status"] = "NOT_TESTED"
        else:
            ok = g["B1_corrects_every_evaluable_encounter"] and g["B1_contacts_le_A"]
            g["status"] = "PASS" if ok else "FAIL"
        gates["B1_bounded"] = g
    kid = q("recovery")
    if kid:
        uninf = [tn for tn in kid if cfg["trials"][tn].get("uninformative_view")]

        def succ(tns, v):
            return sum(x["recovery"]["first_entry_success"] for x in rows(tns, v))

        r2, bx = rows(kid, "R2_recover"), rows(kid, "B1x_exit")
        g = {
            "complete": complete(kid, ["B1_bounded", "B1x_exit", "R2_recover"]),
            "R2_uninformative_successes": succ(uninf, "R2_recover"),
            "B1x_uninformative_successes": succ(uninf, "B1x_exit"),
            "R2_all_successes": succ(kid, "R2_recover"),
            "B1x_all_successes": succ(kid, "B1x_exit"),
            "B1_all_successes": succ(kid, "B1_bounded"),
            "R2_wrong_stops": sum(x["wrong_stop"] for x in r2),
            "B1x_wrong_stops": sum(x["wrong_stop"] for x in bx),
            "exposure": {
                v: exposure(rows(kid, v)) for v in ("B1_bounded", "B1x_exit", "R2_recover")
            },
        }
        ok = (
            g["R2_uninformative_successes"] >= 6
            and g["R2_uninformative_successes"] > g["B1x_uninformative_successes"]
            and g["R2_all_successes"] >= g["B1x_all_successes"]
            and g["R2_wrong_stops"] <= g["B1x_wrong_stops"]
            and contacts(r2) <= contacts(bx)
            and per_m_le(r2, bx)
        )
        g["status"] = "INCOMPLETE" if not g["complete"] else ("PASS" if ok else "FAIL")
        gates["R2_recover"] = g
    arr, pre = q("arrival recognition"), q("premature confirmation")
    if arr or pre:
        vs = ["A_baseline", "C1_verify", "V2a_confirm", "V2b_confirm_steer"]
        summary = {}
        for name, tns in (("arrival_truncated", arr), ("premature_true", pre)):
            summary[name] = {
                v: {
                    "correct": sum(x["correct_stop"] for x in rows(tns, v)),
                    "wrong": sum(x["wrong_stop"] for x in rows(tns, v)),
                    "abstained": sum(bool(x["abstained"]) for x in rows(tns, v)),
                    "timeouts": sum(x["timeout"] and not x["abstained"] for x in rows(tns, v)),
                    "premature_latches": sum(
                        bool((x.get("approach_latch") or {}).get("premature")) for x in rows(tns, v)
                    ),
                    **exposure(rows(tns, v)),
                    "n": len(rows(tns, v)),
                }
                for v in vs
            }
        done = complete(arr + pre, vs) and bool(arr) and bool(pre)
        for v in ("V2a_confirm", "V2b_confirm_steer"):
            a_, p_ = summary["arrival_truncated"], summary["premature_true"]
            ok = (
                a_[v]["correct"] >= 3
                and a_[v]["wrong"] == 0
                and a_[v]["contacts"] <= a_["A_baseline"]["contacts"]
                and a_[v]["correct"] > a_["C1_verify"]["correct"]
                and p_[v]["wrong"] == 0
            )
            gates[v] = {"status": "INCOMPLETE" if not done else ("PASS" if ok else "FAIL")}
        gates["V2_summary"] = summary
        gates["V2b_vs_V2a (descriptive)"] = {
            k: {
                f: summary[k]["V2b_confirm_steer"][f] - summary[k]["V2a_confirm"][f]
                for f in ("correct", "wrong", "contacts")
            }
            for k in summary
        }
    return gates


def required_stage3(passed: set) -> set:
    """Variants stage 3 runs: passing components, A, their counterparts (R2 also B1, reported)."""
    req = set(passed) | {"A_baseline"} | {COUNTERPART[c] for c in passed}
    if "R2_recover" in passed:
        req.add("B1_bounded")
    return req


def stage3_decisions(cfg: dict, attempts: list, ran: set, passed: set, globally_ok: bool) -> dict:
    """Stage-3 retain / revise / INCOMPLETE (config stage_3_criteria)."""
    tns = sorted(tn for tn in cfg["trials"] if cfg["trials"][tn]["stage"] == 3)
    if not set(tns) & ran or not passed:
        return {}
    required = required_stage3(passed)

    def rows(cond, v):
        return [
            x
            for x in attempts
            if x["trial"] in tns
            and cfg["trials"][x["trial"]]["condition"] == cond
            and x["variant"] == v
            and "correct_stop" in x
        ]

    def planned(cond, v):
        return sum(
            len(cfg["trials"][tn]["routes"])
            for tn in tns
            if cfg["trials"][tn]["condition"] == cond and v in cfg["trials"][tn]["variants"]
        )

    conds_all = ("true_chain", "truncated_chain", "wrong_chain_swap")
    rs3 = [x for x in attempts if x["trial"] in tns and x["variant"] in required]
    complete = (
        globally_ok
        and all(tn in ran for tn in tns)
        and all(x.get("integrity_ok") for x in rs3)
        and all(len(rows(c, v)) == planned(c, v) for c in conds_all for v in required)
    )
    out = {}
    for comp in sorted(passed):
        cp = COUNTERPART[comp]
        conds, not_tested = {}, []
        retain = True
        for cond in conds_all:
            c, k, a = rows(cond, comp), rows(cond, cp), rows(cond, "A_baseline")
            if not c or not k or not a:
                conds[cond] = "MISSING"
                continue
            reg = not (
                contacts(c) <= contacts(k)
                and contacts(c) <= contacts(a)
                and per_m_le(c, k)
                and per_m_le(c, a)
            )
            cs = {v: sum(x["correct_stop"] for x in rs) for v, rs in (("c", c), ("k", k))}
            ws = {v: sum(x["wrong_stop"] for x in rs) for v, rs in (("c", c), ("k", k))}
            if comp in ("V2a_confirm", "V2b_confirm_steer"):
                primary = cs["c"] >= cs["k"] and ws["c"] <= ws["k"]
                if cond == "true_chain":
                    primary = primary and ws["c"] == 0
                if cs["c"] == cs["k"] == 0 and ws["c"] == ws["k"] == 0:
                    not_tested.append(f"{cond}: no stops in either arm")
            elif comp == "R2_recover":
                if cond == "wrong_chain_swap":
                    not_tested.append(f"{cond}: recovery (no pose-true node on a swapped chain)")
                    primary = ws["c"] <= ws["k"]
                else:
                    lost_c = sum(x["recovery"]["lost_entries"] for x in c if "recovery" in x)
                    lost_k = sum(x["recovery"]["lost_entries"] for x in k if "recovery" in x)
                    if lost_c == 0 and lost_k == 0:
                        not_tested.append(f"{cond}: recovery (no lost entries)")
                        primary = ws["c"] <= ws["k"]
                    else:
                        sc = sum(x["recovery"]["successes"] for x in c if "recovery" in x)
                        sk = sum(x["recovery"]["successes"] for x in k if "recovery" in x)
                        primary = sc >= sk and ws["c"] <= ws["k"]
            else:
                primary = cs["c"] >= cs["k"]
                if cs["c"] == cs["k"] == 0:
                    not_tested.append(f"{cond}: no correct stops in either arm")
            conds[cond] = {
                "contact_regression": reg,
                "primary_ok": primary,
                "exposure": {
                    v: exposure(rows(cond, v))
                    for v in sorted(
                        {comp, cp, "A_baseline"}
                        | ({"B1_bounded"} if comp == "R2_recover" else set())
                    )
                },
            }
            retain = retain and not reg and primary
        decision = "INCOMPLETE" if not complete else ("RETAIN" if retain else "REVISE")
        out[comp] = {
            "counterpart": cp,
            "reported_also": ["B1_bounded"] if comp == "R2_recover" else [],
            "conditions": conds,
            "not_tested": not_tested,
            "decision": decision,
            "complete": complete,
        }
    return out


def load_stage2(cfg: dict, cfg_sha: str, a, p) -> tuple[set, int]:
    """Admission to stage 3 from a committed stage-2 gate record, recomputed and checked."""
    if not (a.stage2_commit and a.stage2_path):
        p.error("stage-3 trials need --stage2-commit and --stage2-path")
    blob = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{a.stage2_commit}:{a.stage2_path}"],
        capture_output=True,
    )
    if blob.returncode:
        p.error("stage-2 record not found at that commit")
    s2 = json.loads(blob.stdout)
    stage2_trials = {tn for tn, t in cfg["trials"].items() if t["stage"] == 2}
    problems = [
        k
        for k, ok in {
            "freeze_commit": s2.get("freeze_commit") == a.freeze_commit,
            "config_sha256": s2.get("config_sha256") == cfg_sha,
            "negative_control": s2.get("negative_control") is None,
            "all_stage2_trials": stage2_trials <= set(s2.get("trials_analysed", [])),
        }.items()
        if not ok
    ]
    recomputed = compute_gates(cfg, s2["attempts"], set(s2["trials_analysed"]), s2["globally_ok"])
    status = {k: g.get("status") for k, g in recomputed.items() if isinstance(g, dict)}
    if status != {k: g.get("status") for k, g in s2["gates"].items() if isinstance(g, dict)}:
        problems.append("gates_do_not_recompute")
    if problems:
        p.error(f"stage-2 record refused: {problems}")
    commit_time = int(
        subprocess.run(
            ["git", "-C", str(REPO), "log", "-1", "--format=%ct", a.stage2_commit],
            capture_output=True,
            text=True,
        ).stdout
    )
    return {k for k, st in status.items() if st == "PASS"}, commit_time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--freeze-commit", required=True)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--trial", action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--stage2-commit", help="commit holding the stage-2 gate record")
    p.add_argument("--stage2-path", help="repo path of the stage-2 gate record at that commit")
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
    stage3 = [tn for tn in a.trial if cfg["trials"][tn]["stage"] == 3]
    passed: set = set()
    stage2_time = None
    cfg_sha = hashlib.sha256(a.config.read_bytes()).hexdigest()
    if stage3:
        passed, stage2_time = load_stage2(cfg, cfg_sha, a, p)
    ctx = {
        "cfg": cfg,
        "cfg_sha": cfg_sha,
        "freeze_time": int(
            subprocess.run(
                ["git", "-C", str(REPO), "log", "-1", "--format=%ct", a.freeze_commit],
                capture_output=True,
                text=True,
            ).stdout
        ),
        "qual_sha": hashlib.sha256(Path(cfg["runtime"]["qualification"]).read_bytes()).hexdigest(),
        "cache": {},
        "nonrepo": [],
    }
    audit = {(r["collection"], r["route"]): r for r in json.loads(a.audit.read_text())["rows"]}
    variants = list(cfg["variants"])
    close = cfg["runtime"]["close_threshold"]
    attempts, failures, logs = [], [], {}
    for trial in a.trial:
        t = cfg["trials"][trial]
        cond = cfg["conditions"][t["condition"]]
        for v in t["variants"]:
            if t["stage"] == 3 and v not in required_stage3(passed):
                continue  # not required: the protocol does not run it in stage 3
            shifted = variants[(variants.index(v) + 1) % len(variants)]
            spec = cfg["variants"][shifted if a.negative_control == "variant" else v]
            counted, log, violations = discover(trial, v, t["routes"])
            logs[f"{trial}/{v}"] = log
            for route, why in violations:
                failures.append((f"{trial}/{v}", route, [why]))
            for route in t["routes"]:
                att = {"trial": trial, "variant": v, "route": route}
                if route not in counted:
                    att["status"] = "NO_PASS_ATTEMPT"
                    failures.append((f"{trial}/{v}", route, ["no PASS attempt"]))
                    attempts.append(att)
                    continue
                root, _ = counted[route]
                att.update(status="PASS", collection=root.name)
                m = json.loads((root / route / "runtime_manifest.json").read_text())
                try:
                    checks = attempt_checks(
                        a.negative_control, a.freeze_commit, t, trial, cond, spec, v, m, root, ctx
                    )
                except (KeyError, TypeError, IndexError) as exc:
                    checks = {"manifest_fields": False}
                    att["manifest_error"] = repr(exc)
                if stage2_time is not None and t["stage"] == 3:
                    checks["launched_after_stage2_commit"] = (
                        root / "frozen_routes.json"
                    ).stat().st_mtime > stage2_time
                r = audit.get((root.name, route))
                checks["audited"] = r is not None and "measures" in r
                gi = (r or {}).get("goal_identity") or {}
                checks["goal_identity"] = bool(gi) and all(
                    x for x in gi.values() if isinstance(x, bool)
                )
                att["checks"] = checks
                att["integrity_ok"] = all(checks.values())
                if not att["integrity_ok"]:
                    failures.append(
                        (root.name, route, sorted(k for k, ok in checks.items() if not ok))
                    )
                if r is not None and "manifest_fields" not in checks:
                    att.update(measures(m, r, t, spec, close, goal_xy(cfg, route)))
                attempts.append(att)
    nonrepo = ctx["nonrepo"]
    globally_ok = not nonrepo or all(n == nonrepo[0] for n in nonrepo)
    if not globally_ok:
        failures.append(("all", "all", ["nonrepo_influencing_files"]))
    per_check: dict = {}
    for _, _, ks in failures:
        for k in ks:
            per_check[k] = per_check.get(k, 0) + 1
    ran = set(a.trial)
    gates = compute_gates(cfg, attempts, ran, globally_ok)
    decisions = stage3_decisions(cfg, attempts, ran, passed, globally_ok)
    out = {
        "scope": "component_comparison_v2 development",
        "freeze_commit": a.freeze_commit,
        "config_sha256": ctx["cfg_sha"],
        "negative_control": a.negative_control,
        "trials_analysed": sorted(a.trial),
        "globally_ok": globally_ok,
        "attempt_log": logs,
        "attempts": attempts,
        "integrity_failures": failures,
        "integrity_failures_per_check": per_check,
        "gates": gates,
        "stage3": decisions,
    }
    a.out.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(
        json.dumps(
            {
                "attempts": len(attempts),
                "integrity_failures_per_check": per_check,
                "gates": {k: g.get("status") for k, g in gates.items() if isinstance(g, dict)},
                "stage3": {k: d["decision"] for k, d in decisions.items()},
            },
            indent=1,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
