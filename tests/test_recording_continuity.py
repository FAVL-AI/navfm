"""Incremental transition validation, and what still belongs at close.

`validate_records()` originally ran only in `close()`, so a continuity defect at
step 5 of a 180-step engineering run was discovered only after the whole run had
been spent. Validation is now split:

    candidate transition
        -> incremental invariant validation   (append, before any state changes)
        -> persist accepted transition
        ...
        -> final whole-recording validation   (close)

This is defence in depth, not a relocation. Two invariants are genuinely
finalisation-only -- that the recording is non-empty, and that the transition
count equals the written frame count -- and both are still checked at close.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest

from navfm.collection import recording as recording_mod
from navfm.collection.recording import (
    RecordingTrajectoryWriter,
    TransitionRecordError,
    validate_records,
    validate_transition,
)
from navfm.isaac import collect as collect_mod
from navfm.isaac.app import SimConfig
from navfm.isaac.collect import CollectConfig, Collector
from navfm.isaac.randomize import RandomizationConfig
from navfm.isaac.robot import M3PRO
from navfm.planning import OccupancyGrid

HZ = 12.0
DT = 1.0 / HZ
INTENDED_STEPS = 180
#: run_episode() takes one settling step after the teleport, before the loop, so
#: loop iteration k is application step k + SETTLE_STEPS.
SETTLE_STEPS = 1
#: Break the clock on this loop iteration; its append is the one that must be refused.
BREAK_AT_LOOP_STEP = 5


def _record(i: int, dt: float = DT) -> dict[str, Any]:
    return dict(frame_index=i, pre_image_index=i - 1 if i else None,
                time_before=i * dt, time_after=(i + 1) * dt,
                pose_before=[i * 0.02, 0.0, 0.0], pose_after=[(i + 1) * 0.02, 0.0, 0.0],
                command_requested=[0.24, 0.0, 0.0], command_accepted=[0.24, 0.0, 0.0])


# --------------------------------------------------------------------------
# atomicity at the append boundary
# --------------------------------------------------------------------------

def test_refused_candidate_does_not_become_recorded_state(tmp_path: Path) -> None:
    """A rejected transition must leave the writer exactly as it was."""
    out = tmp_path / "trajectory"
    with pytest.raises(TransitionRecordError) as exc, RecordingTrajectoryWriter(out) as w:
        w.append(np.zeros((8, 8, 3), np.uint8), [0.0, 0.0], 0.0, transition=_record(0))
        w.append(np.zeros((8, 8, 3), np.uint8), [0.02, 0.0], 0.0, transition=_record(1))
        assert w.n_frames == 2
        bad = _record(2)
        bad["time_after"] = bad["time_before"]        # non-increasing
        try:
            w.append(np.zeros((8, 8, 3), np.uint8), [0.04, 0.0], 0.0, transition=bad)
        except TransitionRecordError:
            assert w.n_frames == 2, "the refused candidate advanced writer state"
            assert len(w._extras.get("transition", [])) == 2
            raise
    assert exc.value.frame_index == 2
    assert exc.value.stage == "incremental"
    assert "non-increasing simulation time" in str(exc.value)


def test_incremental_check_rejects_a_discontinuous_join(tmp_path: Path) -> None:
    out = tmp_path / "trajectory"
    with pytest.raises(TransitionRecordError) as exc, RecordingTrajectoryWriter(out) as w:
        w.append(np.zeros((8, 8, 3), np.uint8), [0.0, 0.0], 0.0, transition=_record(0))
        gapped = _record(1)
        gapped["time_before"] += 0.01                 # does not join the previous end
        w.append(np.zeros((8, 8, 3), np.uint8), [0.02, 0.0], 0.0, transition=gapped)
    assert "discontinuous simulation time" in str(exc.value)
    assert exc.value.frame_index == 1


# --------------------------------------------------------------------------
# finalisation-only invariants stay at close
# --------------------------------------------------------------------------

def test_count_mismatch_is_still_a_close_time_check() -> None:
    """Transition count vs frame count cannot be known from one candidate."""
    with pytest.raises(TransitionRecordError) as exc:
        validate_records([_record(0), _record(1)], 3)
    assert exc.value.stage == "final"
    assert "count mismatch" in str(exc.value)


def test_empty_recording_is_still_a_close_time_check() -> None:
    with pytest.raises(TransitionRecordError) as exc:
        validate_records([], 0)
    assert exc.value.stage == "final"
    assert "empty recording" in str(exc.value)


def test_per_record_invariants_are_reapplied_at_close() -> None:
    """A record that bypassed append must still be caught by the final pass."""
    rows = [_record(0), _record(1)]
    rows[1]["pre_image_index"] = 99
    with pytest.raises(TransitionRecordError) as exc:
        validate_records(rows, 2)
    assert exc.value.stage == "final"


def test_validate_transition_is_the_single_definition() -> None:
    """Incremental and final validation share one implementation, so they cannot drift."""
    bad = _record(0)
    bad["command_accepted"] = [0.1, 0.2]
    with pytest.raises(TransitionRecordError):
        validate_transition(bad, 0, None)
    with pytest.raises(TransitionRecordError):
        validate_records([bad], 1)


# --------------------------------------------------------------------------
# the 180-step early-failure case
# --------------------------------------------------------------------------

class _FakeRobot:
    def __init__(self) -> None:
        self.x = self.y = self.yaw = 0.0
        self.cmd = (0.0, 0.0, 0.0)

    def teleport(self, xy: Any, yaw: float) -> None:
        self.x, self.y, self.yaw = float(xy[0]), float(xy[1]), float(yaw)
        self.cmd = (0.0, 0.0, 0.0)

    def set_body_velocity(self, vx: float, vy: float, wz: float) -> None:
        self.cmd = (float(vx), float(vy), float(wz))

    def pose(self) -> tuple[np.ndarray, float]:
        return np.array([self.x, self.y], dtype=np.float64), self.yaw

    def rgb(self) -> np.ndarray:
        return np.full((48, 64, 3), 128, dtype=np.uint8)


class _FakeApp:
    """Advances the authoritative clock; optionally stalls it at one chosen step."""

    def __init__(self, robot: _FakeRobot, stall_at_step: int | None = None) -> None:
        self._t = 0.0
        self._robot = robot
        self.config = SimConfig(hz=HZ, headless=True)
        self.steps = 0
        self._stall_at = stall_at_step

    def step(self) -> float:
        self.steps += 1
        vx, vy, wz = self._robot.cmd
        self._robot.x += (vx * np.cos(self._robot.yaw) - vy * np.sin(self._robot.yaw)) * DT
        self._robot.y += (vx * np.sin(self._robot.yaw) + vy * np.cos(self._robot.yaw)) * DT
        self._robot.yaw += wz * DT
        if self.steps != self._stall_at:
            self._t += DT
        return self._t

    def sim_time(self) -> float:
        return self._t


def _spy_recording_writer():
    class _Spy(RecordingTrajectoryWriter):
        accepted: ClassVar[int] = 0
        refusals: ClassVar[list[TransitionRecordError]] = []

        def append(self, image: Any, position_xy: Any, yaw: float, **extras: Any) -> int:
            try:
                t = super().append(image, position_xy, yaw, **extras)
            except TransitionRecordError as exc:
                type(self).refusals.append(exc)
                raise
            type(self).accepted += 1
            return t

    _Spy.accepted = 0
    _Spy.refusals = []
    return _Spy


def _episode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stall_at: int | None):
    spy = _spy_recording_writer()
    monkeypatch.setattr(recording_mod, "RecordingTrajectoryWriter", spy)
    out_dir = tmp_path / "out"
    cfg = CollectConfig(scenes=["probe.usd"], episodes=1, max_steps=INTENDED_STEPS, seed=0)
    collector = Collector(out_dir, cfg, SimConfig(hz=HZ, headless=True), M3PRO,
                          RandomizationConfig(enabled=False))
    robot = _FakeRobot()
    app = _FakeApp(robot, stall_at)
    collector._robot = robot  # type: ignore[assignment]
    collector._app = app      # type: ignore[assignment]
    collector._grid = OccupancyGrid(np.zeros((160, 160), dtype=bool), 0.10, (0.0, 0.0))
    collector.record_transitions = True
    path = np.array([[1.0 + 0.1 * i, 1.0] for i in range(41)], dtype=np.float64)
    collector.fixed_route = (np.array([1.0, 1.0]), 0.0, np.array([5.0, 1.0]), path)
    result = collector.run_episode(0, "probe")
    return result, spy, app, out_dir


def test_continuity_failure_stops_at_the_offending_step_not_at_step_180(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run must end at the violating step, not after the full intended run."""
    result, spy, app, out_dir = _episode(
        tmp_path, monkeypatch, stall_at=SETTLE_STEPS + BREAK_AT_LOOP_STEP)

    # iterations 1..BREAK_AT_LOOP_STEP-1 are admitted; the one whose clock stalled is not
    assert spy.accepted == BREAK_AT_LOOP_STEP - 1, "frames were admitted past the violation"
    assert len(spy.refusals) == 1
    refusal = spy.refusals[0]
    assert refusal.frame_index == spy.accepted
    assert refusal.stage == "incremental"
    assert "non-increasing simulation time" in str(refusal)

    # measured by executed steps, never by elapsed time
    assert app.steps == SETTLE_STEPS + BREAK_AT_LOOP_STEP
    prevented = INTENDED_STEPS - BREAK_AT_LOOP_STEP
    assert prevented == 175, "the intended run was 180 loop steps"
    assert spy.accepted < INTENDED_STEPS / 10, "failure was not early"

    assert result.accepted is False
    assert "exception" in (result.reason or "")
    assert "non-increasing simulation time" in (result.reason or "")
    assert not list(out_dir.glob("*/traj_data.pkl")), "success artefact was written"
    assert not list(out_dir.glob("*/transitions.json"))


def test_a_valid_sequence_passes_both_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control: no violation means incremental and final validation both accept."""
    result, spy, app, out_dir = _episode(tmp_path, monkeypatch, stall_at=None)

    assert result.accepted is True, result.reason
    assert spy.refusals == []
    assert spy.accepted == result.n_frames
    # one settling step precedes the loop; every loop step produces exactly one frame
    assert app.steps == result.n_frames + SETTLE_STEPS

    sidecar = json.loads(next(out_dir.glob("*/transitions.json")).read_text())
    rows = sidecar["records"]
    assert len(rows) == result.n_frames
    assert [r["frame_index"] for r in rows] == list(range(result.n_frames))
    assert [r["pre_image_index"] for r in rows] == [None, *range(result.n_frames - 1)]
    for previous, nxt in pairwise(rows):
        assert nxt["time_before"] == pytest.approx(previous["time_after"], abs=1e-8)
        assert nxt["time_after"] > nxt["time_before"]
    # the sidecar still aligns with the pickle the official loaders read
    import pickle
    with next(out_dir.glob("*/traj_data.pkl")).open("rb") as fh:
        data = pickle.load(fh)
    assert set(data) == {"position", "yaw"}
    np.testing.assert_allclose(
        np.array([r["pose_after"][:2] for r in rows]), data["position"])


def test_default_scientific_path_is_untouched_by_incremental_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The new check lives on the engineering writer only.

    The default collector uses TrajectoryWriter, whose append takes no
    ``transition`` and gains no validation, so the scientific path is unchanged.
    """
    w = collect_mod.TrajectoryWriter(tmp_path / "plain")
    w.open()
    # a transition that the engineering writer would refuse outright
    refused_by_engineering = _record(0)
    refused_by_engineering["time_after"] = refused_by_engineering["time_before"]
    with pytest.raises(TransitionRecordError):
        validate_transition(refused_by_engineering, 0, None)
    # the plain writer neither validates it nor is offered one: sim_time is its keyword
    w.append(np.zeros((8, 8, 3), np.uint8), [0.0, 0.0], 0.0, sim_time=0.1)
    assert w.n_frames == 1
    assert w._extras["sim_time"] == [0.1]
    assert "transition" not in w._extras
    w.abort()
