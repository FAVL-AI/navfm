import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from prospective_budget_proposal_v1 import validate_proposal


def proposal():
    return json.loads(
        (Path(__file__).parents[1] / "configs/eval/prospective_budget_proposal_v1.json").read_text()
    )


def test_complete_budget_remains_nonexecuting_proposal():
    result = validate_proposal(proposal())
    assert result == dict(
        status="VALID_PROPOSAL_ONLY", execution_authorized=False, hard_total_seconds=190
    )


@pytest.mark.parametrize(
    "mutation",
    ["authorize", "missing_phase", "wrong_total", "bool_allowance", "held_steps", "uninspected"],
)
def test_actual_budget_and_exposure_faults_rejected(mutation):
    cfg = copy.deepcopy(proposal())
    if mutation == "authorize":
        cfg["execution_authorized"] = True
    if mutation == "missing_phase":
        del cfg["phase_allowance_seconds"]["sdk_shutdown"]
    if mutation == "wrong_total":
        cfg["hard_total_seconds"] = 191
    if mutation == "bool_allowance":
        cfg["phase_allowance_seconds"]["parent_setup"] = True
    if mutation == "held_steps":
        cfg["unchanged_acquisition"]["held_steps_per_frame"] = 3
    if mutation == "uninspected":
        cfg["prior_layout_exposure"] = "UNINSPECTED"
    with pytest.raises(ValueError):
        validate_proposal(cfg)
