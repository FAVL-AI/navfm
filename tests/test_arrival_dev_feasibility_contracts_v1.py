"""Finite preparation budget and independent refusal controls; no scientific runtime."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from arrival_dev_feasibility_contracts_v1 import CONFIG, design_summary, validate_semantics


def config():
    return json.loads(CONFIG.read_text())


def test_finite_slot_budget_preserves_first_block_and_control_distinction():
    r = design_summary(config())
    assert r["feasible_episode_slots"] == 216
    assert r["separate_control_slots_maximum"] == 108
    assert r["all_slots_maximum"] == 324
    assert r["first_block_slots_included"] == 9
    assert r["navigation_simulation_hours_ceiling"] == pytest.approx(7.32)
    assert r["episode_reserved_wall_GPU_hours"] == 54
    assert r["known_reserved_wall_GPU_hours"] == 66
    assert r["hard_wall_GPU_hours_cap"] == 72
    assert r["unassigned_headroom_hours_no_extra_trials"] == 6
    assert r["external_storage_GiB_cap"] == 50
    assert r["runtime"] == "NOT_RUN"


@pytest.mark.parametrize(
    "section,key,value",
    [
        (None, "runtime_authorized", True),
        ("fairness", "comparator_fallback", True),
        ("backbone", "seeds", [0]),
        ("population", "test_budget_authorization", True),
        ("first_block", "included_in_total", False),
        ("first_block", "outcome_based_retuning_or_early_success", True),
        ("controls", "unsupported_interface", "FORCE_GOAL_INDEX_ZERO"),
        ("fairness", "photometric_or_cadence_perturbation", True),
        ("resources", "total_wall_GPU_hours_cap", 50),
        ("resources", "episode_process_wall_cap_s", float("nan")),
    ],
)
def test_semantic_refusals_precede_source_binding(section, key, value):
    cfg = config()
    (cfg if section is None else cfg[section])[key] = value
    with pytest.raises(ValueError):
        validate_semantics(cfg)


def test_changed_on_disk_draft_cannot_self_certify(tmp_path, monkeypatch):
    import arrival_dev_feasibility_contracts_v1 as contract

    cfg = config()
    cfg["gates"]["authentic_CAD_motion_plant"] = "PASS"
    p = tmp_path / "draft.json"
    p.write_text(json.dumps(cfg))
    monkeypatch.setattr(contract, "CONFIG", p)
    with pytest.raises(ValueError, match="source binding drift"):
        design_summary(cfg)
