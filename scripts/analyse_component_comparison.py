"""Integrity, outcomes, oscillation and look-alike mechanism analysis for component_comparison_v1.

Analysis definitions, not part of the frozen protocol. They were written during collection,
before the scored outcomes were read; one termination label (A true s_bend_run_0000, timeout)
had been seen. Treat them as post-freeze analysis definitions, not pre-registered ones:
- oscillation: a verification-pending run that ends without acceptance because the
  chain's reached_goal fell back (verification state pending -> None).
- look-alike proposal (s_bend true chain only; pose used for evaluation only): a decision
  whose argmin node is >= 3 nodes from the pose-true nearest node while the current node
  is within 1 of it (correctly localised, then offered a distant node).
  'followed' if the followed node that decision is >1 node from the pose-true node,
  'corrected' otherwise. An attempt with no such proposal: not encountered.

Integrity also covers non-repo influencing files (identical across all attempts), inference
completeness (one decision every 6 frames from frame 0, through the budget for timeouts), and
launch after the freeze commit (frozen_routes.json mtime). `--negative-control` checks every
attempt against the next variant's expectations and a wrong chain hash; it must fail.
"""

import collections
import hashlib
import itertools
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

E = Path("/home/favl/navfm-runtime-evidence")
REPO = Path("/home/favl/projects/navfm-engineering-recording")
CFG = json.loads(
    subprocess.run(
        ["git", "-C", str(REPO), "show", "21654ca:configs/eval/component_comparison_v1.json"],
        capture_output=True,
        text=True,
    ).stdout
)
CFG_SHA = "4336aa84d9bdd7f22f142546b5e5dd2f82ca29cfc225bbc293189eab54cdb658"
audit = json.loads(Path(sys.argv[1]).read_text())
NEGATIVE = "--negative-control" in sys.argv[3:]
FREEZE_TIME = int(
    subprocess.run(
        ["git", "-C", str(REPO), "log", "-1", "--format=%ct", "21654ca"],
        capture_output=True,
        text=True,
    ).stdout
)
PERIOD = 6
VARS = ["A_baseline", "B_bounded", "C_verify", "D_both"]
JOBS = {
    "true": "true_chain",
    "trunc": "truncated_chain",
    "swap": "wrong_chain_swap",
    "rep": "true_chain",
}
PLAN = {
    "true": CFG["routes"],
    "trunc": CFG["routes"],
    "swap": CFG["conditions"]["wrong_chain_swap"]["routes"],
    "rep": CFG["repeats"]["routes"],
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


blob = {}


def at(rel, commit="21654ca"):
    if (commit, rel) not in blob:
        r = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{rel}"], capture_output=True)
        blob[commit, rel] = hashlib.sha256(r.stdout).hexdigest()
    return blob[commit, rel]


rows = {(r["collection"], r["route"]): r for r in audit["rows"]}
qual_sha = sha(CFG["runtime"]["qualification"])
ck_sha = CFG["checkpoint"].get("sha256")
out = {"attempts": [], "integrity_failures": []}
for v in VARS:
    vc = CFG["variants"][VARS[(VARS.index(v) + 1) % 4] if NEGATIVE else v]
    for job, cond in JOBS.items():
        coll = f"cmp-{v}-{job}-20261009-01"
        root = E / coll
        launched_after_freeze = (root / "frozen_routes.json").stat().st_mtime > FREEZE_TIME
        cj = (
            json.loads((root / "collection.json").read_text())
            if (root / "collection.json").exists()
            else {"episodes": []}
        )
        eps = {e["id"]: e for e in cj["episodes"]}
        for route in PLAN[job]:
            e = eps.get(route)
            att = {"variant": v, "job": job, "condition": cond, "route": route, "collection": coll}
            if e is None:
                att["status"] = "NEVER_RUN"
                out["attempts"].append(att)
                continue
            att["status"] = e["status"]
            if e["status"] != "PASS":
                out["attempts"].append(att)
                continue
            m = json.loads((root / route / "runtime_manifest.json").read_text())
            checks = {}
            checks["variant"] = m["component_variant"]["variant"] == v
            checks["config_sha"] = m["component_variant"]["comparison_config_sha256"] == CFG_SHA
            checks["checkpoint"] = ck_sha is None or m["policy"]["sha256"] == ck_sha
            checks["chain_root"] = str(Path(m["topomap"]["root"]).resolve()) == str(
                Path(CFG["conditions"][cond]["root"]).resolve()
            )
            expected_chain = "0" * 64 if NEGATIVE else CFG["conditions"][cond]["chain_json_sha256"]
            checks["chain_sha"] = m["topomap"]["chain_json_sha256"] == expected_chain
            checks["launched_after_freeze"] = launched_after_freeze
            pt = m["policy"]["topomap"]
            checks["bounded"] = pt["bounded"] == vc["bounded"]
            checks["close_threshold"] = pt["close_threshold"] == CFG["runtime"]["close_threshold"]
            checks["verify"] = pt["verify_threshold"] == vc["verify_threshold"] and (
                vc["verify_threshold"] is None
                or pt["verify_persistence"] == vc["verify_persistence"]
            )
            checks["radius"] = pt["radius"] == CFG["runtime"]["radius"]
            checks["max_steps"] = m.get("max_steps") == CFG["runtime"]["budget_frames"]
            checks["qualification"] = m.get("qualification_sha256") == qual_sha
            obs = None
            stack = [m]
            while stack:
                x = stack.pop()
                if isinstance(x, dict):
                    if x.get("name") == "influencing_file_digests" and isinstance(
                        x.get("observed"), dict
                    ):
                        obs = x["observed"]
                    stack.extend(x.values())
                elif isinstance(x, list):
                    stack.extend(x)
            rf = {
                p.split(str(REPO) + "/", 1)[1]: d
                for p, d in (obs or {}).items()
                if p.startswith(str(REPO) + "/")
            }
            checks["source_21654ca"] = bool(rf) and all(at(r) == d for r, d in rf.items())
            att["repo_files"] = len(rf)
            att["repo_files_matching_8321e9c"] = sum(at(r, "8321e9c") == d for r, d in rf.items())
            att["nonrepo_files"] = {
                p: d for p, d in (obs or {}).items() if not p.startswith(str(REPO) + "/")
            }
            frames = [x["frame"] for x in m["inference"]]
            checks["inference_complete"] = frames == list(
                range(0, PERIOD * len(frames), PERIOD)
            ) and (
                m.get("policy_stop_frame") is not None
                or frames[-1] >= CFG["runtime"]["budget_frames"] - PERIOD
            )
            r = rows.get((coll, route))
            checks["audited"] = r is not None and "measures" in r
            gi = (r or {}).get("goal_identity") or {}
            checks["goal_identity"] = bool(gi) and all(
                val for k, val in gi.items() if isinstance(val, bool)
            )
            att["checks"] = checks
            if not all(checks.values()):
                out["integrity_failures"].append(
                    (coll, route, [k for k, ok in checks.items() if not ok])
                )
            if r is None:
                out["attempts"].append(att)
                continue
            ms = r["measures"]
            comp = r["components"]
            att.update(
                {
                    k: ms[k]
                    for k in [
                        "correct_stop",
                        "wrong_stop",
                        "timeout",
                        "navigation_success",
                        "collision_before_task_end",
                        "contact_after_stop",
                        "stop_goal_distance_m",
                        "min_goal_distance_m",
                        "final_goal_distance_m",
                        "settle",
                        "route_departure_frame",
                    ]
                }
            )
            inf = m["inference"]
            ver = [x.get("verification") for x in inf]
            osc = sum(1 for a, b in itertools.pairwise(ver) if a == "pending" and b is None)
            att["pending_decisions"] = ver.count("pending")
            att["oscillations"] = osc
            att["chain_end_declarations"] = sum(
                1
                for a, b in itertools.pairwise([False, *(x["chain"]["reached_goal"] for x in inf)])
                if b and not a
            )
            att["verification_delay"] = comp["verification_delay"]
            att["lost_decisions"] = comp["lost_decisions"]
            att["events"] = comp["events"]
            att["jumps"] = comp["localisation_jumps"]
            if cond != "wrong_chain_swap":
                att["closest_off_true"] = comp["decisions_closest_off_true_node"]
                att["followed_off_true"] = comp["decisions_followed_off_true_node"]
            else:
                att["closest_off_true"] = att["followed_off_true"] = (
                    "NOT_APPLICABLE (chain from another scene)"
                )
            # Look-alike mechanism, true chain s_bend only.
            if cond == "true_chain" and route.startswith("s_bend"):
                chain = json.loads((Path(m["topomap"]["root"]) / "chain.json").read_text())[
                    "routes"
                ][route]
                teach = json.loads((Path(chain["traversal"]) / "runtime_manifest.json").read_text())
                npose = np.array(
                    [teach["captures"][n["frame"]]["pose"][:2] for n in chain["nodes"]]
                )
                props = []
                for k, x in enumerate(inf):
                    c = x["chain"]
                    xy = np.array(m["captures"][x["frame"]]["pose"][:2])
                    true = int(np.argmin(np.linalg.norm(npose - xy, axis=1)))
                    prev_closest = inf[k - 1]["chain"]["closest_node"] if k else 0
                    if abs(c["argmin_node"] - true) >= 3 and abs(prev_closest - true) <= 1:
                        props.append(
                            {
                                "decision": k,
                                "true": true,
                                "prev_closest": prev_closest,
                                "argmin": c["argmin_node"],
                                "argmin_distance": round(c["argmin_distance"], 3),
                                "event": c.get("event", "upstream"),
                                "closest_after": c["closest_node"],
                                "followed": c["followed_node"],
                                "outcome": "followed"
                                if abs(c["followed_node"] - true) > 1
                                else "corrected",
                            }
                        )
                att["lookalike"] = {
                    "proposals": props,
                    "encountered": bool(props),
                    "followed": sum(p["outcome"] == "followed" for p in props),
                    "corrected": sum(p["outcome"] == "corrected" for p in props),
                }
            out["attempts"].append(att)
nonrepo = [a.pop("nonrepo_files") for a in out["attempts"] if "nonrepo_files" in a]
out["nonrepo_influencing_files"] = {
    "files": len(nonrepo[0]) if nonrepo else 0,
    "identical_across_attempts": bool(nonrepo) and all(n == nonrepo[0] for n in nonrepo),
    "digests": nonrepo[0] if nonrepo else None,
}
if not out["nonrepo_influencing_files"]["identical_across_attempts"]:
    out["integrity_failures"].append(("all", "all", ["nonrepo_influencing_files"]))
out["negative_control"] = NEGATIVE
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, default=str) + "\n")
print(
    "attempts",
    len(out["attempts"]),
    "status",
    collections.Counter(a["status"] for a in out["attempts"]),
)
print("integrity failures", out["integrity_failures"])
