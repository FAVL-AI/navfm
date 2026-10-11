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

``ArcLengthInterpolatedTargetSelector`` is the preregistered treatment, ported
to this seam from the frozen subclass that defined it. Every semantic it uses --
the clamped parametric foot, ties resolving to the earlier segment, arc length
that clamps at the route end rather than extrapolating, and the inherited vertex
index still advancing so ``finished`` means the same thing in both arms -- was
fixed before any Hospital run and is reproduced here rather than reinvented.

It steers at a point ON the polyline a fixed arc length ahead of the pose's own
projection. That is not the same thing as textbook pure pursuit: no look-ahead
circle is intersected, and a small cross-track error is not evidence that a
forward circle intersection exists. Implementing the circle version here would
be a different experiment than the one that was preregistered.
"""

from __future__ import annotations

import dataclasses
from typing import NamedTuple, Protocol, runtime_checkable

import numpy as np

__all__ = [
    "SELECTOR_REGISTRY",
    "ArcLengthInterpolatedTargetSelector",
    "LegacyVertexTargetSelector",
    "SelectorResolutionRefused",
    "TargetSelection",
    "TargetSelectionRefused",
    "TargetSelector",
    "interpolated_selection",
    "resolve_target_selector",
]


class SelectorResolutionRefused(ValueError):
    """An arm asked for a selector this repository does not implement.

    Refused by name rather than falling back to a default. A fallback would let
    a mistyped arm declaration run the wrong behaviour under the right label,
    which is the one error a one-factor experiment cannot survive.
    """


class TargetSelectionRefused(ValueError):
    """Input a selector cannot answer for.

    Raised with a stated reason rather than allowing an index error or a NaN to
    propagate into a command. The scientific harness converts this into a
    recorded refusal; a barrier that crashes has not refused.
    """


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


@dataclasses.dataclass(frozen=True)
class InterpolatedSelection:
    """The treatment's selection, with the intermediate quantities exposed.

    The arc-length coordinates are what the analytic controls check invariants
    against, so they are produced by the same code that produces the point. A
    second implementation for the analysis to compare against would be a second
    thing to drift.
    """

    point: np.ndarray
    projection_s: float
    target_s: float
    total_length: float
    projection_segment: int
    target_segment: int
    clamped_at_route_end: bool


def _validate(path: np.ndarray, position: np.ndarray, lookahead: float) -> np.ndarray:
    pts = np.asarray(path, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise TargetSelectionRefused(
            f"route must be an (N, 2) array of points; got shape {pts.shape}")
    if pts.shape[0] < 2:
        raise TargetSelectionRefused(
            f"route needs at least two points; got {pts.shape[0]}")
    if not np.all(np.isfinite(pts)):
        raise TargetSelectionRefused("route contains a non-finite coordinate")
    pos = np.asarray(position, dtype=np.float64)
    if pos.shape[0] < 2 or not np.all(np.isfinite(pos[:2])):
        raise TargetSelectionRefused(
            "position must carry two finite coordinates")
    if not np.isfinite(lookahead) or lookahead < 0.0:
        raise TargetSelectionRefused(
            f"look-ahead must be finite and non-negative; got {lookahead!r}")
    if float(np.max(np.linalg.norm(np.diff(pts, axis=0), axis=1))) <= 0.0:
        raise TargetSelectionRefused("route has no segment of non-zero length")
    return pts


def interpolated_selection(
    path: np.ndarray, position: np.ndarray, lookahead: float
) -> InterpolatedSelection:
    """Project onto the route, then step ``lookahead`` metres along it.

    The one implementation of the treatment geometry. The selector calls it and
    so do the analytic controls, so the quantity checked is the quantity used.
    """
    from navfm.collection.route_projection import (
        point_at_arclength,
        polyline_cumlength,
        project_to_polyline,
    )

    pts = _validate(path, position, lookahead)
    cum = polyline_cumlength(pts)
    total = float(cum[-1])
    projection = project_to_polyline(pts, cum, np.asarray(position, dtype=np.float64)[:2])
    # Past the end of the route there is no route. The target clamps to the
    # final point; extrapolating would steer the base beyond the goal.
    target_s = min(projection.s + float(lookahead), total)
    point = point_at_arclength(pts, cum, target_s)
    index = int(np.searchsorted(cum, target_s, side="right") - 1)
    return InterpolatedSelection(
        point=point,
        projection_s=float(projection.s),
        target_s=float(target_s),
        total_length=total,
        projection_segment=int(projection.segment),
        target_segment=min(max(index, 0), pts.shape[0] - 2),
        clamped_at_route_end=bool(projection.s + float(lookahead) > total),
    )


class ArcLengthInterpolatedTargetSelector:
    """Arm B: an arc-length interpolated look-ahead point on the frozen route.

    The manipulated factor, and the only one. The vertex index is still advanced
    by the legacy rule and returned unchanged, because ``PurePursuit.finished``
    reads it -- leaving it frozen would introduce a second uncontrolled
    difference into a one-factor experiment.
    """

    target_type = "ARC_LENGTH_INTERPOLATED"

    def __init__(self) -> None:
        self._legacy = LegacyVertexTargetSelector()

    def select_target(
        self,
        path: np.ndarray,
        position: np.ndarray,
        index: int,
        lookahead: float,
    ) -> TargetSelection:
        inherited = self._legacy.select_target(path, position, index, lookahead)
        selection = interpolated_selection(path, position, lookahead)
        return TargetSelection(selection.point, inherited.next_index)


#: Selector identity -> implementation. Keyed by ``target_type`` because that is
#: the string the manifest, the preflight and the arm evidence already use, so
#: there is one name for an arm's behaviour rather than three that must agree.
SELECTOR_REGISTRY: dict[str, type] = {
    LegacyVertexTargetSelector.target_type: LegacyVertexTargetSelector,
    ArcLengthInterpolatedTargetSelector.target_type: ArcLengthInterpolatedTargetSelector,
}


def resolve_target_selector(declaration: str | None) -> TargetSelector:
    """Turn a declared selector identity into the selector itself.

    ``None`` resolves to the legacy selector, which is what every pre-existing
    collection caller has always used and must keep using: absence is the frozen
    control behaviour, never the treatment. An *unknown* declaration is refused,
    because a typo that silently produced legacy behaviour under a treatment
    label would be indistinguishable from a null result.

    An intervention arm must still declare its selector explicitly; that
    requirement lives in the runner, where an arm identity exists to check it
    against, rather than here where it would change every unrelated caller.
    """
    if declaration is None:
        return LegacyVertexTargetSelector()
    if declaration not in SELECTOR_REGISTRY:
        raise SelectorResolutionRefused(
            f"unknown target selector {declaration!r}; declared selectors are "
            f"{sorted(SELECTOR_REGISTRY)}"
        )
    selector: TargetSelector = SELECTOR_REGISTRY[declaration]()
    return selector
