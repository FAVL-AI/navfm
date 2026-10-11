"""G10 — does a trajectory carry enough structure to be worth collecting?

The six thresholds are **PREDECLARED COLLECTION ADEQUACY THRESHOLDS**. They are
not requirements published by GNM, ViNT or NoMaD, and describing them as such
would attribute to those papers a standard they never set. They were frozen in
``COLLECTION_ROUTE_ADMISSION_V1`` before any candidate route was evaluated, and
they are not retuned against outcomes.

Only the *window* arithmetic is derived from the models, and it is derived from
the pinned loader rather than restated: ``TrajectorySpec.num_samples`` mirrors
``ViNT_Dataset._build_index``, so a trajectory's usable window count is computed
by the same expression the reference loader uses. GNM and ViNT take
``context_size = 5``, NoMaD ``context_size = 3`` with ``len_traj_pred = 8``, and
those differ, so the counts differ and are reported per model.

The gate exists in two forms and they are different claims:

``predict_from_route``
    PREDICTED_CAPABILITY. Estimates what an episode along a planned route would
    yield, from geometry and the collection rate. It is a forecast, and calling
    it a measurement would report a postcondition before the episode ran.

``measure_from_trajectory``
    POSTCONDITION. Computed from recorded positions and yaws.

No rounding into a pass. Comparisons are made against the recorded value as it
is, and the boundary is inclusive exactly where the threshold says ``>=``.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np

from ..schema import TrajectorySpec
from .footprint import heading_changes
from .gates import GateKind, GateResult, GateStatus

__all__ = [
    "LONG_HORIZON_THRESHOLDS",
    "LongHorizonMeasurement",
    "LongHorizonThresholds",
    "measure_from_trajectory",
    "predict_from_route",
    "window_counts",
]


@dataclasses.dataclass(frozen=True)
class LongHorizonThresholds:
    """Frozen in COLLECTION_ROUTE_ADMISSION_V1. Not model requirements."""

    min_usable_frames: int = 120
    min_travelled_distance_m: float = 8.0
    min_start_goal_separation_m: float = 5.0
    min_heading_changes: int = 3
    heading_change_deg: float = 30.0
    min_valid_context_windows: int = 30

    label: str = "PREDECLARED COLLECTION ADEQUACY THRESHOLDS"
    not_defined_by: str = "elapsed wall-clock seconds; nor by any published model requirement"

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


LONG_HORIZON_THRESHOLDS = LongHorizonThresholds()

#: Models whose sampling windows a collected trajectory must supply.
MODELS = ("gnm", "vint", "nomad")


def window_counts(n_frames: int, models: tuple[str, ...] = MODELS) -> dict[str, int]:
    """Valid sampling windows per model, via the pinned loader's own arithmetic.

    Uses ``TrajectorySpec.num_samples``, which mirrors
    ``ViNT_Dataset._build_index``. Restating the expression here would let it
    drift from the loader it is supposed to agree with.
    """
    return {m: TrajectorySpec.for_model(m).num_samples(int(n_frames)) for m in models}


@dataclasses.dataclass(frozen=True)
class LongHorizonMeasurement:
    """The six quantities, plus per-model window counts."""

    usable_frames: int
    travelled_distance_m: float
    start_goal_separation_m: float
    heading_change_count: int
    heading_changes_deg: list[float]
    windows_per_model: dict[str, int]

    @property
    def limiting_window_count(self) -> int:
        """The scarcest model's window count: a trajectory must serve all three."""
        return min(self.windows_per_model.values()) if self.windows_per_model else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "usable_frames": self.usable_frames,
            "travelled_distance_m": self.travelled_distance_m,
            "start_goal_separation_m": self.start_goal_separation_m,
            "heading_change_count": self.heading_change_count,
            "heading_changes_deg": self.heading_changes_deg,
            "windows_per_model": dict(self.windows_per_model),
            "limiting_window_count": self.limiting_window_count,
        }


def _adjudicate(
    measurement: LongHorizonMeasurement,
    thresholds: LongHorizonThresholds,
    kind: GateKind,
    extra: dict[str, Any],
) -> GateResult:
    checks = {
        "usable_frames": measurement.usable_frames >= thresholds.min_usable_frames,
        "travelled_distance": (
            measurement.travelled_distance_m >= thresholds.min_travelled_distance_m),
        "start_goal_separation": (
            measurement.start_goal_separation_m >= thresholds.min_start_goal_separation_m),
        "heading_changes": measurement.heading_change_count >= thresholds.min_heading_changes,
        "context_windows": (
            measurement.limiting_window_count >= thresholds.min_valid_context_windows),
    }
    detail: dict[str, Any] = {
        "measurement": measurement.to_dict(),
        "thresholds": thresholds.to_dict(),
        "checks": checks,
        "threshold_semantics": (
            "PREDECLARED COLLECTION ADEQUACY THRESHOLDS -- frozen before any candidate "
            "route was evaluated; not requirements published by GNM, ViNT or NoMaD"),
        "window_derivation": (
            "TrajectorySpec.num_samples, mirroring ViNT_Dataset._build_index at the "
            "pinned upstream commit; GNM/ViNT context_size 5, NoMaD context_size 3 "
            "with len_traj_pred 8"),
        "no_rounding": "values are compared as measured; nothing is rounded into a pass",
    }
    detail.update(extra)
    failed = [k for k, ok in checks.items() if not ok]
    if not failed:
        return GateResult("G10_LONG_HORIZON", GateStatus.PASS, kind,
                          reason="all six adequacy thresholds met", detail=detail)
    return GateResult("G10_LONG_HORIZON", GateStatus.FAIL, kind,
                      reason=", ".join(failed), detail=detail)


def predict_from_route(
    path: np.ndarray,
    *,
    control_hz: float,
    cruise_v: float,
    thresholds: LongHorizonThresholds = LONG_HORIZON_THRESHOLDS,
) -> GateResult:
    """PREDICTED_CAPABILITY — what a route would yield if driven as planned.

    A forecast, not a measurement. The frame estimate assumes the demonstrator
    holds ``cruise_v``; a real episode decelerates into turns and at the goal, so
    the realised frame count is generally HIGHER and the realised distance close
    to the planned one. The prediction is therefore conservative on frames and is
    never substituted for the postcondition.
    """
    pts = np.asarray(path, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError(f"path must be (N, 2), got {pts.shape}")
    if cruise_v <= 0 or control_hz <= 0:
        raise ValueError("cruise_v and control_hz must be positive")

    length = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()) if pts.shape[0] > 1 else 0.0
    separation = float(np.linalg.norm(pts[-1] - pts[0])) if pts.shape[0] > 1 else 0.0
    n_turns, turns = heading_changes(pts, thresholds.heading_change_deg)
    est_frames = int(math.floor((length / cruise_v) * control_hz))

    measurement = LongHorizonMeasurement(
        usable_frames=est_frames,
        travelled_distance_m=length,
        start_goal_separation_m=separation,
        heading_change_count=n_turns,
        heading_changes_deg=turns,
        windows_per_model=window_counts(est_frames),
    )
    return _adjudicate(measurement, thresholds, GateKind.PREDICTED_CAPABILITY, {
        "estimator": {
            "control_hz": control_hz,
            "cruise_v_m_s": cruise_v,
            "frames": "floor(path_length / cruise_v * control_hz)",
            "is_a_forecast": True,
            "conservative_direction": (
                "a real episode decelerates into turns and at the goal, so realised "
                "frames are generally higher than this estimate"),
        },
    })


def measure_from_trajectory(
    positions: np.ndarray,
    yaws: np.ndarray,
    *,
    thresholds: LongHorizonThresholds = LONG_HORIZON_THRESHOLDS,
) -> GateResult:
    """POSTCONDITION — what the recorded episode actually contains.

    ``usable_frames`` is the recorded frame count, and it is required to agree
    with the yaw series: a positions array longer than its yaws is a writer
    defect, and silently taking the shorter of the two would hide it.
    """
    pos = np.asarray(positions, dtype=float)
    yaw = np.asarray(yaws, dtype=float)
    if pos.ndim != 2 or pos.shape[1] != 2:
        raise ValueError(f"positions must be (T, 2), got {pos.shape}")
    if yaw.ndim != 1:
        raise ValueError(f"yaws must be (T,), got {yaw.shape}")
    if pos.shape[0] != yaw.shape[0]:
        raise ValueError(
            f"positions has {pos.shape[0]} frames and yaws has {yaw.shape[0]}; "
            "taking the shorter would hide a writer defect")

    n = int(pos.shape[0])
    length = float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum()) if n > 1 else 0.0
    separation = float(np.linalg.norm(pos[-1] - pos[0])) if n > 1 else 0.0
    n_turns, turns = heading_changes(pos, thresholds.heading_change_deg)

    measurement = LongHorizonMeasurement(
        usable_frames=n,
        travelled_distance_m=length,
        start_goal_separation_m=separation,
        heading_change_count=n_turns,
        heading_changes_deg=turns,
        windows_per_model=window_counts(n),
    )
    return _adjudicate(measurement, thresholds, GateKind.POSTCONDITION, {
        "source": "recorded positions and yaws",
        "frame_count_is_recorded_not_estimated": True,
    })
