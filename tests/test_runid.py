"""Tests for ``navfm.runid`` — resume identity (1a) and scheduler lineage (1e).

A resume restores weights, optimizer moments and RNG streams into whatever run
asks for them. Nothing in the checkpoint format objects if that run points at a
different dataset, batch size, or environment — and the result is one `runs/`
directory, one set of per-epoch metrics, and one table row describing a
population that was never one experiment.

The properties pinned here are the ones that would let two experiments merge
into one record, or let a deliberate fork masquerade as a continuation.
"""

from __future__ import annotations

import pytest

from navfm.runid import (
    IDENTITY_FIELDS,
    compare,
    identity_digest,
    lineage_link,
    run_identity,
)


def _identity(**overrides: object) -> dict[str, object]:
    base = {
        "checkpoint_sha256": "a" * 64,
        "dataset_split_digest": "b" * 64,
        "evaluator_commit": "c" * 40,
        "config_digest": "d" * 64,
        "metric_set_version": "e" * 16,
        "seed_set": [0],
        "batch_size": 256,
        "environment_id": "f" * 64,
        "evidence_class": "registered_experiment",
        "architecture": "vint",
    }
    return run_identity(**{**base, **overrides})


class TestIdentityFields:
    def test_all_nine_review_fields_are_covered(self) -> None:
        """M2-11 enumerates what a resume must reject a mismatch in."""
        for field in (
            "checkpoint_sha256",
            "dataset_split_digest",
            "evaluator_commit",
            "config_digest",
            "metric_set_version",
            "seed_set",
            "batch_size",
            "environment_id",
            "evidence_class",
        ):
            assert field in IDENTITY_FIELDS

    def test_unknown_field_is_rejected(self) -> None:
        """A typo'd field name must not silently vanish from the identity."""
        with pytest.raises(ValueError, match="not identity fields"):
            run_identity(batch_sizee=256)

    def test_missing_fields_are_none_not_absent(self) -> None:
        identity = run_identity(batch_size=256)
        assert set(identity) == set(IDENTITY_FIELDS)
        assert identity["checkpoint_sha256"] is None

    def test_seed_set_order_does_not_change_identity(self) -> None:
        assert identity_digest(_identity(seed_set=[2, 0, 1])) == identity_digest(
            _identity(seed_set=[0, 1, 2])
        )


class TestRefusal:
    def test_identical_identities_compare_equal(self) -> None:
        assert compare(_identity(), _identity()) == []

    def test_checkpoint_hash_mismatch_is_refused(self) -> None:
        """Named in Task 1a as a required unit test."""
        mismatches = compare(_identity(), _identity(checkpoint_sha256="9" * 64))
        assert len(mismatches) == 1
        assert "checkpoint_sha256" in mismatches[0]

    def test_batch_size_mismatch_is_refused(self) -> None:
        """Named in Task 1a as a required unit test. Metrics in this codebase
        are batch-size dependent, so this is not a cosmetic difference."""
        mismatches = compare(_identity(), _identity(batch_size=400))
        assert len(mismatches) == 1
        assert "batch_size" in mismatches[0]
        assert "256" in mismatches[0] and "400" in mismatches[0]

    @pytest.mark.parametrize("field", IDENTITY_FIELDS)
    def test_every_identity_field_is_load_bearing(self, field: str) -> None:
        """A field that cannot cause a refusal is decoration."""
        changed = _identity(**{field: "CHANGED" if field != "seed_set" else [99]})
        assert compare(_identity(), changed), f"{field} never causes a refusal"

    def test_unknown_on_both_sides_is_not_a_mismatch(self) -> None:
        bare = run_identity(batch_size=256)
        assert compare(bare, run_identity(batch_size=256)) == []

    def test_known_on_one_side_only_IS_a_mismatch(self) -> None:
        """A resume that silently drops a constraint the original declared is
        exactly the hybrid this guards against."""
        assert compare(_identity(), run_identity(batch_size=256))
        assert compare(run_identity(batch_size=256), _identity())

    def test_mismatch_message_names_both_values(self) -> None:
        message = compare(_identity(), _identity(architecture="gnm"))[0]
        assert "vint" in message and "gnm" in message


class TestLineage:
    def test_a_fork_is_not_a_continuation(self) -> None:
        link = lineage_link(_identity(), intervention="scheduler_horizon_redefined")
        assert link["is_continuation"] is False
        assert link["intervention"] == "scheduler_horizon_redefined"

    def test_lineage_records_the_parent_digest_not_its_name(self) -> None:
        """A directory can be renamed; a digest cannot."""
        parent = _identity()
        assert lineage_link(parent, intervention="x")["derived_from_identity"] == identity_digest(
            parent
        )

    def test_an_unnamed_fork_is_refused(self) -> None:
        with pytest.raises(ValueError, match="intervention must be named"):
            lineage_link(_identity(), intervention="")

    def test_redefining_the_horizon_mints_a_new_identity(self) -> None:
        """1e: the two scheduler remedies are distinct experimental
        interventions. Continuing under the original horizon keeps the identity;
        redefining it must not."""
        original = _identity(config_digest="original-config")
        redefined = _identity(config_digest="longer-horizon-config")
        assert identity_digest(original) != identity_digest(redefined)
        assert compare(original, redefined), "a redefined horizon resumed as a continuation"

        link = lineage_link(original, intervention="scheduler_horizon_redefined")
        assert link["derived_from_identity"] == identity_digest(original)
