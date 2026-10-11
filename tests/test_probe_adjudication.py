"""The replacement criterion, tested against the cases that retired the old one.

Every failure class here was measured, not imagined. The numbers come from
``gates/scenes/support_causal_controls_20260906.json``, produced on synthetic
geometry from a committed harness, and from the recovered historical defect at
``acd53d0``. Nothing in this file is tuned to Hospital, and no Hospital value
appears in it.

The load-bearing tests are the ones that must FAIL for a wrong implementation:
raw distance equality must not by itself condemn a probe, and raw distance
diversity must not by itself absolve one. Those two are the whole reason the
previous criterion was retired, so they are asserted directly rather than left
implied by the other cases passing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from navfm.probe_adjudication import (
    DEFAULT_TOLERANCE_M,
    Reason,
    adjudicate,
    geometric_residual,
)

REPO = Path(__file__).resolve().parents[1]
CONTROLS = REPO / "gates" / "scenes" / "support_causal_controls_20260906.json"

#: Measured on the synthetic fixture. Kept as literals so a change to the
#: evidence file is visible as a test failure rather than silently absorbed.
CORRECT_RESIDUAL_M = 5.96e-08
WRONG_COLLIDER_RESIDUAL_M = -0.275
SHARED_OWNER_RESIDUAL_M = +0.550


def _probe(**kw):
    base = dict(hit=True, returned_collider="/W/T", declared_target="/W/T",
                observed_distance_m=0.5, expected_distance_m=0.5)
    base.update(kw)
    return adjudicate(**base)


class TestTheFiveMeasuredCases:
    def test_correct_target_is_probative(self) -> None:
        v = _probe(observed_distance_m=0.5 + CORRECT_RESIDUAL_M)
        assert v.probative and v.reason is Reason.PROBATIVE
        assert v.identity_ok and v.geometry_ok

    def test_removed_target_is_not_probative(self) -> None:
        v = _probe(hit=False, returned_collider=None, observed_distance_m=None)
        assert not v.probative and v.reason is Reason.NO_HIT
        assert v.residual_m is None, "a miss has no residual; 0.0 would read as a perfect answer"

    def test_wrong_collider_is_not_probative(self) -> None:
        v = _probe(returned_collider="/W/Interloper",
                   observed_distance_m=0.5 + WRONG_COLLIDER_RESIDUAL_M)
        assert not v.probative and v.reason is Reason.WRONG_IDENTITY
        assert not v.identity_ok and not v.geometry_ok

    def test_shared_owner_is_not_probative(self) -> None:
        """The historical 12x5.9 mechanism: many targets, one collider."""
        for target in ("/W/S0", "/W/S1", "/W/S2"):
            v = adjudicate(hit=True, returned_collider="/W/SharedSlab",
                           declared_target=target,
                           observed_distance_m=0.5 + SHARED_OWNER_RESIDUAL_M,
                           expected_distance_m=0.5)
            assert not v.probative and v.reason is Reason.WRONG_IDENTITY

    def test_unrelated_geometry_is_not_probative(self) -> None:
        v = _probe(hit=False, returned_collider=None, observed_distance_m=None)
        assert not v.probative


class TestTheRetiredCriterionCannotDriveTheVerdict:
    def test_identical_distances_alone_do_not_condemn(self) -> None:
        """Three correct probes returning the same number stay probative.

        This is the false positive that retired the old rule, on Hospital and
        independently on Warehouse.
        """
        vs = [adjudicate(hit=True, returned_collider=f"/W/T{i}", declared_target=f"/W/T{i}",
                         observed_distance_m=0.5, expected_distance_m=0.5) for i in range(3)]
        assert all(v.probative for v in vs)
        assert len({v.residual_m for v in vs}) == 1, "identical by construction, and permitted"

    def test_diverse_distances_alone_do_not_absolve(self) -> None:
        """Distinct distances on wrong colliders remain non-probative."""
        vs = [adjudicate(hit=True, returned_collider="/W/Other", declared_target=f"/W/T{i}",
                         observed_distance_m=0.5 + 0.1 * (i + 1), expected_distance_m=0.5)
              for i in range(3)]
        assert len({v.residual_m for v in vs}) == 3, "the distances genuinely differ"
        assert not any(v.probative for v in vs)


class TestNeitherConditionSubstitutesForTheOther:
    def test_right_object_at_the_wrong_distance_fails(self) -> None:
        v = _probe(observed_distance_m=0.5 + 0.4)
        assert not v.probative and v.reason is Reason.GEOMETRY_INCONSISTENT
        assert v.identity_ok and not v.geometry_ok

    def test_wrong_object_at_the_right_distance_fails(self) -> None:
        v = _probe(returned_collider="/W/Impostor")
        assert not v.probative and v.reason is Reason.WRONG_IDENTITY
        assert not v.identity_ok and v.geometry_ok, "geometry alone cannot rescue identity"


class TestOwnershipAndTolerance:
    def test_a_preregistered_owner_is_accepted(self) -> None:
        v = _probe(returned_collider="/W/Owner", preregistered_owners=("/W/Owner",))
        assert v.probative

    def test_an_undeclared_owner_is_not_accepted(self) -> None:
        """A shared collider cannot acquire ownership by being what answered."""
        v = _probe(returned_collider="/W/Owner", preregistered_owners=())
        assert not v.probative and v.reason is Reason.WRONG_IDENTITY

    def test_the_default_tolerance_is_the_frozen_height_agreement_value(self) -> None:
        assert DEFAULT_TOLERANCE_M == 0.05

    @pytest.mark.parametrize("residual", [CORRECT_RESIDUAL_M, 0.049, -0.049])
    def test_residuals_inside_tolerance_pass(self, residual: float) -> None:
        assert _probe(observed_distance_m=0.5 + residual).geometry_ok

    @pytest.mark.parametrize("residual", [0.051, -0.051,
                                          WRONG_COLLIDER_RESIDUAL_M, SHARED_OWNER_RESIDUAL_M])
    def test_residuals_outside_tolerance_fail(self, residual: float) -> None:
        assert not _probe(observed_distance_m=0.5 + residual).geometry_ok

    def test_a_zero_tolerance_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            _probe(tolerance_m=0.0)

    def test_a_miss_has_no_residual(self) -> None:
        assert geometric_residual(None, 0.5) is None


@pytest.fixture(scope="module")
def controls() -> dict:
    if not CONTROLS.is_file():
        pytest.skip(f"control evidence absent: {CONTROLS}")
    return json.loads(CONTROLS.read_text())["cases"]


class TestAgainstTheRecordedEvidence:
    """Re-adjudicate the archived control measurements themselves."""

    def test_the_recorded_correct_case_readjudicates_as_probative(self, controls: dict) -> None:
        c = controls["CORRECT_TARGET"]
        v = adjudicate(hit=c["hit"], returned_collider=c["returned_collider"],
                       declared_target=c["declared_target"],
                       observed_distance_m=c["observed_distance_m"],
                       expected_distance_m=c["expected_distance_m"])
        assert v.probative

    @pytest.mark.parametrize("case", ["TARGET_REMOVED", "WRONG_COLLIDER", "UNRELATED_GEOMETRY"])
    def test_the_recorded_failure_cases_readjudicate_as_non_probative(
        self, controls: dict, case: str
    ) -> None:
        c = controls[case]
        v = adjudicate(hit=c["hit"], returned_collider=c["returned_collider"],
                       declared_target=c["declared_target"],
                       observed_distance_m=c["observed_distance_m"],
                       expected_distance_m=c["expected_distance_m"])
        assert not v.probative

    def test_the_recorded_shared_owner_case_readjudicates_as_non_probative(
        self, controls: dict
    ) -> None:
        for r in controls["SHARED_OWNER"]["probes"]:
            v = adjudicate(hit=r["hit"], returned_collider=r["returned_collider"],
                           declared_target=r["declared_target"],
                           observed_distance_m=r["observed_distance_m"],
                           expected_distance_m=r["expected_distance_m"])
            assert not v.probative and v.reason is Reason.WRONG_IDENTITY
