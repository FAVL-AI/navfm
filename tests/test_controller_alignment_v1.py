import math

import pytest
from scripts.analyse_controller_alignment_v1 import (
    join,
    matched_window,
    residual_stats,
    segment,
    validate_frame,
    window,
)


def n(t):
    return {"time": t, "controller_time": t + 0.008333, "angular_velocity": [0, 0, 0.1]}


def r(t):
    return {
        "time": t,
        "evaluation_w": 0.1,
        "evaluation_v": 0.05,
        "command": [0.05, 0.1],
        "control_output": 0.2,
    }


def test_exact_and_rounding_join():
    assert join([n(1)], [r(1 + 0.5e-6)])["pairs"] == [(0, 0)]


def test_no_lag_search():
    assert join([n(1)], [r(1 + 1 / 120)])["pairs"] == []


def test_duplicate_native_retained():
    a = join([n(1), n(1)], [r(1)])
    assert a["pairs"] == [] and a["native_unmatched"] == [0, 1]


def test_duplicate_evaluation_retained():
    a = join([n(1)], [r(1), r(1)])
    assert a["pairs"] == [] and a["evaluation_unmatched"] == [0, 1]


def test_unmatched_retained():
    a = join([n(2)], [r(1)])
    assert a["native_unmatched"] == [0] and a["evaluation_unmatched"] == [0]


def test_units_signed_integrals():
    a = window([r(1)] * 60)
    assert a["achieved_yaw_rad"] == pytest.approx(0.05)
    assert a["achieved_signed_distance_m"] == pytest.approx(0.025)


def test_nonfinite_rejected():
    with pytest.raises(ValueError):
        join([n(math.nan)], [r(1)])


def test_cross_boundary_acquisition_not_consumption():
    a = join([n(179 / 120)], [r(179 / 120), r(180 / 120)])
    assert a["pairs"] == [(0, 0)]
    assert segment(179) == 0 and segment(180) == 1


def test_wrong_frame_rejected():
    with pytest.raises(ValueError):
        validate_frame(
            {"frame": "world", "translation": [0, 0, 0], "orientation_wxyz": [1, 0, 0, 0]}
        )


def test_duplicate_groups_and_ambiguous_evaluation():
    a = join([n(1), n(1)], [r(1), r(1)])
    assert a["exact_native_duplicates"] == [[0, 1]]
    assert a["exact_evaluation_duplicates"] == [[0, 1]]
    assert a["ambiguous_evaluation"] == [0, 1]


def test_partial_matched_window_statistics():
    rows = [
        {
            "evaluation_index": 10,
            "native_gyro_rad_s": 0.3,
            "matched_gt_rad_s": 0.1,
            "gyro_minus_same_time_body_gt_rad_s": 0.2,
        }
    ]
    a = matched_window(rows, 10, 40)
    assert a["coverage"] == "partial" and a["residual"]["count"] == 1
    assert a["matched_only_gyro_integral_rad"] == pytest.approx(0.3 / 120)
    assert a["residual"]["mae_rad_s"] == pytest.approx(0.2)
    assert residual_stats([-0.2, 0.2])["signed_bias_rad_s"] == 0
