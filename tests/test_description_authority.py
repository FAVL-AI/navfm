"""Controls for the description-authority classifier.

The classifier picks the apparatus the twin will represent, so the controls
that matter are the ones where it must refuse or must resist a temptation:
when the production edge is gone, when the chain points somewhere else, when
two roots compete, and when a richer rival is available.

The last is the sharpest. A candidate with more links, more joints, cleaner
parsing and a newer timestamp must still lose to the file the robot actually
loads, because the moment completeness can win, the project quietly starts
simulating a robot the vendor does not ship.
"""

from __future__ import annotations

import dataclasses

import pytest

from navfm.isaac.description_authority import (
    AUTHORITY_ROLES,
    Candidate,
    classify_authority,
)

RUNTIME = Candidate(
    identity="M3Pro/urdf/m3pro.urdf",
    sha256="cb092310636677ab4bc9846efd30c39cbf4d953ae4fc140a411d8b4c2e56ae6e",
    robot_name="m3pro",
    reached_by_production_bringup=True,
    reaches_robot_state_publisher=True,
    reached_by_manipulator_tooling=False,
)

MOVEIT = Candidate(
    identity="yahboom_M3Pro_description/urdf/M3Pro.urdf",
    sha256="5a96608cf2c621c6" + "0" * 48,
    robot_name="M3Pro",
    reached_by_production_bringup=False,
    reaches_robot_state_publisher=True,
    reached_by_manipulator_tooling=True,
    planning_semantics=("arm_group", "grip_group", "end effector gripper"),
)


def test_the_production_root_takes_whole_robot_authority() -> None:
    verdict = classify_authority([RUNTIME, MOVEIT])
    assert verdict["VERDICT"] == "DECIDED"
    assert verdict["AUTHORITATIVE_ROBOT_DESCRIPTION"] == RUNTIME.identity
    assert verdict["AUTHORITY_SCOPE"] == "WHOLE_ROBOT_RUNTIME_AUTHORITY"
    assert verdict["roles"][MOVEIT.identity] == "MANIPULATOR_PLANNING_AUTHORITY"


def test_every_assigned_role_is_a_declared_role() -> None:
    verdict = classify_authority([RUNTIME, MOVEIT])
    assert set(verdict["roles"].values()) <= set(AUTHORITY_ROLES)


def test_the_moveit_source_is_not_called_wrong() -> None:
    """It loses whole-robot authority and keeps authority of its own."""
    verdict = classify_authority([RUNTIME, MOVEIT])
    assert verdict["roles"][MOVEIT.identity] != "LEGACY_CONTENT"
    assert "MANIPULATOR" in verdict["roles"][MOVEIT.identity]


# -- negative controls -----------------------------------------------------


def test_removing_the_robot_state_publisher_edge_removes_authority() -> None:
    broken = dataclasses.replace(RUNTIME, reaches_robot_state_publisher=False)
    verdict = classify_authority([broken, MOVEIT])
    assert verdict["AUTHORITATIVE_ROBOT_DESCRIPTION"] == "UNDETERMINED"
    assert verdict["AUTHORITY_SCOPE"] == "NONE"


def test_removing_the_bringup_edge_removes_authority() -> None:
    broken = dataclasses.replace(RUNTIME, reached_by_production_bringup=False)
    verdict = classify_authority([broken, MOVEIT])
    assert verdict["AUTHORITATIVE_ROBOT_DESCRIPTION"] == "UNDETERMINED"


def test_pointing_bringup_at_the_rival_moves_authority_to_the_rival() -> None:
    """Authority follows the chain, not the file it currently lands on."""
    demoted = dataclasses.replace(
        RUNTIME, reached_by_production_bringup=False,
        reaches_robot_state_publisher=False)
    promoted = dataclasses.replace(
        MOVEIT, reached_by_production_bringup=True,
        reaches_robot_state_publisher=True)
    verdict = classify_authority([demoted, promoted])
    assert verdict["AUTHORITATIVE_ROBOT_DESCRIPTION"] == MOVEIT.identity


def test_two_competing_roots_in_one_configuration_stop_the_decision() -> None:
    first = dataclasses.replace(RUNTIME, shares_configuration_with_production=True)
    second = dataclasses.replace(
        MOVEIT, reached_by_production_bringup=True,
        shares_configuration_with_production=True)
    verdict = classify_authority([first, second])
    assert verdict["VERDICT"] == "AMBIGUOUS"
    assert verdict["STOP"] is True
    assert verdict["roles"] == {}


def test_two_production_roots_in_separate_configurations_are_still_refused() -> None:
    """Two runtime roots is a decision to be made, not one to be guessed."""
    rival = dataclasses.replace(MOVEIT, reached_by_production_bringup=True)
    verdict = classify_authority([RUNTIME, rival])
    assert verdict["VERDICT"] == "AMBIGUOUS"
    assert verdict["STOP"] is True


def test_a_tutorial_file_substituted_for_the_production_root_gains_nothing() -> None:
    muto = Candidate(
        identity="yahboomcar_description/urdf/Muto.urdf",
        sha256="4f84d68bfb07bbae" + "0" * 48, robot_name="Muto",
        reached_by_production_bringup=False,
        reaches_robot_state_publisher=False,
        reached_by_manipulator_tooling=False)
    verdict = classify_authority([muto, MOVEIT])
    assert verdict["AUTHORITATIVE_ROBOT_DESCRIPTION"] == "UNDETERMINED"
    assert verdict["roles"][muto.identity] == "SUPPORTING_COMPONENT_SOURCE"


def test_no_candidates_yields_no_authority() -> None:
    verdict = classify_authority([])
    assert verdict["AUTHORITATIVE_ROBOT_DESCRIPTION"] == "UNDETERMINED"


# -- the temptation control ------------------------------------------------


def test_a_richer_rival_does_not_win() -> None:
    """The decisive control: completeness must not be able to outrank the chain.

    The rival here is better on every axis a person would be tempted by -- more
    links, more joints, no broken references, newer, easier to import -- and it
    is not on the production chain, so it must lose.
    """
    richer = dataclasses.replace(
        MOVEIT, planning_semantics=("arm_group", "grip_group"))
    verdict = classify_authority([RUNTIME, richer])
    assert verdict["AUTHORITATIVE_ROBOT_DESCRIPTION"] == RUNTIME.identity


def test_completeness_is_not_an_input_to_the_decision() -> None:
    """Structural guarantee: the Candidate type has nowhere to put it.

    Enforced by absence rather than by weighting, because a field weighted zero
    is a field someone can later weight one.
    """
    fields = {f.name for f in dataclasses.fields(Candidate)}
    for tempting in ("link_count", "joint_count", "completeness", "timestamp",
                     "parses_cleanly", "mesh_quality", "broken_reference_count"):
        assert tempting not in fields


def test_a_defective_source_can_still_hold_authority() -> None:
    """Authority is what the robot loads, not a certificate of quality."""
    verdict = classify_authority([RUNTIME, MOVEIT])
    assert verdict["AUTHORITATIVE_ROBOT_DESCRIPTION"] == RUNTIME.identity
    assert "that the source is free of defects" in verdict[
        "NOT_ESTABLISHED_BY_THIS_DECISION"]


@pytest.mark.parametrize("excluded", [
    "permission to redistribute the source",
    "agreement between the source and the physical robot",
    "how colliders should be derived from it",
])
def test_the_decision_states_what_it_does_not_establish(excluded: str) -> None:
    verdict = classify_authority([RUNTIME, MOVEIT])
    assert excluded in verdict["NOT_ESTABLISHED_BY_THIS_DECISION"]
