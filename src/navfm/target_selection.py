"""The target-selection seam for TERMINAL_APPROACH_INTERVENTION_V1.

The intervention manipulates one thing: what the tracker steers at. Everything
else -- the heading-error law, the speed law, the angular law, clipping, the
goal predicate, the stop branch, SE(2) integration, dt, max_steps, the route --
is held constant by design. This module is the smallest boundary that isolates
the manipulated factor, so that an arm can replace target selection without
being handed the means to change anything else.

The interface is deliberately narrow. A selector receives the path, a position,
the current index and the frozen look-ahead, and returns a point and the new
index. It is never given the tracker, so it cannot reach ``cruise_v``,
``limits``, ``mode`` or ``goal_tol``; a treatment that wanted to alter the speed
law would have to change the tracker itself, where the change would be visible
as a source diff rather than hidden behind an injected object.

Index advancement is returned rather than mutated in place. The legacy tracker
advanced ``self._idx`` as a side effect of asking for a target, and that
advancement is load-bearing -- ``finished`` reads the same index. Making it part
of the return value keeps the semantics identical while making the state
transition something a proof can compare, which is what the
ARM_A_LEGACY == ARM_A_INJECTED equivalence harness does at every step.

``LegacyVertexTargetSelector`` is a transcription, not a tidy-up. It reproduces
the pre-seam arithmetic exactly, including the strict ``<`` comparison, the
advance-then-break loop, and the ``min`` clamp that can only bind at the final
vertex. Awkward semantics are preserved because Arm A is defined as the frozen
behaviour, and this tranche is not authorised to repair it.
"""

from __future__ import annotations

from typing import NamedTuple, Protocol, runtime_checkable

import numpy as np

__all__ = [
    "LegacyVertexTargetSelector",
    "TargetSelection",
    "TargetSelector",
]


class TargetSelection(NamedTuple):
    """What the tracker steers at, and the index it leaves behind."""

    #: The point to steer at, in world coordinates.
    point: np.ndarray
    #: The path index after advancement. ``PurePursuit.finished`` reads this.
    #: Named ``next_index`` rather than ``index`` because a NamedTuple field
    #: called ``index`` shadows ``tuple.index``, which is a confusing thing to
    #: hand a future reader for no benefit.
    next_index: int


@runtime_checkable
class TargetSelector(Protocol):
    """The one behaviour an arm may replace.

    ``target_type`` is metadata recorded in evidence so an arm cannot be
    mislabelled after the fact. ``select_target`` is the only behavioural
    member; the protocol exposes nothing else, and nothing else is consulted by
    the tracker.
    """

    target_type: str

    def select_target(
        self,
        path: np.ndarray,
        position: np.ndarray,
        index: int,
        lookahead: float,
    ) -> TargetSelection:
        """Return the steering point and the advanced index."""
        ...


class LegacyVertexTargetSelector:
    """The frozen Arm A behaviour: the nearest qualifying path vertex.

    Transcribed from ``PurePursuit.target`` as it stood before the seam existed.
    The loop advances while the *current* vertex is strictly nearer than the
    look-ahead, then stops; it does not search forward for the furthest
    qualifying vertex, and it does not interpolate. That is the behaviour Arm A
    is defined to be.
    """

    target_type = "PATH_VERTEX"

    def select_target(
        self,
        path: np.ndarray,
        position: np.ndarray,
        index: int,
        lookahead: float,
    ) -> TargetSelection:
        idx = index
        while idx < path.shape[0] - 1:
            if np.linalg.norm(path[idx] - position) < lookahead:
                idx += 1
            else:
                break
        # The returned array is a view into ``path``, exactly as the pre-seam
        # implementation returned one. Copying here would be tidier and would
        # also be a behaviour change.
        return TargetSelection(path[min(idx, path.shape[0] - 1)], idx)
