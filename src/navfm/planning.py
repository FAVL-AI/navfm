"""Occupancy-grid mapping and planning for the data-collection demonstrator.

Pure NumPy so it is unit-testable without Isaac Sim. The collector builds the
occupancy grid once per scene by ray-casting on the GPU, then plans every
episode against that grid.

Why a planner at all, rather than a random walk or scripted waypoints:

* GNM-family models learn ``d(o_t, o_g)`` -- a *temporal distance* -- and
  waypoints towards the goal. Both labels are only meaningful if the
  demonstrator is approximately optimal. A random walk produces trajectories
  whose temporal distance is unrelated to spatial proximity, which teaches the
  distance head noise.
* But a *purely* optimal demonstrator collapses the state distribution onto the
  shortest path and gives the policy no recovery behaviour. The reference
  datasets get recovery coverage for free from human teleoperation error.
  We recreate it deliberately with ``noise_sigma`` (goal-directed but perturbed)
  and a configurable fraction of frontier-style exploration episodes, which is
  the distribution NoMaD's unconditioned branch needs.
"""

from __future__ import annotations

import dataclasses
import heapq
import math
from collections.abc import Sequence
from typing import Union

import numpy as np

#: Anything indexable as ``(x, y)``: a tuple, a list, or a NumPy array.
Point = Union[Sequence[float], np.ndarray]  # noqa: UP007

__all__ = ["OccupancyGrid", "PlannerError", "astar", "sample_free_pose", "smooth_path"]


class PlannerError(RuntimeError):
    pass


@dataclasses.dataclass
class OccupancyGrid:
    """2-D occupancy grid in world coordinates.

    ``grid[row, col]`` is True where occupied. ``origin`` is the world
    coordinate of the centre of cell ``(0, 0)``.
    """

    grid: np.ndarray
    resolution: float
    origin: tuple[float, float] = (0.0, 0.0)

    def __post_init__(self) -> None:
        self.grid = np.asarray(self.grid, dtype=bool)
        if self.grid.ndim != 2:
            raise ValueError("grid must be 2-D")
        if self.resolution <= 0:
            raise ValueError("resolution must be positive")

    @property
    def shape(self) -> tuple[int, int]:
        return self.grid.shape  # type: ignore[return-value]

    def world_to_cell(self, xy: Point) -> tuple[int, int]:
        col = int(round((float(xy[0]) - self.origin[0]) / self.resolution))
        row = int(round((float(xy[1]) - self.origin[1]) / self.resolution))
        return row, col

    def cell_to_world(self, rc: Sequence[int] | np.ndarray) -> np.ndarray:
        return np.array(
            [
                self.origin[0] + float(rc[1]) * self.resolution,
                self.origin[1] + float(rc[0]) * self.resolution,
            ]
        )

    def in_bounds(self, rc: Sequence[int] | np.ndarray) -> bool:
        r, c = int(rc[0]), int(rc[1])
        return 0 <= r < self.grid.shape[0] and 0 <= c < self.grid.shape[1]

    def is_free(self, xy: Point) -> bool:
        rc = self.world_to_cell(xy)
        return self.in_bounds(rc) and not bool(self.grid[rc[0], rc[1]])

    def inflate(self, radius_m: float) -> OccupancyGrid:
        """Morphological dilation by ``radius_m`` -- the robot footprint.

        Planning on an inflated grid and then treating the robot as a point is
        both faster and safer than per-configuration collision checks, and it
        is what ROS costmaps do, so behaviour transfers to hardware.
        """
        r = math.ceil(radius_m / self.resolution)
        if r <= 0:
            return OccupancyGrid(self.grid.copy(), self.resolution, self.origin)
        yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
        disk = (xx * xx + yy * yy) <= r * r
        out = np.zeros_like(self.grid)
        rows, cols = np.nonzero(self.grid)
        h, w = self.grid.shape
        for dr, dc in zip(*np.nonzero(disk), strict=True):
            orow = rows + (dr - r)
            ocol = cols + (dc - r)
            m = (orow >= 0) & (orow < h) & (ocol >= 0) & (ocol < w)
            out[orow[m], ocol[m]] = True
        return OccupancyGrid(out, self.resolution, self.origin)

    def free_cells(self) -> np.ndarray:
        """``(N, 2)`` array of free ``(row, col)`` indices."""
        return np.stack(np.nonzero(~self.grid), axis=1)

    def clearance(self) -> np.ndarray:
        """Approximate distance (in cells) from each free cell to the nearest
        obstacle, via a two-pass chamfer transform. Used to bias goal sampling
        away from walls, which otherwise dominates because most free cells in a
        cluttered scene are near something."""
        h, w = self.grid.shape
        big = float(h + w)
        dist = np.where(self.grid, 0.0, big)
        for i in range(h):
            for j in range(w):
                v = dist[i, j]
                if i > 0:
                    v = min(v, dist[i - 1, j] + 1.0)
                if j > 0:
                    v = min(v, dist[i, j - 1] + 1.0)
                if i > 0 and j > 0:
                    v = min(v, dist[i - 1, j - 1] + math.sqrt(2))
                dist[i, j] = v
        for i in range(h - 1, -1, -1):
            for j in range(w - 1, -1, -1):
                v = dist[i, j]
                if i + 1 < h:
                    v = min(v, dist[i + 1, j] + 1.0)
                if j + 1 < w:
                    v = min(v, dist[i, j + 1] + 1.0)
                if i + 1 < h and j + 1 < w:
                    v = min(v, dist[i + 1, j + 1] + math.sqrt(2))
                dist[i, j] = v
        return dist


_NEIGHBOURS = [
    (-1, 0, 1.0),
    (1, 0, 1.0),
    (0, -1, 1.0),
    (0, 1, 1.0),
    (-1, -1, math.sqrt(2)),
    (-1, 1, math.sqrt(2)),
    (1, -1, math.sqrt(2)),
    (1, 1, math.sqrt(2)),
]


def astar(
    grid: OccupancyGrid,
    start_xy: Point,
    goal_xy: Point,
    *,
    max_expansions: int = 2_000_000,
) -> np.ndarray:
    """8-connected A* with an octile heuristic. Returns an ``(N, 2)`` world path.

    Raises :class:`PlannerError` rather than returning an empty path, because a
    silently-empty path in a data collector produces a zero-length trajectory
    that passes every format check and poisons the action statistics.
    """
    start = grid.world_to_cell(start_xy)
    goal = grid.world_to_cell(goal_xy)
    if not grid.in_bounds(start) or grid.grid[start]:
        raise PlannerError(f"start {tuple(start_xy)} is out of bounds or occupied")
    if not grid.in_bounds(goal) or grid.grid[goal]:
        raise PlannerError(f"goal {tuple(goal_xy)} is out of bounds or occupied")
    if start == goal:
        return np.asarray([grid.cell_to_world(start)], dtype=np.float64)

    def h(rc: tuple[int, int]) -> float:
        dr = abs(rc[0] - goal[0])
        dc = abs(rc[1] - goal[1])
        return (dr + dc) + (math.sqrt(2) - 2.0) * min(dr, dc)

    open_heap: list[tuple[float, tuple[int, int]]] = [(h(start), start)]
    came: dict[tuple[int, int], tuple[int, int]] = {}
    gscore: dict[tuple[int, int], float] = {start: 0.0}
    closed: set[tuple[int, int]] = set()
    occ = grid.grid
    height, width = occ.shape
    expansions = 0

    while open_heap:
        _f, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            break
        closed.add(current)
        expansions += 1
        if expansions > max_expansions:
            raise PlannerError("A* exceeded the expansion budget")
        cr, cc = current
        for dr, dc, cost in _NEIGHBOURS:
            nr, nc = cr + dr, cc + dc
            if not (0 <= nr < height and 0 <= nc < width) or occ[nr, nc]:
                continue
            if dr and dc and (occ[cr + dr, cc] or occ[cr, cc + dc]):
                continue  # no corner cutting between two obstacles
            tentative = gscore[current] + cost
            nb = (nr, nc)
            if tentative < gscore.get(nb, math.inf):
                gscore[nb] = tentative
                came[nb] = current
                heapq.heappush(open_heap, (tentative + h(nb), nb))
    else:
        raise PlannerError("no path found")

    path_cells = [goal]
    node = goal
    while node != start:
        node = came[node]
        path_cells.append(node)
    path_cells.reverse()
    return np.asarray([grid.cell_to_world(rc) for rc in path_cells], dtype=np.float64)


def _line_is_free(grid: OccupancyGrid, a: np.ndarray, b: np.ndarray) -> bool:
    n = max(2, int(np.linalg.norm(b - a) / (0.5 * grid.resolution)) + 1)
    return all(grid.is_free(a + t * (b - a)) for t in np.linspace(0.0, 1.0, n))


def smooth_path(grid: OccupancyGrid, path: np.ndarray, *, max_passes: int = 4) -> np.ndarray:
    """String-pulling: drop intermediate vertices whose bypass stays collision free.

    A* on an 8-connected grid produces staircase artefacts at 22.5-degree
    increments. Recorded as demonstrations these become periodic yaw oscillation
    that the model dutifully learns to imitate. Smoothing removes it.
    """
    path = np.asarray(path, dtype=np.float64).reshape(-1, 2)
    if path.shape[0] <= 2:
        return path
    for _ in range(max_passes):
        out = [path[0]]
        i = 0
        while i < path.shape[0] - 1:
            j = path.shape[0] - 1
            while j > i + 1 and not _line_is_free(grid, path[i], path[j]):
                j -= 1
            out.append(path[j])
            i = j
        new = np.asarray(out)
        if new.shape[0] == path.shape[0]:
            break
        path = new
    return path


def sample_free_pose(
    grid: OccupancyGrid,
    rng: np.random.Generator,
    *,
    min_clearance_m: float = 0.35,
    clearance_map: np.ndarray | None = None,
    max_tries: int = 2000,
) -> tuple[np.ndarray, float]:
    """Sample a collision-free ``((x, y), yaw)`` with at least ``min_clearance_m``."""
    if clearance_map is None:
        clearance_map = grid.clearance()
    min_cells = min_clearance_m / grid.resolution
    candidates = np.stack(np.nonzero((~grid.grid) & (clearance_map >= min_cells)), axis=1)
    if candidates.shape[0] == 0:
        raise PlannerError(
            f"no free cell has clearance >= {min_clearance_m} m; "
            "the scene is too cluttered or the inflation radius is too large"
        )
    idx = int(rng.integers(candidates.shape[0]))
    rc = candidates[idx]
    xy = grid.cell_to_world(rc)
    # Jitter within the cell so poses are not quantised to the grid.
    xy = xy + rng.uniform(-0.5, 0.5, size=2) * grid.resolution
    if not grid.is_free(xy):
        xy = grid.cell_to_world(rc)
    return xy, float(rng.uniform(-math.pi, math.pi))


def sample_episode_pair(
    grid: OccupancyGrid,
    rng: np.random.Generator,
    *,
    min_path_m: float = 3.0,
    max_path_m: float = 40.0,
    min_clearance_m: float = 0.35,
    clearance_map: np.ndarray | None = None,
    max_tries: int = 60,
) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    """Sample ``(start_xy, start_yaw, goal_xy, path)`` with a length in range.

    Bounding path length matters: episodes shorter than ``context_size +
    len_traj_pred`` frames contribute zero training samples, and very long ones
    dominate the sampler because the index is per-timestep.
    """
    if clearance_map is None:
        clearance_map = grid.clearance()
    for _ in range(max_tries):
        start, yaw = sample_free_pose(
            grid, rng, min_clearance_m=min_clearance_m, clearance_map=clearance_map
        )
        goal, _ = sample_free_pose(
            grid, rng, min_clearance_m=min_clearance_m, clearance_map=clearance_map
        )
        if np.linalg.norm(goal - start) < min_path_m * 0.5:
            continue
        try:
            path = smooth_path(grid, astar(grid, start, goal))
        except PlannerError:
            continue
        length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
        if min_path_m <= length <= max_path_m:
            # Face roughly along the path so the first frames are informative.
            direction = path[min(3, path.shape[0] - 1)] - path[0]
            if np.linalg.norm(direction) > 1e-6:
                yaw = float(math.atan2(direction[1], direction[0]))
            return start, yaw, goal, path
    raise PlannerError(
        f"could not sample a path of length in [{min_path_m}, {max_path_m}] m "
        f"after {max_tries} tries"
    )


def perturb_path(
    path: np.ndarray,
    grid: OccupancyGrid,
    rng: np.random.Generator,
    *,
    sigma: float = 0.25,
    correlation: int = 6,
) -> np.ndarray:
    """Add smooth lateral noise to a path, keeping every vertex collision free.

    Injects the recovery behaviour that a purely optimal demonstrator lacks.
    The noise is temporally correlated (a moving average of white noise) so it
    produces sustained lateral offsets the policy must correct, rather than
    per-step jitter that just adds label noise.
    """
    path = np.asarray(path, dtype=np.float64).reshape(-1, 2)
    if path.shape[0] < 3 or sigma <= 0:
        return path
    tangents = np.gradient(path, axis=0)
    norms = np.linalg.norm(tangents, axis=1, keepdims=True)
    tangents = tangents / np.maximum(norms, 1e-9)
    normals = np.stack([-tangents[:, 1], tangents[:, 0]], axis=1)

    white = rng.normal(0.0, 1.0, size=path.shape[0])
    kernel = np.ones(correlation) / correlation
    smooth = np.convolve(white, kernel, mode="same")
    smooth[0] = smooth[-1] = 0.0  # keep endpoints exact
    offsets = sigma * smooth[:, None] * normals

    out = path + offsets
    for i in range(out.shape[0]):
        if not grid.is_free(out[i]):
            out[i] = path[i]
    return out
