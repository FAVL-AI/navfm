"""Boundary and negative controls for the prospective recovery protocol."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "prospective", ROOT / "scripts/analyse_prospective_r2.py"
)
prospective = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prospective)


def trace(exit_at, count=60, node=3):
    return [
        {"frame": i * 6, "chain": {"lost": i < exit_at, "closest_node": node}} for i in range(count)
    ]


def test_initial_exit_and_exact_vs_tolerance():
    rows = trace(0, node=4)
    assert prospective.first_entry(rows, [3] * 60)["outcome"] == "wrong_confident"
    assert prospective.first_entry(rows, [3] * 60, 1)["outcome"] == "correct_confident"


def test_horizon_is_shared_and_includes_decision35():
    assert prospective.first_entry(trace(35), [3] * 60)["outcome"] == "correct_confident"
    assert prospective.first_entry(trace(36), [3] * 60)["outcome"] == "failure"


def test_terminal_filler_is_not_durability():
    rows = trace(2)
    assert prospective.first_entry(rows, [3] * 60, terminal_frame=72)["outcome"] == "failure"
    assert (
        prospective.first_entry(rows, [3] * 60, terminal_frame=78)["outcome"] == "correct_confident"
    )
    assert prospective.first_entry(rows, [3] * 60, terminal_frame=6)["outcome"] == "failure"


def test_wrong_terminal_exit_remains_wrong_confident():
    rows = trace(2, node=5)
    assert (
        prospective.first_entry(rows, [3] * 60, terminal_frame=12)["outcome"] == "wrong_confident"
    )


def test_missing_followup_and_reentry_fail():
    assert prospective.first_entry(trace(2, count=12), [3] * 12)["outcome"] == "failure"
    rows = trace(2)
    rows[8]["chain"]["lost"] = True
    assert prospective.first_entry(rows, [3] * 60)["outcome"] == "failure"


def test_no_relocation_abstention_vs_timeout():
    rows = trace(99)
    assert prospective.first_entry(rows, [3] * 60)["outcome"] == "failure"
    rows[35]["chain"]["event"] = "recovery_failed"
    assert prospective.first_entry(rows, [3] * 60)["outcome"] == "abstention"


def test_contact_window_includes24_and_reports_extra_tail():
    m = {
        "captures": [{"pose": [i * 0.01, 0, 0], "simulation_time": i / 12} for i in range(108)],
        "policy_stop_frame": 12,
        "contacts": [{"time": 3.0}, {"time": 4.0}],
        "start_settling": {"pose": [0, 0, 0], "contacts": []},
        "inference": [{"predecision_pose": [0, 0, 0], "predecision_sim_time": -1 / 12}],
    }
    out = prospective.motion(m)
    assert out["window_end_frame"] == 36
    assert out["contact_records"] == 1
    assert out["extra_tail_contact_records"] == 1
    assert out["exposure_s"] == pytest.approx(3 + 1 / 12)
    assert out["path_length_m"] == pytest.approx(0.36)


def test_frozen_variant_contract_and_new_starts():
    old = json.loads((ROOT / "configs/eval/component_comparison_v2.json").read_text())
    cfg = json.loads((ROOT / prospective.CONFIG).read_text())
    assert cfg["variants"] == {k: old["variants"][k] for k in cfg["variants"]}
    assert len(cfg["trials"]) == 4
    assert sum(len(t["routes"]) for t in cfg["trials"].values()) == 16
    previous = [t.get("perturbation") for t in old["trials"].values()]
    assert all(t["perturbation"] not in previous for t in cfg["trials"].values())
    assert cfg["runtime"] == old["runtime"]


def test_first_commanded_interval_is_exposure():
    m = {
        "captures": [
            {"pose": [0.1, 0, 0.2], "simulation_time": 0.1},
            {"pose": [0.1, 0, 0.2], "simulation_time": 0.2},
        ],
        "contacts": [{"time": 0.05}],
        "start_settling": {"pose": [0, 0, 0], "contacts": []},
        "inference": [{"predecision_pose": [0, 0, 0], "predecision_sim_time": 0}],
    }
    out = prospective.motion(m)
    assert out["path_length_m"] == pytest.approx(0.1)
    assert out["exposure_s"] == pytest.approx(0.2)
    assert out["translating_s"] == pytest.approx(0.1)
    assert out["absolute_rotation_rad"] == pytest.approx(0.2)
    assert out["contact_records"] == 1


def initial_ledger(cfg):
    return [
        {
            "event": "launch",
            "trial": t,
            "variant": v,
            "routes": spec["routes"],
            "collection": f"v2-{t}-{v}-20261010-01",
            "robot_usd_sha256": "a" * 64,
        }
        for t, spec in list(cfg["trials"].items())[:1]
        for v in spec["variants"]
    ]


def test_ledger_rejects_cross_arm_robot_change_and_undeclared_start():
    cfg = json.loads((ROOT / prospective.CONFIG).read_text())
    ledger = initial_ledger(cfg)
    assert prospective.ledger_checks(cfg, ledger) == []
    ledger[1]["robot_usd_sha256"] = "b" * 64
    assert "robot digest differs across launches" in prospective.ledger_checks(cfg, ledger)
    ledger[1]["robot_usd_sha256"] = "a" * 64
    ledger[1]["routes"] = [*ledger[1]["routes"], "unplanned_route"]
    assert "undeclared or duplicate routes" in prospective.ledger_checks(cfg, ledger)
    ledger[1]["trial"] = "unplanned_trial"
    assert "undeclared trial or variant" in prospective.ledger_checks(cfg, ledger)


def test_ledger_rejects_duplicates_order_and_missing_pilot_gate():
    cfg = json.loads((ROOT / prospective.CONFIG).read_text())
    ledger = initial_ledger(cfg)
    assert "duplicate launch collection" in prospective.ledger_checks(cfg, [*ledger, ledger[0]])
    assert "initial launch order differs from frozen order" in prospective.ledger_checks(
        cfg, list(reversed(ledger))
    )
    t = list(cfg["trials"])[1]
    v = cfg["trials"][t]["variants"][0]
    ledger.append(
        dict(
            event="launch",
            trial=t,
            variant=v,
            routes=cfg["trials"][t]["routes"],
            collection=f"v2-{t}-{v}-20261010-01",
            robot_usd_sha256="a" * 64,
        )
    )
    assert "remaining stage lacks prior unique pilot gate" in prospective.ledger_checks(cfg, ledger)


def test_scoring_dependency_drift_fails_freeze(monkeypatch, tmp_path):
    monkeypatch.setattr(prospective, "REPO", tmp_path)
    for rel in prospective.FROZEN_FILES:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"frozen")

    class Result:
        stdout = b"frozen"

    monkeypatch.setattr(prospective.subprocess, "run", lambda *a, **k: Result())
    (tmp_path / "src/navfm/collection/episode_measures.py").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Frozen file differs"):
        prospective.frozen_config("freeze")
