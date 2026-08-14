"""Tests for probe-population accounting.

An audit reported `probative_population = -1` by subtracting counts drawn from
different stages. These tests exist to keep that unrepresentable rather than
merely detected.
"""

from __future__ import annotations

import pytest

from navfm.population import AccountingError, Disposition, ProbePopulation, build

D = Disposition


def pop(**over) -> ProbePopulation:
    sel = {f"p{i}": D.PROBATIVE for i in range(3)}
    sel.update({"p3": D.NONPROBATIVE_UNREACHABLE, "p4": D.NONPROBATIVE_NOT_TARGETABLE})
    base = dict(selected=sel, reachable={"p0", "p1", "p2", "p4"},
                targetable={"p0", "p1", "p2"}, fired={"p0", "p1", "p2"},
                adjudicated={"p0", "p1", "p2"})
    base.update(over)
    return build(**base)


class TestTheNegativePopulationIsUnrepresentable:
    def test_probative_population_is_a_set_size(self) -> None:
        assert pop().probative_population == 3

    def test_the_historical_condition_cannot_produce_a_negative(self) -> None:
        """8 selected, 7 reachable, 8 rejected across mixed stages.

        The old arithmetic was reachable - non_probative = 7 - 8 = -1. Counting
        identities cannot express that.
        """
        sel = {f"p{i}": D.NONPROBATIVE_NOT_TARGETABLE for i in range(7)}
        sel["p7"] = D.NONPROBATIVE_UNREACHABLE
        p = build(selected=sel, reachable=set(f"p{i}" for i in range(7)),
                  targetable=set(), fired=set(), adjudicated=set())
        assert p.probative_population == 0
        assert p.probative_population >= 0

    @pytest.mark.parametrize("n", [0, 1, 5])
    def test_population_never_negative(self, n: int) -> None:
        sel = {f"p{i}": D.PROBATIVE for i in range(n)}
        p = build(selected=sel, reachable=set(sel), targetable=set(sel),
                  fired=set(sel), adjudicated=set(sel))
        assert p.probative_population == n


class TestNesting:
    def test_a_probe_cannot_be_targetable_without_being_reachable(self) -> None:
        with pytest.raises(AccountingError, match="targetable is not a subset of reachable"):
            ProbePopulation(selected=frozenset({"a"}), reachable=frozenset(),
                            targetable=frozenset({"a"}))

    def test_a_probe_cannot_be_reachable_without_being_selected(self) -> None:
        with pytest.raises(AccountingError, match="reachable is not a subset of selected"):
            ProbePopulation(selected=frozenset(), reachable=frozenset({"a"}))

    def test_valid_nesting_constructs(self) -> None:
        assert pop().probative_population == 3


class TestPartition:
    def _nested(self, ids: set[str]) -> dict[str, frozenset[str]]:
        """Valid nesting, so the partition check is what a test exercises."""
        f = frozenset(ids)
        return dict(reachable=f, targetable=f, fired=f, adjudicated=f, probative=f)

    def test_every_selected_probe_needs_a_disposition(self) -> None:
        with pytest.raises(AccountingError, match="do not partition"):
            ProbePopulation(selected=frozenset({"a", "b"}), **self._nested({"a"}),
                            dispositions={"a": D.PROBATIVE})

    def test_a_disposition_for_an_unselected_probe_is_refused(self) -> None:
        with pytest.raises(AccountingError, match="unexpected"):
            ProbePopulation(selected=frozenset({"a"}), **self._nested({"a"}),
                            dispositions={"a": D.PROBATIVE, "z": D.PROBATIVE})

    def test_probative_beyond_adjudicated_is_refused_by_nesting(self) -> None:
        """The nesting guard fires before partition, which is the correct order:
        a probe cannot be probative without having been adjudicated."""
        with pytest.raises(AccountingError, match="probative is not a subset of adjudicated"):
            ProbePopulation(selected=frozenset({"a"}), reachable=frozenset({"a"}),
                            probative=frozenset({"a"}))

    def test_probative_set_must_agree_with_dispositions(self) -> None:
        with pytest.raises(AccountingError, match="disagrees with dispositions"):
            ProbePopulation(selected=frozenset({"a"}), reachable=frozenset({"a"}),
                            targetable=frozenset({"a"}), fired=frozenset({"a"}),
                            adjudicated=frozenset({"a"}),
                            dispositions={"a": D.NONPROBATIVE_QUERY},
                            probative=frozenset({"a"}))

    def test_dispositions_sum_to_the_selected_count(self) -> None:
        p = pop()
        assert sum(p.non_probative_by_reason.values()) + p.probative_population == 5


class TestRepresentativeness:
    def test_numerator_and_denominator_stay_visible(self) -> None:
        """1/8 and 8/8 are different evidential situations."""
        assert pop().representativeness == (3, 5)

    @pytest.mark.parametrize("probative,ok", [(1, False), (2, False), (8, True)])
    def test_a_thin_sample_cannot_carry_a_scene_claim(self, probative: int, ok: bool) -> None:
        sel = {f"p{i}": (D.PROBATIVE if i < probative else D.NONPROBATIVE_NOT_TARGETABLE)
               for i in range(8)}
        p = build(selected=sel, reachable=set(sel), targetable=set(sel),
                  fired=set(sel), adjudicated=set(sel))
        assert p.representative(0.5) is ok

    def test_empty_selection_is_never_representative(self) -> None:
        p = build(selected={}, reachable=set(), targetable=set(), fired=set(),
                  adjudicated=set())
        assert p.representative(0.5) is False

    def test_json_exposes_both_terms(self) -> None:
        j = pop().to_json()
        assert j["representativeness_numerator"] == 3
        assert j["representativeness_denominator"] == 5
        assert j["probative_population"] == 3


class TestKnownAnswerPartition:
    def test_eight_selected_two_unreachable_three_not_targetable_three_probative(self) -> None:
        sel = {"p0": D.PROBATIVE, "p1": D.PROBATIVE, "p2": D.PROBATIVE,
               "p3": D.NONPROBATIVE_UNREACHABLE, "p4": D.NONPROBATIVE_UNREACHABLE,
               "p5": D.NONPROBATIVE_NOT_TARGETABLE, "p6": D.NONPROBATIVE_NOT_TARGETABLE,
               "p7": D.NONPROBATIVE_NOT_TARGETABLE}
        p = build(selected=sel, reachable={"p0", "p1", "p2", "p5", "p6", "p7"},
                  targetable={"p0", "p1", "p2"}, fired={"p0", "p1", "p2"},
                  adjudicated={"p0", "p1", "p2"})
        assert len(p.selected) == 8
        assert len(p.reachable) == 6
        assert len(p.targetable) == 3
        assert p.probative_population == 3
        assert p.non_probative_by_reason == {"NONPROBATIVE_UNREACHABLE": 2,
                                             "NONPROBATIVE_NOT_TARGETABLE": 3}
        assert p.representativeness == (3, 8)
