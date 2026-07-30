"""Action-pipeline tests.

The single most important test in this file is
``test_compute_actions_matches_reference_semantics``: if our labels do not agree
with what the upstream trainer computes, every downstream number is wrong in a
way no amount of GPU time will reveal.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from navfm.control import (
    M3PRO_LIMITS,
    BaseKinematics,
    BaseLimits,
    DemonstratorMode,
    PDConfig,
    PurePursuit,
    holonomic_step,
    reference_pd_twist,
    resample_path,
    unicycle_step,
    waypoint_to_twist,
)
from navfm.kinematics import (
    arc_length,
    compute_actions,
    mean_step_distance,
    to_local_coords,
    unwrap_yaw,
    yaw_from_quat_wxyz,
    yaw_rotmat,
)

# ------------------------------------------------------------------ SE(2)


def test_to_local_coords_is_a_rotation_into_the_body_frame():
    # Robot at (1, 1) facing +y. A point one metre ahead of it in the world is
    # (1, 2); in the body frame that must be (1, 0) -- one metre forward.
    out = to_local_coords(np.array([[1.0, 2.0]]), np.array([1.0, 1.0]), math.pi / 2)
    np.testing.assert_allclose(out[0], [1.0, 0.0], atol=1e-12)

    # A point one metre to the robot's left is (0, 1) in the world -> (0, 1) body.
    out = to_local_coords(np.array([[0.0, 1.0]]), np.array([1.0, 1.0]), math.pi / 2)
    np.testing.assert_allclose(out[0], [0.0, 1.0], atol=1e-12)


def test_to_local_coords_preserves_distance():
    rng = np.random.default_rng(0)
    pts = rng.normal(size=(50, 2))
    origin = rng.normal(size=2)
    yaw = 1.234
    local = to_local_coords(pts, origin, yaw)
    np.testing.assert_allclose(
        np.linalg.norm(pts - origin, axis=1), np.linalg.norm(local, axis=1), atol=1e-12
    )


def test_yaw_rotmat_is_orthonormal():
    for yaw in np.linspace(-np.pi, np.pi, 11):
        R = yaw_rotmat(yaw)
        np.testing.assert_allclose(R @ R.T, np.eye(2), atol=1e-12)
        assert np.isclose(np.linalg.det(R), 1.0)


def test_yaw_from_quat_wxyz_roundtrip():
    yaws = np.linspace(-np.pi + 1e-6, np.pi - 1e-6, 17)
    quats = np.stack([np.cos(yaws / 2), np.zeros_like(yaws), np.zeros_like(yaws), np.sin(yaws / 2)], axis=1)
    np.testing.assert_allclose(yaw_from_quat_wxyz(quats), yaws, atol=1e-10)
    assert np.isscalar(float(yaw_from_quat_wxyz(quats[0])))


def test_unwrap_yaw_removes_branch_cuts():
    true = np.linspace(0.0, 6 * np.pi, 200)
    wrapped = np.arctan2(np.sin(true), np.cos(true))
    recovered = unwrap_yaw(wrapped)
    np.testing.assert_allclose(recovered - recovered[0], true - true[0], atol=1e-9)


# ------------------------------------------------------------ action labels


def test_compute_actions_matches_reference_semantics():
    # Straight line along +x at 0.25 m per frame, heading fixed at 0.
    n = 20
    pos = np.stack([np.arange(n) * 0.25, np.zeros(n)], axis=1)
    yaw = np.zeros(n)

    actions = compute_actions(
        pos, yaw, 5, len_traj_pred=5, metric_waypoint_spacing=0.25, learn_angle=True
    )
    assert actions.shape == (5, 3)
    # Normalised by 0.25 m -> one nominal step per frame.
    np.testing.assert_allclose(actions[:, 0], [1, 2, 3, 4, 5], atol=1e-12)
    np.testing.assert_allclose(actions[:, 1], 0.0, atol=1e-12)
    np.testing.assert_allclose(actions[:, 2], 0.0, atol=1e-12)


def test_compute_actions_yaw_column_is_not_normalised():
    n = 20
    pos = np.stack([np.arange(n) * 0.5, np.zeros(n)], axis=1)
    yaw = np.arange(n) * 0.1
    a = compute_actions(pos, yaw, 5, len_traj_pred=5, metric_waypoint_spacing=0.5, learn_angle=True)
    # Upstream divides only columns 0 and 1; yaw stays in raw radians.
    np.testing.assert_allclose(a[:, 2], [0.1, 0.2, 0.3, 0.4, 0.5], atol=1e-12)


def test_compute_actions_right_pads_by_repeating_the_last_element():
    n = 12
    pos = np.stack([np.arange(n) * 0.1, np.zeros(n)], axis=1)
    yaw = np.zeros(n)
    a = compute_actions(pos, yaw, 9, len_traj_pred=5, metric_waypoint_spacing=0.1, learn_angle=False)
    assert a.shape == (5, 2)
    # Positions 10, 11 exist; the remaining three repeat index 11.
    np.testing.assert_allclose(a[2:, 0], a[2, 0], atol=1e-12)


def test_compute_actions_respects_waypoint_spacing():
    n = 40
    pos = np.stack([np.arange(n) * 0.1, np.zeros(n)], axis=1)
    yaw = np.zeros(n)
    a = compute_actions(
        pos, yaw, 10, len_traj_pred=5, waypoint_spacing=3, metric_waypoint_spacing=0.1,
        learn_angle=False,
    )
    # Divisor is metric_waypoint_spacing * waypoint_spacing = 0.3, and the raw
    # displacements are 0.3, 0.6, ... so the normalised values are 1, 2, ...
    np.testing.assert_allclose(a[:, 0], [1, 2, 3, 4, 5], atol=1e-12)


def test_compute_actions_is_frame_invariant():
    """A rigid transform of the whole trajectory must not change the labels."""
    rng = np.random.default_rng(3)
    n = 25
    pos = np.cumsum(rng.normal(0, 0.1, size=(n, 2)), axis=0)
    yaw = np.cumsum(rng.normal(0, 0.05, size=n))

    a = compute_actions(pos, yaw, 8, len_traj_pred=5, metric_waypoint_spacing=0.2)

    theta, shift = 0.7, np.array([3.0, -2.0])
    R = yaw_rotmat(theta)
    pos2 = pos @ R.T + shift
    yaw2 = yaw + theta
    b = compute_actions(pos2, yaw2, 8, len_traj_pred=5, metric_waypoint_spacing=0.2)
    np.testing.assert_allclose(a, b, atol=1e-10)


def test_mean_step_distance_and_arc_length():
    pos = np.stack([np.arange(11) * 0.3, np.zeros(11)], axis=1)
    assert mean_step_distance(pos) == pytest.approx(0.3)
    assert arc_length(pos) == pytest.approx(3.0)
    assert mean_step_distance(pos[:1]) == 0.0


# --------------------------------------------------------------- controllers


def test_reference_pd_twist_matches_upstream_formula():
    limits = BaseLimits(max_v=0.2, max_w=0.4)
    cfg = PDConfig(dt=0.25)
    v, w = reference_pd_twist([0.04, 0.0], limits, cfg)
    assert v == pytest.approx(0.16)
    assert w == pytest.approx(0.0)

    # dx == 0 -> the degenerate spin branch, then saturated by max_w.
    v, w = reference_pd_twist([0.0, 0.01], limits, cfg)
    assert v == 0.0
    assert w == pytest.approx(0.4)

    # Velocity is clipped to [0, max_v] -- upstream never commands reverse.
    v, _ = reference_pd_twist([-1.0, 0.0], limits, cfg)
    assert v == 0.0


def test_holonomic_tracking_uses_lateral_velocity_where_differential_cannot():
    cfg = PDConfig(dt=0.25)
    wp = [0.0, 0.05]  # purely lateral
    _vx_d, vy_d, w_d = waypoint_to_twist(wp, M3PRO_LIMITS, cfg, BaseKinematics.DIFFERENTIAL)
    _vx_h, vy_h, _w_h = waypoint_to_twist(wp, M3PRO_LIMITS, cfg, BaseKinematics.HOLONOMIC)
    assert vy_d == 0.0 and abs(w_d) > 0.0  # must rotate to make progress
    assert vy_h > 0.0  # can strafe


def test_limits_clamp_is_symmetric_and_disables_lateral_for_diff_drive():
    diff = BaseLimits(max_v=0.5, max_w=1.0, max_vy=0.0)
    assert diff.clamp(10.0, 10.0, 10.0) == (0.5, 0.0, 1.0)
    assert diff.clamp(-10.0, -10.0, -10.0) == (-0.5, 0.0, -1.0)


def test_unicycle_step_traces_an_exact_circle():
    pos = np.zeros(2)
    yaw = 0.0
    steps = 1000
    v, w = 1.0, 1.0  # radius 1 m
    dt = 2 * math.pi / (w * steps)  # exactly one revolution
    for _ in range(steps):
        pos, yaw = unicycle_step(pos, yaw, v, w, dt)
    np.testing.assert_allclose(pos, [0.0, 0.0], atol=1e-9)
    assert math.isclose(yaw, 2 * math.pi, abs_tol=1e-9)


def test_holonomic_step_strafes_without_rotating():
    pos, yaw = holonomic_step(np.zeros(2), 0.0, 0.0, 1.0, 0.0, 0.5)
    np.testing.assert_allclose(pos, [0.0, 0.5], atol=1e-12)
    assert yaw == 0.0


def test_pure_pursuit_reaches_the_goal_in_closed_loop():
    path = resample_path(np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 3.0]]), 0.2)
    tracker = PurePursuit(path, limits=M3PRO_LIMITS, mode=DemonstratorMode.NONHOLONOMIC,
                          cruise_v=0.4, goal_tol=0.25)
    pos, yaw, dt = np.zeros(2), 0.0, 1 / 12
    for _ in range(4000):
        vx, _vy, wz, done = tracker.step(pos, yaw)
        if done:
            break
        pos, yaw = unicycle_step(pos, yaw, vx, wz, dt)
    assert done, "nonholonomic pure pursuit failed to converge"
    assert np.linalg.norm(pos - path[-1]) < 0.3


def test_pure_pursuit_holonomic_reaches_the_goal_too():
    path = resample_path(np.array([[0.0, 0.0], [0.0, 3.0], [3.0, 3.0]]), 0.2)
    tracker = PurePursuit(path, limits=M3PRO_LIMITS, mode=DemonstratorMode.HOLONOMIC,
                          cruise_v=0.35, goal_tol=0.25)
    pos, yaw, dt = np.zeros(2), 0.0, 1 / 12
    for _ in range(4000):
        vx, vy, wz, done = tracker.step(pos, yaw)
        if done:
            break
        pos, yaw = holonomic_step(pos, yaw, vx, vy, wz, dt)
    assert done
    assert np.linalg.norm(pos - path[-1]) < 0.3


def test_resample_path_gives_uniform_spacing():
    path = resample_path(np.array([[0.0, 0.0], [10.0, 0.0]]), 0.25)
    steps = np.linalg.norm(np.diff(path, axis=0), axis=1)
    assert np.allclose(steps, steps[0], atol=1e-9)
    assert steps[0] == pytest.approx(0.25, rel=0.05)
