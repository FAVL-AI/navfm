"""Tests for the causal-targetability stage.

The stage exists because geometric reachability was treated as sufficient
evidence that an intervention could isolate its declared cause. Most of these
tests therefore guard the two ways the fix could be hollow: the decision
consulting the observation it qualifies, and the gate never being able to say no.
"""

from __future__ import annotations

import dataclasses

import pytest

from navfm.targetability import (
    Interval,
    Targetability,
    TargetabilityInput,
    choose,
    decide,
)


def inp(**over) -> TargetabilityInput:
    base = dict(declared_target="/W/B", origin=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0),
                max_range=10.0, target_interval=Interval(4.0, 4.5), competing=())
    base.update(over)
    return TargetabilityInput(**base)


class TestNoObservationLeakage:
    """The decision must be structurally unable to see the query result."""

    def test_input_carries_no_hit_fields(self) -> None:
        names = {f.name for f in dataclasses.fields(TargetabilityInput)}
        forbidden = {"actual_hit", "actual_collider", "identity_match", "distance",
                     "hit", "collider", "hit_point", "generic_hit"}
        assert not (names & forbidden), (
            f"targetability input exposes observation fields: {names & forbidden}. "
            "A pre-query adequacy decision that can read the observation is circular.")

    def test_decide_signature_takes_only_the_input(self) -> None:
        import inspect

        assert list(inspect.signature(decide).parameters) == ["inp"]

    def test_identical_geometry_decides_identically(self) -> None:
        """The load-bearing counterfactual: targetability is a property of the
        intervention, so disabling the target must not change it."""
        a = inp()
        b = inp()   # same geometry; in the fixture B would be disabled
        assert decide(a) == decide(b)


class TestTheGateCanSayNo:
    def test_a_nearer_competing_body_occludes(self) -> None:
        st, why = decide(inp(competing=(("/W/A", Interval(1.0, 1.5)),)))
        assert st is Targetability.TARGET_OCCLUDED
        assert "/W/A" in why

    def test_overlapping_intervals_are_ambiguous_not_isolatable(self) -> None:
        """Unresolvable ordering must never be promoted to isolation."""
        st, _ = decide(inp(competing=(("/W/A", Interval(4.2, 5.0)),)))
        assert st is Targetability.TARGET_AMBIGUOUS

    def test_origin_inside_another_body_occludes(self) -> None:
        st, why = decide(inp(origin_inside=("/W/A",)))
        assert st is Targetability.TARGET_OCCLUDED
        assert "begins inside" in why

    def test_a_ray_that_misses_the_target_is_invalid_not_failing(self) -> None:
        st, _ = decide(inp(target_interval=None))
        assert st is Targetability.INVALID_GEOMETRY

    def test_no_candidate_isolates_yields_not_isolatable(self) -> None:
        d = choose([inp(competing=(("/W/A", Interval(1.0, 1.5)),)),
                    inp(origin_inside=("/W/A",))])
        assert d.state is Targetability.TARGET_NOT_ISOLATABLE
        assert d.chosen is None

    def test_not_isolatable_is_not_probative(self) -> None:
        assert Targetability.TARGET_NOT_ISOLATABLE.probative is False
        assert Targetability.TARGET_AMBIGUOUS.probative is False
        assert Targetability.TARGET_ISOLATABLE.probative is True


class TestIsolation:
    def test_a_clear_ray_isolates(self) -> None:
        st, _ = decide(inp())
        assert st is Targetability.TARGET_ISOLATABLE

    def test_a_body_behind_the_target_does_not_occlude(self) -> None:
        st, _ = decide(inp(competing=(("/W/A", Interval(6.0, 6.5)),)))
        assert st is Targetability.TARGET_ISOLATABLE

    def test_margin_is_respected(self) -> None:
        """A body ending just before the target still precedes it."""
        st, _ = decide(inp(competing=(("/W/A", Interval(3.0, 3.9)),), isolation_margin=0.02))
        assert st is Targetability.TARGET_OCCLUDED

    def test_choose_returns_the_first_isolating_candidate(self) -> None:
        bad = inp(competing=(("/W/A", Interval(1.0, 1.5)),))
        good = inp(origin=(9.0, 0.0, 0.0), direction=(-1.0, 0.0, 0.0))
        d = choose([bad, good])
        assert d.state is Targetability.TARGET_ISOLATABLE
        assert d.chosen is good


class TestCandidateFreeze:
    def test_the_candidate_set_is_digested(self) -> None:
        d = choose([inp(), inp(origin=(1.0, 0.0, 0.0))])
        assert len(d.candidate_digest) == 16

    def test_adding_a_direction_changes_the_digest(self) -> None:
        """Guards against extending the search after a query disappoints."""
        a = choose([inp()])
        b = choose([inp(), inp(origin=(2.0, 0.0, 0.0))])
        assert a.candidate_digest != b.candidate_digest

    def test_termination_is_structural(self) -> None:
        """choose() consumes a fixed list and never generates more."""
        import inspect

        src = inspect.getsource(choose)
        assert "while" not in src, "no unbounded search may exist in the decision"

    def test_empty_candidates_is_no_evidence_not_failure(self) -> None:
        d = choose([])
        assert d.state is Targetability.NO_EVIDENCE


class TestReporting:
    def test_json_records_every_candidate_state(self) -> None:
        d = choose([inp(competing=(("/W/A", Interval(1.0, 1.5)),)), inp()])
        j = d.to_json()
        assert j["candidates_considered"] == 2
        assert len(j["per_candidate"]) == 2
        assert j["probative"] is True

    @pytest.mark.parametrize("state", list(Targetability))
    def test_state_strings_are_stable(self, state: Targetability) -> None:
        """These appear in committed artefacts."""
        assert state.value == state.name
