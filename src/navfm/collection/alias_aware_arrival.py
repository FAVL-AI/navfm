"""Offline-ready alias-aware arrival features and probability calibration.

This module is a candidate research component. It is not wired into a
navigation or simulator launcher. Inputs are RGB/reference similarity rows;
pose, graph, controller, and contact state are deliberately outside the API.
Calibration consumes offline ground-truth-labeled development rows in memory
and does not choose the decision threshold, alias-margin floor, terminal
window, or dwell rule. Probability quality still requires disjoint evaluation.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ArrivalFeatures:
    """Ordered similarity for the requested terminal and its alias margin."""

    terminal_score: float
    alias_margin: float
    strongest_distractor_index: int
    scores: tuple[float, ...]


@dataclass(frozen=True)
class GoalRegionFeatures:
    """Candidate scores pooled over explicitly annotated goal-region nodes."""

    goal_region_score: float
    region_margin: float
    strongest_goal_reference_id: str
    strongest_outside_reference_id: str
    scores: tuple[float, ...]


def ordered_similarity_scores(
    history_similarity: Sequence[Sequence[float]],
) -> tuple[float, ...]:
    """Compute S_t(j) from H x N similarity values in temporal order.

    ``history_similarity[k][j]`` is the similarity of current-history image
    ``I[t-k]`` to reference ``R[j]``. For candidate reference j, the method
    compares that image to ``R[max(0, j-k)]`` and averages across history.
    Rows must be equally sized and all entries finite.
    """

    if not history_similarity:
        raise ValueError("history must contain at least one similarity row")
    if len(history_similarity) != 4:
        raise ValueError("candidate method requires exactly four ordered history rows")
    width = len(history_similarity[0])
    if width < 2:
        raise ValueError("reference chain must contain at least two nodes")
    if any(len(row) != width for row in history_similarity):
        raise ValueError("similarity rows must have equal length")
    if any(not math.isfinite(float(value)) for row in history_similarity for value in row):
        raise ValueError("similarities must be finite")

    history_length = len(history_similarity)
    return tuple(
        sum(float(history_similarity[k][max(0, j - k)]) for k in range(history_length))
        / history_length
        for j in range(width)
    )


def arrival_features(
    history_similarity: Sequence[Sequence[float]],
    *,
    terminal_reference_window: int,
) -> ArrivalFeatures:
    """Return requested-terminal score and separation from earlier aliases.

    The terminal window is explicit because the research design has not yet
    selected its value. References in ``[J-window+1, J]`` are treated as the
    terminal region; the strongest earlier reference supplies the distractor.
    """

    scores = ordered_similarity_scores(history_similarity)
    terminal = len(scores) - 1
    if not 1 <= terminal_reference_window <= terminal:
        raise ValueError("terminal window must leave at least one distractor")
    distractors = range(0, terminal - terminal_reference_window + 1)
    strongest = max(distractors, key=scores.__getitem__)
    return ArrivalFeatures(
        terminal_score=scores[terminal],
        alias_margin=scores[terminal] - scores[strongest],
        strongest_distractor_index=strongest,
        scores=scores,
    )


def pool_goal_region_scores(
    scores: Sequence[float],
    *,
    reference_ids: Sequence[str],
    requested_goal_id: str,
    goal_region_reference_ids: Sequence[str],
) -> GoalRegionFeatures:
    """Pool scores using explicit reference-node membership for one goal.

    ``goal_region_reference_ids`` must come from authenticated reference and
    goal-capture poses in a shared frame. This function receives no query pose
    or ground-truth query label. The requested goal must be the final ordered
    node and a member of the region. At least one out-of-region competitor is
    required; missing or ambiguous membership is rejected rather than filled
    with a synthetic score.
    """

    values = tuple(float(value) for value in scores)
    identities = tuple(reference_ids)
    region_ids = tuple(goal_region_reference_ids)
    if len(values) < 2 or len(identities) != len(values):
        raise ValueError("scores and reference identities must align with at least two nodes")
    if any(not identity for identity in identities) or len(set(identities)) != len(identities):
        raise ValueError("reference identities must be non-empty and unique")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("scores must be finite")
    if not requested_goal_id or identities[-1] != requested_goal_id:
        raise ValueError("requested goal must identify the final ordered reference node")
    if not region_ids or any(not identity for identity in region_ids):
        raise ValueError("goal-region reference identities must be explicit and non-empty")
    if len(set(region_ids)) != len(region_ids):
        raise ValueError("goal-region reference identities must be unique")
    unknown = set(region_ids).difference(identities)
    if unknown:
        raise ValueError("goal-region references must exist in the ordered reference chain")
    if requested_goal_id not in region_ids:
        raise ValueError("requested goal reference must belong to its goal region")

    goal_region = set(region_ids)
    goal_indices = [index for index, identity in enumerate(identities) if identity in goal_region]
    outside_indices = [
        index for index, identity in enumerate(identities) if identity not in goal_region
    ]
    if not outside_indices:
        raise ValueError("goal-region scoring requires an out-of-region competitor")
    strongest_goal = max(goal_indices, key=values.__getitem__)
    strongest_outside = max(outside_indices, key=values.__getitem__)
    goal_score = values[strongest_goal]
    return GoalRegionFeatures(
        goal_region_score=goal_score,
        region_margin=goal_score - values[strongest_outside],
        strongest_goal_reference_id=identities[strongest_goal],
        strongest_outside_reference_id=identities[strongest_outside],
        scores=values,
    )


def goal_region_features(
    history_similarity: Sequence[Sequence[float]],
    *,
    reference_ids: Sequence[str],
    requested_goal_id: str,
    goal_region_reference_ids: Sequence[str],
) -> GoalRegionFeatures:
    """Compute ordered history scores, then pool annotated goal-region nodes.

    Reference ordering remains part of ``ordered_similarity_scores``. The
    identity-aware pooling itself is insensitive to permutation or exact
    duplicate scored evidence, but changing the ordered chain can change the
    upstream history alignment and resulting scores.
    """

    scores = ordered_similarity_scores(history_similarity)
    return pool_goal_region_scores(
        scores,
        reference_ids=reference_ids,
        requested_goal_id=requested_goal_id,
        goal_region_reference_ids=goal_region_reference_ids,
    )


@dataclass(frozen=True)
class CalibrationRow:
    """One offline frame label; ``group_id`` identifies its episode."""

    group_id: str
    row_id: str
    terminal_score: float
    alias_margin: float
    requested_goal_valid: bool


@dataclass(frozen=True)
class LogisticArrivalCalibrator:
    """Frozen two-feature logistic map; its probability cutoff is external."""

    mean_terminal: float
    scale_terminal: float
    mean_margin: float
    scale_margin: float
    intercept: float
    terminal_coefficient: float
    margin_coefficient: float
    source_group_count: int
    source_rows: int
    schema_version: int = 1

    def probability(self, terminal_score: float, alias_margin: float) -> float:
        values = (terminal_score, alias_margin)
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("calibrator inputs must be finite")
        z = (
            self.intercept
            + self.terminal_coefficient
            * (float(terminal_score) - self.mean_terminal)
            / self.scale_terminal
            + self.margin_coefficient * (float(alias_margin) - self.mean_margin) / self.scale_margin
        )
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        exp_z = math.exp(z)
        return exp_z / (1.0 + exp_z)


def _solve_3x3(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a small positive-definite Newton system with pivoting."""

    augmented = [[*row, value] for row, value in zip(matrix, vector, strict=True)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            raise ValueError("calibration Hessian is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * base
                for value, base in zip(augmented[row], augmented[column], strict=True)
            ]
    return [augmented[row][3] for row in range(3)]


def fit_logistic_calibrator(
    rows: Iterable[CalibrationRow],
    *,
    l2: float,
    max_iterations: int = 100,
) -> LogisticArrivalCalibrator:
    """Fit a deterministic, episode-balanced logistic probability map.

    Each episode contributes equal total weight so long recordings do not
    dominate. Both classes and at least two episode groups are required.
    This is probability calibration only: it does not select an arrival
    probability cutoff or margin floor. Callers must bind row/group identities
    and keep all tuning and evaluation groups out of this fit.
    """

    data = tuple(rows)
    if len(data) < 4:
        raise ValueError("at least four calibration rows are required")
    if not math.isfinite(l2) or l2 <= 0 or max_iterations < 1:
        raise ValueError("invalid optimizer settings")
    if any(not row.group_id or not row.row_id for row in data):
        raise ValueError("calibration rows require group and row identities")
    if any(not isinstance(row.requested_goal_valid, bool) for row in data):
        raise ValueError("calibration labels must be explicit booleans")
    if len({row.row_id for row in data}) != len(data):
        raise ValueError("calibration row identities must be unique")
    if any(
        not math.isfinite(float(value))
        for row in data
        for value in (row.terminal_score, row.alias_margin)
    ):
        raise ValueError("calibration features must be finite")
    labels = [int(bool(row.requested_goal_valid)) for row in data]
    if set(labels) != {0, 1}:
        raise ValueError("calibration requires positive and negative labels")
    groups = tuple(sorted({row.group_id for row in data}))
    if len(groups) < 2:
        raise ValueError("calibration requires at least two episode groups")

    terminals = [float(row.terminal_score) for row in data]
    margins = [float(row.alias_margin) for row in data]
    group_sizes = {group: sum(row.group_id == group for row in data) for group in groups}
    weights = [1.0 / (len(groups) * group_sizes[row.group_id]) for row in data]
    means = (
        sum(weight * value for weight, value in zip(weights, terminals, strict=True)),
        sum(weight * value for weight, value in zip(weights, margins, strict=True)),
    )
    scales = tuple(
        max(
            math.sqrt(
                sum(
                    weight * (value - mean) ** 2
                    for weight, value in zip(weights, values, strict=True)
                )
            ),
            1e-12,
        )
        for values, mean in ((terminals, means[0]), (margins, means[1]))
    )
    features = [
        (1.0, (terminal - means[0]) / scales[0], (margin - means[1]) / scales[1])
        for terminal, margin in zip(terminals, margins, strict=True)
    ]
    beta = [0.0, 0.0, 0.0]
    converged = False

    def objective(parameters: list[float]) -> float:
        total = 0.5 * l2 * sum(value * value for value in parameters[1:])
        for x, label, weight in zip(features, labels, weights, strict=True):
            z = sum(a * b for a, b in zip(parameters, x, strict=True))
            total += weight * (max(z, 0.0) - label * z + math.log1p(math.exp(-abs(z))))
        return total

    for _ in range(max_iterations):
        gradient = [0.0, l2 * beta[1], l2 * beta[2]]
        hessian = [[0.0] * 3 for _ in range(3)]
        hessian[1][1] = l2
        hessian[2][2] = l2
        for x, label, weight in zip(features, labels, weights, strict=True):
            z = sum(a * b for a, b in zip(beta, x, strict=True))
            probability = (
                1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))
            )
            residual = weight * (probability - label)
            curvature = weight * probability * (1.0 - probability)
            for i in range(3):
                gradient[i] += residual * x[i]
                for j in range(3):
                    hessian[i][j] += curvature * x[i] * x[j]
        step = _solve_3x3(hessian, gradient)
        if max(abs(value) for value in step) < 1e-9:
            converged = True
            break
        old_loss = objective(beta)
        fraction = 1.0
        while fraction >= 1.0 / 1024.0:
            candidate = [value - fraction * delta for value, delta in zip(beta, step, strict=True)]
            if objective(candidate) <= old_loss:
                beta = candidate
                break
            fraction /= 2.0
        else:
            raise ValueError("calibration optimizer did not find a descent step")
    if not converged:
        raise ValueError("calibration optimizer reached its iteration limit")
    if any(not math.isfinite(value) for value in beta):
        raise ValueError("calibration produced nonfinite parameters")
    return LogisticArrivalCalibrator(
        mean_terminal=means[0],
        scale_terminal=scales[0],
        mean_margin=means[1],
        scale_margin=scales[1],
        intercept=beta[0],
        terminal_coefficient=beta[1],
        margin_coefficient=beta[2],
        source_group_count=len(groups),
        source_rows=len(data),
    )


@dataclass(frozen=True)
class ArrivalDecisionConfig:
    """Explicit, externally selected decision settings for later evaluation."""

    probability_threshold: float
    alias_margin_floor: float
    dwell_seconds: float
    maximum_observation_gap_seconds: float

    def __post_init__(self) -> None:
        values = (
            self.probability_threshold,
            self.alias_margin_floor,
            self.dwell_seconds,
            self.maximum_observation_gap_seconds,
        )
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("decision settings must be finite")
        if not 0.0 < self.probability_threshold < 1.0:
            raise ValueError("probability threshold must lie strictly between 0 and 1")
        if self.dwell_seconds <= 0 or self.maximum_observation_gap_seconds <= 0:
            raise ValueError("dwell and maximum observation gap must be positive")


@dataclass
class ArrivalDecisionState:
    """Candidate temporal dwell state; it emits no actuator command."""

    config: ArrivalDecisionConfig
    candidate_since: float | None = None
    last_timestamp: float | None = None
    latched: bool = False

    def reset(self) -> None:
        self.candidate_since = None
        self.last_timestamp = None
        self.latched = False

    def update(
        self,
        *,
        timestamp_seconds: float,
        calibrated_probability: float,
        alias_margin: float,
    ) -> dict[str, float | bool | None]:
        """Update using simulation-time stamps and candidate features only."""

        timestamp = float(timestamp_seconds)
        probability = float(calibrated_probability)
        margin = float(alias_margin)
        if any(not math.isfinite(value) for value in (timestamp, probability, margin)):
            raise ValueError("decision inputs must be finite")
        if not 0.0 <= probability <= 1.0:
            raise ValueError("calibrated probability must be in [0, 1]")
        if self.last_timestamp is not None:
            delta = timestamp - self.last_timestamp
            if delta <= 0.0:
                raise ValueError("decision timestamps must strictly increase")
            if delta > self.config.maximum_observation_gap_seconds:
                self.candidate_since = None
        self.last_timestamp = timestamp

        eligible = (
            probability >= self.config.probability_threshold
            and margin >= self.config.alias_margin_floor
        )
        if not self.latched:
            if eligible:
                if self.candidate_since is None:
                    self.candidate_since = timestamp
                elif timestamp - self.candidate_since >= self.config.dwell_seconds:
                    self.latched = True
            else:
                self.candidate_since = None
        return {
            "eligible": eligible,
            "candidate_since_seconds": self.candidate_since,
            "latched_arrival": self.latched,
            "timestamp_seconds": timestamp,
        }
