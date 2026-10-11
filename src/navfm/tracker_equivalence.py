"""Behavioural equivalence for the target-selection seam.

Introducing an injection seam is a refactor, and a refactor inside the tracker
is exactly the confound the intervention cannot afford: if the seam changed
behaviour even slightly, a later A/B result would mix "arc-length interpolated
targeting" with "we rewrote the tracker". So the seam has to be shown
behaviour-neutral before the treatment exists, while it is still impossible to
choose the answer.

Two things make that proof mean something.

**The reference is the pre-seam code itself, taken from git.** Comparing the
new default path against the new injected path would be close to a tautology --
after the refactor they are the same call. The comparison that carries weight is
against ``PurePursuit`` as it stood at the pinned commit before the seam
existed, loaded from the object store and run side by side.

**State evolution is compared, not just outputs.** Target selection advances an
index that ``finished`` reads, so a selector can agree on the first target and
diverge later. Equality of commands at one step is not equality of behaviour;
the whole sequence of indices is compared, step by step, from an identical
initial state.

The comparators fail closed. Malformed or mismatched inputs return a recorded
``EQUIVALENCE_REFUSED``, because a traceback where a verdict belongs is not a
refusal -- the lesson the environment guard's own refusal paths taught twice.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np

__all__ = [
    "COMMAND_CHANNELS",
    "TARGET_CHANNELS",
    "compare_sequences",
    "equivalence_refused",
    "run_command_sequence",
    "run_target_sequence",
]

#: Compared after every ``step``. Covers the command outputs, the predicates
#: the episode loop branches on, and the index the predicates read.
COMMAND_CHANNELS: tuple[str, ...] = (
    "vx",
    "vy",
    "wz",
    "done",
    "index_after",
    "finished_after",
)

#: Compared after every ``target``. Covers the selection and the state
#: transition it performs.
TARGET_CHANNELS: tuple[str, ...] = (
    "target_x",
    "target_y",
    "index_after",
    "finished_after",
    "target_distance",
    "target_bearing",
    "heading_error",
)


class _Tracker(Protocol):
    _idx: int
    finished: bool

    def target(self, position: np.ndarray) -> np.ndarray: ...

    def step(self, position: np.ndarray, yaw: float) -> tuple[float, float, float, bool]: ...


def equivalence_refused(reason: str, **detail: Any) -> dict[str, Any]:
    """A structured refusal. Never a traceback as the scientific verdict."""
    return {
        "EQUIVALENCE": "EQUIVALENCE_REFUSED",
        "reason": reason,
        "detail": detail,
        "note": (
            "refused rather than raised: an uncontrolled exception is not a "
            "recorded scientific result, and a harness that crashes has not "
            "compared anything"
        ),
    }


def _poses(poses: Any) -> np.ndarray | None:
    try:
        arr = np.asarray(poses, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if arr.ndim != 2 or arr.shape[0] == 0 or arr.shape[1] != 3:
        return None
    if not np.all(np.isfinite(arr)):
        return None
    return arr


def run_command_sequence(tracker: Any, poses: Any) -> dict[str, Any]:
    """Drive ``step`` over a pose trace, recording outputs and state after each.

    The trace is an offline input, never a replay: each pose comes from the
    recording, so no dynamics are integrated and the tracker's own commands do
    not move it.
    """
    arr = _poses(poses)
    if arr is None:
        return equivalence_refused(
            "pose trace is not a finite (N, 3) array of x, y, yaw",
            received_type=type(poses).__name__,
        )
    for name in ("step", "target"):
        if not callable(getattr(tracker, name, None)):
            return equivalence_refused(f"tracker has no callable {name}")

    records: list[dict[str, Any]] = []
    for row in arr:
        position = np.array([row[0], row[1]], dtype=np.float64)
        yaw = float(row[2])
        vx, vy, wz, done = tracker.step(position, yaw)
        records.append(
            {
                "vx": float(vx),
                "vy": float(vy),
                "wz": float(wz),
                "done": bool(done),
                "index_after": int(tracker._idx),
                "finished_after": bool(tracker.finished),
            }
        )
    return {"EQUIVALENCE": "SEQUENCE_RECORDED", "channels": COMMAND_CHANNELS, "records": records}


def run_target_sequence(tracker: Any, poses: Any) -> dict[str, Any]:
    """Drive ``target`` over a pose trace, recording the selection and the
    state transition it performs.

    Kept separate from the command pass on purpose: ``step`` calls ``target``
    internally, so asking for the target and then stepping would advance the
    index twice and compare a trajectory neither implementation ever takes.
    """
    arr = _poses(poses)
    if arr is None:
        return equivalence_refused(
            "pose trace is not a finite (N, 3) array of x, y, yaw",
            received_type=type(poses).__name__,
        )
    if not callable(getattr(tracker, "target", None)):
        return equivalence_refused("tracker has no callable target")

    records: list[dict[str, Any]] = []
    for row in arr:
        position = np.array([row[0], row[1]], dtype=np.float64)
        yaw = float(row[2])
        point = np.asarray(tracker.target(position), dtype=np.float64)
        delta = point - position
        cos_y, sin_y = math.cos(-yaw), math.sin(-yaw)
        body_x = cos_y * delta[0] - sin_y * delta[1]
        body_y = sin_y * delta[0] + cos_y * delta[1]
        records.append(
            {
                "target_x": float(point[0]),
                "target_y": float(point[1]),
                "index_after": int(tracker._idx),
                "finished_after": bool(tracker.finished),
                "target_distance": float(math.hypot(body_x, body_y)),
                "target_bearing": float(math.atan2(delta[1], delta[0])),
                "heading_error": float(math.atan2(body_y, body_x)),
            }
        )
    return {"EQUIVALENCE": "SEQUENCE_RECORDED", "channels": TARGET_CHANNELS, "records": records}


def compare_sequences(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    left_label: str,
    right_label: str,
    channels: Sequence[str],
    tolerance: float = 0.0,
) -> dict[str, Any]:
    """Exact equality by default. Any tolerance must be argued for, not fitted.

    ``tolerance`` exists so the caller can state one explicitly; it defaults to
    zero because two paths executing the same arithmetic should agree bitwise,
    and a tolerance chosen after seeing a discrepancy is a discrepancy that was
    argued away rather than explained.
    """
    for side, payload in ((left_label, left), (right_label, right)):
        if payload.get("EQUIVALENCE") == "EQUIVALENCE_REFUSED":
            return equivalence_refused(f"{side} sequence was refused", upstream=payload)
        if "records" not in payload:
            return equivalence_refused(f"{side} sequence carries no records")

    a: list[dict[str, Any]] = left["records"]
    b: list[dict[str, Any]] = right["records"]
    if len(a) != len(b):
        return equivalence_refused(
            "sequences have different lengths, so no step-by-step comparison exists",
            **{left_label: len(a), right_label: len(b)},
        )
    if not a:
        return equivalence_refused("sequences are empty; nothing was compared")

    mismatches: list[dict[str, Any]] = []
    per_channel = dict.fromkeys(channels, 0)
    max_difference = 0.0
    for step, (x, y) in enumerate(zip(a, b, strict=True)):
        for channel in channels:
            if channel not in x or channel not in y:
                mismatches.append(
                    {"step": step, "channel": channel, left_label: x.get(channel, "<ABSENT>"),
                     right_label: y.get(channel, "<ABSENT>"), "kind": "MISSING_CHANNEL"}
                )
                per_channel[channel] += 1
                continue
            lhs, rhs = x[channel], y[channel]
            if isinstance(lhs, bool) or isinstance(rhs, bool):
                equal = lhs == rhs
                difference: float | None = None
            elif isinstance(lhs, (int, float)) and isinstance(rhs, (int, float)):
                difference = abs(float(lhs) - float(rhs))
                max_difference = max(max_difference, difference)
                equal = lhs == rhs if tolerance == 0.0 else difference <= tolerance
            else:
                equal = lhs == rhs
                difference = None
            if not equal:
                per_channel[channel] += 1
                if len(mismatches) < 50:
                    mismatches.append(
                        {"step": step, "channel": channel, left_label: lhs,
                         right_label: rhs, "difference": difference,
                         "kind": "VALUE_MISMATCH"}
                    )

    total = sum(per_channel.values())
    return {
        "EQUIVALENCE": "PASS" if total == 0 else "FAIL",
        "left": left_label,
        "right": right_label,
        "steps_compared": len(a),
        "channels_compared": list(channels),
        "mismatch_total": total,
        "mismatches_by_channel": dict(per_channel),
        "max_numerical_difference": max_difference,
        "tolerance_used": tolerance,
        "numerical_standard": (
            "exact equality" if tolerance == 0.0 else f"absolute tolerance {tolerance}"
        ),
        "first_mismatches": mismatches[:50],
    }
