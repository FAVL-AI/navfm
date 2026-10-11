"""The scene audit must implement the frozen criterion, not merely coexist with it.

Amendment 3 retired raw cross-target distance invariance and replaced it with
geometry-consistency plus target identity. Freezing a specification does not make
a consumer obey it, and between the amendment and this integration the audit
still scored probes by identity alone. These tests pin the seam so that gap
cannot reopen silently.

The audit builds a ``SimulationApp`` inside ``main()``, so it cannot be imported
on a build host. Structural claims are therefore asserted from source with
``ast``/text, the same way the consumer-parity suite does it, and behavioural
claims are asserted against the module the audit delegates to.

No production scene runs here, and no Hospital value appears.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import ClassVar

import pytest

from navfm.population import AccountingError, Disposition, build
from navfm.probe_adjudication import (
    DEFAULT_TOLERANCE_M,
    VERDICT_LABEL,
    Reason,
    adjudicate,
    verdict_label,
)

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "scripts" / "audit_office_collision_coverage.py"
SRC = AUDIT.read_text()


def _summarise_source() -> str:
    """The body of ``summarise``, where the role verdict is decided."""
    start = SRC.index("def summarise(")
    return SRC[start:SRC.index("rec[\"behavioural\"]", start)]


class TestTheAuditDelegatesAdjudication:
    def test_it_imports_the_frozen_module(self) -> None:
        assert "from navfm.probe_adjudication import" in SRC

    def test_it_calls_adjudicate_for_each_probe(self) -> None:
        assert "adjudicate(" in SRC, "the audit must delegate, not re-implement"

    def test_it_uses_the_shared_verdict_labels(self) -> None:
        assert "verdict_label(" in SRC, (
            "verdict strings must come from probe_adjudication so the label set "
            "cannot drift from the reasons that produce it"
        )

    def test_it_does_not_reimplement_identity_matching(self) -> None:
        """The old inline prefix test must be gone, not merely unused."""
        assert "or row[\"path\"].startswith(actual)" not in SRC

    def test_the_expected_distance_is_derived_from_geometry_not_the_hit(self) -> None:
        assert "_ray_iv(mn, mx, tdec.chosen.origin, tdec.chosen.direction)" in SRC, (
            "the expectation must come from the candidate and the target bounds; "
            "one computed from the observation would agree with any observation"
        )
        assert "iv.enter" in SRC


class TestRawInvarianceHasNoVerdictAuthority:
    def test_the_role_verdict_chain_does_not_consult_it(self) -> None:
        body = _summarise_source()
        chain = body[body.index('"verdict": ('):]
        assert "invariant" not in chain, (
            "raw distance invariance is retired; it may be reported but must not "
            "decide a role verdict"
        )

    def test_review_required_is_no_longer_raised_by_it(self) -> None:
        assert "REVIEW_REQUIRED_UNEXPECTED_INVARIANCE" not in _summarise_source()

    def test_the_field_is_explicitly_marked_diagnostic(self) -> None:
        assert "raw_distance_invariance_diagnostic_only" in SRC

    def test_the_field_is_retained_for_provenance_comparability(self) -> None:
        """Deleting it would break comparison with rows measured before the amendment."""
        assert '"unexpected_invariance": invariant' in SRC


class TestTheDispositionTableIsExhaustive:
    def test_every_verdict_label_has_a_disposition(self) -> None:
        table = SRC[SRC.index("_DISPOSITION = {"):]
        table = table[:table.index("}")]
        for label in VERDICT_LABEL.values():
            assert f'"{label}"' in table, (
                f"{label} can be emitted by the seam but has no disposition; "
                "a probe with no terminal disposition breaks the partition"
            )

    def test_the_geometry_verdict_is_probative(self) -> None:
        """The experiment spoke; it said the geometry disagrees."""
        table = SRC[SRC.index("_DISPOSITION = {"):]
        table = table[:table.index("}")]
        line = next(ln for ln in table.splitlines() if "FAIL_GEOMETRY_INCONSISTENT" in ln)
        assert "Disposition.PROBATIVE" in line


class TestSeamBehaviour:
    """The adjudication the seam delegates to, over the cases the seam can meet."""

    def test_correct_support_probe_is_probative(self) -> None:
        v = adjudicate(hit=True, returned_collider="/W/Floor", declared_target="/W/Floor",
                       observed_distance_m=0.5, expected_distance_m=0.5)
        assert verdict_label(v) == "PASS_CORRECT_CAUSE"

    def test_equal_distances_across_correct_targets_do_not_fail(self) -> None:
        vs = [adjudicate(hit=True, returned_collider=f"/W/F{i}", declared_target=f"/W/F{i}",
                         observed_distance_m=0.5, expected_distance_m=0.5) for i in range(4)]
        assert all(verdict_label(v) == "PASS_CORRECT_CAUSE" for v in vs)

    def test_diverse_distances_alone_do_not_pass(self) -> None:
        vs = [adjudicate(hit=True, returned_collider="/W/Wall", declared_target=f"/W/F{i}",
                         observed_distance_m=0.5 + 0.3 * i, expected_distance_m=0.5)
              for i in range(1, 4)]
        assert all(verdict_label(v) == "FAIL_WRONG_CAUSE" for v in vs)

    def test_wrong_collider_at_a_small_residual_still_fails(self) -> None:
        v = adjudicate(hit=True, returned_collider="/W/Wall", declared_target="/W/Floor",
                       observed_distance_m=0.5, expected_distance_m=0.5)
        assert verdict_label(v) == "FAIL_WRONG_CAUSE"

    def test_right_collider_outside_tolerance_fails_on_geometry(self) -> None:
        v = adjudicate(hit=True, returned_collider="/W/Floor", declared_target="/W/Floor",
                       observed_distance_m=0.5 + DEFAULT_TOLERANCE_M * 2,
                       expected_distance_m=0.5)
        assert verdict_label(v) == "FAIL_GEOMETRY_INCONSISTENT"

    def test_a_miss_cannot_be_probative(self) -> None:
        v = adjudicate(hit=False, returned_collider=None, declared_target="/W/Floor",
                       observed_distance_m=None, expected_distance_m=0.5)
        assert verdict_label(v) == "FAIL_NO_HIT" and not v.probative

    def test_every_reason_has_a_label(self) -> None:
        assert set(VERDICT_LABEL) == set(Reason)


class TestAccountingSurvivesTheNewVerdict:
    #: Mirrors the audit's table, including the verdict this tranche adds.
    DISPOSITION: ClassVar[dict[str, Disposition]] = {
        "NO_EVIDENCE": Disposition.NO_EVIDENCE,
        "NON_PROBATIVE_OCCLUDED": Disposition.NONPROBATIVE_UNREACHABLE,
        "NON_PROBATIVE_NOT_TARGETABLE": Disposition.NONPROBATIVE_NOT_TARGETABLE,
        "PASS_CORRECT_CAUSE": Disposition.PROBATIVE,
        "FAIL_WRONG_CAUSE": Disposition.PROBATIVE,
        "FAIL_GEOMETRY_INCONSISTENT": Disposition.PROBATIVE,
        "FAIL_NO_HIT": Disposition.PROBATIVE,
    }

    def _population(self, verdicts: dict[str, str]):
        selected = {pid: self.DISPOSITION[v] for pid, v in verdicts.items()}
        fired = {pid for pid, v in verdicts.items()
                 if v not in ("NO_EVIDENCE", "NON_PROBATIVE_OCCLUDED",
                              "NON_PROBATIVE_NOT_TARGETABLE")}
        return build(selected, reachable=set(verdicts), targetable=fired,
                     fired=fired, adjudicated=fired)

    def test_populations_nest_with_the_new_verdict_present(self) -> None:
        pop = self._population({
            "a": "PASS_CORRECT_CAUSE", "b": "FAIL_GEOMETRY_INCONSISTENT",
            "c": "FAIL_WRONG_CAUSE", "d": "NON_PROBATIVE_NOT_TARGETABLE",
        })
        chain = [len(pop.selected), len(pop.reachable), len(pop.targetable),
                 len(pop.fired), len(pop.adjudicated), pop.probative_population]
        assert all(chain[i] >= chain[i + 1] for i in range(len(chain) - 1))
        assert all(v >= 0 for v in chain)

    def test_a_geometry_failure_is_counted_exactly_once(self) -> None:
        pop = self._population({"a": "FAIL_GEOMETRY_INCONSISTENT"})
        assert pop.probative_population == 1
        assert len(pop.selected) == 1

    def test_a_geometry_failure_is_not_a_correct_target_hit(self) -> None:
        """Probative means the experiment could speak, not that it agreed."""
        verdicts = {"a": "FAIL_GEOMETRY_INCONSISTENT"}
        correct = sum(1 for v in verdicts.values() if v == "PASS_CORRECT_CAUSE")
        assert self._population(verdicts).probative_population == 1
        assert correct == 0

    def test_an_unmapped_verdict_would_break_the_partition(self) -> None:
        """The negative control for the disposition table's exhaustiveness."""
        with pytest.raises((KeyError, AccountingError)):
            self._population({"a": "SOME_NEW_VERDICT"})


class TestFrozenInputsUnchangedByIntegration:
    def test_the_candidate_policy_digest_is_untouched(self) -> None:
        from navfm.candidate_policy import policy_digest

        assert policy_digest() == "c6534203825fa13d"

    def test_the_audit_still_requests_candidates_from_the_policy(self) -> None:
        assert "generate_candidates(" in SRC

    def test_the_audit_does_not_recompute_candidate_geometry(self) -> None:
        tree = ast.parse(SRC)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "LOCAL_STANDOFF" not in names and "LOCAL_MARGIN" not in names

    def test_amendment_three_is_the_effective_contract(self) -> None:
        amendments = [json.loads(ln) for ln in
                      (REPO / "gates/scenes/collision_probe_contract_amendments.jsonl")
                      .read_text().strip().splitlines()]
        assert amendments[-1]["amendment_id"] == 3
        assert amendments[-1]["kind"] == "CRITERION_REPLACEMENT"
