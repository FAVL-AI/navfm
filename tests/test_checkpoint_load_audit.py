"""Tests for ``navfm.models.loader.audit_load``.

``load_state_dict(strict=False)`` is the upstream default and it cannot fail.
A checkpoint whose keys share no prefix with the constructed model loads zero
tensors, prints a summary, and leaves a randomly initialised model behind --
which then produces a number under a run record naming a checkpoint and its
SHA-256.

That failure is invisible to every other control in this repository. The
``random_init`` stamp asks whether a checkpoint was *named*; the contamination
barrier asks whether a row is a smoke test; neither asks whether the weights
actually arrived. This is the control that does, so the property worth pinning
is the refusal itself -- and that the refusal cannot be lost by accident.
"""

from __future__ import annotations

import pytest

from navfm.models.loader import CheckpointLoadError, audit_load


class _FakeModel:
    """Stands in for a torch module: only ``state_dict()`` size is consulted."""

    def __init__(self, n_tensors: int) -> None:
        self._state = {f"layer{i}.weight": object() for i in range(n_tensors)}

    def state_dict(self) -> dict[str, object]:
        return self._state


def _missing(n: int) -> list[str]:
    return [f"layer{i}.weight" for i in range(n)]


class TestRefusal:
    def test_a_checkpoint_that_matched_nothing_is_refused(self) -> None:
        """The headline case: zero tensors loaded, model is random, SHA recorded."""
        model = _FakeModel(100)
        with pytest.raises(CheckpointLoadError) as excinfo:
            audit_load(model, _missing(100), [])
        assert "0.0%" in str(excinfo.value)

    def test_the_refusal_message_names_the_consequence_not_just_the_symptom(self) -> None:
        model = _FakeModel(100)
        with pytest.raises(CheckpointLoadError) as excinfo:
            audit_load(model, _missing(100), [])
        message = str(excinfo.value)
        assert "randomly initialised" in message
        assert "--allow-partial-load" in message

    @pytest.mark.parametrize("n_missing", [11, 25, 50, 99, 100])
    def test_refuses_below_the_threshold(self, n_missing: int) -> None:
        with pytest.raises(CheckpointLoadError):
            audit_load(_FakeModel(100), _missing(n_missing), [])

    @pytest.mark.parametrize("n_missing", [0, 1, 5, 10])
    def test_accepts_at_or_above_the_threshold(self, n_missing: int) -> None:
        census = audit_load(_FakeModel(100), _missing(n_missing), [])
        assert census["loaded_fraction"] >= 0.90

    def test_a_full_load_is_the_ordinary_case(self) -> None:
        census = audit_load(_FakeModel(799), [], [])
        assert census["loaded_fraction"] == 1.0
        assert census["missing_keys"] == 0


class TestOverride:
    def test_explicit_override_permits_a_partial_load(self) -> None:
        census = audit_load(_FakeModel(100), _missing(100), [], allow_partial=True)
        assert census["loaded_fraction"] == 0.0

    def test_the_override_is_recorded_so_the_manifest_shows_the_decision(self) -> None:
        """An override that leaves no trace is indistinguishable from no check."""
        census = audit_load(_FakeModel(100), _missing(60), [], allow_partial=True)
        assert census["partial_load_allowed"] is True
        assert audit_load(_FakeModel(100), [], [])["partial_load_allowed"] is False


class TestCensus:
    def test_census_carries_what_the_run_record_needs(self) -> None:
        census = audit_load(_FakeModel(200), _missing(4), ["extra.weight", "other.bias"])
        assert census["model_tensors"] == 200
        assert census["missing_keys"] == 4
        assert census["unexpected_keys"] == 2
        assert census["loaded_fraction"] == pytest.approx(0.98)

    def test_unexpected_keys_alone_do_not_refuse(self) -> None:
        """Extra keys mean the checkpoint knows more than the model, which is
        a different situation from the model being empty."""
        census = audit_load(_FakeModel(100), [], [f"extra{i}" for i in range(500)])
        assert census["loaded_fraction"] == 1.0

    def test_empty_model_does_not_divide_by_zero(self) -> None:
        assert audit_load(_FakeModel(0), [], [])["loaded_fraction"] == 1.0

    def test_threshold_is_tunable_but_defaults_strict(self) -> None:
        audit_load(_FakeModel(100), _missing(50), [], min_loaded_fraction=0.4)
        with pytest.raises(CheckpointLoadError):
            audit_load(_FakeModel(100), _missing(50), [])
