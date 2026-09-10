"""Three clearances that are not the same quantity, declared before comparison.

The original F-G5 disagreement was reported as "the planner says 0.4 m, PhysX
says 0.0003 m", which invites the reading that one instrument is broken. Part of
that gap was a real defect. Part of it was never a disagreement at all, because
the two numbers answer different questions and were compared as though they
answered the same one.

So the three quantities are defined here first, with their frames, units, sign
conventions and footprint treatment, and only then compared.

``ANALYTIC_CLEARANCE``
    Geometric surface-to-surface distance between the robot footprint boundary
    and the obstacle surface, for a robot centred at a given point. Continuous,
    exact, no grid. Negative means penetration. This is ground truth.

``PLANNER_CLEARANCE``
    What the rasterised-and-inflated occupancy representation implies. It is a
    distance from the robot CENTRE to the nearest INFLATED-occupied cell, in
    cells scaled by resolution. It is quantised to the grid, and the inflation
    has already subtracted a footprint radius, so it is not comparable to a
    surface-to-surface distance without adding that radius back.

``PHYSX_CLEARANCE``
    What the scene query measures: centre-to-surface distance from the query
    point to the nearest collider, ignoring the footprint entirely. To compare
    with the analytic quantity the footprint radius must be subtracted.

The reconciliation is therefore not "do the numbers match" but "do they match
after each is converted to the same estimand". A comparison that skips the
conversion will always find a discrepancy of roughly one footprint radius plus
one inflation radius, and will always blame the wrong thing.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np

__all__ = [
    "ClearanceComparison",
    "ClearanceEstimands",
    "analytic_clearance_to_box",
    "expected_inflated_cells",
    "physx_clearance_to_surface",
    "planner_clearance_to_surface",
]


@dataclasses.dataclass(frozen=True)
class ClearanceEstimands:
    """The declared semantics. Frozen before any number is compared."""

    frame: str = "world, metres, right-handed, z up"
    analytic: str = ("surface-to-surface: distance from the robot footprint boundary to "
                     "the obstacle surface, robot centred at the query point. "
                     "Negative = penetration. Continuous, no grid.")
    planner: str = ("centre-to-inflated-cell: chamfer distance in CELLS from the robot "
                    "centre to the nearest inflated-occupied cell, multiplied by "
                    "resolution. Quantised to the grid. Inflation has already removed a "
                    "footprint radius.")
    physx: str = ("centre-to-surface: distance from the query point to the nearest "
                  "collider surface. Ignores the footprint entirely. Always >= 0.")
    conversion_to_analytic: str = (
        "analytic ~= physx - footprint_radius; "
        "analytic ~= planner + inflation_radius - footprint_radius, "
        "up to grid quantisation of +/- resolution")
    footprint_treatment: str = "disc of footprint_radius about the robot centre"
    sign_convention: str = "analytic may be negative; planner and physx are non-negative"
    discretisation: str = "planner values are multiples of resolution; comparisons carry +/- resolution"

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def analytic_clearance_to_box(
    centre: tuple[float, float],
    box: tuple[float, float, float, float],
    footprint_radius_m: float,
) -> float:
    """Exact surface-to-surface clearance from a disc robot to an axis-aligned box.

    ``box`` is ``(min_x, min_y, max_x, max_y)``. Negative when the footprint
    overlaps the box.
    """
    cx, cy = centre
    min_x, min_y, max_x, max_y = box
    dx = max(min_x - cx, 0.0, cx - max_x)
    dy = max(min_y - cy, 0.0, cy - max_y)
    if dx == 0.0 and dy == 0.0:
        # Centre inside the box: penetration depth to the nearest face.
        inward = min(cx - min_x, max_x - cx, cy - min_y, max_y - cy)
        return -(inward + footprint_radius_m)
    return math.hypot(dx, dy) - footprint_radius_m


def physx_clearance_to_surface(centre_to_surface_m: float, footprint_radius_m: float) -> float:
    """Convert a PhysX centre-to-surface reading to the analytic estimand."""
    return centre_to_surface_m - footprint_radius_m


def planner_clearance_to_surface(
    planner_cells: float,
    resolution_m: float,
    inflation_radius_m: float,
    footprint_radius_m: float,
) -> float:
    """Convert a planner chamfer reading, in cells, to the analytic estimand.

    The inflation radius is added back because the inflated grid has already
    consumed it, and the footprint radius is then removed because the analytic
    quantity is surface-to-surface. Skipping either step is what makes the
    planner look like it disagrees with PhysX by roughly half a metre.
    """
    return planner_cells * resolution_m + inflation_radius_m - footprint_radius_m


def expected_inflated_cells(
    occupied: set[tuple[int, int]],
    inflation_radius_m: float,
    resolution_m: float,
    shape: tuple[int, int],
) -> set[tuple[int, int]]:
    """Cells forbidden after dilating ``occupied`` by the inflation radius.

    Mirrors ``OccupancyGrid.inflate``: the radius is converted to whole cells
    with ``ceil`` and the structuring element is the discrete disc of that
    radius. Written independently so a defect in either implementation shows up
    as a disagreement rather than being reproduced identically in both.
    """
    r = math.ceil(inflation_radius_m / resolution_m)
    if r <= 0:
        return set(occupied)
    rows, cols = shape
    out: set[tuple[int, int]] = set()
    offsets = [(dr, dc) for dr in range(-r, r + 1) for dc in range(-r, r + 1)
               if dr * dr + dc * dc <= r * r]
    for (row, col) in occupied:
        for dr, dc in offsets:
            nr, nc = row + dr, col + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                out.add((nr, nc))
    return out


@dataclasses.dataclass(frozen=True)
class ClearanceComparison:
    """One geometry, all three quantities, converted to a common estimand."""

    label: str
    analytic_m: float
    planner_raw_cells: float
    planner_converted_m: float
    physx_raw_m: float
    physx_converted_m: float
    resolution_m: float

    @property
    def physx_agrees(self) -> bool:
        """PhysX is continuous, so it should match analytic closely."""
        return abs(self.physx_converted_m - self.analytic_m) <= 1e-6

    @property
    def planner_agrees(self) -> bool:
        """The planner is quantised, so it is allowed one resolution of slack."""
        return abs(self.planner_converted_m - self.analytic_m) <= self.resolution_m + 1e-9

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "analytic_m": self.analytic_m,
            "planner_raw_cells": self.planner_raw_cells,
            "planner_converted_m": self.planner_converted_m,
            "physx_raw_m": self.physx_raw_m,
            "physx_converted_m": self.physx_converted_m,
            "physx_agrees_with_analytic": self.physx_agrees,
            "planner_agrees_within_one_cell": self.planner_agrees,
            "tolerance_m": {"physx": 1e-6, "planner": self.resolution_m},
        }


def chamfer_distance_cells(blocked: np.ndarray, cell: tuple[int, int]) -> float:
    """Euclidean distance in cells from ``cell`` to the nearest blocked cell."""
    rows, cols = np.nonzero(np.asarray(blocked, dtype=bool))
    if rows.size == 0:
        return float("inf")
    return float(np.min(np.hypot(rows - cell[0], cols - cell[1])))
