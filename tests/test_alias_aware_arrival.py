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
    goal_region_features,
    ordered_similarity_scores,
    pool_goal_region_scores,
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


def test_goal_region_pooling_accepts_stronger_valid_nonterminal_match() -> None:
    # A positive query is closest to an in-region nonterminal. The legacy
    # terminal-only margin is negative, while explicit region pooling retains
    # that valid reference as goal support.
    row = [0.1, 0.1, 0.1, 0.2, 0.9, 0.9, 0.9, 0.1]
    history = [row, row, row, row]
    ids = tuple(f"ref-{index}" for index in range(len(row)))
    features = goal_region_features(
        history,
        reference_ids=ids,
        requested_goal_id=ids[-1],
        goal_region_reference_ids=(ids[6], ids[7]),
    )
    legacy = arrival_features(history, terminal_reference_window=1)

    assert legacy.alias_margin < 0.0
    assert features.strongest_goal_reference_id == ids[6]
    assert features.goal_region_score > features.scores[-1]
    assert features.region_margin > 0.0


def test_goal_region_support_uses_all_valid_goal_references() -> None:
    features = pool_goal_region_scores(
        [0.1, 0.8, 0.7, 0.2],
        reference_ids=("far", "near-a", "near-b", "goal"),
        requested_goal_id="goal",
        goal_region_reference_ids=("near-a", "near-b", "goal"),
    )

    assert features.goal_region_score == pytest.approx(0.8)
    assert features.region_margin == pytest.approx(0.7)
    assert features.strongest_goal_reference_id == "near-a"
    assert features.strongest_outside_reference_id == "far"


def test_reviewed_terminal_margin_counterexample_is_recovered_by_region_support() -> None:
    scores = (0.125, 0.125, 0.125, 0.2, 0.9, 0.1, 0.1, 0.6)
    identities = tuple(f"ref-{index}" for index in range(len(scores)))
    query_distance_to_goal_m = 0.4  # Synthetic positive under the frozen radius.
    assert query_distance_to_goal_m <= 0.5

    legacy_margin = scores[-1] - max(scores[:-1])
    features = pool_goal_region_scores(
        scores,
        reference_ids=identities,
        requested_goal_id=identities[-1],
        goal_region_reference_ids=(identities[4], identities[7]),
    )

    assert legacy_margin == pytest.approx(-0.3)
    assert features.goal_region_score == pytest.approx(0.9)
    assert features.region_margin == pytest.approx(0.7)


def test_distant_lookalike_can_defeat_both_feature_formulations() -> None:
    positive = pool_goal_region_scores(
        [0.2, 0.95],
        reference_ids=("lookalike", "goal"),
        requested_goal_id="goal",
        goal_region_reference_ids=("goal",),
    )
    negative = pool_goal_region_scores(
        [0.2, 0.95],
        reference_ids=("lookalike", "goal"),
        requested_goal_id="goal",
        goal_region_reference_ids=("goal",),
    )

    # Opposite geometric labels with identical feature inputs are
    # non-identifiable from these scores; synthetic fixtures cannot establish
    # visual discrimination.
    assert positive == negative
    assert positive.goal_region_score == pytest.approx(0.95)
    assert positive.region_margin > 0.0


def test_goal_region_pooling_is_identity_bound_but_ordered_scores_are_not() -> None:
    scores = [0.2, 0.6, 0.4, 0.8]
    identities = ["outside-a", "inside-a", "outside-b", "goal"]
    expected = pool_goal_region_scores(
        scores,
        reference_ids=identities,
        requested_goal_id="goal",
        goal_region_reference_ids=("inside-a", "goal"),
    )
    permutation = [2, 1, 0, 3]
    reordered = pool_goal_region_scores(
        [scores[index] for index in permutation],
        reference_ids=[identities[index] for index in permutation],
        requested_goal_id="goal",
        goal_region_reference_ids=("inside-a", "goal"),
    )
    assert reordered.goal_region_score == pytest.approx(expected.goal_region_score)
    assert reordered.region_margin == pytest.approx(expected.region_margin)
    assert reordered.strongest_goal_reference_id == expected.strongest_goal_reference_id

    history = [
        [0.0, 1.0, 2.0, 3.0],
        [10.0, 11.0, 12.0, 13.0],
        [20.0, 21.0, 22.0, 23.0],
        [30.0, 31.0, 32.0, 33.0],
    ]
    ordered = ordered_similarity_scores(history)
    swapped = ordered_similarity_scores([[row[1], row[0], *row[2:]] for row in history])
    assert ordered != swapped


def test_region_max_is_duplicate_score_invariant_but_chain_density_is_not() -> None:
    original = pool_goal_region_scores(
        [0.2, 0.7, 0.5],
        reference_ids=("outside", "inside", "goal"),
        requested_goal_id="goal",
        goal_region_reference_ids=("inside", "goal"),
    )
    with_duplicate = pool_goal_region_scores(
        [0.2, 0.7, 0.7, 0.5],
        reference_ids=("outside", "inside", "inside-copy", "goal"),
        requested_goal_id="goal",
        goal_region_reference_ids=("inside", "inside-copy", "goal"),
    )
    assert with_duplicate.goal_region_score == pytest.approx(original.goal_region_score)
    assert with_duplicate.region_margin == pytest.approx(original.region_margin)

    history = [[float(index) for index in range(5)] for _ in range(4)]
    before = ordered_similarity_scores(history)
    densified = ordered_similarity_scores([[*row[:2], row[1], *row[2:]] for row in history])
    assert densified != before


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "reference_ids": ("a", "goal"),
            "requested_goal_id": "goal",
            "goal_region_reference_ids": (),
        },
        {
            "reference_ids": ("a", "goal"),
            "requested_goal_id": "goal",
            "goal_region_reference_ids": ("a",),
        },
        {
            "reference_ids": ("a", "goal"),
            "requested_goal_id": "other",
            "goal_region_reference_ids": ("goal",),
        },
        {
            "reference_ids": ("a", "goal"),
            "requested_goal_id": "goal",
            "goal_region_reference_ids": ("unknown", "goal"),
        },
    ],
)
def test_goal_region_contract_rejects_missing_or_ambiguous_membership(kwargs) -> None:
    with pytest.raises(ValueError):
        pool_goal_region_scores([0.1, 0.2], **kwargs)


def test_logistic_fit_can_learn_negative_margin_association() -> None:
    rows = [
        CalibrationRow("episode-a", "a0", 0.6, -0.3, True),
        CalibrationRow("episode-a", "a1", 0.7, -0.2, True),
        CalibrationRow("episode-a", "a2", 0.6, 0.2, False),
        CalibrationRow("episode-a", "a3", 0.7, 0.3, False),
        CalibrationRow("episode-b", "b0", 0.6, -0.3, True),
        CalibrationRow("episode-b", "b1", 0.7, -0.2, True),
        CalibrationRow("episode-b", "b2", 0.6, 0.2, False),
        CalibrationRow("episode-b", "b3", 0.7, 0.3, False),
    ]
    calibrator = fit_logistic_calibrator(rows, l2=0.2)

    assert calibrator.margin_coefficient < 0.0
    assert calibrator.probability(0.65, -0.25) > calibrator.probability(0.65, 0.25)


def test_legacy_hard_margin_floor_vetoes_high_probability() -> None:
    state = ArrivalDecisionState(_config())

    result = state.update(timestamp_seconds=0.0, calibrated_probability=0.99, alias_margin=-0.3)

    assert result["eligible"] is False
    assert result["candidate_since_seconds"] is None


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


def _config(*, alias_margin_veto: bool = True, **changes: float) -> ArrivalDecisionConfig:
    values = {
        "probability_threshold": 0.8,
        "alias_margin_floor": 0.2,
        "dwell_seconds": 1.0,
        "maximum_observation_gap_seconds": 0.5,
    }
    values.update(changes)
    return ArrivalDecisionConfig(**values, alias_margin_veto=alias_margin_veto)


def _history_for_scores(scores: tuple[float, ...]) -> list[list[float]]:
    """Create a synthetic four-frame similarity matrix with known ordered scores."""

    return [
        [scores[min(index + history_index, len(scores) - 1)] for index in range(len(scores))]
        for history_index in range(4)
    ]


def _run_synthetic_decision(
    history: list[list[float]], *, alias_margin_veto: bool
) -> tuple[float, float, list[dict[str, float | bool | None]], ArrivalDecisionState]:
    features = arrival_features(history, terminal_reference_window=1)
    # Fixed synthetic coefficients isolate the decision-rule difference. This
    # map is not fitted or evidence of calibrated probabilities.
    calibrator = LogisticArrivalCalibrator(
        mean_terminal=0.0,
        scale_terminal=1.0,
        mean_margin=0.0,
        scale_margin=1.0,
        intercept=1.0,
        terminal_coefficient=1.0,
        margin_coefficient=0.0,
        source_group_count=0,
        source_rows=0,
    )
    probability = calibrator.probability(features.terminal_score, features.alias_margin)
    state = ArrivalDecisionState(_config(alias_margin_veto=alias_margin_veto))
    outputs = [
        state.update(
            timestamp_seconds=timestamp,
            calibrated_probability=probability,
            alias_margin=features.alias_margin,
        )
        for timestamp in (0.0, 0.5, 1.0)
    ]
    return probability, features.alias_margin, outputs, state


def test_synthetic_decision_rule_comparison_preserves_dwell_and_reset() -> None:
    # A geometrically valid near-goal query matches a nonterminal reference
    # more strongly: the camera-only terminal margin is negative.
    near_goal = _history_for_scores((0.2, 0.2, 0.2, 0.2, 0.9, 0.2, 0.2, 0.6))
    assert ordered_similarity_scores(near_goal) == pytest.approx(
        (0.2, 0.2, 0.2, 0.2, 0.9, 0.2, 0.2, 0.6)
    )
    strict_p, strict_margin, strict_rows, _ = _run_synthetic_decision(
        near_goal, alias_margin_veto=True
    )
    plain_p, plain_margin, plain_rows, plain_state = _run_synthetic_decision(
        near_goal, alias_margin_veto=False
    )
    assert strict_p == pytest.approx(plain_p)
    assert strict_p >= 0.8
    assert strict_margin == plain_margin == pytest.approx(-0.3)
    assert all(row["eligible"] is False for row in strict_rows)
    assert strict_rows[-1]["latched_arrival"] is False
    assert all(row["eligible"] is True for row in plain_rows)
    assert [row["latched_arrival"] for row in plain_rows] == [False, False, True]

    # A distant terminal lookalike with a strong terminal score and positive
    # margin passes both rules. The no-veto rule does not solve this failure.
    distant_lookalike = _history_for_scores((0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.65, 0.95))
    assert ordered_similarity_scores(distant_lookalike) == pytest.approx(
        (0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.65, 0.95)
    )
    lookalike_a = _run_synthetic_decision(distant_lookalike, alias_margin_veto=True)
    lookalike_b = _run_synthetic_decision(distant_lookalike, alias_margin_veto=False)
    assert lookalike_a[0] == pytest.approx(lookalike_b[0])
    assert lookalike_a[0] >= 0.8
    assert lookalike_a[1] == lookalike_b[1] == pytest.approx(0.3)
    assert lookalike_a[2][-1]["latched_arrival"] is True
    assert lookalike_b[2][-1]["latched_arrival"] is True

    # Distinct geometric labels attached to identical visual input produce
    # identical decisions: neither camera-only rule can infer the label.
    same_visual_cases = {"near_goal": True, "distant_wrong_location": False}
    assert set(same_visual_cases.values()) == {False, True}
    for veto in (True, False):
        paired = [
            _run_synthetic_decision(near_goal, alias_margin_veto=veto)[2]
            for _label in same_visual_cases.values()
        ]
        assert paired[0] == paired[1]

    # Reset semantics are shared: the probability-only rule clears its latch
    # and must accumulate the full dwell again.
    plain_state.reset()
    assert plain_state.latched is False
    assert plain_state.candidate_since is None
    restarted = plain_state.update(
        timestamp_seconds=10.0,
        calibrated_probability=plain_p,
        alias_margin=plain_margin,
    )
    assert restarted["candidate_since_seconds"] == 10.0
    assert restarted["latched_arrival"] is False


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


def test_decision_config_requires_boolean_margin_policy() -> None:
    with pytest.raises(ValueError, match="alias_margin_veto"):
        ArrivalDecisionConfig(
            probability_threshold=0.8,
            alias_margin_floor=0.2,
            dwell_seconds=1.0,
            maximum_observation_gap_seconds=0.5,
            alias_margin_veto=1,  # type: ignore[arg-type]
        )


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
