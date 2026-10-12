from __future__ import annotations

import math

import numpy as np
import pytest
from scripts.audit_arrival_training_geometry_v1 import (
    ordered_distinct_frame_pairs,
    wrapped_heading_difference,
)


def test_known_geometry_and_identity_preservation() -> None:
    rows = ordered_distinct_frame_pairs(
        "episode-1",
        "route-2",
        "scene-3",
        np.asarray([[0.0, 0.0], [3.0, 4.0]]),
        np.asarray([0.0, math.pi / 2]),
    )

    assert len(rows) == 2
    assert rows[0]["trajectory_id"] == "episode-1"
    assert rows[0]["route_id"] == "route-2"
    assert rows[0]["scene_id"] == "scene-3"
    assert (rows[0]["query_frame_index"], rows[0]["goal_frame_index"]) == (0, 1)
    assert rows[0]["distance_m"] == pytest.approx(5.0)
    assert rows[1]["distance_m"] == pytest.approx(5.0)
    assert rows[0]["query_minus_goal_heading_rad"] == pytest.approx(-math.pi / 2)
    assert rows[1]["query_minus_goal_heading_rad"] == pytest.approx(math.pi / 2)


def test_heading_difference_wraps_at_pi_boundary() -> None:
    assert wrapped_heading_difference(-math.pi + 0.1, math.pi - 0.1) == pytest.approx(0.2)
    assert wrapped_heading_difference(math.pi - 0.1, -math.pi + 0.1) == pytest.approx(-0.2)


@pytest.mark.parametrize(
    "position,yaw",
    [
        (np.asarray([[0.0, 0.0]]), np.asarray([0.0])),
        (np.asarray([[0.0, 0.0], [1.0, 1.0]]), np.asarray([0.0])),
        (np.asarray([[0.0, 0.0], [math.nan, 1.0]]), np.asarray([0.0, 0.0])),
        (np.asarray([[0.0, 0.0], [1.0, 1.0]]), np.asarray([0.0, math.inf])),
        (np.asarray([0.0, 1.0]), np.asarray([0.0, 1.0])),
    ],
)
def test_invalid_shapes_and_nonfinite_inputs_reject(position, yaw) -> None:
    with pytest.raises(ValueError):
        ordered_distinct_frame_pairs("e", "r", "s", position, yaw)


def test_wrapped_heading_rejects_nonfinite_input() -> None:
    with pytest.raises(ValueError, match="finite"):
        wrapped_heading_difference(math.nan, 0.0)
