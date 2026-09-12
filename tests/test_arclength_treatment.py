"""Controls for ArcLengthInterpolatedTargetSelector.

The treatment is the manipulated factor, so the tests that matter are the ones
that would catch it being subtly wrong rather than obviously broken: the corner
where arc length and Euclidean chord diverge, the tie that decides which segment
a pose belongs to, and the route end where clamping is the difference between
steering at the goal and steering past it.

Four expectations are restated here as literals rather than imported from the
validation script. The script's fixture table is the oracle, and an oracle that
only ever checks itself is worth less than one that two independent hands agree
on.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from navfm.arm_environment_guard import check_contract
from navfm.collection.interpolated_target import InterpolatedLookaheadPursuit
from navfm.control import M3PRO_LIMITS, DemonstratorMode, PurePursuit
from navfm.target_selection import (
    ArcLengthInterpolatedTargetSelector,
    LegacyVertexTargetSelector,
    TargetSelection,
    TargetSelectionRefused,
    TargetSelector,
    interpolated_selection,
)

REPO = Path(__file__).resolve().parents[1]
ARTEFACT = REPO / "gates/BO10/arclength_treatment_validation_20260912.json"

_SPEC = importlib.util.spec_from_file_location(
    "validate_treatment", REPO / "scripts" / "validate_arclength_treatment.py")
assert _SPEC and _SPEC.loader
harness = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(harness)

LOOKAHEAD = 0.45
TOL = 1e-12
CONFIG: dict[str, Any] = {
    "lookahead": LOOKAHEAD, "goal_tol": 0.20, "limits": M3PRO_LIMITS,
    "mode": DemonstratorMode.NONHOLONOMIC, "cruise_v": 0.35,
}
#: 3 m east then 4 m north. Cumulative arc length 0, 3, 7.
L_ROUTE = np.array([[0.0, 0.0], [3.0, 0.0], [3.0, 4.0]])


def _tracker(route: np.ndarray, **kwargs: Any) -> PurePursuit:
    return PurePursuit(route.copy(), **CONFIG, **kwargs)


# --------------------------------------------------------------------------
# expectations restated independently of the harness table
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pose", "target", "why"),
    [
        ((3.0, 0.0), (3.0, 0.45), "the corner tie resolves to s=3, then 0.45 up leg two"),
        ((2.7, 0.0), (3.0, 0.15), "arc length turns the corner; a 0.45 m chord would "
                                  "reach (3.15, 0), which is off the route"),
        ((3.0, 3.8), (3.0, 4.0), "6.8 + 0.45 exceeds the 7 m route, so it clamps"),
        ((1.0, 2.0), (1.45, 0.0), "equidistant from both legs; the tie takes s=1, not s=5"),
    ],
)
def test_hand_computed_targets(
    pose: tuple[float, float], target: tuple[float, float], why: str
) -> None:
    got = interpolated_selection(L_ROUTE, np.array(pose), LOOKAHEAD).point
    assert math.hypot(got[0] - target[0], got[1] - target[1]) <= TOL, why


def test_arc_length_is_not_euclidean_chord() -> None:
    """The distinguishing property of the treatment."""
    got = interpolated_selection(L_ROUTE, np.array([2.7, 0.0]), LOOKAHEAD)
    chord = np.array([2.7 + LOOKAHEAD, 0.0])
    assert math.hypot(*(got.point - chord)) > 0.1
    assert got.target_s == pytest.approx(3.15)


def test_target_is_always_on_the_polyline() -> None:
    """Arm B is defined as a point ON the route. A target off it would be a
    different experiment."""
    for x in np.linspace(-1.0, 4.0, 60):
        for y in np.linspace(-1.0, 5.0, 30):
            point = interpolated_selection(L_ROUTE, np.array([x, y]), LOOKAHEAD).point
            on_leg_one = abs(point[1]) <= TOL and -TOL <= point[0] <= 3.0 + TOL
            on_leg_two = abs(point[0] - 3.0) <= TOL and -TOL <= point[1] <= 4.0 + TOL
            assert on_leg_one or on_leg_two


def test_it_is_not_circle_intersection_pure_pursuit() -> None:
    """Q3's distinction, preserved. The target sits one look-ahead along the
    ROUTE, which is not the same as a look-ahead circle intersection, and it is
    generally not 0.45 m from the pose at all."""
    selection = interpolated_selection(L_ROUTE, np.array([1.0, 2.0]), LOOKAHEAD)
    euclidean = float(np.linalg.norm(selection.point - np.array([1.0, 2.0])))
    assert euclidean > LOOKAHEAD
    assert selection.target_s == pytest.approx(1.45)


# --------------------------------------------------------------------------
# arc-length invariants
# --------------------------------------------------------------------------


@pytest.mark.parametrize("x", np.linspace(-1.0, 4.0, 25))
@pytest.mark.parametrize("y", np.linspace(-1.0, 5.0, 13))
def test_arclength_invariants_hold_everywhere(x: float, y: float) -> None:
    selection = interpolated_selection(L_ROUTE, np.array([x, y]), LOOKAHEAD)
    assert selection.target_s >= selection.projection_s - 1e-15
    assert selection.target_s <= selection.total_length + TOL
    assert selection.target_s == pytest.approx(
        min(selection.projection_s + LOOKAHEAD, selection.total_length), abs=TOL)


def test_target_never_moves_backwards_along_the_route() -> None:
    previous = -1.0
    for x in np.linspace(0.0, 3.0, 40):
        selection = interpolated_selection(L_ROUTE, np.array([x, 0.0]), LOOKAHEAD)
        assert selection.target_s >= previous - TOL
        previous = selection.target_s


def test_clamp_flag_marks_the_route_end() -> None:
    assert interpolated_selection(L_ROUTE, np.array([3.0, 3.8]), LOOKAHEAD).clamped_at_route_end
    assert not interpolated_selection(L_ROUTE, np.array([1.0, 0.0]), LOOKAHEAD).clamped_at_route_end


# --------------------------------------------------------------------------
# Arm A is untouched
# --------------------------------------------------------------------------


def test_default_path_is_still_the_legacy_selector() -> None:
    assert isinstance(_tracker(L_ROUTE)._selector, LegacyVertexTargetSelector)


def test_default_and_explicit_legacy_still_agree_after_treatment_exists() -> None:
    default = _tracker(L_ROUTE)
    injected = _tracker(L_ROUTE, target_selector=LegacyVertexTargetSelector())
    for x in np.linspace(0.0, 3.0, 40):
        position = np.array([x, 0.1])
        assert default.target(position).tolist() == injected.target(position).tolist()
        assert default._idx == injected._idx
        assert default.finished == injected.finished


def test_treatment_advances_the_vertex_index_exactly_as_the_control_arm() -> None:
    """`finished` reads that index. Leaving it frozen would add a second
    uncontrolled difference to a one-factor experiment."""
    legacy = _tracker(L_ROUTE)
    treatment = _tracker(L_ROUTE, target_selector=ArcLengthInterpolatedTargetSelector())
    for x in np.linspace(0.0, 3.0, 40):
        position = np.array([x, 0.0])
        legacy.target(position)
        treatment.target(position)
        assert treatment._idx == legacy._idx
        assert treatment.finished == legacy.finished


# --------------------------------------------------------------------------
# surface
# --------------------------------------------------------------------------


def test_selector_surface_is_one_method() -> None:
    behavioural = [
        n for n in dir(ArcLengthInterpolatedTargetSelector)
        if not n.startswith("_") and callable(getattr(ArcLengthInterpolatedTargetSelector, n))
    ]
    assert behavioural == ["select_target"]


def test_treatment_satisfies_the_selector_protocol() -> None:
    assert isinstance(ArcLengthInterpolatedTargetSelector(), TargetSelector)
    assert ArcLengthInterpolatedTargetSelector.target_type == "ARC_LENGTH_INTERPOLATED"


def test_treatment_cannot_reach_the_speed_law() -> None:
    """Same command for the same target, whatever else the selector carries."""

    class Loud(ArcLengthInterpolatedTargetSelector):
        def __init__(self) -> None:
            super().__init__()
            self.cruise_v = 99.0
            self.max_w = 99.0

    plain = _tracker(L_ROUTE, target_selector=ArcLengthInterpolatedTargetSelector())
    loud = _tracker(L_ROUTE, target_selector=Loud())
    for x in np.linspace(0.0, 3.0, 25):
        assert plain.step(np.array([x, 0.1]), 0.3) == loud.step(np.array([x, 0.1]), 0.3)


def test_subclass_override_surface_is_still_target_only() -> None:
    base = {n for n in dir(PurePursuit) if not n.startswith("__")}
    overridden = sorted(n for n in base if n in InterpolatedLookaheadPursuit.__dict__)
    assert [n for n in overridden if n not in {"target_type"}] == ["target"]


# --------------------------------------------------------------------------
# port fidelity
# --------------------------------------------------------------------------


def test_selector_reproduces_the_frozen_subclass() -> None:
    seam = _tracker(L_ROUTE, target_selector=ArcLengthInterpolatedTargetSelector())
    frozen = InterpolatedLookaheadPursuit(L_ROUTE.copy(), **CONFIG)
    for s in np.linspace(-0.5, 7.5, 80):
        pose = np.array([s * 0.6, s * 0.4])
        assert np.array_equal(seam.target(pose), frozen.target(pose))
        assert seam._idx == frozen._idx


# --------------------------------------------------------------------------
# refusals
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("route", "pose", "lookahead"),
    [
        (np.zeros((0, 2)), (0.0, 0.0), LOOKAHEAD),
        (np.array([[0.0, 0.0]]), (0.0, 0.0), LOOKAHEAD),
        (np.array([0.0, 1.0, 2.0]), (0.0, 0.0), LOOKAHEAD),
        (np.zeros((3, 3)), (0.0, 0.0), LOOKAHEAD),
        (np.array([[0.0, 0.0], [float("inf"), 0.0]]), (0.0, 0.0), LOOKAHEAD),
        (np.array([[1.0, 1.0], [1.0, 1.0]]), (0.0, 0.0), LOOKAHEAD),
        (L_ROUTE, (float("nan"), 0.0), LOOKAHEAD),
        (L_ROUTE, (0.0, 0.0), -0.45),
        (L_ROUTE, (0.0, 0.0), float("nan")),
    ],
)
def test_invalid_input_is_refused_with_a_reason(
    route: np.ndarray, pose: tuple[float, float], lookahead: float
) -> None:
    with pytest.raises(TargetSelectionRefused) as excinfo:
        interpolated_selection(route, np.asarray(pose, dtype=np.float64), lookahead)
    assert str(excinfo.value)


def test_the_refusal_is_a_named_type_not_a_bare_error() -> None:
    assert issubclass(TargetSelectionRefused, ValueError)


def test_valid_input_is_not_refused() -> None:
    assert interpolated_selection(L_ROUTE, np.array([1.0, 0.0]), LOOKAHEAD).point is not None


# --------------------------------------------------------------------------
# negative controls: the fixture suite must reject a wrong treatment
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "selector",
    [harness._WrongOffsetSelector, harness._BackwardSelector,
     harness._ExtrapolatingSelector, harness._LaterSegmentTieSelector],
)
def test_defective_selectors_are_rejected_by_the_fixtures(selector: Any) -> None:
    results = harness.negative_controls()
    assert all(r["DETECTED"] for r in results.values())


def test_wrong_offset_is_caught_on_the_target_coordinate() -> None:
    result = harness.negative_controls()["wrong_offset"]
    assert result["DETECTED"]
    assert "target" in result["first_rejection"]["quantity"]
    assert result["first_rejection"]["separation_m"] > TOL


def test_endpoint_violation_is_caught_by_the_clamp_fixtures() -> None:
    """A treatment that extrapolates past the route end works fine on interior
    segments, which is exactly why the endpoint fixtures exist."""
    result = harness.negative_controls()["extrapolates_past_route_end"]
    assert result["DETECTED"]
    rejected = set(result["fixtures_rejected"])
    assert {"J_REMAINING_SHORTER_THAN_LOOKAHEAD", "K_EXACT_ROUTE_ENDPOINT"} & rejected


def test_tie_violation_is_caught_by_the_tie_fixture() -> None:
    result = harness.negative_controls()["tie_resolves_to_later_segment"]
    assert result["DETECTED"]
    assert "L_PROJECTION_TIE_CASE" in result["fixtures_rejected"]


# --------------------------------------------------------------------------
# sensitivity
# --------------------------------------------------------------------------


def test_treatment_is_not_a_no_op() -> None:
    sens = harness.sensitivity()
    assert sens["TREATMENT_IS_NOT_A_NO_OP"] is True
    assert sens["differs"]["legacy_target"] != sens["differs"]["treatment_target"]


def test_the_two_rules_agree_at_the_route_end() -> None:
    sens = harness.sensitivity()
    assert sens["TREATMENT_AGREES_WHERE_GEOMETRY_COINCIDES"] is True
    assert all(case["agree"] for case in sens["agrees"]["cases"])


def test_interior_agreement_is_geometrically_impossible() -> None:
    """Recorded because it is a true property of the two rules, not a quirk:
    a vertex one look-ahead along the route is at most 0.45 m away in a straight
    line, so the legacy strict-less-than test always steps past it."""
    route = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    legacy = _tracker(route)
    legacy._idx = 1
    treatment = _tracker(route, target_selector=ArcLengthInterpolatedTargetSelector())
    treatment._idx = 1
    pose = np.array([0.55, 0.0])
    assert float(np.linalg.norm(route[1] - pose)) < LOOKAHEAD
    assert not np.allclose(legacy.target(pose), treatment.target(pose))


# --------------------------------------------------------------------------
# contracts: history stays frozen
# --------------------------------------------------------------------------


def test_v2_still_refuses_for_the_historically_correct_reason() -> None:
    result = check_contract(REPO, "V2")
    assert result["CONTRACT_SATISFIED"] == "FAIL"
    assert "scientific_code.control_sha256" in [d["field"] for d in result["drift"]]


def test_v3_now_refuses_because_the_treatment_landed_in_the_pinned_seam() -> None:
    result = check_contract(REPO, "V3")
    assert result["CONTRACT_SATISFIED"] == "FAIL"
    assert "scientific_code.target_selection_sha256" in [
        d["field"] for d in result["drift"]]


# --------------------------------------------------------------------------
# the persisted evidence
# --------------------------------------------------------------------------


@pytest.fixture
def record() -> dict[str, Any]:
    return json.loads(ARTEFACT.read_text())


def test_validation_passed_and_no_arm_ran(record: dict[str, Any]) -> None:
    assert record["ARC_LENGTH_TREATMENT_VALIDATION"] == "PASS"
    assert record["TREATMENT_SELECTOR"] == "IMPLEMENTED_AND_VALIDATED"
    assert record["EXECUTION_STATUS"] == "NOT_RUN"
    assert record["arms_executed"] == 0
    assert record["ARM_A_EXECUTION"] == "NOT_STARTED"
    assert record["ARM_B_EXECUTION"] == "NOT_STARTED"
    assert record["V4_AMENDMENT"] == "NOT_CREATED"
    assert record["EXECUTION_MANIFEST"] == "NOT_FROZEN"


def test_arm_a_regression_is_clean(record: dict[str, Any]) -> None:
    regression = record["arm_a_post_treatment_regression"]
    assert regression["verdict"] == "PASS"
    for trace in regression["recorded_traces"].values():
        assert trace["steps_evaluated"] == 1200
        assert sum(trace["mismatches_by_channel"].values()) == 0
        assert set(trace["comparisons"].values()) == {"PASS"}
        assert trace["max_numerical_difference"] == 0.0


def test_tolerance_was_declared_before_use(record: dict[str, Any]) -> None:
    standard = record["numerical_standard"]
    assert standard["declared_before_fixtures_ran"] is True
    assert standard["tolerance_m"] == TOL
    assert "cannot absorb a geometric error" in standard["justification"]


def test_command_field_is_labelled_a_counterfactual(record: dict[str, Any]) -> None:
    field = record["offline_command_field"]
    assert field["LABEL"] == "COMMAND_FIELD_COUNTERFACTUAL_ONLY"
    assert field["steps_evaluated"] == 1200
    joined = " ".join(field["WHAT_THIS_DOES_NOT_ANSWER"])
    assert "what trajectory Arm B would produce" in joined
    assert "success rate" in joined
    # The substance, not the word: the poses came from the control behaviour and
    # the treatment would not have visited them.
    why = field["why_the_domain_is_endogenous"]
    assert "produced by the control behaviour" in why
    assert "would not have visited them" in why
    assert "never a miniature Arm B" in why


def test_no_threshold_was_introduced(record: dict[str, Any]) -> None:
    note = record["offline_command_field"]["no_threshold_is_introduced"]
    assert "not a success threshold" in note
    assert "not a target to beat" in note


def test_independent_oracle_is_declared(record: dict[str, Any]) -> None:
    oracle = record["independent_oracle"]
    assert "integer arc lengths" in oracle["method"]
    assert "self-consistency" in oracle["not_validated_against"]


def test_shared_laws_recorded_unchanged(record: dict[str, Any]) -> None:
    laws = record["shared_controller_laws"]
    assert laws["SHARED_CONTROLLER_LAWS"] == "UNCHANGED"
    assert laws["control_py_unchanged_by_this_tranche"] is True
    assert all(m["identical"] for m in laws["members"].values())


def test_port_fidelity_states_its_boundary(record: dict[str, Any]) -> None:
    fidelity = record["port_fidelity"]
    assert fidelity["PORT_FIDELITY"] == "PASS"
    assert "does NOT independently establish" in fidelity["claim_boundary"]


def test_frozen_semantics_are_cited_not_invented(record: dict[str, Any]) -> None:
    semantics = record["frozen_semantics_used"]
    assert "gates/BO10/target_selection_controls_20260911.json" in semantics["source_of_truth"]
    assert "earlier segment" in semantics["tie_rule"]
    assert "never extrapolates" in semantics["route_end_rule"]
    assert "NOT" in semantics["not_circle_intersection"]


def test_artefact_records_the_contract_refusals(record: dict[str, Any]) -> None:
    status = record["contract_status"]
    assert status["V2"]["CONTRACT_SATISFIED"] == "FAIL"
    assert status["V3"]["CONTRACT_SATISFIED"] == "FAIL"
    assert status["V3"]["drift"] == ["scientific_code.target_selection_sha256"]


def test_implementation_identity_is_pinned(record: dict[str, Any]) -> None:
    implementation = record["implementation"]
    assert implementation["target_type"] == "ARC_LENGTH_INTERPOLATED"
    assert implementation["frozen_lookahead_m"] == LOOKAHEAD
    # The seam module has moved on since (the selector registry was added for
    # collector wiring), so the artefact is checked against the tree it actually
    # validated rather than against today's.
    import subprocess

    at_validation = subprocess.run(
        ["git", "-C", str(REPO), "show",
         "58825a6bdb36a09721e481640082ac5fca429550:src/navfm/target_selection.py"],
        capture_output=True, check=False)
    treatment_commit = subprocess.run(
        ["git", "-C", str(REPO), "show",
         "ef5e7f0feb6eb1bd5eed4ebb0638aaf2306e5333:src/navfm/target_selection.py"],
        capture_output=True, check=False)
    assert implementation["source_sha256"] == hashlib.sha256(
        treatment_commit.stdout).hexdigest()
    assert at_validation.returncode == 0


def test_selection_returns_the_declared_tuple_type() -> None:
    result = ArcLengthInterpolatedTargetSelector().select_target(
        L_ROUTE, np.array([1.0, 0.0]), 0, LOOKAHEAD)
    assert isinstance(result, TargetSelection)
    assert isinstance(result.next_index, int)
