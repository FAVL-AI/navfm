"""Opt-in engineering recording sidecars; the legacy writer remains unchanged."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from ..writer import TrajectoryWriter

SCHEMA = "navfm_transition_recording_v1"


def validate_records(records: list[dict[str, Any]], n_frames: int) -> None:
    """Refuse missing, nonfinite, misindexed or temporally discontinuous records."""
    if len(records) != n_frames or not records:
        raise ValueError("transition/frame count mismatch or empty recording")
    previous = None
    for i, rec in enumerate(records):
        if rec["frame_index"] != i or rec["pre_image_index"] != (i - 1 if i else None):
            raise ValueError("transition image index mismatch")
        start, end = rec["time_before"], rec["time_after"]
        values = [start, end, *rec["pose_before"], *rec["pose_after"],
                  *rec["command_requested"], *rec["command_accepted"]]
        if not all(math.isfinite(float(x)) for x in values):
            raise ValueError("nonfinite transition")
        if end <= start or (previous is not None and abs(start - previous) > 1e-8):
            raise ValueError("non-increasing or discontinuous simulation time")
        for key in ("pose_before", "pose_after", "command_requested", "command_accepted"):
            if len(rec[key]) != 3:
                raise ValueError("transition vector shape")
        previous = end


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
                        policy_inputs="NOT_APPLICABLE_DEMONSTRATOR",
                        labels="observed position/yaw; commands are provenance, not waypoint labels")
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
