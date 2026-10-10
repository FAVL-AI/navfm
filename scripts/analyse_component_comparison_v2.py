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


def ambiguity(m: dict, true: list[int], lateral: np.ndarray, initial_node: int) -> dict:
    """Encounter / correction / followed / avoidance (frozen definitions)."""
    inf = m["inference"]
    encounters = []
    for k, r in enumerate(inf):
        c = r["chain"]
        prev = inf[k - 1]["chain"]["closest_node"] if k else initial_node
        if c.get("lost") or "argmin_node" not in c:
            continue
        if abs(c["argmin_node"] - true[k]) >= 3 and abs(prev - true[k]) <= 1:
            followed = abs(c["followed_node"] - true[k]) > 1
            nxt = range(k + 1, min(k + 1 + AFTER, len(inf)))
            held = all(abs(inf[j]["chain"]["closest_node"] - true[j]) <= 1 for j in nxt)
            encounters.append(
                {
                    "decision": k,
                    "true": true[k],
                    "prev_current": prev,
                    "argmin": c["argmin_node"],
                    "argmin_distance": c["argmin_distance"],
                    "event": c.get("event", "upstream"),
                    "followed_node": c["followed_node"],
                    "outcome": "followed"
                    if followed
                    else ("corrected" if held else "withheld_then_lost_track"),
                }
            )
    first = inf[encounters[0]["decision"]]["frame"] if encounters else 0
    after = lateral[first:]
    return {
        "encountered": bool(encounters),
        "encounters": encounters,
        "followed": sum(e["outcome"] == "followed" for e in encounters),
        "corrected": sum(e["outcome"] == "corrected" for e in encounters),
        "withheld_then_lost_track": sum(
            e["outcome"] == "withheld_then_lost_track" for e in encounters
        ),
        "status": "NOT_TESTED (avoidance)" if not encounters else "TESTED",
        "departure_after_first": bool((after > 0.5).any()),
        "max_lateral_after_first_m": float(after.max()) if len(after) else None,
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
        reentry = any(lost[j] for j in range(reloc + 1, min(reloc + 1 + AFTER, len(inf))))
        out.append(
            {
                "entry": k0,
                "relocalised": reloc,
                "node": node,
                "true": true[reloc],
                "event": inf[reloc]["chain"].get("event"),
                "decisions_lost": reloc - k0,
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--freeze-commit", required=True)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--trial", action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--negative-control", action="store_true")
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
    cfg_sha = hashlib.sha256(a.config.read_bytes()).hexdigest()
    freeze_time = int(
        subprocess.run(
            ["git", "-C", str(REPO), "log", "-1", "--format=%ct", a.freeze_commit],
            capture_output=True,
            text=True,
        ).stdout
    )
    audit = {(r["collection"], r["route"]): r for r in json.loads(a.audit.read_text())["rows"]}
    qual_sha = hashlib.sha256(Path(cfg["runtime"]["qualification"]).read_bytes()).hexdigest()
    variants = list(cfg["variants"])
    cache: dict = {}
    attempts, failures, nonrepo = [], [], []
    for trial in a.trial:
        t = cfg["trials"][trial]
        cond = cfg["conditions"][t["condition"]]
        for v in t["variants"]:
            coll = f"v2-{trial}-{v}-{a.tag}"
            root = E / coll
            spec = cfg["variants"][
                variants[(variants.index(v) + 1) % len(variants)] if a.negative_control else v
            ]
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
                    attempts.append(att)
                    continue
                att["status"] = "PASS"
                m = json.loads((root / route / "runtime_manifest.json").read_text())
                pt = m["policy"]["topomap"]
                checks = {
                    "variant": m["component_variant"]["variant"] == v,
                    "config_sha": m["component_variant"]["comparison_config_sha256"] == cfg_sha,
                    "checkpoint": m["policy"]["sha256"] == cfg["checkpoint"]["sha256"],
                    "chain_root": str(Path(m["topomap"]["root"]).resolve())
                    == str(Path(cond["root"]).resolve()),
                    "chain_sha": m["topomap"]["chain_json_sha256"]
                    == ("0" * 64 if a.negative_control else cond["chain_json_sha256"]),
                    "bounded": pt["bounded"] == spec["bounded"],
                    "verify": pt["verify_threshold"] == spec["verify_threshold"],
                    "confirmation": pt.get("confirmation") == spec.get("confirmation"),
                    "recovery": pt.get("recovery") == spec.get("recovery"),
                    "start_lost": bool(pt.get("start_lost")) == bool(t.get("start_lost")),
                    "radius": pt["radius"] == cfg["runtime"]["radius"],
                    "close_threshold": pt["close_threshold"] == cfg["runtime"]["close_threshold"],
                    "budget": m.get("max_steps")
                    == t.get("budget_frames", cfg["runtime"]["budget_frames"]),
                    "qualification": m.get("qualification_sha256") == qual_sha,
                    "launched_after_freeze": (root / "frozen_routes.json").stat().st_mtime
                    > freeze_time,
                    "perturbation": [
                        m["start_perturbation"][k] for k in ("arc_fraction", "lateral_m", "yaw_deg")
                    ]
                    == t.get("perturbation", [0.0, 0.0, 0.0]),
                }
                obs = influencing(m)
                rf = {
                    q.split(str(REPO) + "/", 1)[1]: d
                    for q, d in obs.items()
                    if q.startswith(str(REPO) + "/")
                }
                checks["source_at_freeze"] = bool(rf) and all(
                    git_blob_sha(a.freeze_commit, r, cache) == d for r, d in rf.items()
                )
                nonrepo.append({q: d for q, d in obs.items() if not q.startswith(str(REPO) + "/")})
                frames = [r["frame"] for r in m["inference"]]
                end = m.get("policy_stop_frame")
                end = end if end is not None else m.get("policy_abstain_frame")
                checks["inference_complete"] = frames == list(
                    range(0, PERIOD * len(frames), PERIOD)
                ) and (end is not None or frames[-1] >= m["max_steps"] - PERIOD)
                resume = m.get("resume")
                if t.get("resume_from"):
                    rm_path = Path(t["resume_from"])
                    rm = json.loads((rm_path / "runtime_manifest.json").read_text())
                    K = t["resume_decision"]
                    checks["resume"] = (
                        resume is not None
                        and resume["episode"] == str(rm_path.resolve())
                        and resume["decision"] == K
                        and resume["initial_node"]
                        == rm["inference"][K - 1]["chain"]["closest_node"]
                        and pt.get("initial_node") == resume["initial_node"]
                        and resume["history_sha256"]
                        == [
                            hashlib.sha256(
                                (rm_path / "trajectory" / f"{q}.jpg").read_bytes()
                            ).hexdigest()
                            for q in resume["history_frames"]
                        ]
                    )
                else:
                    checks["resume"] = resume is None
                r = audit.get((coll, route))
                checks["audited"] = r is not None and "measures" in r
                gi = (r or {}).get("goal_identity") or {}
                checks["goal_identity"] = bool(gi) and all(
                    x for x in gi.values() if isinstance(x, bool)
                )
                att["checks"] = checks
                if not all(checks.values()):
                    failures.append((coll, route, sorted(k for k, ok in checks.items() if not ok)))
                if r is None:
                    attempts.append(att)
                    continue
                ms = r["measures"]
                inf = m["inference"]
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
                        abs(x["chain"]["closest_node"] - tn) > 1
                        for x, tn in zip(inf, true, strict=True)
                    )
                    caps = m["captures"]
                    line = np.asarray(m["route"]["waypoints"], float)
                    line[:, 1] += m["route"]["scene_index"] * 20.0
                    lateral = np.array([to_polyline(np.array(c["pose"][:2]), line) for c in caps])
                    if t["question"] == "look-alike":
                        att["ambiguity"] = ambiguity(m, true, lateral, pt.get("initial_node", 0))
                    att["recovery"] = recovery(m, true, bool(t.get("start_lost")))
                attempts.append(att)
    if nonrepo and not all(n == nonrepo[0] for n in nonrepo):
        failures.append(("all", "all", ["nonrepo_influencing_files"]))

    def rows(trial_prefix, variant):
        return [
            x
            for x in attempts
            if x["trial"].startswith(trial_prefix)
            and x["variant"] == variant
            and "correct_stop" in x
        ]

    def contacts(rs):
        return sum(bool(x["collision_before_task_end"]) for x in rs)

    gates = {}
    amb_a, amb_b = rows("ambiguity_", "A_baseline"), rows("ambiguity_", "B1_bounded")
    if amb_a or amb_b:
        b_enc = [e for x in amb_b for e in x["ambiguity"]["encounters"]]
        gates["B1_bounded"] = {
            "A_follows_in_some_trial": any(x["ambiguity"]["followed"] for x in amb_a),
            "B1_encounters": bool(b_enc),
            "B1_corrects_every_encounter": bool(b_enc)
            and all(e["outcome"] == "corrected" for e in b_enc),
            "B1_contacts_le_A": contacts(amb_b) <= contacts(amb_a),
            "trials": [len(amb_a), len(amb_b)],
        }
        gates["B1_bounded"]["pass"] = all(
            v for k, v in gates["B1_bounded"].items() if k != "trials"
        )
        if not gates["B1_bounded"]["B1_encounters"]:
            gates["B1_bounded"]["status"] = "NOT_TESTED"
    kid_b, kid_r = rows("kidnapped_", "B1_bounded"), rows("kidnapped_", "R2_recover")
    if kid_b or kid_r:
        gates["R2_recover"] = {
            "R2_first_entry_successes": sum(x["recovery"]["first_entry_success"] for x in kid_r),
            "B1_first_entry_successes": sum(x["recovery"]["first_entry_success"] for x in kid_b),
            "trials": [len(kid_b), len(kid_r)],
            "R2_contacts": contacts(kid_r),
            "B1_contacts": contacts(kid_b),
        }
        g = gates["R2_recover"]
        g["pass"] = g["R2_first_entry_successes"] >= 6 and g["R2_contacts"] <= g["B1_contacts"]
    arr = {v: rows("arrival_truncated", v) for v in ("A_baseline", "C1_verify", "V2_confirm")}
    if any(arr.values()):
        g = {
            v: {
                "correct": sum(x["correct_stop"] for x in rs),
                "wrong": sum(x["wrong_stop"] for x in rs),
                "contacts": contacts(rs),
                "abstained": sum(bool(x["abstained"]) for x in rs),
                "timeouts": sum(x["timeout"] and not x["abstained"] for x in rs),
                "n": len(rs),
            }
            for v, rs in arr.items()
        }
        g["pass"] = (
            g["V2_confirm"]["correct"] >= 3
            and g["V2_confirm"]["wrong"] == 0
            and g["V2_confirm"]["contacts"] <= g["A_baseline"]["contacts"]
        )
        gates["V2_confirm"] = g
    out = {
        "scope": "component_comparison_v2 development",
        "freeze_commit": a.freeze_commit,
        "config_sha256": cfg_sha,
        "negative_control": a.negative_control,
        "attempts": attempts,
        "integrity_failures": failures,
        "gates": gates,
    }
    a.out.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(
        json.dumps(
            {"attempts": len(attempts), "integrity_failures": failures, "gates": gates},
            indent=1,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
