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
        "inference": [{"frame": 6 * k, "chain": {"closest_node": k // 2}} for k in range(10)],
        "captures": [{"pose": [0.01 * q, 1.0, 0.1]} for q in range(60)],
    }
    (rec / "runtime_manifest.json").write_text(json.dumps(rm))
    root = tmp_path / "coll"
    root.mkdir(exist_ok=True)
    (root / "frozen_routes.json").write_text("[]")
    cfg = {
        "checkpoint": {"sha256": "c" * 64},
        "runtime": {"radius": 4, "close_threshold": 3.0, "budget_frames": 600},
    }
    t = {"stage": 2, "start_lost": False}
    K = 8
    if resume:
        t.update(resume_from=str(rec), resume_decision=K, budget_frames=480)
    cond = {"root": str(chain), "chain_json_sha256": "h" * 64}
    spec = SPECS[variant]
    hist = [rm["inference"][j]["frame"] - 1 for j in range(K - 6, K)]
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
        "max_steps": 480 if resume else 600,
        "qualification_sha256": "q" * 64,
        "start_perturbation": {"arc_fraction": 0.0, "lateral_m": 0.0, "yaw_deg": 0.0},
        "start_pose": rm["captures"][rm["inference"][K]["frame"] - 1]["pose"]
        if resume
        else [0, 0, 0],
        "inference": [{"frame": 6 * k} for k in range(100)],
        "policy_stop_frame": None,
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
            "episode": str(rec.resolve()),
            "decision": K,
            "initial_node": rm["inference"][K - 1]["chain"]["closest_node"],
            "source_checkpoint_sha256": "c" * 64,
            "history_frames": hist,
            "history_sha256": [
                hashlib.sha256((rec / "trajectory" / f"{q}.jpg").read_bytes()).hexdigest()
                for q in hist
            ],
        }
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


def test_a_tampered_resume_history_is_detected(tmp_path):
    t, cond, spec, m, root, ctx = fixture(tmp_path, resume=True)
    m["resume"]["history_frames"][0] += 1
    c = v2.attempt_checks(None, "HEAD", t, "tr", cond, spec, "B1_bounded", m, root, ctx)
    assert not c["resume"]


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
