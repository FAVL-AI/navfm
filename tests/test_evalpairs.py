"""Tests for ``navfm.evalpairs`` — the frozen evaluation population.

A seed reproduces a population only under an unchanged sampler, and the sampler
is upstream code this repository patches. The manifest therefore pins the
population *directly*, and every arm verifies what it actually scored against
it. These tests pin the ways that verification could quietly stop verifying.
"""

from __future__ import annotations

from pathlib import Path

from navfm import evalpairs

PAIRS = [("no2vc_1_0", 3, "no2vc_1_0", 9), ("sim1h_2_0", 0, "no5vc_4_1", 5)]


def _manifest(pairs=PAIRS):
    return evalpairs.build(
        pairs,
        generation_command="python -m navfm.evalpairs --population-seed 0",
        population_seed=0,
        dataset_digest="d" * 64,
        split_digest="s" * 64,
        trajectory_count=3696,
    )


class TestManifest:
    def test_all_eight_fields_recorded(self) -> None:
        assert set(_manifest().to_dict()) == {
            "schema_version",
            "sha256",
            "generation_command",
            "population_seed",
            "dataset_digest",
            "split_digest",
            "trajectory_count",
            "pair_count",
        }

    def test_round_trips_through_disk(self, tmp_path: Path) -> None:
        m = _manifest()
        evalpairs.save(m, tmp_path / "m.json")
        assert evalpairs.load(tmp_path / "m.json") == m

    def test_pair_count_is_derived_not_asserted(self) -> None:
        assert _manifest().pair_count == len(PAIRS)


class TestVerification:
    def test_identical_population_verifies(self) -> None:
        assert evalpairs.verify(_manifest(), PAIRS) == []

    def test_a_different_pair_is_caught(self) -> None:
        altered = [PAIRS[0], ("sim1h_2_0", 0, "no5vc_4_1", 6)]
        assert evalpairs.verify(_manifest(), altered)

    def test_reordering_is_caught(self) -> None:
        """Order is part of the population: same pairs in a different order are
        different batches, and every metric here is batch-composition dependent."""
        assert evalpairs.verify(_manifest(), list(reversed(PAIRS)))

    def test_a_missing_pair_is_caught_by_count_and_digest(self) -> None:
        problems = evalpairs.verify(_manifest(), PAIRS[:1])
        assert any("pair count" in p for p in problems)
        assert any("population digest" in p for p in problems)

    def test_schema_drift_is_caught(self) -> None:
        m = _manifest()
        drifted = evalpairs.EvaluationPairManifest(
            **{**m.to_dict(), "schema_version": "evaluation_pairs_v0"}
        )
        assert any("schema" in p for p in evalpairs.verify(drifted, PAIRS))

    def test_manifest_digest_excludes_its_own_sha(self) -> None:
        """Otherwise the digest could never be computed before it exists."""
        m = _manifest()
        other = evalpairs.EvaluationPairManifest(**{**m.to_dict(), "sha256": "0" * 64})
        assert evalpairs.manifest_digest(m) == evalpairs.manifest_digest(other)

    def test_manifest_digest_moves_with_any_recorded_field(self) -> None:
        m = _manifest()
        base = evalpairs.manifest_digest(m)
        for field, value in (
            ("population_seed", 1),
            ("dataset_digest", "x" * 64),
            ("split_digest", "y" * 64),
            ("trajectory_count", 1),
            ("generation_command", "other"),
        ):
            other = evalpairs.EvaluationPairManifest(**{**m.to_dict(), field: value})
            assert evalpairs.manifest_digest(other) != base, f"{field} does not move the digest"
