"""Prospective start-pose perturbations along a route polyline.

A perturbed start places the robot at a fraction of the route's arc length,
offset sideways from the route and rotated away from the local route heading.
The route itself (and therefore the goal and every route-relative metric) is
unchanged; only the initial condition moves.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class StartPerturbation:
    arc_fraction: float = 0.0
    lateral_m: float = 0.0
    yaw_deg: float = 0.0

    def __post_init__(self):
        if not 0.0 <= self.arc_fraction < 1.0:
            raise ValueError("arc fraction must be in [0, 1)")
        if not (math.isfinite(self.lateral_m) and math.isfinite(self.yaw_deg)):
            raise ValueError("nonfinite perturbation")

    @property
    def is_identity(self) -> bool:
        return self.arc_fraction == 0.0 and self.lateral_m == 0.0 and self.yaw_deg == 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def perturbed_start(waypoints, p: StartPerturbation):
    """Return (start_xy, start_yaw, remaining_waypoints) for world-frame waypoints.

    Lateral offsets are positive to the left of the local route direction.
    remaining_waypoints starts at the perturbed start and continues with the
    route waypoints strictly after the start's arc position.
    """
    pts = np.asarray(waypoints, float)
    seg = np.diff(pts, axis=0)
    lengths = np.linalg.norm(seg, axis=1)
    if (lengths <= 0).any():
        raise ValueError("degenerate route segment")
    cumulative = np.concatenate([[0.0], np.cumsum(lengths)])
    s = p.arc_fraction * cumulative[-1]
    i = min(int(np.searchsorted(cumulative, s, side="right")) - 1, len(seg) - 1)
    direction = seg[i] / lengths[i]
    on_route = pts[i] + (s - cumulative[i]) * direction
    normal = np.array([-direction[1], direction[0]])
    start = on_route + p.lateral_m * normal
    yaw = math.atan2(direction[1], direction[0]) + math.radians(p.yaw_deg)
    remaining = np.vstack([start, pts[i + 1 :]])
    return start, yaw, remaining
