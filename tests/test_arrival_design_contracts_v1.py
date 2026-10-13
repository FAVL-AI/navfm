"""Design-only arithmetic and refusal controls; no study or model execution."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from arrival_design_contracts_v1 import (
    CONFIG,
    design_summary,
    required_layouts,
    validate_draft_semantics,
)


def config():
    return json.loads(CONFIG.read_text())


def test_layout_sensitivity_and_resource_envelope():
    result = design_summary(config())
    assert result["binary_sensitivity_layouts"] == [32, 71, 126]
    assert result["time_sensitivity_layouts"] == [32, 71, 126]
    assert result["binary_sd_ceiling_for_planned_layouts"] == pytest.approx(0.15962876753)
    assert result["full_design_episodes"] == 9600
    assert result["primary_pair_episodes"] == 4800
    assert result["full_design_simulated_hours_ceiling"] == pytest.approx(325.333333333)
    assert result["primary_pair_simulated_hours_ceiling"] == pytest.approx(162.666666667)
    assert result["proposed_full_with_preparation_wall_hours_ceiling"] == pytest.approx(
        1978.666666667
    )
    assert result["proposed_full_with_preparation_GPU_hours_ceiling"] == pytest.approx(
        1978.666666667
    )
    assert result["proposed_storage_GiB_cap"] == 500
    assert result["runtime"] == "NOT_RUN"


@pytest.mark.parametrize(
    "section,key,value",
    [
        (None, "runtime_authorized", True),
        ("population", "test_access", "SEALED_BY_SELF"),
        ("population", "human_reviewer", "same_custodian"),
        ("gates", "motion_qualification", "PASS"),
        ("gates", "illumination_authorization", "AUTHORIZED"),
        ("comparison", "test_tuning", True),
        ("comparison", "seed_aggregation", "best_test_seed"),
        ("population", "denominator", "successful_attempts_only"),
        ("population", "unit", "frame"),
        ("metrics", "oracle", "ground_truth_policy_stop"),
        ("method", "cadence_hz", 3),
    ],
)
def test_unsupported_amendments_cannot_silently_pass(section, key, value):
    cfg = copy.deepcopy(config())
    target = cfg if section is None else cfg[section]
    target[key] = value
    with pytest.raises(ValueError, match="semantics violated"):
        validate_draft_semantics(cfg)
    with pytest.raises(ValueError):
        design_summary(cfg)


def test_absent_subject_and_unknown_field_fail():
    with pytest.raises(ValueError):
        design_summary({})
    cfg = config()
    cfg["unknown_runtime_launcher"] = True
    with pytest.raises(ValueError):
        design_summary(cfg)


@pytest.mark.parametrize(
    "sd,gap", [(0, 0.05), (0.15, 0), (float("nan"), 0.05), (0.15, float("inf")), (True, 0.05)]
)
def test_invalid_planning_assumptions_fail(sd, gap):
    with pytest.raises(ValueError):
        required_layouts(sd, gap)


def test_more_layout_variance_or_smaller_effect_gap_needs_more_layouts():
    assert required_layouts(0.2, 0.05) > required_layouts(0.15, 0.05)
    assert required_layouts(0.15, 0.025) > required_layouts(0.15, 0.05)


def test_changed_on_disk_design_cannot_self_certify(tmp_path, monkeypatch):
    import arrival_design_contracts_v1 as contract

    cfg = config()
    cfg["gates"]["motion_qualification"] = "PASS"
    edited = tmp_path / "draft.json"
    edited.write_text(json.dumps(cfg))
    monkeypatch.setattr(contract, "CONFIG", edited)
    with pytest.raises(ValueError, match="source binding drift"):
        design_summary(cfg)


@pytest.mark.parametrize("key,value", [("schema_version", True), ("runtime_authorized", 0)])
def test_boolean_numeric_schema_confusion_fails(key, value):
    cfg = config()
    cfg[key] = value
    with pytest.raises(ValueError):
        design_summary(cfg)
