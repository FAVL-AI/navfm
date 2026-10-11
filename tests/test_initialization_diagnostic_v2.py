"""Explicit bootstrap never earns capture credit; eligibility remains fixed."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from initialization_diagnostic_v2 import FILES, bootstrap_ok, eligibility_ok


def test_zero_delta_bootstrap_is_explicitly_unqualified():
    bootstrap_ok(
        dict(
            before_sim_time=0.058333,
            after_sim_time=0.058333,
            requested_delta_s=0.0,
            feedback_updates=0,
            qualified_policy_observation=False,
            sensor_time=0.0,
        )
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("after_sim_time", 0.06),
        ("feedback_updates", 1),
        ("requested_delta_s", 1 / 12),
        ("qualified_policy_observation", True),
    ],
)
def test_bootstrap_rejects_advance_or_scientific_capture_credit(field, value):
    record = dict(
        before_sim_time=0.058333,
        after_sim_time=0.058333,
        requested_delta_s=0.0,
        feedback_updates=0,
        qualified_policy_observation=False,
    )
    record[field] = value
    with pytest.raises(ValueError):
        bootstrap_ok(record)


@pytest.fixture
def eligibility():
    return [
        dict(
            physical_step=i + 1,
            mechanical_ok=True,
            unknown=[],
            sensor_time=(i + 1) / 12,
            sim_time=(i + 1) / 12,
            settings={"/rtx/post/dlss/execMode": 0},
        )
        for i in range(3)
    ]


def test_three_fixed_eligibility_captures_pass(eligibility):
    eligibility_ok(eligibility, 0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("physical_step", 4),
        ("unknown", ["exposure"]),
        ("sensor_time", 0.0),
        ("mechanical_ok", False),
        ("settings", {"/rtx/post/dlss/execMode": 2}),
    ],
)
def test_eligibility_has_no_timestamp_or_mode_exemption(eligibility, field, value):
    captures = copy.deepcopy(eligibility)
    captures[1][field] = value
    with pytest.raises(ValueError):
        eligibility_ok(captures, 0)


def test_no_adaptive_frame_selection(eligibility):
    with pytest.raises(ValueError):
        eligibility_ok(eligibility[:2], 0)
    with pytest.raises(ValueError):
        eligibility_ok([*eligibility, eligibility[-1]], 0)


def test_v1_contract_and_v2_implementation_dependencies_pinned():
    assert "scripts/initialization_diagnostic.py" in FILES
    assert "scripts/collect_initialization_diagnostic.py" in FILES
    assert "scripts/run_initialization_diagnostic.py" in FILES
    assert "scripts/collect_initialization_diagnostic_v2.py" in FILES
    assert "tests/test_initialization_diagnostic_v2.py" in FILES
