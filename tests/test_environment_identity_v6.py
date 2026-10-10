"""Controls for V6: the first contract that pins a tree an arm can walk.

V5 pinned a tree in which every component resolved and nothing invoked them.
The distinction V6 exists to hold is:

    component exists != component is reachable != component is invoked in the
    intended sequence != real runtime succeeds

So these controls check two different things and never let them blur. The
amendment's own claims are checked against the artefacts it binds by hash. And
the readiness levels are checked to stop short: V6 must establish levels 1-3
and must NOT claim level 5, because no rehearsal can establish that Isaac
launches.

The predecessor controls are permanent. If V2, V3, V4 or V5 ever accepts this
tree, an old contract was rewritten and the chain is no longer append-only.
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
    V2_AMENDMENT_SHA256,
    V3_AMENDMENT_SHA256,
    V4_AMENDMENT_SHA256,
    V5_AMENDMENT_REL,
    V5_AMENDMENT_SHA256,
    V6_AMENDMENT_REL,
    V6_AMENDMENT_SHA256,
    check_contract,
)
from navfm.execution_environment import (
    CONTRACT_FIELDS_BY_VERSION,
    V6_ADDITIONAL_CRITICAL_FIELDS,
)

REPO = Path(__file__).resolve().parents[1]
V6 = REPO / V6_AMENDMENT_REL
LIFECYCLE_REL = "gates/BO10/lifecycle_reachability_rehearsal_20260912.json"
GAP_REL = "gates/BO10/execution_reachability_gap_v2_20260912.json"

_SPEC = importlib.util.spec_from_file_location(
    "amend_v6", REPO / "scripts" / "amend_environment_identity_v6.py")
assert _SPEC and _SPEC.loader
v6mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v6mod)


def _sha() -> str:
    return hashlib.sha256(V6.read_bytes()).hexdigest()


@pytest.fixture
def amendment() -> dict[str, Any]:
    return json.loads(V6.read_text())


# --- the chain ---------------------------------------------------------------

#: V6's own freeze. Its tree is the one V6 answers for, and the one whose runner
#: had no real entry point -- which is why V7 exists.
V6_FREEZE_COMMIT = "356ef56cee20e2d82e5275e8316d9d3158fbd665"


@pytest.mark.isaac_host
def test_v6_remains_reachable_after_being_superseded() -> None:
    """Which version is authoritative is asserted by that version's own suite.
    What this checks is that V6 still answers for itself."""
    assert AUTHORITATIVE_CONTRACT_VERSION in CONTRACTS
    assert {"V2", "V3", "V4", "V5", "V6"} <= set(CONTRACTS)
    assert check_contract(REPO, "V6")["version"] == "V6"


def test_v6_accepted_the_tree_at_its_own_freeze_commit() -> None:
    """Each amendment answers for the state it froze, not for every later one."""
    frozen = json.loads(V6.read_text())["EXECUTION_ENVIRONMENT_IDENTITY_V6"][
        "frozen_contract_values"]
    for field, rel in (
            ("scientific_code.arm_runner_sha256",
             "scripts/run_terminal_approach_intervention.py"),
            ("scientific_code.arm_lifecycle_sha256", "src/navfm/arm_lifecycle.py")):
        at_freeze = subprocess.run(
            ["git", "-C", str(REPO), "show", f"{V6_FREEZE_COMMIT}:{rel}"],
            capture_output=True, check=False)
        assert at_freeze.returncode == 0, rel
        assert frozen[field] == hashlib.sha256(at_freeze.stdout).hexdigest(), field


@pytest.mark.isaac_host
def test_v6_now_refuses_the_real_mode_tree() -> None:
    """Expected: the runner gained the entry point that builds the real adapter.

    Permanent historical control. If this ever passes, V6 was rewritten.
    """
    result = check_contract(REPO, "V6")
    assert result["CONTRACT_SATISFIED"] == "FAIL"
    assert "scientific_code.arm_runner_sha256" in [d["field"] for d in result["drift"]]


@pytest.mark.isaac_host
@pytest.mark.parametrize("version", ["V2", "V3", "V4", "V5"])
def test_every_predecessor_still_refuses(version: str) -> None:
    """Permanent. If any of these passes, an old contract was rewritten."""
    assert check_contract(REPO, version)["CONTRACT_SATISFIED"] == "FAIL"


@pytest.mark.isaac_host
def test_v5_refuses_for_the_lifecycle_transition_specifically() -> None:
    """Not merely 'invalid' -- it must name the field that moved."""
    drift = [d["field"] for d in check_contract(REPO, "V5")["drift"]]
    assert "scientific_code.arm_runner_sha256" in drift


@pytest.mark.isaac_host
def test_each_predecessor_refuses_for_its_own_reason() -> None:
    reasons = {v: tuple(sorted(d["field"] for d in check_contract(REPO, v)["drift"]))
               for v in ("V2", "V3", "V5")}
    assert len(set(reasons.values())) == len(reasons), reasons


def test_predecessor_files_are_byte_unchanged() -> None:
    for rel, pinned in (
            ("gates/BO10/environment_identity_v2_20260911.json", V2_AMENDMENT_SHA256),
            ("gates/BO10/environment_identity_v3_20260911.json", V3_AMENDMENT_SHA256),
            ("gates/BO10/environment_identity_v4_20260912.json", V4_AMENDMENT_SHA256),
            (V5_AMENDMENT_REL, V5_AMENDMENT_SHA256)):
        assert hashlib.sha256((REPO / rel).read_bytes()).hexdigest() == pinned, rel


def test_v6_does_not_claim_to_repair_v5(amendment: dict[str, Any]) -> None:
    amends = amendment["amends"]
    assert amends["append_only"] is True
    assert amends["v1_to_v5_rewritten"] is False
    assert "continue to refuse" in amends["this_does_not_repair_v5"]


def test_v6_adds_exactly_one_contract_field() -> None:
    """A version bump must be justified by what it pins, not by its number."""
    added = set(CONTRACT_FIELDS_BY_VERSION["V6"]) - set(CONTRACT_FIELDS_BY_VERSION["V5"])
    assert added == set(V6_ADDITIONAL_CRITICAL_FIELDS)
    assert added == {"scientific_code.arm_lifecycle_sha256"}


def test_pinned_v6_sha_matches_the_artefact() -> None:
    assert _sha() == V6_AMENDMENT_SHA256


# --- what V6 records ---------------------------------------------------------

def test_the_lifecycle_evidence_is_bound_by_hash(amendment: dict[str, Any]) -> None:
    evidence = amendment["LIFECYCLE_REACHABILITY_EVIDENCE"]
    assert evidence["artefact"]["sha256"] == hashlib.sha256(
        (REPO / LIFECYCLE_REL).read_bytes()).hexdigest()
    assert evidence["verdict"] == "PASS"
    assert evidence["ENTRYPOINT_REACHABILITY"] == "PASS"
    assert evidence["NON_ISAAC_LIFECYCLE_REHEARSAL"] == "PASS"


def test_the_gap_record_is_bound_by_hash(amendment: dict[str, Any]) -> None:
    record = amendment["EXECUTION_REACHABILITY_GAP_V2"]["record"]
    assert record["sha256"] == hashlib.sha256(
        (REPO / GAP_REL).read_bytes()).hexdigest()


def test_every_negative_control_is_recorded_as_having_fired(
    amendment: dict[str, Any],
) -> None:
    """A readiness instrument that cannot fail has not been shown to measure."""
    controls = amendment["LIFECYCLE_REACHABILITY_EVIDENCE"]["negative_controls"]
    expected = {"missing_call", "defined_but_never_called", "wrong_order",
                "duplicate_call", "early_return", "structured_refusal",
                "exception_during_refusal_handling", "unknown_mode"}
    assert set(controls) == expected
    assert all(controls[name] is True for name in expected), controls


def test_producer_reachability_does_not_reuse_the_old_label(
    amendment: dict[str, Any],
) -> None:
    """The V2 definition was 'an importable callable exists'. Same words for a
    different claim would be the more dangerous outcome, not the tidier one."""
    coverage = amendment["LIFECYCLE_REACHABILITY_EVIDENCE"]["OUTPUT_PRODUCER_REACHABILITY"]
    assert coverage["verdict"] == "PASS"
    assert "importable callable" in coverage["supersedes"]
    for requirement in ("bound to a lifecycle stage", "reachable from",
                        "demonstrated invocation", "ordering", "multiplicity"):
        assert requirement in coverage["definition"], requirement


def test_one_orchestration_serves_both_arms_and_both_modes(
    amendment: dict[str, Any],
) -> None:
    lifecycle = amendment["ARM_LIFECYCLE"]
    assert lifecycle["one_orchestration_for_both_arms_and_both_modes"] is True
    assert lifecycle["adapters_cannot_change_scientific_configuration"] is True
    assert lifecycle["real_adapter"] != lifecycle["rehearsal_adapter"]
    assert lifecycle["required_arm_scoped_producers"] == 6


def test_the_only_manipulated_factor_is_target_selection(
    amendment: dict[str, Any],
) -> None:
    contract = amendment["ONE_FACTOR_EXECUTION_CONTRACT"]
    assert contract["behavioural_overrides"] == ["target"]
    difference = contract["only_declared_difference"]
    assert difference["ARM_A_CONTROL"]["target_type"] == "PATH_VERTEX"
    assert difference["ARM_B_TREATMENT"]["target_type"] == "ARC_LENGTH_INTERPOLATED"
    assert contract["rehearsal_confirmed_only_target_differs"] == ["target_selector"]


# --- where V6 must stop ------------------------------------------------------

def test_v6_establishes_levels_one_to_three_and_not_level_five(
    amendment: dict[str, Any],
) -> None:
    """The whole point of the layered model: stop short, explicitly."""
    levels = amendment["READINESS_MODEL"]
    for level in ("LEVEL_1_COMPONENT_RESOLUTION", "LEVEL_2_ENTRYPOINT_REACHABILITY",
                  "LEVEL_3_NON_ISAAC_LIFECYCLE_REHEARSAL"):
        assert levels[level] == "established", level
    assert levels["LEVEL_5_REAL_RUNTIME_ATTEMPT"].startswith("NOT established")


def test_v6_does_not_claim_isaac_will_run(amendment: dict[str, Any]) -> None:
    assert "does NOT establish that Isaac launches" in amendment[
        "LIFECYCLE_REACHABILITY_EVIDENCE"]["CLAIM_BOUNDARY"]
    environment = amendment["EXECUTION_ENVIRONMENT_CLAIM_BOUNDARY"]
    for unclaimed in ("Hospital scene loads", "render loop runs",
                      "collector completes"):
        assert unclaimed in environment, unclaimed
    assert amendment["authorisation"].startswith("NOT AUTHORISED")


def test_v6_freezes_no_execution_manifest(amendment: dict[str, Any]) -> None:
    """A contract that froze its own manifest could not be checked against one."""
    assert amendment["EXECUTION_MANIFEST"] == "NOT_FROZEN_BY_THIS_AMENDMENT"


def test_no_arm_has_executed(amendment: dict[str, Any]) -> None:
    assert amendment["EXECUTION_STATUS"] == "NOT_RUN"
    assert amendment["arms_executed"] == 0
    assert amendment["ARM_A_EXECUTION"] == "NOT_STARTED"
    assert amendment["ARM_B_EXECUTION"] == "NOT_STARTED"


def test_the_artefact_says_no_arm_has_run_in_its_own_semantics(
    amendment: dict[str, Any],
) -> None:
    assert amendment["artifact_semantics"] == "AMENDMENT_ONLY_NO_ARM_HAS_RUN"


# --- refusal controls --------------------------------------------------------

def test_v6_refuses_to_refreeze_on_a_tree_it_no_longer_describes() -> None:
    """A superseded amendment must not quietly re-freeze itself onto a later
    tree. It refuses, and -- the part that matters -- it writes nothing."""
    before = _sha()
    outcome = v6mod.freeze()
    assert outcome["V6_AMENDMENT"] == "REFUSED"
    assert _sha() == before


def test_the_v6_artefact_is_byte_unchanged_by_any_of_this() -> None:
    """The whole point of an append-only chain: V6's bytes never move."""
    assert _sha() == V6_AMENDMENT_SHA256


@pytest.mark.parametrize("attribute", ["V5_SHA256", "PREREG_SHA256"])
def test_a_mutated_pin_refuses_and_writes_nothing(
    attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not hasattr(v6mod, attribute):
        pytest.skip(f"{attribute} is not a pin in this amender")
    before = _sha()
    monkeypatch.setattr(v6mod, attribute, "0" * 64)
    assert v6mod.freeze()["V6_AMENDMENT"] == "REFUSED"
    assert _sha() == before


def test_a_failed_lifecycle_rehearsal_blocks_the_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V6's central claim is the rehearsal. It must not survive losing it."""
    before = _sha()
    broken = json.loads((REPO / LIFECYCLE_REL).read_text())
    broken["LIFECYCLE_REACHABILITY"] = "FAIL"
    monkeypatch.setattr(v6mod, "verify_lifecycle", lambda: {
        "ok": False, "reasons": ["the lifecycle rehearsal did not pass"],
        "record": broken})
    assert v6mod.freeze()["V6_AMENDMENT"] == "REFUSED"
    assert _sha() == before


def test_the_amender_declines_rather_than_raising() -> None:
    """A refusal is a recorded result. A traceback is not."""
    assert "recorded scientific result" in v6mod.refused("probe", ["reason"])["note"]


def test_v6_refuses_to_silently_overwrite_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing a frozen, cited amendment requires a V7, not a rewrite."""
    before = _sha()
    monkeypatch.setattr(v6mod, "EXPECTED_RECORDED_STEPS", 1)
    outcome = v6mod.freeze()
    assert outcome["V6_AMENDMENT"] == "REFUSED"
    assert _sha() == before


def test_v5_is_still_readable_from_history() -> None:
    """V6's measured transitions are only meaningful if V5's tree can be read."""
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"HEAD:{V5_AMENDMENT_REL}"],
        capture_output=True, check=False)
    assert proc.returncode == 0
    assert hashlib.sha256(proc.stdout).hexdigest() == V5_AMENDMENT_SHA256
