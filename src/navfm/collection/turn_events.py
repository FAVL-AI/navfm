"""G10_TURN_SEMANTICS_V2 — realised turn events on a continuously curved path.

`F-G10-1`: the same route measures 3 turns from its planned polyline and 1 from
the driven path. The original rule closes a turn episode only when it meets a
segment that is essentially straight, which is correct for a piecewise-linear
plan and wrong for a pure-pursuit execution that never travels exactly straight.

The fix is not to lower a threshold. It is that "three turns" must mean **three
distinct events**, and distinctness needs a separator that a curved path can
actually exhibit: a *low-curvature run of meaningful length*, not a single
straight sample.

Three properties this is built around, each chosen against a specific way of
being wrong:

**Net, not cumulative.** An episode's magnitude is the signed sum of its heading
deltas. Cumulative absolute change would let tracking oscillation and left-right
corrections accumulate into a turn that never happened.

**Path tangent, not robot yaw.** Turns are events in the path the robot
travelled. A mecanum base can yaw while translating sideways, so yaw is recorded
as a corroborative viewpoint metric and never substituted for the tangent.

**One arc is one event.** A continuous 172 degree sweep is one turn, not
``floor(172/30)`` turns. Partitioning an arc into qualifying pieces would make
the requirement satisfiable by any sufficiently long bend.

This module deliberately does NOT try to make any particular trajectory pass.
Where a driven path has no low-curvature separators, the honest count is one.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import numpy as np

from .footprint import resample_route

__all__ = [
    "TURN_SEMANTICS_V2",
    "TurnEvent",
    "TurnSemanticsV2",
    "realised_turn_events",
]


@dataclasses.dataclass(frozen=True)
class TurnSemanticsV2:
    """Frozen parameters. Derived from geometry, never from a trajectory."""

    #: REUSED, already frozen: the decimation the original rule used.
    resample_interval_m: float = 0.5

    #: REUSED, already frozen as `straight_deg`: per-segment heading change below
    #: which a decimated segment is not turning.
    low_curvature_segment_deg: float = 1.0

    #: THE ONLY NEW PARAMETER. A separator must be a RUN, not a single sample,
    #: so it spans at least two decimated segments: 2 x 0.5 m. Derived from the
    #: resample interval alone and justified without reference to any collected
    #: trajectory.
    min_separator_distance_m: float = 1.0

    #: A qualifying event's NET heading change. UNCHANGED from the frozen
    #: contract; this amendment does not move it.
    qualifying_turn_deg: float = 30.0

    #: Below this displacement a tangent estimate is noise, not direction.
    min_tangent_displacement_m: float = 0.5

    epsilon: float = 1e-9

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["parameter_provenance"] = {
            "resample_interval_m": "REUSED from the original frozen rule",
            "low_curvature_segment_deg": "REUSED -- the frozen straight_deg",
            "qualifying_turn_deg": "UNCHANGED from the frozen collection contract",
            "min_tangent_displacement_m": "equals the resample interval",
            "min_separator_distance_m": ("NEW. Two resample intervals, so a separator is a "
                                         "run rather than a single sample. Derived from the "
                                         "resample interval; not derived from any trajectory."),
        }
        return d


TURN_SEMANTICS_V2 = TurnSemanticsV2()


@dataclasses.dataclass(frozen=True)
class TurnEvent:
    """One contiguous curvature event."""

    net_deg: float
    start_progress_m: float
    end_progress_m: float
    segments: int

    @property
    def qualifies(self) -> bool:
        return abs(self.net_deg) >= TURN_SEMANTICS_V2.qualifying_turn_deg

    def to_dict(self) -> dict[str, Any]:
        return {
            "net_deg": round(self.net_deg, 4),
            "start_progress_m": round(self.start_progress_m, 4),
            "end_progress_m": round(self.end_progress_m, 4),
            "segments": self.segments,
            "qualifies": self.qualifies,
        }


def _wrap_deg(a: float) -> float:
    return math.degrees(math.atan2(math.sin(math.radians(a)), math.cos(math.radians(a))))


def realised_turn_events(
    positions: np.ndarray,
    semantics: TurnSemanticsV2 = TURN_SEMANTICS_V2,
) -> tuple[list[TurnEvent], dict[str, Any]]:
    """Turn events in a travelled path, with the diagnostics behind the count.

    Returns ``(events, detail)``. ``detail`` carries the separator statistics,
    because "one event" and "three events that were never separated" are
    different situations and the count alone cannot distinguish them.
    """
    pts = np.asarray(positions, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError(f"positions must be (T, 2), got {pts.shape}")

    sampled, progress = resample_route(pts, semantics.resample_interval_m)
    if sampled.shape[0] < 3:
        return [], {"reason": "path too short for a tangent estimate",
                    "sampled_points": int(sampled.shape[0])}

    d = np.diff(sampled, axis=0)
    lengths = np.hypot(d[:, 0], d[:, 1])
    ang = np.degrees(np.arctan2(d[:, 1], d[:, 0]))

    events: list[TurnEvent] = []
    open_net = 0.0
    open_start: float | None = None
    open_segments = 0
    separator_run = 0.0
    turning_segments = 0
    low_curvature_segments = 0
    separator_runs: list[float] = []

    def close() -> None:
        nonlocal open_net, open_start, open_segments
        if open_start is not None and open_segments > 0:
            events.append(TurnEvent(net_deg=open_net, start_progress_m=open_start,
                                    end_progress_m=float(progress[min(len(progress) - 1,
                                                                      open_segments + 1)]),
                                    segments=open_segments))
        open_net = 0.0
        open_start = None
        open_segments = 0

    for k in range(1, len(ang)):
        if lengths[k] < semantics.min_tangent_displacement_m * 0.5:
            continue
        delta = _wrap_deg(float(ang[k]) - float(ang[k - 1]))
        seg_len = float(lengths[k])

        if abs(delta) < semantics.low_curvature_segment_deg:
            low_curvature_segments += 1
            separator_run += seg_len
            if separator_run >= semantics.min_separator_distance_m - semantics.epsilon:
                separator_runs.append(separator_run)
                close()
            continue

        turning_segments += 1
        # A sign reversal is itself a boundary: an S-curve is two events, not one
        # whose halves cancel.
        if open_start is not None and open_net != 0.0 and (delta > 0) != (open_net > 0):
            close()
        if separator_run > 0.0:
            separator_run = 0.0
        if open_start is None:
            open_start = float(progress[k])
        open_net += delta
        open_segments += 1

    close()

    qualifying = [e for e in events if e.qualifies]
    detail = {
        "semantics": semantics.to_dict(),
        "sampled_points": int(sampled.shape[0]),
        "segments": int(len(ang) - 1),
        "turning_segments": turning_segments,
        "low_curvature_segments": low_curvature_segments,
        "separator_runs_m": [round(r, 3) for r in separator_runs],
        "longest_separator_run_m": round(max(separator_runs), 3) if separator_runs else 0.0,
        "all_events": [e.to_dict() for e in events],
        "qualifying_events": [e.to_dict() for e in qualifying],
        "qualifying_count": len(qualifying),
        "why_a_count_alone_is_not_enough": (
            "one event and three events that were never separated are different "
            "situations; the separator statistics distinguish them"),
    }
    return qualifying, detail
