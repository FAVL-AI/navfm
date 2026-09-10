"""Analytic occupancy rasterisation, and the metrics that judge a probe against it.

`OBSTACLE_CELL_OCCUPANCY_V1` defines an occupied cell as one whose full
horizontal area, extruded through the frozen obstacle slab, intersects blocking
collision geometry. That definition is exactly computable for simple shapes, so
a physical probe can be judged against a known answer rather than against
another probe or against an aggregate.

Judging by aggregate is what let the previous builders through. A raycast probe
raised furniture occupancy from 0% to 76% while dropping a known wall from 12.5%
to 0%; the scene-wide numbers improved. So the comparison here is **set against
set**, and false negatives -- cells containing blocking geometry that the probe
reported free -- are reported separately and never folded into an average. For
obstacle rasterisation they are the safety-critical direction: a false positive
costs a route, a false negative costs a collision.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np

__all__ = [
    "AABB",
    "RasterComparison",
    "cell_bounds",
    "compare_cells",
    "expected_cells_for_box",
    "expected_cells_for_boxes",
]


@dataclasses.dataclass(frozen=True)
class AABB:
    """An axis-aligned box in world coordinates."""

    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def intersects_slab(self, z_lo: float, z_hi: float) -> bool:
        """Does the box's vertical extent overlap the obstacle slab?

        Uses strict inequalities, so a box that merely touches a slab face at a
        single height is not counted. Touching is a measure-zero contact and
        treating it as occupancy would mark cells blocked from geometry the
        robot passes cleanly under or over.
        """
        return self.min_z < z_hi and self.max_z > z_lo

    def to_dict(self) -> dict[str, float]:
        return dataclasses.asdict(self)


def cell_bounds(
    origin: tuple[float, float], resolution: float, row: int, col: int
) -> tuple[float, float, float, float]:
    """World-space ``(min_x, min_y, max_x, max_y)`` of one cell.

    ``origin`` is the world coordinate of the CENTRE of cell (0, 0), matching
    ``OccupancyGrid``. The cell therefore spans half a resolution either side of
    its centre; reading ``origin`` as a corner would shift every cell by half a
    cell and quietly misplace the whole map.
    """
    half = resolution / 2.0
    cx = origin[0] + col * resolution
    cy = origin[1] + row * resolution
    return cx - half, cy - half, cx + half, cy + half


def expected_cells_for_box(
    box: AABB,
    origin: tuple[float, float],
    resolution: float,
    shape: tuple[int, int],
    *,
    slab: tuple[float, float] = (0.10, 0.60),
    boundary_touch_counts: bool = False,
) -> set[tuple[int, int]]:
    """Cells whose volume intersects ``box`` within the slab, computed exactly.

    ``boundary_touch_counts`` decides the one genuinely ambiguous case: geometry
    lying exactly on a cell boundary. It is a parameter rather than a choice
    baked in, because the frozen estimand says the convention is settled by
    measurement against the physical probe and then recorded -- not assumed here
    and then asserted of the probe.
    """
    z_lo, z_hi = slab
    if not box.intersects_slab(z_lo, z_hi):
        return set()

    rows, cols = shape
    half = resolution / 2.0
    out: set[tuple[int, int]] = set()

    # Only the cells whose centres could possibly be within reach are examined,
    # which keeps this exact rather than approximate: the bound is derived, not
    # guessed.
    col_lo = int(math.floor((box.min_x - half - origin[0]) / resolution))
    col_hi = int(math.ceil((box.max_x + half - origin[0]) / resolution))
    row_lo = int(math.floor((box.min_y - half - origin[1]) / resolution))
    row_hi = int(math.ceil((box.max_y + half - origin[1]) / resolution))

    for row in range(max(0, row_lo), min(rows, row_hi + 1)):
        for col in range(max(0, col_lo), min(cols, col_hi + 1)):
            x0, y0, x1, y1 = cell_bounds(origin, resolution, row, col)
            if boundary_touch_counts:
                overlaps = (x0 <= box.max_x and x1 >= box.min_x
                            and y0 <= box.max_y and y1 >= box.min_y)
            else:
                overlaps = (x0 < box.max_x and x1 > box.min_x
                            and y0 < box.max_y and y1 > box.min_y)
            if overlaps:
                out.add((row, col))
    return out


def expected_cells_for_boxes(
    boxes: list[AABB],
    origin: tuple[float, float],
    resolution: float,
    shape: tuple[int, int],
    *,
    slab: tuple[float, float] = (0.10, 0.60),
    boundary_touch_counts: bool = False,
) -> set[tuple[int, int]]:
    """Union over several boxes -- a hollow wall is two thin boxes."""
    out: set[tuple[int, int]] = set()
    for box in boxes:
        out |= expected_cells_for_box(box, origin, resolution, shape, slab=slab,
                                      boundary_touch_counts=boundary_touch_counts)
    return out


@dataclasses.dataclass(frozen=True)
class RasterComparison:
    """Set-against-set comparison of a measured raster with the expected one."""

    expected: frozenset[tuple[int, int]]
    measured: frozenset[tuple[int, int]]

    @property
    def false_negatives(self) -> frozenset[tuple[int, int]]:
        """Blocking geometry the probe missed. The safety-critical direction."""
        return self.expected - self.measured

    @property
    def false_positives(self) -> frozenset[tuple[int, int]]:
        return self.measured - self.expected

    @property
    def true_positives(self) -> frozenset[tuple[int, int]]:
        return self.expected & self.measured

    @property
    def exact_agreement(self) -> bool:
        return self.expected == self.measured

    @property
    def recall(self) -> float | None:
        """None when nothing was expected -- 1.0 would claim a success not earned."""
        if not self.expected:
            return None
        return len(self.true_positives) / len(self.expected)

    @property
    def precision(self) -> float | None:
        if not self.measured:
            return None
        return len(self.true_positives) / len(self.measured)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_cells": len(self.expected),
            "measured_cells": len(self.measured),
            "true_positives": len(self.true_positives),
            "false_negatives": len(self.false_negatives),
            "false_positives": len(self.false_positives),
            "recall": self.recall,
            "precision": self.precision,
            "exact_agreement": self.exact_agreement,
            "false_negative_cells": sorted(self.false_negatives)[:32],
            "false_positive_cells": sorted(self.false_positives)[:32],
            "safety_note": (
                "false negatives are cells containing blocking geometry reported free. "
                "They require explicit adjudication and are never averaged away."),
        }


def compare_cells(
    expected: set[tuple[int, int]] | frozenset[tuple[int, int]],
    measured: set[tuple[int, int]] | frozenset[tuple[int, int]],
) -> RasterComparison:
    return RasterComparison(frozenset(expected), frozenset(measured))


def measured_cells_from_grid(grid: np.ndarray) -> set[tuple[int, int]]:
    """Occupied cells of a boolean raster, as a set of ``(row, col)``."""
    rows, cols = np.nonzero(np.asarray(grid, dtype=bool))
    return {(int(r), int(c)) for r, c in zip(rows, cols, strict=True)}
