"""RNG domain separation: model identity and evaluation population are independent.

Upstream's `_sample_goal` drew from the global NumPy stream
(`vint_dataset.py:195,207`, called at `:301`). `seed_model_rng` seeds that same
global stream before model construction, so changing `--model-seed` changed
*which (observation, goal) pairs were scored* as well as the weights. The three
random-init controls were therefore three initialisations on three different
evaluation populations, and the checkpoint arm scored a fourth — making every
Layer-C comparison an impure contrast.

The `sampling_rng_isolation` patch gives goal sampling its own RandomState,
seeded only by `navfm_seed_sampling` from a declared population seed.

The two **causal-contract invariants** below express the intervention directly:
each holds one factor fixed and varies the other, and asserts that exactly one
consequence follows. They sit above five lower-level assertions about the
domains themselves.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from navfm.eval.offline import seed_model_rng

torch = pytest.importorskip("torch")

_UPSTREAM = Path(__file__).resolve().parents[1] / "third_party" / "visualnav-transformer" / "train"
if _UPSTREAM.is_dir() and str(_UPSTREAM) not in sys.path:
    sys.path.insert(0, str(_UPSTREAM))

vint_dataset = pytest.importorskip("vint_train.data.vint_dataset")
pytestmark = pytest.mark.upstream

if not hasattr(vint_dataset, "navfm_seed_sampling"):  # pragma: no cover
    pytest.skip("clone is unpatched: run scripts/patch_upstream.py", allow_module_level=True)


def _pairs(n: int = 40) -> list[int]:
    """Draws from the sampling stream, exactly as `_sample_goal` makes them."""
    return [int(vint_dataset._NAVFM_SAMPLING_RNG.randint(0, 1000)) for _ in range(n)]


def _weights() -> list[float]:
    """A sample of what model construction consumes."""
    return torch.randn(8).tolist()


def _run(*, model_seed: int, eval_seed: int) -> tuple[list[float], list[int]]:
    """One arm: seed the model, then seed the population, then draw both."""
    seed_model_rng(model_seed)
    weights = _weights()
    vint_dataset.navfm_seed_sampling(eval_seed)
    return weights, _pairs()


class TestCausalContract:
    """The two invariants that express the intervention."""

    def test_model_seed_varies_weights_only(self) -> None:
        """Fixed evaluation seed, model seeds A and B:
        identical sampled pairs, different weights."""
        weights_a, pairs_a = _run(model_seed=1, eval_seed=99)
        weights_b, pairs_b = _run(model_seed=2, eval_seed=99)

        assert pairs_a == pairs_b, (
            "changing the model seed changed the evaluation population -- the domains "
            "are still coupled"
        )
        assert weights_a != weights_b, "changing the model seed did not change the weights"

    def test_eval_seed_varies_population_only(self) -> None:
        """Fixed model seed, evaluation seeds A and B:
        identical weights, different pairs."""
        weights_a, pairs_a = _run(model_seed=5, eval_seed=1)
        weights_b, pairs_b = _run(model_seed=5, eval_seed=2)

        assert weights_a == weights_b, (
            "changing the evaluation seed changed the model weights -- the domains are "
            "still coupled in the other direction"
        )
        assert pairs_a != pairs_b, "changing the evaluation seed did not change the population"


class TestRngDomains:
    """Five lower-level assertions about the domains themselves."""

    def test_global_numpy_does_not_reach_the_sampling_stream(self) -> None:
        vint_dataset.navfm_seed_sampling(7)
        first = _pairs()
        np.random.seed(123456)  # perturb the global stream
        vint_dataset.navfm_seed_sampling(7)
        assert _pairs() == first

    def test_model_seeding_does_not_reach_the_sampling_stream(self) -> None:
        """seed_model_rng seeds global numpy; that must no longer matter."""
        vint_dataset.navfm_seed_sampling(11)
        first = _pairs()
        seed_model_rng(4242)
        vint_dataset.navfm_seed_sampling(11)
        assert _pairs() == first

    def test_population_is_reproducible_from_its_seed_alone(self) -> None:
        vint_dataset.navfm_seed_sampling(3)
        first = _pairs()
        seed_model_rng(1)
        np.random.seed(2)
        import random

        random.seed(3)
        vint_dataset.navfm_seed_sampling(3)
        assert _pairs() == first, "the population is not reproducible from its seed alone"

    def test_sampling_stream_is_not_reset_by_drawing_from_it(self) -> None:
        """Successive draws advance; a stream that repeats is not sampling."""
        vint_dataset.navfm_seed_sampling(21)
        assert _pairs(20) != _pairs(20)

    def test_identical_population_across_all_four_arms(self) -> None:
        """Both checkpoint repeats and all three controls score one population."""
        populations = [_run(model_seed=m, eval_seed=0)[1] for m in (0, 0, 0, 1, 2)]
        assert all(p == populations[0] for p in populations), (
            "arms did not share one evaluation population"
        )
