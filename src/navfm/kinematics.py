"""SE(2) utilities, reimplemented to bit-match the reference training pipeline.

Everything here is a deliberate mirror of
``vint_train/data/data_utils.py`` and ``ViNT_Dataset._compute_actions``. It
exists so that (a) we can unit-test the action pipeline without importing the
upstream package, and (b) the Isaac Sim collector can assert that the labels it
would produce agree with what the trainer will compute.

Frame conventions, stated once:

* World frame is right-handed, ``+z`` up. ``position`` is ``(x, y)`` in metres.
* ``yaw`` is counter-clockwise from ``+x``, in radians, **unwrapped** (see
  :mod:`navfm.schema`).
* The robot's body frame has ``+x`` forward and ``+y`` left. Local-frame
  waypoints therefore read as "forward, left".
* Isaac Sim returns quaternions in ``wxyz`` order. :func:`yaw_from_quat_wxyz`
  is the only place that convention is consumed.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "arc_length",
    "compute_actions",
    "mean_step_distance",
    "to_local_coords",
    "unwrap_yaw",
    "yaw_from_quat_wxyz",
    "yaw_rotmat",
]


def yaw_rotmat(yaw: float | np.ndarray) -> np.ndarray:
    """2x2 rotation matrix, matching ``data_utils.yaw_rotmat`` (upper-left block).

    The upstream helper returns a 3x3 matrix and callers slice ``[:2, :2]``.
    """
    c, s = np.cos(yaw), np.sin(yaw)
    return np.array([[c, -s], [s, c]], dtype=np.float64)


def to_local_coords(positions: np.ndarray, curr_pos: np.ndarray, curr_yaw: float) -> np.ndarray:
    """Express world-frame positions in the body frame at ``(curr_pos, curr_yaw)``.

    Upstream writes ``(positions - curr_pos).dot(yaw_rotmat(curr_yaw)[:2, :2])``.
    With row-vector convention that is ``R(yaw)^T (p - p0)``, i.e. a rotation
    *into* the body frame -- correct, but easy to misread as its inverse. We
    reproduce it exactly rather than "fixing" it.
    """
    positions = np.asarray(positions, dtype=np.float64)
    curr_pos = np.asarray(curr_pos, dtype=np.float64)
    rotmat = yaw_rotmat(curr_yaw)
    return (positions - curr_pos).dot(rotmat)


def unwrap_yaw(yaw: np.ndarray) -> np.ndarray:
    """Remove +/-pi branch cuts so that consecutive differences stay small.

    Required by the GNM format (see :mod:`navfm.schema`). ``np.unwrap`` with the
    default period of ``2*pi`` is exactly the right operation; this wrapper
    exists to make the intent greppable and to guarantee float64 output.
    """
    return np.unwrap(np.asarray(yaw, dtype=np.float64))


def yaw_from_quat_wxyz(quat: np.ndarray) -> np.ndarray:
    """Extract planar yaw from ``wxyz`` quaternions (Isaac Sim's convention).

    Accepts shape ``(4,)`` or ``(N, 4)``. Returns a scalar array or ``(N,)``.
    Uses the standard ZYX-Tait-Bryan yaw term, which is well-conditioned for the
    near-planar motion of a ground robot.
    """
    q = np.asarray(quat, dtype=np.float64)
    single = q.ndim == 1
    q = np.atleast_2d(q)
    if q.shape[-1] != 4:
        raise ValueError(f"expected quaternions of shape (..., 4), got {q.shape}")
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = np.arctan2(siny_cosp, cosy_cosp)
    return yaw[0] if single else yaw


def compute_actions(
    position: np.ndarray,
    yaw: np.ndarray,
    curr_time: int,
    *,
    len_traj_pred: int,
    waypoint_spacing: int = 1,
    metric_waypoint_spacing: float = 1.0,
    learn_angle: bool = True,
    normalize: bool = True,
) -> np.ndarray:
    """Reference-exact reimplementation of ``ViNT_Dataset._compute_actions``.

    Returns ``(len_traj_pred, 3)`` when ``learn_angle`` (columns
    ``dx, dy, dyaw``) else ``(len_traj_pred, 2)``. The trainer later expands the
    yaw column into ``(cos, sin)`` via ``calculate_sin_cos``.

    Reproduces two upstream behaviours that matter and are easy to miss:

    * short slices are right-padded by *repeating the final element*, not by
      zero-filling or truncating;
    * only the ``x, y`` columns are divided by
      ``metric_waypoint_spacing * waypoint_spacing``. The yaw column is left in
      raw radians.
    """
    position = np.asarray(position, dtype=np.float64)
    yaw = np.asarray(yaw, dtype=np.float64)
    if yaw.ndim == 2 and yaw.shape[1] == 1:
        yaw = yaw[:, 0]

    start = curr_time
    end = curr_time + len_traj_pred * waypoint_spacing + 1
    yaw_slice = yaw[start:end:waypoint_spacing]
    pos_slice = position[start:end:waypoint_spacing]

    want = len_traj_pred + 1
    if yaw_slice.shape[0] < want:
        pad = want - yaw_slice.shape[0]
        if yaw_slice.shape[0] == 0:
            raise IndexError(f"curr_time={curr_time} is past the end of the trajectory")
        yaw_slice = np.concatenate([yaw_slice, np.repeat(yaw_slice[-1], pad)])
        pos_slice = np.concatenate([pos_slice, np.repeat(pos_slice[-1][None], pad, axis=0)], axis=0)

    waypoints = to_local_coords(pos_slice, pos_slice[0], yaw_slice[0])

    if learn_angle:
        dyaw = yaw_slice[1:] - yaw_slice[0]
        actions = np.concatenate([waypoints[1:], dyaw[:, None]], axis=-1)
    else:
        actions = waypoints[1:]

    if normalize:
        actions = actions.copy()
        actions[:, :2] /= metric_waypoint_spacing * waypoint_spacing

    return actions


def mean_step_distance(position: np.ndarray) -> float:
    """Mean Euclidean distance between consecutive frames, in metres.

    This is the estimator for ``metric_waypoint_spacing``. Upstream never
    published how the published constants were derived (see issues #45, #64,
    #67 on the reference repo); the mean inter-frame displacement is the only
    definition consistent with how the constant is *used* -- as the divisor that
    maps one recorded step to a normalised displacement of 1.0.
    """
    position = np.asarray(position, dtype=np.float64)
    if position.shape[0] < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(position, axis=0), axis=1).mean())


def arc_length(position: np.ndarray) -> float:
    """Total path length in metres."""
    position = np.asarray(position, dtype=np.float64)
    if position.shape[0] < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(position, axis=0), axis=1).sum())
