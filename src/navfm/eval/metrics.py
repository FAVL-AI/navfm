"""Evaluation metrics, defined to match the reference implementation exactly.

Reproducing a published number means reproducing its *definition*, and the
reference metrics have three quirks that a naive reimplementation gets wrong.
All three are reproduced here, with a ``strict`` flag to disable them when you
want a clean number for your own reporting.

1. **``action_reduce`` is not a mean.** It is
   ``(loss * mask).mean() / (mask.mean() + 1e-2)``. The ``+1e-2`` is a
   divide-by-zero guard that also scales every reported value by
   ``p / (p + 0.01)`` where ``p`` is the unmasked fraction. At the typical
   ``p ~ 0.85`` that is a 1.2 % systematic shift -- small, but enough that
   "our cosine similarity is 0.951 vs their 0.963" is meaningless without it.

2. **Cosine similarities go through ``action_reduce`` too.** So the logged
   ``*_cos_sim`` values are not in ``[-1, 1]``; they are masked-mean-scaled.

3. **NoMaD's ``dist_loss`` goal-masking is a no-op.** The code multiplies a
   *scalar* ``F.mse_loss(..., reduction='mean')`` by a ``(B,)`` mask vector and
   then takes ``.mean()``, so the distance head is in fact trained and scored on
   goal-masked samples too, merely scaled by ~0.98 at ``p_m = 0.5``. Anyone
   matching the released checkpoint's behaviour must reproduce this.

The closed-loop metrics (success rate, collisions, SPL, maximum displacement
before intervention) follow the ViNT and NoMaD papers' definitions, which are
stated in prose rather than equations; each docstring quotes the source.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import numpy as np

__all__ = [
    "ClosedLoopEpisode",
    "action_mse",
    "action_reduce",
    "ade",
    "bootstrap_ci",
    "collisions_per_episode",
    "distance_mse",
    "fde",
    "max_displacement_before_intervention",
    "multi_action_cosine_similarity",
    "multi_orientation_cosine_similarity",
    "orientation_cosine_similarity",
    "reference_losses",
    "spl",
    "success_rate",
    "waypoint_cosine_similarity",
]

REFERENCE_EPS = 1e-2


def action_reduce(unreduced: np.ndarray, mask: np.ndarray, *, strict: bool = True) -> float:
    """Port of ``train_utils.action_reduce``.

    ``unreduced`` has shape ``(B, ...)``; every non-batch dimension is averaged
    away first, exactly as upstream does with its ``while dim() > 1`` loop.
    ``strict=False`` gives the plain masked mean instead.
    """
    x = np.asarray(unreduced, dtype=np.float64)
    while x.ndim > 1:
        x = x.mean(axis=-1)
    m = np.asarray(mask, dtype=np.float64).reshape(-1)
    if x.shape != m.shape:
        raise ValueError(f"mask shape {m.shape} does not match batch shape {x.shape}")
    if strict:
        return float((x * m).mean() / (m.mean() + REFERENCE_EPS))
    denom = m.sum()
    return float((x * m).sum() / denom) if denom > 0 else float("nan")


def action_mse(
    pred: np.ndarray, target: np.ndarray, mask: np.ndarray, *, strict: bool = True
) -> float:
    """Reference ``action_loss``: elementwise MSE then ``action_reduce``."""
    pred = np.asarray(pred, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    return action_reduce((pred - target) ** 2, mask, strict=strict)


def distance_mse(pred: np.ndarray, target: np.ndarray) -> float:
    """Reference ``dist_loss``: plain MSE, no masking, on integer timestep labels.

    The labels are raw timestep counts in ``[0, max_dist_cat]`` and are *not*
    rescaled, which is why the training objective multiplies this term by
    ``1e-2`` before combining. Report it in the same units to stay comparable.
    """
    return float(
        np.mean(
            (
                np.asarray(pred, dtype=np.float64).reshape(-1)
                - np.asarray(target, dtype=np.float64).reshape(-1)
            )
            ** 2
        )
    )


def _cosine(a: np.ndarray, b: np.ndarray, axis: int = -1) -> np.ndarray:
    num = (a * b).sum(axis=axis)
    den = np.linalg.norm(a, axis=axis) * np.linalg.norm(b, axis=axis)
    return num / np.maximum(den, 1e-8)


def waypoint_cosine_similarity(
    pred: np.ndarray, target: np.ndarray, mask: np.ndarray, *, strict: bool = True
) -> float:
    """``*_action_waypts_cos_sim``: per-waypoint cosine, then ``action_reduce``.

    Inputs are ``(B, T, >=2)``; only the ``x, y`` columns participate.
    """
    p = np.asarray(pred, dtype=np.float64)[..., :2]
    t = np.asarray(target, dtype=np.float64)[..., :2]
    return action_reduce(_cosine(p, t, axis=-1), mask, strict=strict)


def multi_action_cosine_similarity(
    pred: np.ndarray, target: np.ndarray, mask: np.ndarray, *, strict: bool = True
) -> float:
    """``*_multi_action_waypts_cos_sim``: cosine over the flattened trajectory.

    This is the more informative of the two -- it is sensitive to the *shape* of
    the whole predicted path, not just to each step's direction.
    """
    p = np.asarray(pred, dtype=np.float64)[..., :2].reshape(pred.shape[0], -1)
    t = np.asarray(target, dtype=np.float64)[..., :2].reshape(target.shape[0], -1)
    return action_reduce(_cosine(p, t, axis=-1), mask, strict=strict)


def orientation_cosine_similarity(
    pred: np.ndarray, target: np.ndarray, mask: np.ndarray, *, strict: bool = True
) -> float:
    """``*_action_orien_cos_sim``: per-waypoint cosine over the ``(cos, sin)`` columns.

    Logged by ViNT and GNM whenever ``learn_angle`` is true, and omitted
    entirely when it is false. Only meaningful because
    ``calculate_sin_cos`` guarantees those two columns are unit-norm, which
    makes this the cosine of the *heading error* at each waypoint.

    **Finding F12.** This is numerically identical to
    :func:`multi_orientation_cosine_similarity` for both released
    architectures, so upstream logs the same number under two names. Both
    models L2-normalise their predicted heading columns before returning
    (``vint.py:135-137``, ``gnm.py:85-87``) and the labels are already
    unit-norm, and for unit vectors the mean per-waypoint cosine and the
    flattened cosine are the same quantity -- the ``sqrt(T) * sqrt(T)`` in the
    flattened denominator is exactly the ``1/T`` of the mean. Proven against
    the reference in ``tests/test_upstream_losses.py``. Report one of them.
    """
    p = np.asarray(pred, dtype=np.float64)[..., 2:]
    t = np.asarray(target, dtype=np.float64)[..., 2:]
    return action_reduce(_cosine(p, t, axis=-1), mask, strict=strict)


def multi_orientation_cosine_similarity(
    pred: np.ndarray, target: np.ndarray, mask: np.ndarray, *, strict: bool = True
) -> float:
    """``*_multi_action_orien_cos_sim``: cosine over the flattened heading columns.

    Redundant with :func:`orientation_cosine_similarity` in practice; see
    finding F12 there. Kept because the reference logs it and a reproduction
    that silently dropped a logged metric would be harder to check.
    """
    p = np.asarray(pred, dtype=np.float64)[..., 2:].reshape(np.shape(pred)[0], -1)
    t = np.asarray(target, dtype=np.float64)[..., 2:].reshape(np.shape(target)[0], -1)
    return action_reduce(_cosine(p, t, axis=-1), mask, strict=strict)


def reference_losses(
    *,
    dist_pred: np.ndarray,
    dist_label: np.ndarray,
    action_pred: np.ndarray,
    action_label: np.ndarray,
    action_mask: np.ndarray,
    alpha: float = 0.5,
    learn_angle: bool = True,
    strict: bool = True,
) -> dict[str, float]:
    """The full metric dict ``train_utils._compute_losses`` returns, in numpy.

    Keys, values and the ``total_loss`` weighting match the reference exactly at
    ``strict=True``; ``tests/test_upstream_losses.py`` asserts that against the
    reference function itself rather than against our reading of it.

    ``alpha`` is the reference's own name for the split, and the effective
    weighting is ``alpha * 1e-2 * dist + (1 - alpha) * action`` -- at the
    configs' ``alpha = 0.5`` that is a distance:action ratio of ``0.01``, i.e.
    ViNT's published ``lambda``. The ``1e-2`` is *not* folded into alpha
    upstream and is not folded here either, so a run that sweeps alpha sweeps
    the same quantity the reference would.

    ``strict=False`` swaps ``action_reduce``'s ``+1e-2``-guarded reduction for a
    plain masked mean throughout. It changes every action-derived value by
    ``p / (p + 0.01)`` and changes ``dist_loss`` not at all -- ``dist_loss`` is
    unmasked in the reference.
    """
    out: dict[str, float] = {
        "dist_loss": distance_mse(dist_pred, dist_label),
        "action_loss": action_mse(action_pred, action_label, action_mask, strict=strict),
        "action_waypts_cos_sim": waypoint_cosine_similarity(
            action_pred, action_label, action_mask, strict=strict
        ),
        "multi_action_waypts_cos_sim": multi_action_cosine_similarity(
            action_pred, action_label, action_mask, strict=strict
        ),
    }
    if learn_angle:
        out["action_orien_cos_sim"] = orientation_cosine_similarity(
            action_pred, action_label, action_mask, strict=strict
        )
        out["multi_action_orien_cos_sim"] = multi_orientation_cosine_similarity(
            action_pred, action_label, action_mask, strict=strict
        )
    out["total_loss"] = (
        alpha * REFERENCE_EPS * out["dist_loss"] + (1.0 - alpha) * out["action_loss"]
    )
    return out


def ade(pred: np.ndarray, target: np.ndarray, mask: np.ndarray | None = None) -> float:
    """Average displacement error in *normalised waypoint units*.

    Not a reference metric -- the reference repo reports only MSE and cosine
    similarity -- but MSE on normalised waypoints is uninterpretable, and ADE
    multiplied by ``metric_waypoint_spacing`` converts straight to metres.
    Report both.
    """
    p = np.asarray(pred, dtype=np.float64)[..., :2]
    t = np.asarray(target, dtype=np.float64)[..., :2]
    d = np.linalg.norm(p - t, axis=-1).mean(axis=-1)
    if mask is None:
        return float(d.mean())
    m = np.asarray(mask, dtype=np.float64).reshape(-1)
    return float((d * m).sum() / max(m.sum(), 1e-9))


def fde(pred: np.ndarray, target: np.ndarray, mask: np.ndarray | None = None) -> float:
    """Final displacement error, same units as :func:`ade`."""
    p = np.asarray(pred, dtype=np.float64)[..., -1, :2]
    t = np.asarray(target, dtype=np.float64)[..., -1, :2]
    d = np.linalg.norm(p - t, axis=-1)
    if mask is None:
        return float(d.mean())
    m = np.asarray(mask, dtype=np.float64).reshape(-1)
    return float((d * m).sum() / max(m.sum(), 1e-9))


# ---------------------------------------------------------------- closed loop


@dataclasses.dataclass
class ClosedLoopEpisode:
    """One closed-loop rollout.

    ``reached_goal`` is the success criterion; ``n_collisions`` counts contact
    events; ``path`` is the executed ``(N, 2)`` trajectory; ``shortest_path_m``
    is the planner's optimal length between the same endpoints, needed for SPL.
    ``displacement_before_intervention_m`` is the ViNT paper's cross-embodiment
    metric ("maximum displacement in metres, no intervention").
    """

    reached_goal: bool
    path: np.ndarray
    shortest_path_m: float
    n_collisions: int = 0
    n_interventions: int = 0
    displacement_before_intervention_m: float | None = None
    steps: int = 0
    scene: str = ""

    @property
    def executed_length_m(self) -> float:
        p = np.asarray(self.path, dtype=np.float64).reshape(-1, 2)
        if p.shape[0] < 2:
            return 0.0
        return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


def success_rate(episodes: Sequence[ClosedLoopEpisode]) -> float:
    """Fraction of episodes reaching the goal. ViNT/NoMaD Table metric."""
    if not episodes:
        return float("nan")
    return float(np.mean([e.reached_goal for e in episodes]))


def spl(episodes: Sequence[ClosedLoopEpisode]) -> float:
    """Success weighted by inverse Path Length (Anderson et al., 2018).

    ``SPL = (1/N) * sum_i S_i * l_i / max(p_i, l_i)`` with ``l`` the shortest
    path and ``p`` the executed path. Reported by ViNT for the GPS and
    satellite-guided experiments.
    """
    if not episodes:
        return float("nan")
    vals = []
    for e in episodes:
        if not e.reached_goal:
            vals.append(0.0)
            continue
        executed = max(e.executed_length_m, 1e-9)
        optimal = max(e.shortest_path_m, 1e-9)
        vals.append(optimal / max(executed, optimal))
    return float(np.mean(vals))


def collisions_per_episode(episodes: Sequence[ClosedLoopEpisode]) -> float:
    """NoMaD Table I "# Collisions": mean collisions per experiment."""
    if not episodes:
        return float("nan")
    return float(np.mean([e.n_collisions for e in episodes]))


def max_displacement_before_intervention(episodes: Sequence[ClosedLoopEpisode]) -> float:
    """ViNT's zero-shot cross-embodiment metric, in metres.

    The paper reports the *maximum* displacement achieved without human
    intervention; we take the mean over episodes of each episode's value, which
    is the only reading consistent with a per-environment table.
    """
    vals = [
        e.displacement_before_intervention_m
        if e.displacement_before_intervention_m is not None
        else e.executed_length_m
        for e in episodes
    ]
    return float(np.mean(vals)) if vals else float("nan")


def bootstrap_ci(
    values: Sequence[float], *, n_boot: int = 10_000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float]:
    """Percentile bootstrap CI for a mean.

    Included because the reference papers report point estimates without trial
    counts or intervals. Any claim built on top of them needs its own interval,
    and with the 10-40 episode counts typical of robot evaluation the normal
    approximation is not safe.
    """
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, v.size, size=(n_boot, v.size))
    means = v[idx].mean(axis=1)
    return (
        float(np.percentile(means, 100 * alpha / 2)),
        float(np.percentile(means, 100 * (1 - alpha / 2))),
    )
