"""Projection of a pose onto a frozen route polyline.

This is the single geometric instrument shared by the controller and the
analysis in TERMINAL_APPROACH_INTERVENTION_V1. Both arms must be measured
against the same polyline with the same conventions, and the treatment arm also
*steers* by arc length, so a second implementation drifting from the first would
corrupt the comparison in a way no downstream check would catch.

The conventions, stated once:

**The parametric foot is clamped to the segment.** Without the clamp a pose
beyond a segment's end projects past it, which produces a negative or
overlong arc length near vertices and silently breaks the ordering of the
progress coordinate. Clamping is what makes the projection valid at vertices and
outside the route's span.

**Ties go to the earlier segment.** A pose equidistant from two segments is
ambiguous; resolving to the smaller arc length keeps the coordinate
deterministic, which matters because the progress coordinate is differenced.

**Arc length past the end of the route does not exist.** ``point_at_arclength``
clamps rather than extrapolating. A route is a finite polyline, and a target
extrapolated beyond its final point would steer a robot past the goal it is
meant to approach.
"""

from __future__ import annotations

import dataclasses

import numpy as np

__all__ = [
    "Projection",
    "point_at_arclength",
    "polyline_cumlength",
    "project_to_polyline",
]


@dataclasses.dataclass(frozen=True)
class Projection:
    """Where a pose sits relative to the route."""

    #: Arc length along the polyline of the projected point, in metres.
    s: float
    #: Signed lateral offset. Positive is to the left of the travel direction.
    cross_track: float
    #: Heading of the segment the projection landed on, in radians.
    tangent: float
    #: Index of that segment.
    segment: int


def polyline_cumlength(path: np.ndarray) -> np.ndarray:
    """Cumulative arc length at each vertex, starting at zero."""
    pts = np.asarray(path, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] < 2:
        raise ValueError("a polyline needs at least two points")
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(seg)])


def project_to_polyline(
    path: np.ndarray, cum: np.ndarray, point: np.ndarray
) -> Projection:
    """Nearest valid projection of ``point`` onto ``path``."""
    pts = np.asarray(path, dtype=np.float64).reshape(-1, 2)
    p = np.asarray(point, dtype=np.float64).reshape(2)
    best: Projection | None = None
    best_d = float("inf")
    for i in range(pts.shape[0] - 1):
        a, b = pts[i], pts[i + 1]
        ab = b - a
        length = float(np.linalg.norm(ab))
        if length <= 0.0:
            continue
        t = float(np.clip(np.dot(p - a, ab) / (length * length), 0.0, 1.0))
        d = float(np.linalg.norm(p - (a + t * ab)))
        # Strictly less than, so a tie resolves to the earlier segment.
        if d < best_d:
            best_d = d
            unit = ab / length
            offset = p - a
            best = Projection(
                s=float(cum[i] + t * length),
                cross_track=float(unit[0] * offset[1] - unit[1] * offset[0]),
                tangent=float(np.arctan2(ab[1], ab[0])),
                segment=i,
            )
    if best is None:
        raise ValueError("polyline has no segment of non-zero length")
    return best


def point_at_arclength(path: np.ndarray, cum: np.ndarray, s: float) -> np.ndarray:
    """The point at arc length ``s``, clamped to the polyline's span."""
    pts = np.asarray(path, dtype=np.float64).reshape(-1, 2)
    target = float(np.clip(s, 0.0, float(cum[-1])))
    i = int(np.searchsorted(cum, target, side="right") - 1)
    i = min(max(i, 0), pts.shape[0] - 2)
    span = float(cum[i + 1] - cum[i])
    t = 0.0 if span <= 0.0 else (target - float(cum[i])) / span
    return pts[i] + t * (pts[i + 1] - pts[i])
