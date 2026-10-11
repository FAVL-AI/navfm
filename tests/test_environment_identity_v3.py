"""Controls for the V3 amendment and the source-identity transition.

V3 exists because V2 worked. V2 pinned the controller by content hash so a
change would be impossible to miss; the injection seam changed it, and V2
refuses. The thing that would quietly destroy that evidence is a successor
amendment that edits its predecessor's hash so everything passes again, so the
central control here is the opposite: today's tree must still FAIL against V2
and PASS against V3, and both answers must remain reachable.

The second thing under test is chronology. The re-pin has to have been frozen
while the seam was empty, because a justification written after the treatment
landed would cover the neutral refactor and the manipulated factor with one
piece of evidence and no later reader could separate them.
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
    V2_AMENDMENT_REL,
    V2_AMENDMENT_SHA256,
    V3_AMENDMENT_REL,
    V3_AMENDMENT_SHA256,
    check_contract,
)
from navfm.execution_environment import (
    CONTRACT_CRITICAL_FIELDS,
    V3_ADDITIONAL_CRITICAL_FIELDS,
    contract_fields,
)

REPO = Path(__file__).resolve().parents[1]
V3 = REPO / V3_AMENDMENT_REL
V2 = REPO / V2_AMENDMENT_REL
EQUIVALENCE = REPO / "gates/BO10/tracker_injection_equivalence_20260911.json"
V3_FREEZE_COMMIT = "58825a6bdb36a09721e481640082ac5fca429550"

_SPEC = importlib.util.spec_from_file_location(
    "amend_v3", REPO / "scripts" / "amend_environment_identity_v3.py")
assert _SPEC and _SPEC.loader
v3mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v3mod)


@pytest.fixture
def amendment() -> dict[str, Any]:
    return json.loads(V3.read_text())


# --------------------------------------------------------------------------
# V3 did not weaken V2
# --------------------------------------------------------------------------


@pytest.mark.isaac_host
def test_current_tree_still_fails_against_v2() -> None:
    """The load-bearing control. If this ever passes, V2 was rewritten.

    Membership rather than equality: later tranches legitimately move more
    fields, so V2's drift list grows. What must never change is that V2 still
    names the controller it froze."""
    result = check_contract(REPO, "V2")
    assert result["CONTRACT_SATISFIED"] == "FAIL"
    assert "scientific_code.control_sha256" in [d["field"] for d in result["drift"]]


def test_v3_accepted_the_tree_at_its_own_freeze_commit() -> None:
    """The historically meaningful claim. V3 pinned what was there when it
    froze; asserting that it still accepts today's tree would just be asserting
    that nothing has happened since."""
    frozen = json.loads(V3.read_text())["EXECUTION_ENVIRONMENT_IDENTITY_V3"][
        "frozen_contract_values"]
    at_freeze = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{V3_FREEZE_COMMIT}:src/navfm/target_selection.py"],
        capture_output=True, check=False)
    assert at_freeze.returncode == 0
    assert frozen["scientific_code.target_selection_sha256"] == hashlib.sha256(
        at_freeze.stdout).hexdigest()
    control_at_freeze = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{V3_FREEZE_COMMIT}:src/navfm/control.py"],
        capture_output=True, check=False)
    assert frozen["scientific_code.control_sha256"] == hashlib.sha256(
        control_at_freeze.stdout).hexdigest()


@pytest.mark.isaac_host
def test_current_tree_now_refuses_against_v3_because_the_treatment_landed() -> None:
    """Expected, and the reason is reported rather than assumed: the treatment
    was implemented in the seam module V3 pins, after V3 froze."""
    result = check_contract(REPO, "V3")
    assert result["CONTRACT_SATISFIED"] == "FAIL"
    assert "scientific_code.target_selection_sha256" in [
        d["field"] for d in result["drift"]]


@pytest.mark.isaac_host
def test_v2_and_v3_refuse_for_different_reasons() -> None:
    """Both refuse, which is correct, but not for the same thing. V2 names the
    controller the seam edited; V3 does not, because V3 froze after it."""
    v2_drift = {d["field"] for d in check_contract(REPO, "V2")["drift"]}
    v3_drift = {d["field"] for d in check_contract(REPO, "V3")["drift"]}
    assert "scientific_code.control_sha256" in v2_drift
    assert "scientific_code.control_sha256" not in v3_drift
    assert "scientific_code.target_selection_sha256" in v3_drift
    assert v2_drift != v3_drift


def test_v2_file_is_untouched() -> None:
    assert hashlib.sha256(V2.read_bytes()).hexdigest() == V2_AMENDMENT_SHA256


def test_v2_field_set_is_not_mutated_by_v3() -> None:
    """V3 pins more; it does not edit what V2 pinned."""
    assert contract_fields("V2") == CONTRACT_CRITICAL_FIELDS
    assert len(contract_fields("V3")) == len(contract_fields("V2")) + 1
    assert set(contract_fields("V3")) - set(contract_fields("V2")) == set(
        V3_ADDITIONAL_CRITICAL_FIELDS)


@pytest.mark.isaac_host
def test_the_guard_does_not_fall_back_between_versions() -> None:
    """A barrier that tried one contract and fell back to another would accept a
    tree the authoritative one rejects.

    Which version is authoritative is asserted by that version's own suite; what
    is checked here is that naming a version answers for that version, and that
    V3 remains reachable after being superseded."""
    assert AUTHORITATIVE_CONTRACT_VERSION in CONTRACTS
    assert {"V2", "V3"} <= set(CONTRACTS)
    for version in ("V2", "V3"):
        assert check_contract(REPO, version)["version"] == version


def test_unknown_contract_version_is_refused_not_guessed() -> None:
    assert check_contract(REPO, "V9")["CONTRACT_SATISFIED"] == "UNKNOWN_VERSION"


# --------------------------------------------------------------------------
# the transition is recorded, not concealed
# --------------------------------------------------------------------------


def test_source_identity_transition_is_explicit(amendment: dict[str, Any]) -> None:
    transition = amendment["SOURCE_IDENTITY_TRANSITION"]
    assert transition["SOURCE_BYTE_IDENTITY_ACROSS_V2_TO_V3"] == "CHANGED"
    assert transition["expected_and_intentional"] is True
    assert transition["V2_CONTROL_SOURCE_IDENTITY"] != transition["V3_CONTROL_SOURCE_IDENTITY"]
    assert transition["V2_CONTROL_SOURCE_IDENTITY"].startswith("f5992b60")
    assert transition["V3_CONTROL_SOURCE_IDENTITY"].startswith("679cd60f")


def test_the_obsolete_claim_is_retired_not_restated(amendment: dict[str, Any]) -> None:
    transition = amendment["SOURCE_IDENTITY_TRANSITION"]
    assert "is now false" in transition["retired_claim"]
    assert "changed solely to introduce" in transition["replacement_claim"]
    assert "demonstrated behaviourally equivalent" in transition["replacement_claim"]


def test_replacement_claim_is_not_semantic_equivalence_by_inspection(
    amendment: dict[str, Any],
) -> None:
    transition = amendment["SOURCE_IDENTITY_TRANSITION"]
    assert "no one read the diff" in transition[
        "this_is_not_a_claim_of_semantic_equivalence_by_inspection"]


def test_every_changed_field_carries_a_justification_and_evidence(
    amendment: dict[str, Any],
) -> None:
    changed = amendment["changed_from_v2"]
    assert changed["unexplained_hash_replacements"] == []
    for field in ("scientific_code.control_sha256", "scientific_code.target_selection_sha256"):
        entry = changed[field]
        assert entry["justification"]
        assert entry["evidence"]["sha256"]
        assert entry["old"] != entry["new"]


def test_the_added_field_is_marked_as_an_addition(amendment: dict[str, Any]) -> None:
    entry = amendment["changed_from_v2"]["scientific_code.target_selection_sha256"]
    assert entry["field_added_not_replaced"] is True
    assert entry["old"] == "<NOT_PINNED_BY_V2>"


# --------------------------------------------------------------------------
# the equivalence proof is bound, not merely cited
# --------------------------------------------------------------------------


def test_equivalence_artefact_is_bound_by_hash(amendment: dict[str, Any]) -> None:
    artefact = amendment["INJECTION_SEAM_BEHAVIOURAL_NEUTRALITY"]["artefact"]
    assert artefact["sha256"] == hashlib.sha256(EQUIVALENCE.read_bytes()).hexdigest()
    assert artefact["verdict"] == "PASS"


def test_the_counts_that_earned_the_pass_are_bound(amendment: dict[str, Any]) -> None:
    neutrality = amendment["INJECTION_SEAM_BEHAVIOURAL_NEUTRALITY"]
    assert neutrality["recorded_step_count"] == 1200
    assert neutrality["analytic_fixture_count"] == 15
    assert neutrality["target_mismatch_count"] == 0
    assert neutrality["state_mismatch_count"] == 0
    assert neutrality["command_mismatch_count"] == 0
    assert neutrality["predicate_mismatch_count"] == 0
    assert all(neutrality["negative_controls"].values())
    assert neutrality["state_drift_detected_on_index_after"] is True


def test_claim_wording_is_domain_bounded(amendment: dict[str, Any]) -> None:
    neutrality = amendment["INJECTION_SEAM_BEHAVIOURAL_NEUTRALITY"]
    assert "No behavioural difference was detected" in neutrality["CLAIM"]
    assert "1200 recorded run_00001 poses" in neutrality["CLAIM"]
    assert "15 analytic fixtures" in neutrality["CLAIM"]


def test_claim_does_not_assert_universal_equivalence(amendment: dict[str, Any]) -> None:
    """A substring ban would be the wrong test: the boundary earns its keep by
    naming the over-claim in order to deny it, and banning the words would push
    the artefact towards vaguer language, not safer language. So the assertion
    and the denial are checked separately."""
    neutrality = amendment["INJECTION_SEAM_BEHAVIOURAL_NEUTRALITY"]
    assert "universally equivalent" not in neutrality["CLAIM"].lower()
    boundary = neutrality["CLAIM_BOUNDARY"]
    assert "not a mathematical proof" in boundary
    assert "NOT claimed to be" in boundary and "universally equivalent" in boundary
    # the over-claim appears nowhere except inside its own denial
    for key, value in neutrality.items():
        if key == "CLAIM_BOUNDARY" or not isinstance(value, str):
            continue
        assert "universally equivalent" not in value.lower()


def test_outside_seam_laws_are_bound_by_region_hash(amendment: dict[str, Any]) -> None:
    laws = amendment["OUTSIDE_SEAM_LAW_IDENTITY"]
    assert laws["verdict"] == "PASS"
    assert laws["file_changed"] is True
    assert laws["mathematics_outside_seam_changed"] is False
    assert all(member["identical"] for member in laws["members"].values())
    for law in ("speed_and_angular_law_step", "route_completion_finished",
                "velocity_clipping_clamp", "se2_integration_unicycle"):
        assert law in laws["members"]


# --------------------------------------------------------------------------
# chronology
# --------------------------------------------------------------------------


def test_treatment_was_absent_at_freeze(amendment: dict[str, Any]) -> None:
    treatment = amendment["TREATMENT_ABSENCE_AT_FREEZE"]
    assert treatment["TREATMENT_SELECTOR_IMPLEMENTED"] is False
    assert treatment["ARC_LENGTH_INTERPOLATED_TARGET_SELECTOR"] == (
        "NOT_PRESENT_BEHIND_INJECTION_SEAM")
    assert treatment["concrete_selectors_declared_under_src"] == [
        "src/navfm/target_selection.py::LegacyVertexTargetSelector"]
    assert treatment["default_selector_is_legacy"] is True


def test_treatment_absence_claim_is_precise_about_the_old_subclass(
    amendment: dict[str, Any],
) -> None:
    """The interpolated subclass exists from an earlier tranche. The claim is
    that the SEAM is empty, not that no interpolated code exists anywhere."""
    note = amendment["TREATMENT_ABSENCE_AT_FREEZE"]["pre_existing_subclass_note"]
    assert "InterpolatedLookaheadPursuit" in note
    assert "does not occupy the injection seam" in note


def test_the_protocol_is_not_counted_as_a_selector(amendment: dict[str, Any]) -> None:
    treatment = amendment["TREATMENT_ABSENCE_AT_FREEZE"]
    assert treatment["selector_protocols_declared_under_src"] == [
        "src/navfm/target_selection.py::TargetSelector"]


def test_causal_chronology_is_recorded(amendment: dict[str, Any]) -> None:
    chain = amendment["causal_chronology"]
    assert chain[0].startswith("V2 froze")
    assert "no treatment present" in chain[2]
    assert chain[-1] == "only then may treatment code appear"
    assert "bundle the neutral refactor" in amendment["why_the_order_matters"]


def test_version_chain_is_complete_and_linked(amendment: dict[str, Any]) -> None:
    nodes = amendment["VERSION_CHAIN"]
    assert [n["node"] for n in nodes] == [
        "INTERVENTION_V1", "ENVIRONMENT_V2", "TRACKER_INJECTION_EQUIVALENCE",
        "ENVIRONMENT_V3"]
    assert nodes[0]["predecessor"] is None
    for earlier, later in itertools.pairwise(nodes):
        assert later["predecessor"] == earlier["node"]
        assert later["reason"]
        assert later["evidence_basis"]
        assert later["timestamp_utc"]


def test_v3_declares_v2_still_refuses(amendment: dict[str, Any]) -> None:
    history = amendment["V2_REMAINS_VALID_HISTORY"]
    assert history["v2_is_not_rewritten"] is True
    assert history["v2_still_refuses_the_post_seam_tree"] is True
    assert history["required_control"]["current_repo_against_V2"].startswith("REFUSE")


# --------------------------------------------------------------------------
# scope: V3 is not permission to reopen V2
# --------------------------------------------------------------------------


def test_nothing_else_moved(amendment: dict[str, Any]) -> None:
    unchanged = amendment["amends"]["unchanged_by_this_amendment"]
    for item in ("the seed", "arm order", "max_steps", "the target-selection factor",
                 "the kernel contract", "the NVIDIA hold count",
                 "the remote Hospital scene limitation", "the dirty-tree rules",
                 "the arm environment-equivalence policy"):
        assert item in unchanged
    assert amendment["changed_from_v2"]["no_other_field_changed"] is True


def test_scene_limitation_carried_forward(amendment: dict[str, Any]) -> None:
    scene = amendment["scene_limitation_carried_forward"]
    assert scene["scene_byte_identity"] == "NOT_VERIFIED_REMOTE_STREAMED_ASSET"
    assert scene["no_scene_sha_generated"] is True


def test_outstanding_dependencies_are_preserved(amendment: dict[str, Any]) -> None:
    assert amendment["EXECUTION_MANIFEST_OWES_ARM_OUTPUT_ALLOWLIST"] is True
    assert amendment["EXECUTION_MANIFEST"] == "NOT_FROZEN"


def test_no_arm_ran(amendment: dict[str, Any]) -> None:
    assert amendment["EXECUTION_STATUS"] == "NOT_RUN"
    assert amendment["arms_executed"] == 0
    assert amendment["ARM_A_EXECUTION"] == "NOT_STARTED"
    assert amendment["ARM_B_EXECUTION"] == "NOT_STARTED"
    assert amendment["TREATMENT_SELECTOR"] == "NOT_IMPLEMENTED"
    assert "NOT AUTHORISED" in amendment["authorisation"]


def test_amendment_is_append_only(amendment: dict[str, Any]) -> None:
    assert amendment["amends"]["append_only"] is True
    assert amendment["amends"]["v1_and_v2_rewritten"] is False
    assert amendment["amends"]["predecessor"]["sha256"] == V2_AMENDMENT_SHA256


def test_pinned_v3_sha_matches_the_artefact() -> None:
    assert hashlib.sha256(V3.read_bytes()).hexdigest() == V3_AMENDMENT_SHA256


# --------------------------------------------------------------------------
# regeneration and refusal
# --------------------------------------------------------------------------


def _artefact_sha() -> str:
    return hashlib.sha256(V3.read_bytes()).hexdigest()


def test_regeneration_now_refuses_and_demands_a_new_amendment() -> None:
    """V3 is frozen and cited by hash. The treatment changed a field it pins, so
    regenerating under the same identity is refused -- which is the mechanism
    that forces V4 to exist rather than letting V3 quietly absorb the change."""
    before = _artefact_sha()
    outcome = v3mod.freeze()
    assert outcome["V3_AMENDMENT"] == "REFUSED"
    # The chronology guard fires first, and it is the stronger refusal: V3 can
    # never be re-frozen now, because it is defined as the amendment that froze
    # while the seam was empty.
    assert outcome["stage"] == "treatment absence"
    assert "ArcLengthInterpolatedTargetSelector" in " ".join(outcome["reasons"])
    assert _artefact_sha() == before, "a refusal must not touch the frozen artefact"


def test_contract_drift_would_also_refuse_underneath_the_chronology_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two independent mechanisms, not one. With the chronology check satisfied,
    the frozen contract still refuses on the field the treatment moved."""
    before = _artefact_sha()
    monkeypatch.setattr(
        v3mod, "selectors_defined_in_source",
        lambda: {"concrete": ["src/navfm/target_selection.py::LegacyVertexTargetSelector"],
                 "protocols": ["src/navfm/target_selection.py::TargetSelector"]})
    outcome = v3mod.freeze()
    assert outcome["V3_AMENDMENT"] == "REFUSED"
    assert outcome["stage"] == "canonical regeneration"
    joined = " ".join(outcome["reasons"])
    assert "target_selection_sha256" in joined
    assert "V4" in joined
    assert _artefact_sha() == before


@pytest.mark.parametrize(
    "attribute",
    ["V3_CONTROL_SOURCE_IDENTITY", "EQUIVALENCE_SHA256", "V2_SHA256", "PREREG_SHA256"],
)
def test_a_mutated_pin_refuses_and_writes_nothing(
    attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _artefact_sha()
    monkeypatch.setattr(v3mod, attribute, "0" * 64)
    outcome = v3mod.freeze()
    assert outcome["V3_AMENDMENT"] == "REFUSED"
    assert outcome["reasons"]
    assert _artefact_sha() == before, "a refusal must not touch the frozen artefact"


def test_the_frozen_v3_artefact_is_never_rewritten() -> None:
    """Whatever the freeze path decides, the committed record keeps its hash."""
    before = _artefact_sha()
    v3mod.freeze()
    assert _artefact_sha() == before == V3_AMENDMENT_SHA256


def test_refusal_is_structured_not_a_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v3mod, "EQUIVALENCE_SHA256", "0" * 64)
    outcome = v3mod.freeze()
    assert outcome["V3_AMENDMENT"] == "REFUSED"
    assert "stage" in outcome
    assert isinstance(outcome["reasons"], list)
    assert "declines rather than raising" in outcome["note"]


def test_a_failing_equivalence_verdict_would_block_the_freeze(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The proof is a precondition, not a citation."""
    broken = json.loads(EQUIVALENCE.read_text())
    broken["ARM_A_LEGACY_INJECTION_EQUIVALENCE"] = "FAIL"
    target = tmp_path / "broken.json"
    target.write_text(json.dumps(broken))
    monkeypatch.setattr(v3mod, "EQUIVALENCE_REL", str(target.relative_to(tmp_path)))
    monkeypatch.setattr(v3mod, "REPO", tmp_path)
    outcome = v3mod.verify_equivalence()
    assert outcome["ok"] is False


def test_a_treatment_selector_would_block_the_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chronology is enforced, not merely documented."""
    monkeypatch.setattr(
        v3mod, "selectors_defined_in_source",
        lambda: {
            "concrete": [
                "src/navfm/target_selection.py::LegacyVertexTargetSelector",
                "src/navfm/target_selection.py::ArcLengthInterpolatedTargetSelector",
            ],
            "protocols": [],
        },
    )
    before = _artefact_sha()
    outcome = v3mod.freeze()
    assert outcome["V3_AMENDMENT"] == "REFUSED"
    assert outcome["stage"] == "treatment absence"
    assert _artefact_sha() == before
