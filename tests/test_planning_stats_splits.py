from __future__ import annotations

import numpy as np
import pytest

from navfm.planning import (
    OccupancyGrid,
    PlannerError,
    astar,
    perturb_path,
    sample_episode_pair,
    sample_free_pose,
    smooth_path,
)
from navfm.splits import scene_of, split_names, stable_fraction
from navfm.stats import estimate_action_stats, estimate_metric_waypoint_spacing
from navfm.writer import TrajectoryWriter


def corridor_grid(res: float = 0.1) -> OccupancyGrid:
    """A 6 m x 4 m room with a wall and a doorway -- forces a non-trivial plan."""
    h, w = int(4.0 / res), int(6.0 / res)
    grid = np.zeros((h, w), dtype=bool)
    grid[0, :] = grid[-1, :] = True
    grid[:, 0] = grid[:, -1] = True
    wall = w // 2
    grid[:, wall] = True
    door = slice(int(2.8 / res), int(3.4 / res))
    grid[door, wall] = False
    return OccupancyGrid(grid, res, origin=(0.0, 0.0))


# ------------------------------------------------------------------ planning


def test_astar_finds_the_doorway():
    grid = corridor_grid()
    path = astar(grid, (1.0, 1.0), (5.0, 1.0))
    assert path.shape[0] > 2
    # Must pass through the door band in y.
    ys_at_wall = path[np.abs(path[:, 0] - 3.0) < 0.15][:, 1]
    assert ys_at_wall.size > 0
    assert np.all((ys_at_wall > 2.6) & (ys_at_wall < 3.6))


def test_astar_rejects_occupied_endpoints():
    grid = corridor_grid()
    with pytest.raises(PlannerError):
        astar(grid, (0.0, 0.0), (5.0, 1.0))  # start on the wall
    with pytest.raises(PlannerError):
        astar(grid, (1.0, 1.0), (3.0, 0.5))  # goal inside the dividing wall


def test_astar_raises_rather_than_returning_empty():
    grid = OccupancyGrid(np.zeros((20, 20), dtype=bool), 0.1)
    grid.grid[10, :] = True  # full-width wall, no door
    with pytest.raises(PlannerError):
        astar(grid, (0.5, 0.5), (0.5, 1.5))


def test_astar_does_not_cut_corners_between_obstacles():
    grid = OccupancyGrid(np.zeros((5, 5), dtype=bool), 1.0)
    grid.grid[1, 2] = True
    grid.grid[2, 1] = True
    path = astar(grid, (1.0, 1.0), (2.0, 2.0))
    # A diagonal squeeze through (1,2)/(2,1) would be a 2-vertex path.
    assert path.shape[0] > 2


def test_inflate_grows_obstacles_by_the_footprint():
    grid = OccupancyGrid(np.zeros((21, 21), dtype=bool), 0.1)
    grid.grid[10, 10] = True
    inflated = grid.inflate(0.25)
    assert inflated.grid.sum() > grid.grid.sum()
    assert inflated.grid[10, 12]  # 0.2 m away -> inside the 0.25 m radius
    assert not inflated.grid[10, 14]  # 0.4 m away -> outside


def test_smooth_path_shortens_and_stays_free():
    grid = corridor_grid()
    raw = astar(grid, (1.0, 1.0), (5.0, 1.0))
    smooth = smooth_path(grid, raw)
    assert smooth.shape[0] <= raw.shape[0]
    length = lambda p: np.linalg.norm(np.diff(p, axis=0), axis=1).sum()  # noqa: E731
    assert length(smooth) <= length(raw) + 1e-9
    for i in range(smooth.shape[0] - 1):
        for t in np.linspace(0, 1, 25):
            assert grid.is_free(smooth[i] + t * (smooth[i + 1] - smooth[i]))


def test_sample_free_pose_respects_clearance():
    grid = corridor_grid()
    rng = np.random.default_rng(0)
    for _ in range(30):
        xy, yaw = sample_free_pose(grid, rng, min_clearance_m=0.3)
        assert grid.is_free(xy)
        assert -np.pi <= yaw <= np.pi


def test_sample_episode_pair_respects_length_bounds():
    grid = corridor_grid().inflate(0.2)
    rng = np.random.default_rng(1)
    start, _yaw, goal, path = sample_episode_pair(
        grid, rng, min_path_m=3.0, max_path_m=12.0, min_clearance_m=0.25
    )
    length = np.linalg.norm(np.diff(path, axis=0), axis=1).sum()
    assert 3.0 <= length <= 12.0
    assert grid.is_free(start) and grid.is_free(goal)


def test_perturb_path_keeps_endpoints_and_stays_free():
    grid = corridor_grid()
    rng = np.random.default_rng(2)
    path = smooth_path(grid, astar(grid, (1.0, 1.0), (5.0, 1.0)))
    from navfm.control import resample_path

    dense = resample_path(path, 0.1)
    noisy = perturb_path(dense, grid, rng, sigma=0.15)
    np.testing.assert_allclose(noisy[0], dense[0], atol=1e-9)
    np.testing.assert_allclose(noisy[-1], dense[-1], atol=1e-9)
    assert all(grid.is_free(p) for p in noisy)
    assert not np.allclose(noisy, dense)


# -------------------------------------------------------------------- splits


def test_stable_fraction_is_deterministic_and_uniform():
    a = stable_fraction("office_a")
    assert a == stable_fraction("office_a")
    assert 0.0 <= a < 1.0
    vals = np.array([stable_fraction(f"traj_{i}") for i in range(4000)])
    assert abs(vals.mean() - 0.5) < 0.02
    assert np.histogram(vals, bins=10, range=(0, 1))[0].std() < 60


def test_split_is_stable_under_reordering_and_growth():
    names = [f"scene{i % 4}_run_{i:04d}" for i in range(200)]
    tr1, te1 = split_names(names, split=0.8)
    tr2, te2 = split_names(list(reversed(names)), split=0.8)
    assert tr1 == tr2 and te1 == te2

    grown = names + [f"scene{i % 4}_run_{i:04d}" for i in range(200, 260)]
    tr3, te3 = split_names(grown, split=0.8)
    assert set(tr1).issubset(set(tr3))
    assert set(te1).issubset(set(te3))


def test_scene_grouping_prevents_leakage():
    names = [f"scene{s}_run_{i:04d}" for s in range(6) for i in range(20)]
    train, test = split_names(names, split=0.6, group_by=scene_of)
    train_scenes = {scene_of(n) for n in train}
    test_scenes = {scene_of(n) for n in test}
    assert train_scenes and test_scenes
    assert not (train_scenes & test_scenes)
    assert len(train) + len(test) == len(names)


@pytest.mark.parametrize("n_scenes", [2, 3, 4, 5, 8, 12])
@pytest.mark.parametrize("split", [0.5, 0.7, 0.8, 0.9])
@pytest.mark.parametrize("salt", ["", "a", "b"])
def test_grouped_split_always_yields_a_non_empty_test_set(n_scenes, split, salt):
    """The failure mode that a hash threshold has and ranking does not: with a
    handful of scenes, every one landing on the same side."""
    names = [f"scene{s}_run_{i:04d}" for s in range(n_scenes) for i in range(5)]
    train, test = split_names(names, split=split, salt=salt, group_by=scene_of)
    assert train and test
    assert not ({scene_of(n) for n in train} & {scene_of(n) for n in test})


def test_grouped_split_is_deterministic():
    names = [f"scene{s}_run_{i:04d}" for s in range(5) for i in range(4)]
    a = split_names(names, split=0.8, group_by=scene_of)
    b = split_names(list(reversed(names)), split=0.8, group_by=scene_of)
    assert a == b


def test_grouped_split_rejects_a_single_group():
    with pytest.raises(ValueError, match="at least 2 groups"):
        split_names(["only_run_0001", "only_run_0002"], group_by=scene_of)


def test_scene_of_parses_collector_names():
    assert scene_of("office_a_run_00012") == "office_a"
    assert scene_of("hospital_run_00001") == "hospital"
    assert scene_of("warehouse") == "warehouse"


# --------------------------------------------------------------------- stats


def _write_dataset(tmp_path, n_traj=6, n=40, step=0.2):
    rng = np.random.default_rng(0)
    for k in range(n_traj):
        pos = np.stack([np.arange(n) * step, np.zeros(n)], axis=1)
        pos[:, 1] += np.cumsum(rng.normal(0, 0.01, n))
        yaw = np.zeros(n)
        with TrajectoryWriter(tmp_path / f"scene{k % 2}_run_{k:05d}") as w:
            for i in range(n):
                w.append(np.zeros((8, 8, 3), dtype=np.uint8), pos[i], yaw[i])
    return tmp_path


def test_estimate_metric_waypoint_spacing_recovers_the_true_step(tmp_path):
    _write_dataset(tmp_path, step=0.2)
    out = estimate_metric_waypoint_spacing(tmp_path)
    assert out["metric_waypoint_spacing"] == pytest.approx(0.2, rel=0.05)
    assert out["n_trajectories"] == 6
    assert out["frac_stationary"] == pytest.approx(0.0, abs=0.01)


def test_estimate_action_stats_is_self_consistent(tmp_path):
    _write_dataset(tmp_path, step=0.2)
    spacing = estimate_metric_waypoint_spacing(tmp_path)["metric_waypoint_spacing"]
    stats = estimate_action_stats(
        tmp_path,
        len_traj_pred=8,
        context_size=3,
        metric_waypoint_spacing=spacing,
        stride=1,
    )
    # Forward motion of exactly one nominal step per frame -> dx delta ~ 1.0.
    assert stats["mean"][0] == pytest.approx(1.0, rel=0.1)
    assert abs(stats["mean"][1]) < 0.1
    assert stats["lateral_energy_ratio"] < 0.2
    # The published range comfortably contains a straight-line dataset.
    assert stats["frac_clipped_by_published"] == pytest.approx(0.0, abs=1e-6)
