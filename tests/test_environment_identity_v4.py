"""Controls for V4: the amendment that pins the executable state.

The invariant chain is historical, and each amendment answers for the state it
froze rather than for every future one:

    V2 accepts its freeze state, rejects the later seam state
    V3 accepts its freeze state, rejects the later treatment state
    V4 accepts the final treatment-capable execution state

The failure this suite is built to catch is a successor that quietly edits a
predecessor so everything passes again. V2 and V3 must keep refusing, and they
must refuse for their own distinct reasons.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from navfm.arm_environment_guard import (
    AUTHORITATIVE_CONTRACT_VERSION,
    CONTRACTS,
    V2_AMENDMENT_SHA256,
    V3_AMENDMENT_SHA256,
    V4_AMENDMENT_REL,
    V4_AMENDMENT_SHA256,
    check_contract,
)
from navfm.execution_environment import contract_fields

REPO = Path(__file__).resolve().parents[1]
V4 = REPO / V4_AMENDMENT_REL
TREATMENT_REL = "gates/BO10/arclength_treatment_validation_20260912.json"
V3_FREEZE_COMMIT = "58825a6bdb36a09721e481640082ac5fca429550"
TREATMENT_COMMIT = "ef5e7f0feb6eb1bd5eed4ebb0638aaf2306e5333"

_SPEC = importlib.util.spec_from_file_location(
    "amend_v4", REPO / "scripts" / "amend_environment_identity_v4.py")
assert _SPEC and _SPEC.loader
v4mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v4mod)


@pytest.fixture
def amendment() -> dict[str, Any]:
    return json.loads(V4.read_text())


def _sha() -> str:
    return hashlib.sha256(V4.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# the historical invariant chain
# --------------------------------------------------------------------------


def test_v4_is_authoritative() -> None:
    assert AUTHORITATIVE_CONTRACT_VERSION == "V4"
    assert set(CONTRACTS) == {"V2", "V3", "V4"}


def test_v4_accepts_the_executable_state() -> None:
    result = check_contract(REPO, "V4")
    assert result["CONTRACT_SATISFIED"] == "PASS"
    assert result["drift"] == []


def test_v3_still_refuses_the_treatment_tree() -> None:
    """Permanent. If this passes, V3 was rewritten."""
    result = check_contract(REPO, "V3")
    assert result["CONTRACT_SATISFIED"] == "FAIL"
    assert [d["field"] for d in result["drift"]] == [
        "scientific_code.target_selection_sha256"]


def test_v2_still_refuses_the_post_seam_tree() -> None:
    result = check_contract(REPO, "V2")
    assert result["CONTRACT_SATISFIED"] == "FAIL"
    assert [d["field"] for d in result["drift"]] == ["scientific_code.control_sha256"]


def test_each_predecessor_refuses_for_its_own_reason() -> None:
    v2 = [d["field"] for d in check_contract(REPO, "V2")["drift"]]
    v3 = [d["field"] for d in check_contract(REPO, "V3")["drift"]]
    assert v2 != v3


def test_predecessor_files_are_byte_unchanged() -> None:
    assert hashlib.sha256(
        (REPO / "gates/BO10/environment_identity_v2_20260911.json").read_bytes()
    ).hexdigest() == V2_AMENDMENT_SHA256
    assert hashlib.sha256(
        (REPO / "gates/BO10/environment_identity_v3_20260911.json").read_bytes()
    ).hexdigest() == V3_AMENDMENT_SHA256


def test_v3_accepted_the_tree_at_its_own_freeze_commit() -> None:
    """Each amendment answers for the state it froze."""
    frozen = json.loads(
        (REPO / "gates/BO10/environment_identity_v3_20260911.json").read_text()
    )["EXECUTION_ENVIRONMENT_IDENTITY_V3"]["frozen_contract_values"]
    at_freeze = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{V3_FREEZE_COMMIT}:src/navfm/target_selection.py"],
        capture_output=True, check=False)
    assert at_freeze.returncode == 0
    assert frozen["scientific_code.target_selection_sha256"] == hashlib.sha256(
        at_freeze.stdout).hexdigest()


def test_v4_pins_the_current_seam_module() -> None:
    frozen = json.loads(V4.read_text())["EXECUTION_ENVIRONMENT_IDENTITY_V4"][
        "frozen_contract_values"]
    assert frozen["scientific_code.target_selection_sha256"] == hashlib.sha256(
        (REPO / "src/navfm/target_selection.py").read_bytes()).hexdigest()


def test_v4_adds_no_contract_field() -> None:
    assert contract_fields("V4") == contract_fields("V3")
    assert json.loads(V4.read_text())["EXECUTION_ENVIRONMENT_IDENTITY_V4"][
        "fields_added_since_v3"] == []


def test_pinned_v4_sha_matches_the_artefact() -> None:
    assert _sha() == V4_AMENDMENT_SHA256


# --------------------------------------------------------------------------
# what V4 claims
# --------------------------------------------------------------------------


def test_v4_does_not_claim_to_repair_v3(amendment: dict[str, Any]) -> None:
    note = amendment["amends"]["this_does_not_repair_v3"]
    assert "remains historically correct" in note
    assert "continue to refuse" in note


def test_source_transition_is_explicit(amendment: dict[str, Any]) -> None:
    transition = amendment["SOURCE_IDENTITY_TRANSITION"]
    assert transition["SOURCE_BYTE_IDENTITY_ACROSS_V3_TO_V4"] == "CHANGED"
    assert transition["expected_and_intentional"] is True
    changed = transition["changed_from_v3"]
    assert changed["no_other_field_changed"] is True
    assert changed["fields_added"] == []
    entry = changed["scientific_code.target_selection_sha256"]
    assert entry["justification"]
    assert entry["evidence"]["sha256"]


def test_regression_claim_is_domain_bounded(amendment: dict[str, Any]) -> None:
    regression = amendment["ARM_A_POST_TREATMENT_REGRESSION"]
    assert "no behavioural difference was detected" in regression["CLAIM"].lower()
    assert "frozen regression domain" in regression["CLAIM"]
    boundary = regression["CLAIM_BOUNDARY"]
    assert "NOT a mathematical proof" in boundary
    assert "nothing whatever about treatment effectiveness" in boundary


def test_regression_counts_are_all_zero(amendment: dict[str, Any]) -> None:
    regression = amendment["ARM_A_POST_TREATMENT_REGRESSION"]
    assert regression["verdict"] == "PASS"
    assert regression["recorded_steps_per_trace"] == 1200
    for key in ("target_mismatches", "state_mismatches", "vx_mismatches",
                "wz_mismatches", "predicate_mismatches"):
        assert regression[key] == 0


def test_regression_counts_match_the_treatment_artefact(amendment: dict[str, Any]) -> None:
    """Bound from the evidence, not restated from an instruction."""
    treatment = json.loads((REPO / TREATMENT_REL).read_text())
    totals: dict[str, int] = {}
    for trace in treatment["arm_a_post_treatment_regression"]["recorded_traces"].values():
        for channel, count in trace["mismatches_by_channel"].items():
            totals[channel] = totals.get(channel, 0) + count
    assert amendment["ARM_A_POST_TREATMENT_REGRESSION"]["per_channel"] == totals


def test_treatment_evidence_is_bound_by_hash(amendment: dict[str, Any]) -> None:
    bound = amendment["TREATMENT_EVIDENCE"]["validation_artefact"]
    assert bound["sha256"] == hashlib.sha256(
        (REPO / TREATMENT_REL).read_bytes()).hexdigest()
    assert bound["verdict"] == "PASS"
    assert amendment["TREATMENT_EVIDENCE"]["treatment_commit"] == TREATMENT_COMMIT


def test_treatment_evidence_is_not_reduced_to_a_boolean(amendment: dict[str, Any]) -> None:
    evidence = amendment["TREATMENT_EVIDENCE"]
    assert evidence["analytic_fixtures"]["count"] == 13
    assert len(evidence["analytic_fixtures"]["names"]) == 13
    assert len(evidence["defective_selector_controls"]) == 4
    assert all(c["detected"] for c in evidence["defective_selector_controls"].values())
    assert evidence["refusal_controls"]["all_refused"] is True
    assert evidence["treatment_sensitivity"]["is_not_a_no_op"] is True


def test_one_factor_contract_declares_exactly_one_difference(
    amendment: dict[str, Any],
) -> None:
    contract = amendment["ONE_FACTOR_EXECUTION_CONTRACT"]
    assert contract["behavioural_overrides"] == ["target"]
    difference = contract["only_declared_difference"]
    assert difference["ARM_A_CONTROL"]["target_type"] == "PATH_VERTEX"
    assert difference["ARM_B_TREATMENT"]["target_type"] == "ARC_LENGTH_INTERPOLATED"
    shared = contract["shared_by_both_arms"]
    for item in ("the seed", "max_steps", "the goal tolerance", "the route and frozen polyline",
                 "the look-ahead distance", "the primary outcome"):
        assert item in shared


def test_both_arms_must_execute_from_one_tree(amendment: dict[str, Any]) -> None:
    note = amendment["ONE_FACTOR_EXECUTION_CONTRACT"]["both_arms_execute_from_one_source_tree"]
    assert "one repository HEAD" in note
    assert "pre-treatment commit" in note


def test_version_chain_is_complete_and_linked(amendment: dict[str, Any]) -> None:
    nodes = amendment["VERSION_CHAIN"]
    assert [n["node"] for n in nodes] == [
        "INTERVENTION_V1", "ENVIRONMENT_V2", "TRACKER_INJECTION_EQUIVALENCE",
        "ENVIRONMENT_V3", "ARC_LENGTH_INTERPOLATED_TARGET_SELECTOR_VALIDATION",
        "ENVIRONMENT_V4"]
    assert nodes[0]["predecessor"] is None
    for earlier, later in itertools.pairwise(nodes):
        assert later["predecessor"] == earlier["node"]
        assert later["reason"] and later["evidence_basis"] and later["timestamp_utc"]


def test_no_arm_ran_and_the_manifest_is_not_frozen_here(amendment: dict[str, Any]) -> None:
    assert amendment["EXECUTION_STATUS"] == "NOT_RUN"
    assert amendment["arms_executed"] == 0
    assert amendment["ARM_A_EXECUTION"] == "NOT_STARTED"
    assert amendment["ARM_B_EXECUTION"] == "NOT_STARTED"
    assert amendment["EXECUTION_MANIFEST"] == "NOT_FROZEN_BY_THIS_AMENDMENT"
    assert "cannot truthfully contain the SHA" in amendment["execution_manifest_note"]


def test_scene_and_environment_boundaries_carry_forward(amendment: dict[str, Any]) -> None:
    scene = amendment["scene_limitation_carried_forward"]
    assert scene["scene_byte_identity"] == "NOT_VERIFIED_REMOTE_STREAMED_ASSET"
    assert scene["no_scene_sha_generated"] is True
    assert "does not establish that the Hospital scene loads" in amendment[
        "EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY"]


# --------------------------------------------------------------------------
# immutability controls
# --------------------------------------------------------------------------


def test_unchanged_regeneration_reproduces_the_artefact() -> None:
    before = _sha()
    outcome = v4mod.freeze()
    assert outcome["V4_AMENDMENT"] == "FROZEN"
    assert outcome["refrozen"] is False
    assert _sha() == before


@pytest.mark.parametrize(
    "attribute",
    ["V4_SEAM_SHA256", "TREATMENT_SHA256", "V3_SHA256", "V2_SHA256",
     "PREREG_SHA256", "EQUIVALENCE_SHA256", "CONTROL_SHA256"],
)
def test_a_mutated_pin_refuses_and_writes_nothing(
    attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _sha()
    monkeypatch.setattr(v4mod, attribute, "0" * 64)
    outcome = v4mod.freeze()
    assert outcome["V4_AMENDMENT"] == "REFUSED"
    assert outcome["reasons"]
    assert _sha() == before


def test_a_changed_override_surface_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    before = _sha()
    monkeypatch.setattr(
        v4mod, "live_override_surface",
        lambda: {"behavioural_overrides": ["target", "step"],
                 "both_selectors_expose_one_method": False})
    outcome = v4mod.freeze()
    assert outcome["V4_AMENDMENT"] == "REFUSED"
    assert outcome["stage"] == "override surface"
    assert _sha() == before


def test_a_failed_arm_a_regression_would_block_the_freeze(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = json.loads((REPO / TREATMENT_REL).read_text())
    broken["arm_a_post_treatment_regression"]["verdict"] = "FAIL"
    target = tmp_path / "broken.json"
    target.write_text(json.dumps(broken))
    monkeypatch.setattr(v4mod, "REPO", tmp_path)
    monkeypatch.setattr(v4mod, "TREATMENT_REL", target.name)
    monkeypatch.setattr(v4mod, "TREATMENT_SHA256", hashlib.sha256(
        target.read_bytes()).hexdigest())
    outcome = v4mod.verify_treatment(
        {"behavioural_overrides": ["target"], "both_selectors_expose_one_method": True,
         "subclass_behavioural_overrides": ["target"]})
    assert outcome["ok"] is False
    assert any("regression" in r for r in outcome["reasons"])


def test_refusal_is_structured_not_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v4mod, "TREATMENT_SHA256", "0" * 64)
    outcome = v4mod.freeze()
    assert outcome["V4_AMENDMENT"] == "REFUSED"
    assert isinstance(outcome["reasons"], list)
    assert "declines rather than raising" in outcome["note"]


def test_restoring_the_pins_reproduces_the_original_sha() -> None:
    before = _sha()
    assert v4mod.freeze()["V4_AMENDMENT"] == "FROZEN"
    assert _sha() == before == V4_AMENDMENT_SHA256
