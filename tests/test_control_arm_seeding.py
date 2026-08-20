"""The random-init control arm must be reproducible.

Required infrastructure for the G0.c decision rule, not amendment content: the
amendment states the behavioural requirement (seeded, deterministic replay of
the control arm) and this is what satisfies it.

Before this, `offline.py` seeded only the DataLoader generator. Model
construction drew from the ambient global RNG, so the control's weights were an
unrecorded, unrepeatable draw — which makes Layer B's repeatability requirement
unsatisfiable for that arm, and leaves every Layer C directional comparison
resting on a single draw nobody can reproduce.

These tests exercise the seeding contract directly rather than through the
evaluator's CLI, so they need no checkpoint, no dataset and no GPU.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from navfm.eval.offline import seed_model_rng

torch = pytest.importorskip("torch")


def _draw() -> tuple[float, float, float]:
    """One sample from each RNG stream model construction can touch."""
    return (torch.randn(1).item(), float(np.random.rand()), random.random())


class TestReplay:
    @pytest.mark.torch
    def test_same_seed_replays_exactly(self) -> None:
        seed_model_rng(1234)
        first = _draw()
        seed_model_rng(1234)
        assert _draw() == first

    @pytest.mark.torch
    def test_different_seeds_diverge(self) -> None:
        """Three control arms must be three genuinely different initialisations,
        not three shuffles of one."""
        draws = []
        for seed in (0, 1, 2):
            seed_model_rng(seed)
            draws.append(_draw())
        assert len({d[0] for d in draws}) == 3, "torch stream did not vary with the seed"
        assert len({d[1] for d in draws}) == 3, "numpy stream did not vary with the seed"
        assert len({d[2] for d in draws}) == 3, "python stream did not vary with the seed"

    @pytest.mark.torch
    @pytest.mark.parametrize("stream", ["torch", "numpy", "python"])
    def test_every_stream_is_covered(self, stream: str) -> None:
        """A stream left unseeded is a channel through which the control arm
        becomes unrepeatable, whatever the other streams do."""
        index = {"torch": 0, "numpy": 1, "python": 2}[stream]
        seed_model_rng(7)
        a = _draw()[index]
        seed_model_rng(7)
        assert _draw()[index] == a

    @pytest.mark.torch
    def test_seeding_survives_intervening_consumption(self) -> None:
        """Re-seeding must reset the streams, not merely offset them."""
        seed_model_rng(99)
        expected = _draw()
        for _ in range(50):
            _draw()
        seed_model_rng(99)
        assert _draw() == expected


class TestModelConstruction:
    @pytest.mark.torch
    def test_two_seeded_constructions_give_identical_weights(self) -> None:
        """The property that actually matters: a control arm replays."""
        import torch.nn as nn

        def build() -> list[float]:
            layer = nn.Linear(32, 16)
            return layer.weight.detach().flatten()[:8].tolist()

        seed_model_rng(4242)
        first = build()
        seed_model_rng(4242)
        assert build() == first

        seed_model_rng(4243)
        assert build() != first, "different control arms must differ"
