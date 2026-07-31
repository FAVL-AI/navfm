"""Proof that :func:`navfm.eval.metrics.reference_losses` *is* the reference loss.

CLAUDE.md's adversarial-review policy calls for red-teaming any semantic change
to ``eval/metrics.py``, on the grounds that no oracle exists there and a
plausible misreading would be co-signed by our own tests. This file removes the
premise: the oracle is ``vint_train.training.train_utils._compute_losses``, so
the definitions are checked against the reference function on random tensors
instead of being argued about.

Every quirk documented in ``navfm.eval.metrics`` is exercised here rather than
asserted in prose:

* ``action_reduce``'s ``(loss * mask).mean() / (mask.mean() + 1e-2)``, including
  the systematic ``p / (p + 0.01)`` scaling at partial masks;
* cosine similarities passing through that same reduction, so the logged values
  are not confined to ``[-1, 1]``;
* ``dist_loss`` being unmasked;
* ``total_loss = alpha * 1e-2 * dist + (1 - alpha) * action``.

Skipped unless the reference clone and the packages ``train_utils`` imports
transitively (wandb, prettytable, matplotlib, cv2, diffusers) are present.
"""

from __future__ import annotations

import numpy as np
import pytest

from navfm.eval import metrics
from navfm.upstream import UpstreamNotFound, ensure_upstream

torch = pytest.importorskip("torch")

pytestmark = [pytest.mark.upstream, pytest.mark.torch]

try:
    ensure_upstream()
except UpstreamNotFound:  # pragma: no cover - environment dependent
    pytest.skip("reference visualnav-transformer not found", allow_module_level=True)

# train_utils drags in the whole visualisation/logging stack. If any of it is
# missing the oracle is unavailable and there is nothing honest to assert.
_compute_losses = pytest.importorskip(
    "vint_train.training.train_utils",
    reason="train_utils needs wandb/prettytable/matplotlib/cv2/diffusers",
)._compute_losses


def _batch(rng, *, batch=7, horizon=5, mask_p=0.85, learn_angle=True):
    """Random predictions/labels shaped like a ViNT batch.

    The label's heading columns are unit-norm, as ``calculate_sin_cos``
    guarantees; the *prediction*'s are not, because the model's are not either.
    """
    dim = 4 if learn_angle else 2
    action_pred = rng.normal(size=(batch, horizon, dim))
    action_label = rng.normal(size=(batch, horizon, dim))
    if learn_angle:
        theta = rng.uniform(-np.pi, np.pi, size=(batch, horizon))
        action_label[..., 2] = np.cos(theta)
        action_label[..., 3] = np.sin(theta)
    dist_pred = rng.normal(size=(batch, 1))
    dist_label = rng.integers(0, 20, size=(batch,))
    mask = (rng.random(batch) < mask_p).astype(np.float64)
    return dist_pred, dist_label, action_pred, action_label, mask


def _upstream(dist_pred, dist_label, action_pred, action_label, mask, *, alpha, learn_angle):
    out = _compute_losses(
        dist_label=torch.as_tensor(dist_label),
        action_label=torch.as_tensor(action_label, dtype=torch.float64),
        dist_pred=torch.as_tensor(dist_pred, dtype=torch.float64),
        action_pred=torch.as_tensor(action_pred, dtype=torch.float64),
        alpha=alpha,
        learn_angle=learn_angle,
        action_mask=torch.as_tensor(mask, dtype=torch.float64),
    )
    return {k: float(v) for k, v in out.items()}


@pytest.mark.parametrize("mask_p", [1.0, 0.85, 0.5, 0.1])
@pytest.mark.parametrize("alpha", [0.5, 0.25])
def test_reference_losses_match_compute_losses(mask_p, alpha):
    """The decisive check: identical keys and identical values, every mask rate."""
    rng = np.random.default_rng(int(1000 * mask_p) + int(100 * alpha))
    for _ in range(5):
        args = _batch(rng, mask_p=mask_p)
        ours = metrics.reference_losses(
            dist_pred=args[0],
            dist_label=args[1],
            action_pred=args[2],
            action_label=args[3],
            action_mask=args[4],
            alpha=alpha,
            learn_angle=True,
            strict=True,
        )
        theirs = _upstream(*args, alpha=alpha, learn_angle=True)

        assert set(ours) == set(theirs), "our metric dict must have the reference's keys"
        for key in theirs:
            assert ours[key] == pytest.approx(theirs[key], rel=1e-10, abs=1e-12), key


def test_learn_angle_false_drops_the_orientation_keys():
    """Upstream omits both orientation metrics entirely when learn_angle is off;
    reporting them as NaN or 0.0 would put a column in the results table that
    the reference never computes."""
    rng = np.random.default_rng(3)
    args = _batch(rng, learn_angle=False)
    ours = metrics.reference_losses(
        dist_pred=args[0],
        dist_label=args[1],
        action_pred=args[2],
        action_label=args[3],
        action_mask=args[4],
        learn_angle=False,
    )
    theirs = _upstream(*args, alpha=0.5, learn_angle=False)
    assert set(ours) == set(theirs)
    assert "action_orien_cos_sim" not in ours
    for key in theirs:
        assert ours[key] == pytest.approx(theirs[key], rel=1e-10, abs=1e-12), key


def test_the_plain_reduction_differs_from_the_reference_by_the_documented_factor():
    """strict=False is our own reporting variant, not upstream's. It must differ
    from the reference by exactly p/(p+0.01) on the action terms and not at all
    on dist_loss -- if it ever agrees exactly, the +1e-2 guard has been lost."""
    rng = np.random.default_rng(17)
    args = _batch(rng, batch=200, mask_p=0.85)
    mask = args[4]
    p = float(mask.mean())

    strict = metrics.reference_losses(
        dist_pred=args[0], dist_label=args[1], action_pred=args[2],
        action_label=args[3], action_mask=args[4], strict=True,
    )
    plain = metrics.reference_losses(
        dist_pred=args[0], dist_label=args[1], action_pred=args[2],
        action_label=args[3], action_mask=args[4], strict=False,
    )
    theirs = _upstream(*args, alpha=0.5, learn_angle=True)

    assert strict["action_loss"] == pytest.approx(theirs["action_loss"], rel=1e-10)
    assert plain["action_loss"] != pytest.approx(theirs["action_loss"], rel=1e-6)
    # strict = plain * p / (p + 1e-2)
    assert strict["action_loss"] == pytest.approx(plain["action_loss"] * p / (p + 1e-2), rel=1e-10)
    # dist_loss is unmasked upstream, so the reduction variant cannot touch it.
    assert plain["dist_loss"] == pytest.approx(strict["dist_loss"], rel=1e-12)


def test_the_two_orientation_metrics_are_the_same_number():
    """Finding F12: for ViNT and GNM, ``action_orien_cos_sim`` and
    ``multi_action_orien_cos_sim`` are provably identical, so one of the two is
    redundant.

    Both models L2-normalise their predicted heading columns before returning
    (``vint.py:135-137``, ``gnm.py:85-87``), and the labels' heading columns are
    unit-norm by construction in ``calculate_sin_cos``. With unit vectors on
    both sides the per-waypoint cosine is ``p_k . l_k`` and its mean over the
    horizon is ``(1/T) sum_k p_k . l_k``; the flattened cosine is
    ``(sum_k p_k . l_k) / (sqrt(T) sqrt(T))`` -- the same quantity.

    Asserted against the reference function so the claim is about upstream's
    behaviour, not ours. It does *not* hold for the xy columns, which are
    cumulative sums of unbounded deltas, and the test checks that too so a
    future change cannot make the identity vacuous.
    """
    rng = np.random.default_rng(23)
    args = list(_batch(rng, batch=32, mask_p=0.9))
    action_pred, action_label = args[2], args[3]

    # Reproduce what the models actually emit: unit-norm heading columns.
    for arr in (action_pred, action_label):
        head = arr[..., 2:]
        arr[..., 2:] = head / np.linalg.norm(head, axis=-1, keepdims=True)

    theirs = _upstream(*args, alpha=0.5, learn_angle=True)
    assert theirs["action_orien_cos_sim"] == pytest.approx(
        theirs["multi_action_orien_cos_sim"], rel=1e-9
    )
    # The xy pair is genuinely two different measurements.
    assert theirs["action_waypts_cos_sim"] != pytest.approx(
        theirs["multi_action_waypts_cos_sim"], rel=1e-3
    )


def test_cosine_similarity_can_leave_the_unit_interval():
    """A consequence of quirk 2 that a reader of the logs must know: with a
    fully-masked-in batch the reduction scales by 1/1.01, so a perfect cosine
    logs as 0.990 rather than 1.0."""
    rng = np.random.default_rng(5)
    action = rng.normal(size=(9, 5, 4))
    mask = np.ones(9)
    ours = metrics.waypoint_cosine_similarity(action, action, mask, strict=True)
    assert ours == pytest.approx(1.0 / 1.01, rel=1e-12)
    assert metrics.waypoint_cosine_similarity(action, action, mask, strict=False) == pytest.approx(1.0)
