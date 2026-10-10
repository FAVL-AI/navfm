"""Definitions computed by scripts/analyse_component_comparison_v2.py (frozen in the v2 config)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyse_component_comparison_v2 as v2


def rec(argmin, closest, followed, dist=5.0, lost=False, stop=False):
    return {
        "chain": {
            "argmin_node": argmin,
            "argmin_distance": dist,
            "closest_node": closest,
            "followed_node": followed,
            "lost": lost,
        },
        "policy_stop": stop,
        "frame": 0,
    }


def manifest(records):
    for k, r in enumerate(records):
        r["frame"] = 6 * k
    return {"inference": records}


def lateral(n):
    return np.zeros(6 * n + 1)


def test_decision_zero_encounter_uses_the_resumed_initial_node():
    # Red-team H2: the d22 start meets the look-alike on its first decision.
    recs = [rec(10, 10, 10)] + [rec(11, 11, 11) for _ in range(12)]
    out = v2.ambiguity(manifest(recs), [5] * 13, lateral(13), initial_node=5, close=3.0)
    assert out["encountered"] and out["encounters"][0]["decision"] == 0
    assert out["followed"] == 1
    missed = v2.ambiguity(manifest(recs), [5] * 13, lateral(13), initial_node=0, close=3.0)
    assert not missed["encountered"]


def test_correction_needs_the_full_horizon_before_the_task_end():
    held = [rec(10, 5, 6)] + [rec(5, 5, 6) for _ in range(10)]
    out = v2.ambiguity(manifest(held), [5] * 11, lateral(11), initial_node=5, close=3.0)
    assert out["corrected"] == 1
    short = [rec(10, 5, 6)] + [rec(5, 5, 6) for _ in range(4)] + [rec(5, 5, 6, stop=True)]
    out = v2.ambiguity(manifest(short), [5] * 6, lateral(6), initial_node=5, close=3.0)
    assert out["NOT_EVALUABLE"] == 1 and out["corrected"] == 0


def test_lost_following_of_the_aliased_node_counts_as_followed():
    recs = [rec(10, 5, 10, lost=True)] + [rec(10, 5, 10, lost=True) for _ in range(11)]
    out = v2.ambiguity(manifest(recs), [5] * 12, lateral(12), initial_node=5, close=3.0)
    assert out["followed"] >= 1


def test_decisions_after_the_task_end_are_ignored():
    recs = [rec(5, 5, 6, stop=True)] + [rec(10, 5, 10) for _ in range(5)]
    out = v2.ambiguity(manifest(recs), [5] * 6, lateral(6), initial_node=5, close=3.0)
    assert not out["encountered"]


def test_withheld_then_lost_track():
    recs = [rec(10, 5, 6)] + [rec(9, 9, 9) for _ in range(10)]
    out = v2.ambiguity(manifest(recs), [5] * 11, lateral(11), initial_node=5, close=3.0)
    assert out["withheld_then_lost_track"] == 1


def test_backward_proposals_are_tallied_with_correctness():
    # Previous node 4; argmin 3 at distance 4.1 (> close) proposes node 3: backward.
    recs = [rec(3, 3, 3, dist=4.1), rec(3, 3, 4, dist=2.0)]
    out = v2.ambiguity(manifest(recs), [4, 4], lateral(2), initial_node=4, close=3.0)
    b = out["backward_proposals"]
    assert len(b) == 1 and b[0]["accepted"] and not b[0]["proposal_closer_to_true"]


# --- integrity checks and negative-control modes ---------------------------------

import hashlib  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
B = {"max_jump": 2, "persistence": 2, "lost_enter": 6.752, "lost_exit": 2.215, "lost_patience": 3}
SPECS = {
    "A_baseline": {"bounded": None, "verify_threshold": None, "verify_persistence": 2},
    "B1_bounded": {"bounded": B, "verify_threshold": None, "verify_persistence": 2},
}


def head_blob(rel):
    out = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{rel}"], capture_output=True)
    return hashlib.sha256(out.stdout).hexdigest()


def fixture(tmp_path, variant="B1_bounded", resume=False):
    chain = tmp_path / "chain"
    chain.mkdir(exist_ok=True)
    rec = tmp_path / "recorded"
    (rec / "trajectory").mkdir(parents=True, exist_ok=True)
    for q in range(60):
        (rec / "trajectory" / f"{q}.jpg").write_bytes(f"img{q}".encode())
    rm = {
        "start_pose": [1.0, 60.0, 0.5],
        "inference": [
            {"frame": 6 * k, "chain": {"closest_node": k // 2}, "command": [0.1, 0.0, 0.01 * k]}
            for k in range(10)
        ],
        "captures": [{"pose": [0.01 * q, 1.0, 0.1]} for q in range(60)],
    }
    (rec / "runtime_manifest.json").write_text(json.dumps(rm))
    root = tmp_path / "coll"
    root.mkdir(exist_ok=True)
    (root / "frozen_routes.json").write_text("[]")
    cfg = {
        "checkpoint": {"sha256": "c" * 64},
        "runtime": {"radius": 4, "close_threshold": 3.0, "budget_frames": 600},
        "replay_fidelity": {
            "position_m": 0.02,
            "yaw_deg": 2.0,
            "image_mean_abs_grey": 2.5,
            "max_distance_diff": 1.0,
        },
    }
    t = {"stage": 2, "start_lost": False}
    K = 8
    if resume:
        t.update(resume_from=str(rec), resume_decision=K)
    cond = {"root": str(chain), "chain_json_sha256": "h" * 64}
    spec = SPECS[variant]
    m = {
        "policy": {
            "sha256": "c" * 64,
            "topomap": {
                "radius": 4,
                "close_threshold": 3.0,
                "bounded": spec["bounded"],
                "verify_threshold": None,
                "confirmation": None,
                "approach_steering": None,
                "recovery": None,
                "scan_rate": None,
                "start_lost": False,
            },
        },
        "topomap": {
            "root": str(chain),
            "chain_json_sha256": "h" * 64,
            "initial_node": rm["inference"][K - 1]["chain"]["closest_node"] if resume else 0,
            "start_lost": False,
        },
        "component_variant": {
            "variant": variant,
            "trial": "tr",
            "stage": 2,
            "comparison_config_sha256": "s" * 64,
        },
        "max_steps": 600,
        "qualification_sha256": "q" * 64,
        "start_perturbation": {"arc_fraction": 0.0, "lateral_m": 0.0, "yaw_deg": 0.0},
        "start_pose": rm["start_pose"] if resume else [0, 0, 0],
        "inference": [{"frame": 6 * k} for k in range(K if resume else 0, 100)],
        "policy_stop_frame": None,
        "route": {"id": "r"},
        "captures": [{"simulation_time": q / 12} for q in range(600)],
        "contacts": [],
        "preflight": {
            "observations": [
                {
                    "name": "influencing_file_digests",
                    "observed": {str(REPO / "pyproject.toml"): head_blob("pyproject.toml")},
                }
            ]
        },
    }
    if resume:
        m["resume"] = {
            "mode": "replay_to_handover",
            "episode": str(rec.resolve()),
            "decision": K,
            "handover_frame": 6 * K,
            "initial_node": rm["inference"][K - 1]["chain"]["closest_node"],
            "source_checkpoint_sha256": "c" * 64,
            "replayed_commands": [rm["inference"][k]["command"] for k in range(K)],
            "recorded_start_pose": rm["start_pose"],
            "handover_position_error_m": 0.004,
            "handover_yaw_error_deg": 0.3,
            "handover_image_mean_abs_grey": 0.39,
            "handover_window_matches": True,
            "handover_max_distance_diff": 0.068,
            "manifest_sha256": hashlib.sha256(
                (rec / "runtime_manifest.json").read_bytes()
            ).hexdigest(),
        }
        tdir = root / "r" / "trajectory"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "transitions.json").write_text(
            json.dumps(
                {
                    "records": [
                        {"command_requested": rm["inference"][i // 6]["command"]}
                        for i in range(6 * K)
                    ]
                }
            )
        )
    ctx = {
        "cfg": cfg,
        "cfg_sha": "s" * 64,
        "qual_sha": "q" * 64,
        "freeze_time": 0,
        "cache": {},
        "nonrepo": [],
    }
    return t, cond, spec, m, root, ctx


def checks_for(tmp_path, neg=None, resume=False, spec_variant=None):
    t, cond, spec, m, root, ctx = fixture(tmp_path, resume=resume)
    if spec_variant:
        spec = SPECS[spec_variant]
    return v2.attempt_checks(neg, "HEAD", t, "tr", cond, spec, "B1_bounded", m, root, ctx)


def test_a_correct_attempt_passes_every_check(tmp_path):
    for resume in (False, True):
        c = checks_for(tmp_path, resume=resume)
        assert all(c.values()), {k for k, ok in c.items() if not ok}


def test_each_negative_control_mode_fails_its_check(tmp_path):
    expect = {"chain": "chain_sha", "start_lost": "start_lost", "trial": "trial"}
    for mode, key in expect.items():
        c = checks_for(tmp_path, neg=mode)
        assert not c[key] and all(ok for k, ok in c.items() if k != key), mode
    c = checks_for(tmp_path, neg="resume", resume=True)
    assert not c["resume"]
    c = checks_for(tmp_path, spec_variant="A_baseline")  # what --negative-control variant does
    assert not c["bounded"]


def test_a_tampered_replay_or_poor_fidelity_is_detected(tmp_path):
    t, cond, spec, m, root, ctx = fixture(tmp_path, resume=True)
    m["resume"]["replayed_commands"][3] = [0.1, 0.0, 0.4]
    c = v2.attempt_checks(None, "HEAD", t, "tr", cond, spec, "B1_bounded", m, root, ctx)
    assert not c["resume"] and c["replay_fidelity"]
    t, cond, spec, m, root, ctx = fixture(tmp_path, resume=True)
    m["resume"]["handover_position_error_m"] = 0.05
    c = v2.attempt_checks(None, "HEAD", t, "tr", cond, spec, "B1_bounded", m, root, ctx)
    assert c["resume"] and not c["replay_fidelity"]


# --- gates and stage-3 decisions -------------------------------------------------

CFG = {
    "trials": {
        "amb": {
            "stage": 2,
            "question": "look-alike",
            "variants": ["A_baseline", "B1_bounded"],
            "condition": "true_chain",
            "routes": ["r"],
        },
        "kid_u": {
            "stage": 2,
            "question": "recovery",
            "uninformative_view": True,
            "variants": ["B1_bounded", "B1x_exit", "R2_recover"],
            "condition": "true_chain",
            "routes": [f"r{i}" for i in range(8)],
        },
        "s3_true": {
            "stage": 3,
            "condition": "true_chain",
            "question": "complete",
            "variants": ["A_baseline", "B1_bounded"],
            "routes": ["r"],
        },
        "s3_trunc": {
            "stage": 3,
            "condition": "truncated_chain",
            "question": "complete",
            "variants": ["A_baseline", "B1_bounded"],
            "routes": ["r"],
        },
        "s3_swap": {
            "stage": 3,
            "condition": "wrong_chain_swap",
            "question": "complete",
            "variants": ["A_baseline", "B1_bounded"],
            "routes": ["r"],
        },
    }
}


def att(trial, variant, route="r", **kw):
    base = {
        "trial": trial,
        "variant": variant,
        "route": route,
        "integrity_ok": True,
        "correct_stop": False,
        "wrong_stop": False,
        "timeout": True,
        "abstained": None,
        "collision_before_task_end": False,
        "path_length_m": 2.0,
        "exposure_s": 50.0,
    }
    return {**base, **kw}


def amb(followed=0, outcomes=()):
    return {"followed": followed, "encounters": [{"outcome": o} for o in outcomes]}


def test_look_alike_gate_is_not_tested_when_a_does_not_reproduce_the_failure():
    rows = [
        att("amb", "A_baseline", ambiguity=amb(0)),
        att("amb", "B1_bounded", ambiguity=amb(0, ["corrected"])),
    ]
    assert v2.compute_gates(CFG, rows, {"amb"}, True)["B1_bounded"]["status"] == "NOT_TESTED"
    rows[0]["ambiguity"] = amb(1)
    assert v2.compute_gates(CFG, rows, {"amb"}, True)["B1_bounded"]["status"] == "PASS"
    rows[1]["ambiguity"] = amb(0, ["NOT_EVALUABLE"])
    assert v2.compute_gates(CFG, rows, {"amb"}, True)["B1_bounded"]["status"] == "NOT_TESTED"
    rows[1]["ambiguity"] = amb(0, ["withheld_then_lost_track"])
    assert v2.compute_gates(CFG, rows, {"amb"}, True)["B1_bounded"]["status"] == "FAIL"


def test_a_gate_is_incomplete_with_a_missing_attempt_or_an_integrity_failure():
    rows = [att("amb", "A_baseline", ambiguity=amb(1))]
    assert v2.compute_gates(CFG, rows, {"amb"}, True)["B1_bounded"]["status"] == "INCOMPLETE"
    rows.append(att("amb", "B1_bounded", ambiguity=amb(0, ["corrected"]), integrity_ok=False))
    assert v2.compute_gates(CFG, rows, {"amb"}, True)["B1_bounded"]["status"] == "INCOMPLETE"
    rows[1]["integrity_ok"] = True
    assert v2.compute_gates(CFG, rows, {"amb"}, False)["B1_bounded"]["status"] == "INCOMPLETE"


def rec_(ok):
    return {"first_entry_success": ok, "successes": int(ok), "lost_entries": 1}


def test_recovery_gate_is_comparative():
    def rows(r2_ok, bx_ok):
        out = []
        for i in range(8):
            for v, ok in (
                ("B1_bounded", False),
                ("B1x_exit", i < bx_ok),
                ("R2_recover", i < r2_ok),
            ):
                out.append(att("kid_u", v, route=f"r{i}", recovery=rec_(ok)))
        return out

    assert v2.compute_gates(CFG, rows(6, 2), {"kid_u"}, True)["R2_recover"]["status"] == "PASS"
    assert v2.compute_gates(CFG, rows(6, 6), {"kid_u"}, True)["R2_recover"]["status"] == "FAIL"
    assert v2.compute_gates(CFG, rows(5, 0), {"kid_u"}, True)["R2_recover"]["status"] == "FAIL"
    r = rows(7, 0)
    r[2]["collision_before_task_end"] = True  # an R2 contact the control did not have
    assert v2.compute_gates(CFG, r, {"kid_u"}, True)["R2_recover"]["status"] == "FAIL"


def test_stage3_revises_on_a_contact_regression_and_retains_otherwise():
    def rows(contact):
        out = []
        for tr in ("s3_true", "s3_trunc", "s3_swap"):
            out.append(att(tr, "A_baseline", correct_stop=True))
            out.append(
                att(
                    tr,
                    "B1_bounded",
                    correct_stop=True,
                    collision_before_task_end=contact and tr == "s3_trunc",
                )
            )
        return out

    ran = {"s3_true", "s3_trunc", "s3_swap"}
    d = v2.stage3_decisions(CFG, rows(False), ran, {"B1_bounded"}, True)
    assert d["B1_bounded"]["decision"] == "RETAIN"
    d = v2.stage3_decisions(CFG, rows(True), ran, {"B1_bounded"}, True)
    assert d["B1_bounded"]["decision"] == "REVISE"
    d = v2.stage3_decisions(CFG, rows(False)[:-1], ran, {"B1_bounded"}, True)
    assert d["B1_bounded"]["conditions"]["wrong_chain_swap"] == "MISSING"
    # Red-team M3: missing data or an integrity failure is INCOMPLETE, not REVISE.
    assert d["B1_bounded"]["decision"] == "INCOMPLETE"
    bad = rows(False)
    bad[1]["integrity_ok"] = False
    assert v2.stage3_decisions(CFG, bad, ran, {"B1_bounded"}, True)["B1_bounded"]["decision"] == (
        "INCOMPLETE"
    )


def test_a_gate_needs_every_declared_trial_of_its_question():
    # Red-team H1: a gate computed from a hand-picked subset of trials.
    cfg = {"trials": {**CFG["trials"], "amb2": {**CFG["trials"]["amb"]}}}
    rows = [
        att("amb", "A_baseline", ambiguity=amb(1)),
        att("amb", "B1_bounded", ambiguity=amb(0, ["corrected"])),
    ]
    assert v2.compute_gates(cfg, rows, {"amb"}, True)["B1_bounded"]["status"] == "INCOMPLETE"
    rows += [
        att("amb2", "A_baseline", ambiguity=amb(0)),
        att("amb2", "B1_bounded", ambiguity=amb(0)),
    ]
    assert v2.compute_gates(cfg, rows, {"amb", "amb2"}, True)["B1_bounded"]["status"] == "PASS"


def test_stage3_requires_only_the_protocol_variants():
    # Red-team H2: V2a passing runs V2a, C1 and A; B1 and B1x are not required.
    cfg = {
        "trials": {
            f"s3_{c}": {
                "stage": 3,
                "condition": c,
                "question": "complete",
                "routes": ["r"],
                "variants": ["A_baseline", "B1_bounded", "B1x_exit", "C1_verify", "V2a_confirm"],
            }
            for c in ("true_chain", "truncated_chain", "wrong_chain_swap")
        }
    }
    rows = [
        att(tn, v, correct_stop=(v != "C1_verify"))
        for tn in cfg["trials"]
        for v in ("A_baseline", "C1_verify", "V2a_confirm")
    ]
    d = v2.stage3_decisions(cfg, rows, set(cfg["trials"]), {"V2a_confirm"}, True)
    assert d["V2a_confirm"]["decision"] == "RETAIN"
    assert v2.required_stage3({"R2_recover"}) == {
        "R2_recover",
        "B1x_exit",
        "B1_bounded",
        "A_baseline",
    }


def make_collection(base, name, planned, episodes, status="COMPLETED", age=0):
    import os
    import time

    d = base / name
    d.mkdir()
    (d / "frozen_routes.json").write_text(json.dumps([{"id": r} for r in planned]))
    (d / "collection.json").write_text(
        json.dumps({"status": status, "episodes": [{"id": r, "status": st} for r, st in episodes]})
    )
    t = time.time() - 1000 + age
    os.utime(d / "frozen_routes.json", (t, t))


def test_retry_rule_is_enforced(tmp_path):
    # Red-team M1: fail, fail, PASS must not count; a crash is an attempt.
    make_collection(
        tmp_path,
        "v2-tr-B1_bounded-a",
        ["r1", "r2", "r3"],
        [("r1", "FAIL"), ("r2", "FAIL"), ("r3", "PASS")],
        age=0,
    )
    make_collection(tmp_path, "v2-tr-B1_bounded-b", ["r1", "r2"], [("r1", "FAIL")], age=10)
    make_collection(
        tmp_path, "v2-tr-B1_bounded-c", ["r1", "r2"], [("r1", "PASS"), ("r2", "PASS")], age=20
    )
    counted, log, violations = v2.discover("tr", "B1_bounded", ["r1", "r2", "r3"], base=tmp_path)
    assert {"collection": "v2-tr-B1_bounded-b", "route": "r2", "status": "CRASHED"} in log
    assert "r1" not in counted and ("r1", "more than one rerun") in violations
    assert "r2" not in counted  # FAIL, CRASHED, PASS: a third attempt
    assert counted["r3"][0].name == "v2-tr-B1_bounded-a"


def test_a_rerun_after_a_pass_is_a_violation(tmp_path):
    make_collection(tmp_path, "v2-tr-A_baseline-a", ["r"], [("r", "PASS")], age=0)
    make_collection(tmp_path, "v2-tr-A_baseline-b", ["r"], [("r", "PASS")], age=10)
    counted, _, violations = v2.discover("tr", "A_baseline", ["r"], base=tmp_path)
    assert "r" not in counted and ("r", "attempt after a PASS") in violations


def test_one_rerun_after_a_failure_counts(tmp_path):
    make_collection(tmp_path, "v2-tr-A_baseline-a", ["r"], [("r", "FAIL")], age=0)
    make_collection(tmp_path, "v2-tr-A_baseline-b", ["r"], [("r", "PASS")], age=10)
    counted, _, violations = v2.discover("tr", "A_baseline", ["r"], base=tmp_path)
    assert counted["r"][0].name == "v2-tr-A_baseline-b" and not violations


def test_stage2_record_must_be_committed_consistent_and_complete(tmp_path, monkeypatch):
    # Red-team M2: the stage-2 record is checked, not trusted.
    import argparse

    import pytest

    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *c: subprocess.run(["git", "-C", str(repo), *c], check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    monkeypatch.setattr(v2, "REPO", repo)
    cfg = {"trials": {"amb": CFG["trials"]["amb"]}}
    rows = [
        att("amb", "A_baseline", ambiguity=amb(1)),
        att("amb", "B1_bounded", ambiguity=amb(0, ["corrected"])),
    ]
    good = {
        "freeze_commit": "F",
        "config_sha256": "S",
        "negative_control": None,
        "trials_analysed": ["amb"],
        "globally_ok": True,
        "attempts": rows,
        "gates": v2.compute_gates(cfg, rows, {"amb"}, True),
    }

    def commit(record):
        (repo / "g.json").write_text(json.dumps(record))
        run("add", "g.json")
        run("commit", "-q", "-m", "g")
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()

    parser = argparse.ArgumentParser()
    args = argparse.Namespace(freeze_commit="F", stage2_commit=commit(good), stage2_path="g.json")
    passed, _ = v2.load_stage2(cfg, "S", args, parser)
    assert passed == {"B1_bounded"}
    for bad in (
        {**good, "negative_control": "chain"},
        {**good, "config_sha256": "X"},
        {**good, "trials_analysed": []},
        {**good, "gates": {"B1_bounded": {"status": "PASS"}}, "attempts": rows[:1]},
    ):
        args.stage2_commit = commit(bad)
        with pytest.raises(SystemExit):
            v2.load_stage2(cfg, "S", args, parser)


def resumed(tmp_path, mutate):
    t, cond, spec, m, root, ctx = fixture(tmp_path, resume=True)
    mutate(m, root)
    return v2.attempt_checks(None, "HEAD", t, "tr", cond, spec, "B1_bounded", m, root, ctx)


def test_replay_checks_fail_on_broken_states(tmp_path):
    def unapplied(m, root):
        p = root / "r" / "trajectory" / "transitions.json"
        recs = json.loads(p.read_text())
        recs["records"][7]["command_requested"] = [0.0, 0.0, 0.0]
        p.write_text(json.dumps(recs))

    assert not resumed(tmp_path, unapplied)["replay_applied"]
    assert not resumed(tmp_path, lambda m, r: m["resume"].update(manifest_sha256="0" * 64))[
        "resume"
    ]
    # The at-rest start's image error (11.3 grey) fails image fidelity.
    c = resumed(tmp_path, lambda m, r: m["resume"].update(handover_image_mean_abs_grey=11.3))
    assert not c["replay_fidelity"]
    c = resumed(tmp_path, lambda m, r: m["resume"].update(handover_max_distance_diff=10.28))
    assert not c["replay_fidelity"]
    c = resumed(tmp_path, lambda m, r: m["resume"].update(handover_window_matches=False))
    assert not c["replay_fidelity"]
    # A perfect match (0.0) is not mistaken for a missing value.
    c = resumed(tmp_path, lambda m, r: m["resume"].update(handover_max_distance_diff=0.0))
    assert c["replay_fidelity"]
    c = resumed(tmp_path, lambda m, r: m["resume"].pop("handover_image_mean_abs_grey"))
    assert not c["replay_fidelity"]


def test_resumed_inference_must_start_at_handover(tmp_path):
    c = resumed(tmp_path, lambda m, r: m.update(inference=[{"frame": 6 * k} for k in range(100)]))
    assert not c["inference_complete"]


def test_contact_before_handover_is_an_integrity_failure(tmp_path):
    c = resumed(tmp_path, lambda m, r: m.update(contacts=[{"time": 10 / 12}]))
    assert not c["no_contact_before_handover"]
    c = resumed(tmp_path, lambda m, r: m.update(contacts=[{"time": 100 / 12}]))
    assert c["no_contact_before_handover"]
