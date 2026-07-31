"""Tests for ``navfm.evidence``.

The class declares what a run's numbers *are*. Everything downstream — the
contamination barrier, table eligibility, the checkpoint-hash requirement —
reads that declaration rather than re-deriving it, so the properties worth
pinning are the ones that would let a non-result acquire the standing of a
result.
"""

from __future__ import annotations

import pytest

from navfm.evidence import EvidenceClass, evidence_block


class TestEnum:
    def test_the_six_required_classes_exist(self) -> None:
        assert {c.value for c in EvidenceClass} >= {
            "pipeline_smoke_test",
            "random_init_control",
            "checkpoint_sanity",
            "baseline_evaluation",
            "registered_experiment",
            "diagnostic_unregistered",
        }

    @pytest.mark.parametrize(
        "cls",
        [
            EvidenceClass.PIPELINE_SMOKE_TEST,
            EvidenceClass.RANDOM_INIT_CONTROL,
            EvidenceClass.CHECKPOINT_SANITY,
            EvidenceClass.DIAGNOSTIC_UNREGISTERED,
        ],
    )
    def test_non_results_are_not_results(self, cls: EvidenceClass) -> None:
        assert cls.scientific_result is False
        assert cls.table_eligible is False

    @pytest.mark.parametrize(
        "cls", [EvidenceClass.BASELINE_EVALUATION, EvidenceClass.REGISTERED_EXPERIMENT]
    )
    def test_only_registered_and_baseline_are_results(self, cls: EvidenceClass) -> None:
        assert cls.scientific_result is True
        assert cls.table_eligible is True

    def test_a_diagnostic_is_real_but_barred(self) -> None:
        """Unregistered work is legitimate; it is barred because it is
        unregistered, not because it is fake. Conflating the two is what drives
        exploratory work underground."""
        cls = EvidenceClass.DIAGNOSTIC_UNREGISTERED
        assert cls.scientific_result is False

    def test_model_claims_require_identifying_the_bytes(self) -> None:
        assert EvidenceClass.BASELINE_EVALUATION.requires_checkpoint_hash is True
        assert EvidenceClass.REGISTERED_EXPERIMENT.requires_checkpoint_hash is True
        assert EvidenceClass.CHECKPOINT_SANITY.requires_checkpoint_hash is True
        assert EvidenceClass.RANDOM_INIT_CONTROL.requires_checkpoint_hash is False
        assert EvidenceClass.PIPELINE_SMOKE_TEST.requires_checkpoint_hash is False

    def test_unknown_class_is_refused_and_lists_the_valid_ones(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            EvidenceClass.parse("looks_scientific")
        message = str(excinfo.value)
        assert "looks_scientific" in message
        assert "baseline_evaluation" in message

    def test_parse_round_trips_every_class(self) -> None:
        for cls in EvidenceClass:
            assert EvidenceClass.parse(cls.value) is cls


class TestBlock:
    def test_block_carries_the_four_required_fields(self) -> None:
        block = evidence_block(
            EvidenceClass.PIPELINE_SMOKE_TEST,
            model_initialization="random",
            data_source="synthetic_noise",
        )
        assert set(block) == {
            "evidence_class",
            "scientific_result",
            "model_initialization",
            "data_source",
        }

    def test_smoke_tests_stamp_false(self) -> None:
        """Task 1b names this case explicitly."""
        block = evidence_block(
            EvidenceClass.PIPELINE_SMOKE_TEST,
            model_initialization="random",
            data_source="synthetic_noise",
        )
        assert block["evidence_class"] == "pipeline_smoke_test"
        assert block["scientific_result"] is False

    def test_scientific_result_cannot_be_asserted_against_the_class(self) -> None:
        """It is derived, not passed. A run cannot declare a smoke-test class
        and a scientific-result flag at once."""
        for cls in EvidenceClass:
            block = evidence_block(cls, model_initialization="x", data_source="y")
            assert block["scientific_result"] is cls.scientific_result
