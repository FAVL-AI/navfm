"""Opt-in engineering recording sidecars; the legacy writer remains unchanged."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from ..writer import TrajectoryWriter

SCHEMA = "navfm_transition_recording_v1"

#: Vector fields that must each carry exactly three components.
_VECTORS = ("pose_before", "pose_after", "command_requested", "command_accepted")

#: Tolerance for "this record starts where the previous one ended".
_TIME_JOIN_TOLERANCE = 1e-8


class TransitionRecordError(ValueError):
    """A transition record violated an invariant.

    A ``ValueError`` subclass so existing callers -- including the collector's
    ``except Exception`` episode guard and the tests that assert ``ValueError`` --
    keep working unchanged, while carrying enough detail to say which record
    failed and how.
    """

    def __init__(
        self,
        reason: str,
        *,
        stage: str,
        frame_index: int | None = None,
        expected: object = None,
        observed: object = None,
    ) -> None:
        self.reason = reason
        self.stage = stage
        self.frame_index = frame_index
        self.expected = expected
        self.observed = observed
        detail = f"{stage}: {reason}"
        if frame_index is not None:
            detail += f" at frame_index {frame_index}"
        if expected is not None or observed is not None:
            detail += f" (expected {expected!r}, observed {observed!r})"
        super().__init__(detail)


def validate_transition(
    record: dict[str, Any],
    frame_index: int,
    previous_time_after: float | None,
    *,
    stage: str = "incremental",
) -> None:
    """Per-record invariants, every one checkable the moment a candidate arrives.

    Called from ``RecordingTrajectoryWriter.append`` BEFORE the candidate becomes
    recorded state, so a continuity defect is refused at the offending step
    instead of being discovered after a whole run has been spent. The same
    function is reapplied by :func:`validate_records` at close, so incremental
    and final validation cannot drift apart: there is one definition of these
    invariants.
    """
    if record.get("frame_index") != frame_index:
        raise TransitionRecordError(
            "transition image index mismatch", stage=stage, frame_index=frame_index,
            expected=frame_index, observed=record.get("frame_index"))
    expected_pre = frame_index - 1 if frame_index else None
    if record.get("pre_image_index") != expected_pre:
        raise TransitionRecordError(
            "transition image index mismatch", stage=stage, frame_index=frame_index,
            expected=expected_pre, observed=record.get("pre_image_index"))
    start, end = record["time_before"], record["time_after"]
    values = [start, end, *record["pose_before"], *record["pose_after"],
              *record["command_requested"], *record["command_accepted"]]
    if not all(math.isfinite(float(x)) for x in values):
        raise TransitionRecordError(
            "nonfinite transition", stage=stage, frame_index=frame_index)
    if end <= start:
        raise TransitionRecordError(
            "non-increasing simulation time", stage=stage, frame_index=frame_index,
            expected=f"time_after > {start!r}", observed=end)
    if (previous_time_after is not None
            and abs(start - previous_time_after) > _TIME_JOIN_TOLERANCE):
        raise TransitionRecordError(
            "discontinuous simulation time", stage=stage, frame_index=frame_index,
            expected=previous_time_after, observed=start)
    for key in _VECTORS:
        if len(record[key]) != 3:
            raise TransitionRecordError(
                "transition vector shape", stage=stage, frame_index=frame_index,
                expected=3, observed=len(record[key]))


def validate_records(records: list[dict[str, Any]], n_frames: int) -> None:
    """Whole-recording validation at close. Defence in depth, not a replacement.

    Two invariants here are genuinely finalisation-only and cannot be known from
    a single candidate: that the recording is non-empty, and that the number of
    transitions equals the number of written frames. Everything else is the
    per-record set, reapplied so the final state is validated as a whole even if
    a record reached the buffer by some path that bypassed ``append``.
    """
    if not records:
        raise TransitionRecordError("empty recording", stage="final")
    if len(records) != n_frames:
        raise TransitionRecordError(
            "transition/frame count mismatch", stage="final",
            expected=n_frames, observed=len(records))
    previous = None
    for i, rec in enumerate(records):
        validate_transition(rec, i, previous, stage="final")
        previous = rec["time_after"]


class RecordingTrajectoryWriter(TrajectoryWriter):
    """Use the tested image/pose writer with extras moved to versioned sidecars.

    The protected staging buffers are deliberately used at this narrow boundary;
    roundtrip tests assert the inherited writer still writes only position/yaw.
    Existing TrajectoryWriter callers and historical datasets are untouched.
    """

    def open(self) -> None:
        if self.path.exists():
            raise FileExistsError(self.path)
        super().open()

    def append(self, image: Any, position_xy: Any, yaw: float, **extras: Any) -> int:
        """Validate a candidate transition before it can become recorded state.

        The check runs before ``super().append()``, which is what writes the JPEG
        and extends the position/yaw/extras buffers. So a refused candidate
        leaves the writer exactly as it was: nothing persisted, nothing counted,
        and the previously accepted records still valid.
        """
        transition = extras.get("transition")
        if transition is not None:
            recorded = self._extras.get("transition", [])
            previous = recorded[-1]["time_after"] if recorded else None
            validate_transition(transition, self.n_frames, previous)
        return super().append(image, position_xy, yaw, **extras)

    def close(self) -> Path:
        if self._closed:
            return super().close()
        if self.path.exists():
            raise FileExistsError(self.path)
        records = self._extras.get("transition", [])
        validate_records(records, self.n_frames)
        if self._staging is None:
            raise RuntimeError("writer not opened")
        metadata = dict(self.metadata)
        metadata.update(recording_schema=SCHEMA, n_frames=self.n_frames,
                        labels="observed position/yaw; commands are provenance, not waypoint labels")
        metadata.setdefault("policy_inputs", "NOT_APPLICABLE_DEMONSTRATOR")
        for name, value in (("metadata.json", metadata), ("transitions.json", {
            "schema": SCHEMA,
            "alignment": "command[i] follows pose_before at time_before and precedes image i / pose_after at time_after; image i-1 is the preceding saved observation; first command has no preceding saved RGB",
            "records": records,
        })):
            with (self._staging / name).open("x") as fh:
                json.dump(value, fh, indent=2, allow_nan=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
        self.metadata = {}
        self._extras = {}
        return super().close()
