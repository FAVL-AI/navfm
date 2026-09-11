"""Arm B of TERMINAL_APPROACH_INTERVENTION_V1: interpolated look-ahead targeting.

``PurePursuit.target`` returns a path VERTEX. The look-ahead radius is only the
distance within which the tracker advances to the next vertex, so with a
five-point route the tracker steers at points up to 7.85 m away, and the frozen
curvature law ``2 * lateral_offset / dist^2`` gives angular authority that falls
with the square of that distance. Q3 recorded this and deliberately stopped
short of calling it a cause, because the vertex rule and the speed law act
through the same heading-error term and cannot be separated by observation.

This class is the treatment arm that separates them. It overrides ``target`` and
nothing else, so every other behaviour -- the goal predicate, the speed law, the
curvature law, the clamps, the integration, the stop logic -- is inherited
unchanged from the frozen implementation. ``src/navfm/control.py`` is not
modified, which is what lets arm A run byte-identical code and lets the
preregistration pin it by hash.

Two semantics are fixed here deliberately, and both were fixed before the
treatment arm was ever run against Hospital:

**Past the end of the route the target is the final path point.** It is clamped,
never extrapolated. Arm B is defined as a point ON the polyline, and beyond the
final vertex there is no polyline; extrapolating would steer the base past the
goal it is approaching.

**The inherited vertex index is still advanced.** Arm B does not use ``_idx`` to
choose a target, but ``PurePursuit.finished`` reads it. Leaving it frozen would
introduce a second uncontrolled difference between the arms in a one-factor
experiment, so the inherited advance is called and its return value discarded.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..control import PurePursuit
from .route_projection import point_at_arclength, polyline_cumlength, project_to_polyline

__all__ = ["InterpolatedLookaheadPursuit"]


class InterpolatedLookaheadPursuit(PurePursuit):
    """Pure pursuit that steers at an arc-length interpolated look-ahead point.

    The manipulated factor, and the only one: target selection.
    """

    #: Recorded in evidence so an arm cannot be mislabelled after the fact.
    target_type = "ARC_LENGTH_INTERPOLATED"

    def __init__(self, path: np.ndarray, **kwargs: Any) -> None:
        super().__init__(path, **kwargs)
        self._cum = polyline_cumlength(self.path)

    def target(self, position: np.ndarray) -> np.ndarray:
        pos = np.asarray(position, dtype=np.float64)[:2]
        # Advance the inherited index exactly as the control arm would, so that
        # `finished` means the same thing in both arms. The returned vertex is
        # deliberately discarded: it is what this arm exists to replace.
        super().target(pos)
        proj = project_to_polyline(self.path, self._cum, pos)
        return point_at_arclength(self.path, self._cum, proj.s + self.lookahead)
