import math

import numpy as np
import pytest

from navfm.collection.perturbation import StartPerturbation, perturbed_start

ROUTE = [[0.0, 0.0], [2.0, 0.0], [2.0, 2.0]]


def test_identity_returns_route_start():
    start, yaw, rest = perturbed_start(ROUTE, StartPerturbation())
    assert np.allclose(start, [0, 0]) and yaw == 0.0
    assert np.allclose(rest, ROUTE)


def test_lateral_offset_is_left_of_local_heading_and_route_continues():
    start, yaw, rest = perturbed_start(ROUTE, StartPerturbation(0.75, 0.3, 20.0))
    # 75% of 4 m arc is (2, 1) on the second, +y segment; left of +y is -x.
    assert np.allclose(start, [1.7, 1.0])
    assert yaw == pytest.approx(math.pi / 2 + math.radians(20))
    assert np.allclose(rest, [[1.7, 1.0], [2.0, 2.0]])


def test_rejects_out_of_range():
    with pytest.raises(ValueError):
        StartPerturbation(1.0)
    with pytest.raises(ValueError):
        StartPerturbation(0.2, float("nan"))
