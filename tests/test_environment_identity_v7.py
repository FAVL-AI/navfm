"""Controls for V7: the first contract that pins a reachable real path.

V6 pinned a tree whose rehearsal passed end to end. That was true, and it was
measured entirely through the rehearsal adapter. The manifest declared the real
adapter by dotted path, nothing constructed it, and ``mode="REAL"`` was passed
nowhere -- so the canonical Arm-A invocation V6 authorised could only refuse.

The distinction V7 holds is one rung finer than V6's:

    rehearsal reachability != real-mode reachability != real runtime succeeds

So these controls never assert that a name resolves. They assert that the
contract moved for exactly one reason, that the reachability evidence it binds
was measured rather than declared, and that V7 stops short of claiming Isaac
runs. The predecessor controls are permanent: if V2-V6 ever accept this tree,
an old contract was rewritten.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from navfm.arm_environment_guard import (
    AUTHORITATIVE_CONTRACT_VERSION,
    CONTRACTS,
    V6_AMENDMENT_REL,
    V6_AMENDMENT_SHA256,
    V7_AMENDMENT_REL,
    V7_AMENDMENT_SHA256,
    check_contract,
)
from navfm.execution_environment import CONTRACT_FIELDS_BY_VERSION

REPO = Path(__file__).resolve().parents[1]
V7 = REPO / V7_AMENDMENT_REL
REACHABILITY_REL = "gates/BO10/real_mode_reachability_20260917.json"
V6_FREEZE_COMMIT = "356ef56cee20e2d82e5275e8316d9d3158fbd665"

_SPEC = importlib.util.spec_from_file_location(
    "amend_v7", REPO / "scripts" / "amend_environment_identity_v7.py")
assert _SPEC and _SPEC.loader
v7mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v7mod)


def _sha() -> str:
    return hashlib.sha256(V7.read_bytes()).hexdigest()


@pytest.fixture
def amendment() -> dict[str, Any]:
    return json.loads(V7.read_text())


# --- the chain ---------------------------------------------------------------

#: V7's own freeze. Its tree is the one V7 answers for -- the one whose real
#: path was reachable and whose adapter handed the collector a SimConfig.
V7_FREEZE_COMMIT = "01916dfa3a2901177ae1bc07caffd0881139d798"


def test_v7_remains_reachable_after_being_superseded() -> None:
    """Which version is authoritative is asserted by that version's own suite.
    What this checks is that V7 still answers for itself."""
    assert AUTHORITATIVE_CONTRACT_VERSION in CONTRACTS
    assert {"V2", "V3", "V4", "V5", "V6", "V7"} <= set(CONTRACTS)
    assert check_contract(REPO, "V7")["version"] == "V7"


def test_v7_accepted_the_tree_at_its_own_freeze_commit() -> None:
    """Each amendment answers for the state it froze, not for every later one."""
    frozen = json.loads(V7.read_text())["EXECUTION_ENVIRONMENT_IDENTITY_V7"][
        "frozen_contract_values"]
    for field, rel in (
            ("scientific_code.arm_lifecycle_sha256", "src/navfm/arm_lifecycle.py"),
            ("scientific_code.collect_sha256", "src/navfm/isaac/collect.py")):
        at_freeze = subprocess.run(
            ["git", "-C", str(REPO), "show", f"{V7_FREEZE_COMMIT}:{rel}"],
            capture_output=True, check=False)
        assert at_freeze.returncode == 0, rel
        assert frozen[field] == hashlib.sha256(at_freeze.stdout).hexdigest(), field


def test_v7_now_refuses_the_repaired_seam_tree() -> None:
    """Expected: the adapter now hands the collector the app it owns.

    Permanent historical control. If this ever passes, V7 was rewritten.
    """
    result = check_contract(REPO, "V7")
    assert result["CONTRACT_SATISFIED"] == "FAIL"
    drift = [d["field"] for d in result["drift"]]
    assert "scientific_code.collect_sha256" in drift


@pytest.mark.parametrize("version", ["V2", "V3", "V4", "V5", "V6"])
def test_every_predecessor_still_refuses(version: str) -> None:
    """Permanent. If any of these passes, an old contract was rewritten."""
    assert check_contract(REPO, version)["CONTRACT_SATISFIED"] == "FAIL"


def test_v6_refuses_for_the_runner_transition_specifically() -> None:
    """Not merely 'invalid' -- it must name the field that moved."""
    drift = [d["field"] for d in check_contract(REPO, "V6")["drift"]]
    assert "scientific_code.arm_runner_sha256" in drift


def test_v7_pins_the_same_fields_as_v6() -> None:
    """A version bump is justified by what moved, not by inventing a field."""
    assert CONTRACT_FIELDS_BY_VERSION["V7"] == CONTRACT_FIELDS_BY_VERSION["V6"]


def test_only_the_execution_path_moved(amendment: dict[str, Any]) -> None:
    """Three values moved, and each is the entry point or its dispatch.

    The controller, the selectors, the collector and the preregistration are
    not among them: the manipulated factor must not shift in a tranche about
    reachability.
    """
    transitions = amendment["SOURCE_IDENTITY_TRANSITIONS_V6_TO_V7"]
    assert set(transitions["changed"]) == {
        "scientific_code.arm_runner_sha256",
        "scientific_code.intervention_runner_sha256",
        "scientific_code.arm_lifecycle_sha256",
    }
    assert transitions["added"] == {}
    assert transitions["unchanged_field_count"] == 46


def test_every_moved_value_carries_a_rationale(amendment: dict[str, Any]) -> None:
    """A changed pin without a reason is a changed pin nobody reviewed."""
    transitions = amendment["SOURCE_IDENTITY_TRANSITIONS_V6_TO_V7"]
    rationale = transitions["expected_change"]
    assert set(rationale) == set(transitions["changed"])
    assert all(len(text) > 40 for text in rationale.values())


def test_the_manipulated_factor_did_not_move(amendment: dict[str, Any]) -> None:
    transitions = amendment["SOURCE_IDENTITY_TRANSITIONS_V6_TO_V7"]
    for untouched in ("scientific_code.control_sha256",
                      "scientific_code.target_selection_sha256",
                      "scientific_code.collect_sha256",
                      "scientific_code.preregistration_sha256"):
        assert untouched not in transitions["changed"], untouched


def test_v6_is_byte_unchanged(amendment: dict[str, Any]) -> None:
    assert hashlib.sha256(
        (REPO / V6_AMENDMENT_REL).read_bytes()).hexdigest() == V6_AMENDMENT_SHA256
    assert amendment["amends"]["predecessor"]["sha256"] == V6_AMENDMENT_SHA256


def test_v7_does_not_claim_to_repair_v6(amendment: dict[str, Any]) -> None:
    amends = amendment["amends"]
    assert amends["append_only"] is True
    assert amends["v1_to_v6_rewritten"] is False
    assert "continue to refuse" in amends["this_does_not_repair_v6"]


def test_pinned_v7_sha_matches_the_artefact() -> None:
    assert _sha() == V7_AMENDMENT_SHA256


# --- what V7 records ---------------------------------------------------------

def test_the_defect_is_recorded_as_not_started(amendment: dict[str, Any]) -> None:
    """An authorisation that never began is not a failed control arm."""
    gap = amendment["REAL_MODE_UNREACHABLE_FROM_ENTRYPOINT"]
    assert gap["attempted_arm_a_authorisation"] == "AUTHORISED_BUT_NOT_STARTED"
    assert gap["explicitly_not"] == "ARM_A_FAILED"
    assert gap["observed"]["adapter_ever_constructed"] is False
    assert gap["observed"]["mode_real_passed_anywhere"] is False
    assert gap["observed"]["canonical_arm_a_invocation_exit_code"] == 2
    assert gap["observed_at"] == V6_FREEZE_COMMIT
    for key in ("pre_arm_a_created", "post_arm_a_created", "isaac_started"):
        assert gap["evidence"][key] is False


def test_the_reachability_evidence_is_bound_by_hash(amendment: dict[str, Any]) -> None:
    evidence = amendment["REAL_MODE_REACHABILITY_EVIDENCE"]
    assert evidence["artefact"]["sha256"] == hashlib.sha256(
        (REPO / REACHABILITY_REL).read_bytes()).hexdigest()
    assert evidence["verdict"] == "PASS"
    assert evidence["mode_entered"] == "REAL"
    assert evidence["real_adapter_instantiated"] is True


def test_the_probe_stopped_before_any_capture(amendment: dict[str, Any]) -> None:
    """PRE_ENV_CAPTURED writes PRE_ARM_A, and no arm is authorised."""
    evidence = amendment["REAL_MODE_REACHABILITY_EVIDENCE"]
    assert evidence["refused_at_stage"] == "MANIFEST_VALIDATED"
    assert evidence["production_labels_present"] == []


def test_every_reachability_control_fired(amendment: dict[str, Any]) -> None:
    """A readiness instrument that cannot fail has not been shown to measure."""
    controls = amendment["REAL_MODE_REACHABILITY_EVIDENCE"]["negative_controls"]
    assert controls, "no controls were recorded"
    assert all(controls.values()), controls
    # The two that matter most: the criterion can pass, and the historical tree fails.
    assert controls["a_correct_probe_is_accepted"] is True
    assert controls["the_runner_at_the_v6_freeze_has_no_real_entry_point"] is True


# --- where V7 must stop ------------------------------------------------------

def test_v7_establishes_level_four_five_and_not_level_five(
    amendment: dict[str, Any],
) -> None:
    levels = amendment["READINESS_MODEL"]
    assert levels["LEVEL_4_5_REAL_MODE_ENTRYPOINT_REACHABILITY"] == "established by V7"
    assert levels["LEVEL_5_REAL_RUNTIME_ATTEMPT"].startswith("NOT established")


def test_v7_does_not_claim_isaac_will_run(amendment: dict[str, Any]) -> None:
    boundary = amendment["EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY"]
    for unclaimed in ("Isaac launches", "Hospital scene loads", "render loop",
                      "collector completes"):
        assert unclaimed in boundary, unclaimed
    assert amendment["authorisation"].startswith("NOT AUTHORISED")


def test_v7_freezes_no_execution_manifest(amendment: dict[str, Any]) -> None:
    assert amendment["EXECUTION_MANIFEST"] == "NOT_FROZEN_BY_THIS_AMENDMENT"


def test_no_arm_has_executed(amendment: dict[str, Any]) -> None:
    assert amendment["EXECUTION_STATUS"] == "NOT_RUN"
    assert amendment["arms_executed"] == 0
    assert amendment["ARM_A_EXECUTION"] == "NOT_STARTED"
    assert amendment["ARM_B_EXECUTION"] == "NOT_STARTED"
    assert amendment["artifact_semantics"] == "AMENDMENT_ONLY_NO_ARM_HAS_RUN"


# --- refusal controls --------------------------------------------------------

def test_v7_refuses_to_refreeze_on_a_tree_it_no_longer_describes() -> None:
    """A superseded amendment must not quietly re-freeze itself onto a later
    tree. It refuses, and -- the part that matters -- it writes nothing."""
    before = _sha()
    outcome = v7mod.freeze()
    assert outcome["V7_AMENDMENT"] == "REFUSED"
    assert _sha() == before


def test_the_v7_artefact_is_byte_unchanged_by_any_of_this() -> None:
    """The whole point of an append-only chain: V7's bytes never move."""
    assert _sha() == V7_AMENDMENT_SHA256


@pytest.mark.parametrize("attribute", ["PREREG_SHA256", "CONTROL_SHA256"])
def test_a_mutated_pin_refuses_and_writes_nothing(
    attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _sha()
    monkeypatch.setattr(v7mod, attribute, "0" * 64)
    assert v7mod.freeze()["V7_AMENDMENT"] == "REFUSED"
    assert _sha() == before


def test_a_failed_reachability_probe_blocks_the_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V7's central claim is the probe. It must not survive losing it."""
    before = _sha()
    monkeypatch.setattr(v7mod, "verify_reachability", lambda: {
        "ok": False, "reasons": ["the real-mode probe did not pass"], "record": None})
    assert v7mod.freeze()["V7_AMENDMENT"] == "REFUSED"
    assert _sha() == before


def test_the_amender_declines_rather_than_raising() -> None:
    """A refusal is a recorded result. A traceback is not."""
    assert "recorded scientific result" in v7mod.refused("probe", ["reason"])["note"]


def test_v6_is_still_readable_from_history() -> None:
    """V7's measured transitions are only meaningful if V6's tree can be read."""
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"HEAD:{V6_AMENDMENT_REL}"],
        capture_output=True, check=False)
    assert proc.returncode == 0
    assert hashlib.sha256(proc.stdout).hexdigest() == V6_AMENDMENT_SHA256
