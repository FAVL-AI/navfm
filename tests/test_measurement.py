"""Tests for the measurement envelope.

The whole point of the type is that `0` and "no measurement" cannot collapse into
each other, so most of these tests assert on that boundary directly, using the
three real incidents that motivated it.
"""

from __future__ import annotations

import pytest

from navfm.measurement import (
    Liveness,
    MeasurementEnvelope,
    MeasurementError,
    Status,
    not_run,
)


def live(**over) -> Liveness:
    base = dict(process_started=True, runtime_started=True, subject_open_attempted=True,
                subject_open_succeeded=True, measurement_executed=True, artifact_written=True)
    base.update(over)
    return Liveness(**base)


class TestTheThreeIncidents:
    """Each of these passed as clean once. None may pass again."""

    def test_scene_never_loaded_is_not_zero_errors(self) -> None:
        """`mdl_error_count = 0` from a run whose preflight refused the URL."""
        e = MeasurementEnvelope(
            measurement="mdl_error_count",
            liveness=Liveness(process_started=True),  # died at preflight
            items_examined=0,
        )
        assert e.status is Status.RUN_FAILED
        assert e.is_evidence is False
        assert e.to_json()["value"] is None
        assert "NO_EVIDENCE" in e.render()

    def test_a_job_that_never_ran_reports_not_run(self) -> None:
        """The self-matching `pgrep` wait: a wrapper alive, the job inert."""
        e = not_run("render_completed", note="wrapper self-matched; job never started")
        assert e.status is Status.NOT_RUN
        assert e.is_evidence is False

    def test_a_verifier_that_examined_nothing_is_not_clean(self) -> None:
        """A validator over an empty population found no faults. Not the same."""
        e = MeasurementEnvelope(measurement="unresolved_references", liveness=live(),
                                value=0, items_examined=0)
        assert e.status is Status.RUN_LIVE_NO_MEASUREMENT
        assert e.is_evidence is False

    def test_a_stationary_robot_does_not_prove_zero_collisions(self) -> None:
        e = MeasurementEnvelope(measurement="collisions", liveness=live(),
                                value=0, items_examined=0)
        assert e.is_evidence is False


class TestTheCleanZero:
    def test_a_live_measurement_over_a_real_population_is_evidence(self) -> None:
        e = MeasurementEnvelope(measurement="mdl_error_count", liveness=live(),
                                value=0, items_examined=1917)
        assert e.status is Status.MEASURED_ZERO
        assert e.is_evidence is True
        assert e.require_evidence() == 0

    def test_a_nonzero_measurement_is_also_evidence(self) -> None:
        e = MeasurementEnvelope(measurement="mdl_error_count", liveness=live(),
                                value=138, items_examined=1917)
        assert e.status is Status.MEASURED_NONZERO
        assert e.require_evidence() == 138

    @pytest.mark.parametrize("zero", [0, 0.0, False, [], {}, ""])
    def test_every_falsy_value_still_needs_liveness(self, zero) -> None:
        good = MeasurementEnvelope(measurement="m", liveness=live(), value=zero,
                                   items_examined=5)
        assert good.status is Status.MEASURED_ZERO


class TestLivenessIsEnforced:
    def test_a_value_without_liveness_is_refused_at_construction(self) -> None:
        with pytest.raises(MeasurementError, match="liveness is incomplete"):
            MeasurementEnvelope(measurement="m", liveness=Liveness(), value=0)

    @pytest.mark.parametrize("missing", Liveness.ORDER)
    def test_each_precondition_in_turn(self, missing: str) -> None:
        with pytest.raises(MeasurementError, match=missing):
            MeasurementEnvelope(measurement="m", liveness=live(**{missing: False}), value=0)

    def test_the_first_missing_step_is_named(self) -> None:
        """An operator needs to know which step did not happen."""
        assert live(subject_open_succeeded=False).first_missing() == "subject_open_succeeded"

    def test_defaults_are_pessimistic(self) -> None:
        """A forgotten field must not read as a pass."""
        assert Liveness().complete is False
        assert not_run("m").status is Status.NOT_RUN

    def test_require_evidence_refuses_rather_than_returning_zero(self) -> None:
        e = MeasurementEnvelope(measurement="collisions", liveness=Liveness(process_started=True))
        with pytest.raises(MeasurementError, match="never 0"):
            e.require_evidence()


class TestPopulation:
    def test_partial_population_is_visible(self) -> None:
        e = MeasurementEnvelope(measurement="rows", liveness=live(), value=0,
                                items_examined=90, expected_items=100)
        assert e.population_complete is False
        assert e.is_evidence is True, "a partial population is still a measurement"

    def test_complete_population(self) -> None:
        e = MeasurementEnvelope(measurement="rows", liveness=live(), value=0,
                                items_examined=100, expected_items=100)
        assert e.population_complete is True

    def test_unknown_expectation_is_none_not_true(self) -> None:
        e = MeasurementEnvelope(measurement="rows", liveness=live(), value=0, items_examined=10)
        assert e.population_complete is None


class TestSerialisation:
    def test_no_evidence_serialises_a_null_value_and_a_reason(self) -> None:
        d = not_run("mdl_error_count").to_json()
        assert d["value"] is None
        assert d["is_evidence"] is False
        assert "why_no_value" in d

    def test_a_zero_measurement_serialises_its_zero(self) -> None:
        d = MeasurementEnvelope(measurement="m", liveness=live(), value=0,
                                items_examined=3).to_json()
        assert d["value"] == 0
        assert d["status"] == "MEASURED_ZERO"

    def test_status_strings_are_stable(self) -> None:
        """These appear in committed artefacts; renaming one rewrites history."""
        assert {s.value for s in Status} == {
            "NOT_RUN", "RUN_FAILED", "RUN_LIVE_NO_MEASUREMENT",
            "MEASURED_ZERO", "MEASURED_NONZERO",
        }

    def test_only_measured_statuses_count_as_evidence(self) -> None:
        assert [s for s in Status if s.is_evidence] == [Status.MEASURED_ZERO,
                                                        Status.MEASURED_NONZERO]
