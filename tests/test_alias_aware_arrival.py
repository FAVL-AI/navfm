"""Synthetic contract tests for the detached alias-aware arrival candidate."""

from __future__ import annotations

import inspect
import math
from dataclasses import fields

import pytest

from navfm.collection.alias_aware_arrival import (
    ArrivalDecisionConfig,
    ArrivalDecisionState,
    CalibrationRow,
    LogisticArrivalCalibrator,
    arrival_features,
    fit_logistic_calibrator,
    ordered_similarity_scores,
)


def _calibration_rows() -> list[CalibrationRow]:
    """Unequal episode lengths with both outcomes represented in both groups."""

    return [
        CalibrationRow("episode-a", "a0", -1.0, -0.8, False),
        CalibrationRow("episode-a", "a1", 0.1, -0.2, False),
        CalibrationRow("episode-a", "a2", 0.8, 0.6, True),
        CalibrationRow("episode-b", "b0", -0.8, -0.7, False),
        CalibrationRow("episode-b", "b1", -0.3, -0.1, False),
        CalibrationRow("episode-b", "b2", 0.4, 0.2, True),
        CalibrationRow("episode-b", "b3", 1.2, 0.9, True),
    ]


def _fit(rows: list[CalibrationRow]) -> LogisticArrivalCalibrator:
    return fit_logistic_calibrator(rows, l2=0.2)


def test_ordered_scores_follow_history_and_reference_order() -> None:
    history = [
        [0, 1, 2, 3, 4],
        [10, 11, 12, 13, 14],
        [20, 21, 22, 23, 24],
        [30, 31, 32, 33, 34],
    ]

    assert ordered_similarity_scores(history) == pytest.approx((15.0, 15.25, 15.75, 16.5, 17.5))


def test_alias_margin_excludes_the_explicit_terminal_window() -> None:
    history = [[0, 1, 2, 3, 4]] * 4

    one_terminal_node = arrival_features(history, terminal_reference_window=1)
    two_terminal_nodes = arrival_features(history, terminal_reference_window=2)

    assert one_terminal_node.strongest_distractor_index == 3
    assert one_terminal_node.alias_margin == pytest.approx(1.0)
    assert two_terminal_nodes.strongest_distractor_index == 2
    assert two_terminal_nodes.alias_margin == pytest.approx(1.75)
    assert one_terminal_node.scores[-1] == one_terminal_node.terminal_score


@pytest.mark.parametrize(
    ("history", "message"),
    [
        ([], "at least one"),
        ([[0, 1], [0, 1], [0, 1]], "exactly four"),
        ([[0], [0], [0], [0]], "at least two"),
        ([[0, 1], [0], [0, 1], [0, 1]], "equal length"),
        ([[0, 1], [0, 1], [0, 1], [0, math.nan]], "finite"),
        ([[0, 1], [0, 1], [0, 1], [0, math.inf]], "finite"),
    ],
)
def test_ordered_scores_reject_invalid_history(history, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ordered_similarity_scores(history)


@pytest.mark.parametrize("window", [0, -1, 5, 6])
def test_terminal_window_must_leave_an_earlier_distractor(window: int) -> None:
    with pytest.raises(ValueError, match="leave at least one distractor"):
        arrival_features([[0, 1, 2, 3, 4]] * 4, terminal_reference_window=window)


def test_episode_balance_controls_feature_center_and_scale() -> None:
    rows = _calibration_rows()
    calibrator = _fit(rows)
    group_a = [row.terminal_score for row in rows if row.group_id == "episode-a"]
    group_b = [row.terminal_score for row in rows if row.group_id == "episode-b"]
    expected_center = (sum(group_a) / len(group_a) + sum(group_b) / len(group_b)) / 2

    assert calibrator.mean_terminal == pytest.approx(expected_center)
    assert calibrator.source_group_count == 2
    assert calibrator.source_rows == len(rows)


def test_duplicating_one_episode_frames_preserves_its_aggregate_influence() -> None:
    rows = _calibration_rows()
    duplicated_episode = [
        CalibrationRow(
            row.group_id,
            f"{row.row_id}-copy",
            row.terminal_score,
            row.alias_margin,
            row.requested_goal_valid,
        )
        for row in rows
        if row.group_id == "episode-a"
    ]

    original = _fit(rows)
    duplicated = _fit(rows + duplicated_episode)

    assert duplicated.mean_terminal == pytest.approx(original.mean_terminal)
    assert duplicated.scale_terminal == pytest.approx(original.scale_terminal)
    assert duplicated.mean_margin == pytest.approx(original.mean_margin)
    assert duplicated.scale_margin == pytest.approx(original.scale_margin)
    for terminal, margin in [(-0.5, -0.4), (0.2, 0.1), (0.9, 0.7)]:
        assert duplicated.probability(terminal, margin) == pytest.approx(
            original.probability(terminal, margin), abs=1e-9
        )


def test_constant_features_have_finite_scales_and_probabilities() -> None:
    rows = [
        CalibrationRow("episode-a", "a0", 0.5, 0.25, False),
        CalibrationRow("episode-a", "a1", 0.5, 0.25, True),
        CalibrationRow("episode-b", "b0", 0.5, 0.25, False),
        CalibrationRow("episode-b", "b1", 0.5, 0.25, True),
    ]

    calibrator = _fit(rows)

    assert calibrator.scale_terminal == pytest.approx(1e-12)
    assert calibrator.scale_margin == pytest.approx(1e-12)
    assert math.isfinite(calibrator.probability(0.5, 0.25))


@pytest.mark.parametrize(
    "rows",
    [
        [
            CalibrationRow("episode-a", "a0", 0.0, 0.0, True),
            CalibrationRow("episode-a", "a1", 1.0, 1.0, True),
            CalibrationRow("episode-b", "b0", 0.0, 0.0, True),
            CalibrationRow("episode-b", "b1", 1.0, 1.0, True),
        ],
        [
            CalibrationRow("episode-a", "a0", 0.0, 0.0, False),
            CalibrationRow("episode-a", "a1", 1.0, 1.0, False),
            CalibrationRow("episode-b", "b0", 0.0, 0.0, False),
            CalibrationRow("episode-b", "b1", 1.0, 1.0, False),
        ],
    ],
)
def test_calibration_rejects_degenerate_labels(rows: list[CalibrationRow]) -> None:
    with pytest.raises(ValueError, match="positive and negative labels"):
        _fit(rows)


def test_calibration_is_deterministic_for_identical_ordered_rows() -> None:
    rows = _calibration_rows()

    first = _fit(rows)
    second = _fit(rows)

    assert first == second
    assert [first.probability(row.terminal_score, row.alias_margin) for row in rows] == [
        second.probability(row.terminal_score, row.alias_margin) for row in rows
    ]


@pytest.mark.parametrize(
    "rows",
    [
        [CalibrationRow("", "a", 0, 0, False)],
        [CalibrationRow("episode-a", "", 0, 0, False)],
        [
            CalibrationRow("episode-a", "same", 0, 0, False),
            CalibrationRow("episode-b", "same", 1, 1, True),
        ],
        [
            CalibrationRow("episode-a", "a0", math.nan, 0, False),
            CalibrationRow("episode-b", "b0", 1, 1, True),
        ],
        [
            CalibrationRow("episode-a", "a0", 0, math.inf, False),
            CalibrationRow("episode-b", "b0", 1, 1, True),
        ],
        [
            CalibrationRow("episode-a", "a0", 0, 0, 0),
            CalibrationRow("episode-b", "b0", 1, 1, True),
        ],
    ],
)
def test_calibration_rejects_invalid_row_contracts(rows: list[CalibrationRow]) -> None:
    with pytest.raises(ValueError):
        _fit(rows)


def test_constant_calibration_labels_are_not_implicitly_accepted() -> None:
    with pytest.raises(ValueError, match="at least four"):
        fit_logistic_calibrator([], l2=0.2)
    with pytest.raises(ValueError, match="optimizer settings"):
        fit_logistic_calibrator(_calibration_rows(), l2=0.0)
    with pytest.raises(ValueError, match="optimizer settings"):
        fit_logistic_calibrator(_calibration_rows(), l2=0.2, max_iterations=0)


def _config(**changes: float) -> ArrivalDecisionConfig:
    values = {
        "probability_threshold": 0.8,
        "alias_margin_floor": 0.2,
        "dwell_seconds": 1.0,
        "maximum_observation_gap_seconds": 0.5,
    }
    values.update(changes)
    return ArrivalDecisionConfig(**values)


def test_dwell_requires_continuous_eligible_observations() -> None:
    state = ArrivalDecisionState(_config())
    assert (
        state.update(timestamp_seconds=0.0, calibrated_probability=0.9, alias_margin=0.3)[
            "latched_arrival"
        ]
        is False
    )
    assert (
        state.update(timestamp_seconds=0.4, calibrated_probability=0.9, alias_margin=0.3)[
            "latched_arrival"
        ]
        is False
    )
    # A gap larger than the declared maximum restarts the dwell interval.
    assert (
        state.update(timestamp_seconds=1.0, calibrated_probability=0.9, alias_margin=0.3)[
            "candidate_since_seconds"
        ]
        == 1.0
    )
    assert (
        state.update(timestamp_seconds=1.5, calibrated_probability=0.9, alias_margin=0.3)[
            "latched_arrival"
        ]
        is False
    )
    assert (
        state.update(timestamp_seconds=2.0, calibrated_probability=0.9, alias_margin=0.3)[
            "latched_arrival"
        ]
        is True
    )


def test_ineligible_sample_cancels_dwell_and_latch_is_sticky_until_reset() -> None:
    state = ArrivalDecisionState(_config())
    state.update(timestamp_seconds=0.0, calibrated_probability=0.9, alias_margin=0.3)
    cancelled = state.update(timestamp_seconds=0.25, calibrated_probability=0.79, alias_margin=0.3)
    assert cancelled["candidate_since_seconds"] is None
    state.update(timestamp_seconds=0.5, calibrated_probability=0.9, alias_margin=0.3)
    state.update(timestamp_seconds=1.0, calibrated_probability=0.9, alias_margin=0.3)
    assert (
        state.update(timestamp_seconds=1.5, calibrated_probability=0.9, alias_margin=0.3)[
            "latched_arrival"
        ]
        is True
    )

    state.update(timestamp_seconds=1.75, calibrated_probability=0.0, alias_margin=-1.0)
    assert state.latched is True
    state.reset()
    assert state.latched is False
    assert state.candidate_since is None
    assert state.last_timestamp is None


def test_out_of_order_timestamp_rejects_without_mutating_state() -> None:
    state = ArrivalDecisionState(_config())
    state.update(timestamp_seconds=1.0, calibrated_probability=0.9, alias_margin=0.3)
    before = (state.candidate_since, state.last_timestamp, state.latched)

    with pytest.raises(ValueError, match="strictly increase"):
        state.update(timestamp_seconds=0.5, calibrated_probability=0.9, alias_margin=0.3)

    assert (state.candidate_since, state.last_timestamp, state.latched) == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timestamp_seconds": math.nan, "calibrated_probability": 0.9, "alias_margin": 0.3},
        {"timestamp_seconds": 1.0, "calibrated_probability": math.inf, "alias_margin": 0.3},
        {"timestamp_seconds": 1.0, "calibrated_probability": 0.9, "alias_margin": math.nan},
        {"timestamp_seconds": 1.0, "calibrated_probability": 1.01, "alias_margin": 0.3},
    ],
)
def test_decision_rejects_nonfinite_or_out_of_range_inputs(kwargs) -> None:
    state = ArrivalDecisionState(_config())
    with pytest.raises(ValueError):
        state.update(**kwargs)
    assert state.last_timestamp is None


@pytest.mark.parametrize(
    "changes",
    [
        {"probability_threshold": math.nan},
        {"probability_threshold": 0.0},
        {"alias_margin_floor": math.inf},
        {"dwell_seconds": 0.0},
        {"maximum_observation_gap_seconds": -1.0},
    ],
)
def test_decision_config_rejects_invalid_explicit_settings(changes: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        _config(**changes)


def test_thresholds_and_terminal_window_are_never_implicitly_fitted() -> None:
    config_parameters = inspect.signature(ArrivalDecisionConfig).parameters.values()
    assert all(parameter.default is inspect.Parameter.empty for parameter in config_parameters)
    calibrator_field_names = {field.name for field in fields(_fit(_calibration_rows()))}
    assert "probability_threshold" not in calibrator_field_names
    assert "alias_margin_floor" not in calibrator_field_names
    assert "terminal_reference_window" in inspect.signature(arrival_features).parameters
    assert (
        inspect.signature(arrival_features).parameters["terminal_reference_window"].default
        is inspect.Parameter.empty
    )
