"""Tests for the forensic ledger schema.

The ledger's value is that it cannot be filled in loosely. So these tests are
mostly about refusal: an entry that omits its causal reasoning must fail to
construct, not produce a document with a gap. Per the standing rule that a check
must be shown to fail before it is trusted, every guard here is exercised in both
directions.
"""

from __future__ import annotations

import json

import pytest

from navfm.forensics import (
    REQUIRED_FIELDS,
    ForensicEntry,
    LedgerError,
    render_markdown,
    write_jsonl,
)


def _valid(**overrides):
    base = dict(
        issue_id="FL-999",
        title="A finding",
        observation="Something was observed.",
        root_cause="Because of a cause.",
        why_existing_checks_missed_it="The checks looked elsewhere.",
        scientific_risk="A wrong number could have been published.",
        alternatives_considered=["do nothing", "do something"],
        decision="Did something.",
        decision_rule="Always do something.",
        rejected_alternative="Doing nothing was rejected.",
        correction="Applied a fix.",
        validation="Ran the harness.",
        regression_control="A test now fails if it recurs.",
        evidence=["path/to/evidence.json"],
        impact="No published result affected.",
        propagation="Applies to one module.",
        impact_score=3,
        detectability_score=3,
        propagation_score=3,
        claim_boundary="Holds under the pinned configuration.",
        non_claim="Does not establish hardware behaviour.",
    )
    base.update(overrides)
    return ForensicEntry(**base)


class TestSchemaIsEnforced:
    def test_a_complete_entry_constructs(self) -> None:
        assert _valid().issue_id == "FL-999"

    @pytest.mark.parametrize("missing", REQUIRED_FIELDS)
    def test_every_causal_field_is_required(self, missing: str) -> None:
        """Each field in turn — so none can quietly become optional."""
        blank = [] if missing in ("alternatives_considered", "evidence") else ""
        if missing in ("impact_score", "detectability_score", "propagation_score"):
            pytest.skip("scored separately; empty is not representable for an int")
        with pytest.raises(LedgerError, match=missing):
            _valid(**{missing: blank})

    def test_the_hardest_field_to_omit_is_the_one_most_worth_having(self) -> None:
        with pytest.raises(LedgerError, match="why_existing_checks_missed_it"):
            _valid(why_existing_checks_missed_it="")

    @pytest.mark.parametrize("bad", [0, 6, -1, 100])
    def test_scores_outside_one_to_five_are_refused(self, bad: int) -> None:
        with pytest.raises(LedgerError, match="impact_score must be 1-5"):
            _valid(impact_score=bad)

    def test_ids_must_be_namespaced(self) -> None:
        with pytest.raises(LedgerError, match="must start with 'FL-'"):
            _valid(issue_id="007")


class TestScoring:
    def test_severity_is_the_product(self) -> None:
        assert _valid(impact_score=5, detectability_score=4, propagation_score=3).severity == 60

    def test_a_quiet_defect_outranks_a_loud_one_of_equal_impact(self) -> None:
        """The whole point of inverting detectability."""
        quiet = _valid(impact_score=4, detectability_score=5, propagation_score=3)
        loud = _valid(impact_score=4, detectability_score=1, propagation_score=3)
        assert quiet.severity > loud.severity

    @pytest.mark.parametrize(
        "scores,band",
        [((5, 5, 5), "CRITICAL"), ((5, 4, 3), "CRITICAL"), ((4, 4, 2), "HIGH"),
         ((2, 2, 3), "MODERATE"), ((1, 1, 1), "LOW")],
    )
    def test_bands(self, scores: tuple[int, int, int], band: str) -> None:
        e = _valid(impact_score=scores[0], detectability_score=scores[1],
                   propagation_score=scores[2])
        assert e.severity_band == band

    def test_irreversibility_is_not_folded_into_severity(self) -> None:
        """A cheap permanent error and an expensive recoverable one differ in kind."""
        a = _valid(irreversible=True)
        b = _valid(irreversible=False)
        assert a.severity == b.severity
        assert a.irreversible != b.irreversible


class TestEmission:
    def test_jsonl_is_one_object_per_line_and_carries_the_score(self, tmp_path) -> None:
        p = write_jsonl([_valid(), _valid(issue_id="FL-998")], tmp_path / "l.jsonl")
        lines = p.read_text().strip().split("\n")
        assert len(lines) == 2
        rec = json.loads(lines[0])
        assert rec["severity"] == 27
        assert rec["severity_band"] == "MODERATE"
        assert rec["attribution"] == "Frank Asante Van Laarhoven"

    def test_markdown_ranks_quietest_and_widest_first(self) -> None:
        low = _valid(issue_id="FL-001", title="Loud", impact_score=1,
                     detectability_score=1, propagation_score=1)
        high = _valid(issue_id="FL-002", title="Quiet", impact_score=5,
                      detectability_score=5, propagation_score=5)
        md = render_markdown([low, high], title="T", preamble="P")
        assert md.index("FL-002") < md.index("FL-001")

    def test_every_causal_field_reaches_the_document(self) -> None:
        """A field that is required but never rendered is a field nobody reads."""
        e = _valid()
        md = render_markdown([e], title="T", preamble="P")
        for text in (e.observation, e.root_cause, e.why_existing_checks_missed_it,
                     e.scientific_risk, e.decision, e.decision_rule, e.rejected_alternative,
                     e.correction, e.validation, e.regression_control, e.impact,
                     e.claim_boundary, e.non_claim, e.propagation, e.attribution):
            assert text in md


class TestTheRealLedger:
    """The committed ledger must satisfy its own schema."""

    def test_it_builds_and_ids_are_unique(self) -> None:
        import importlib.util
        from pathlib import Path

        repo = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "_bfl", repo / "scripts" / "build_forensic_ledger.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ids = [e.issue_id for e in mod.ENTRIES]
        assert len(ids) == len(set(ids)), "duplicate issue ids"
        assert len(ids) >= 10

    def test_no_entry_claims_more_than_its_evidence(self) -> None:
        """Each entry names at least one artefact, and states a non-claim."""
        import importlib.util
        from pathlib import Path

        repo = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "_bfl2", repo / "scripts" / "build_forensic_ledger.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for e in mod.ENTRIES:
            assert e.evidence, f"{e.issue_id} cites no evidence"
            assert len(e.non_claim) > 20, f"{e.issue_id} has a token non-claim"
