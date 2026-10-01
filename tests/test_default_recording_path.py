"""Regression coverage for the DEFAULT collection path.

The engineering recording work added an opt-in branch that swaps
``TrajectoryWriter`` for ``RecordingTrajectoryWriter`` and replaces the
``sim_time=`` append keyword with ``transition=``. Nothing proved that the
default branch -- the one every scientific collection uses -- still constructs
``TrajectoryWriter`` and still records ``sim_time``. That was the main
default-path regression gap.

These tests drive the real ``Collector.run_episode`` control flow with fakes at
the external-runtime boundary only (application and robot). Isaac is never
launched: launching a simulator to prove a Python branch would measure the
wrong thing.

The negative control is not manufactured. Engineering mode is itself the
counterfactual -- it is real production behaviour in which
``TrajectoryWriter`` is NOT constructed and ``sim_time`` is NOT written -- so
``test_engineering_mode_is_the_counterfactual`` shows both detectors firing.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest

from navfm.isaac import collect as collect_mod
from navfm.isaac.app import SimConfig
from navfm.isaac.collect import CollectConfig, Collector
from navfm.isaac.randomize import RandomizationConfig
from navfm.isaac.robot import M3PRO
from navfm.planning import OccupancyGrid

HZ = 12.0
DT = 1.0 / HZ


class _FakeRobot:
    """SE(2) integrator standing in for the articulation at the runtime boundary."""

    def __init__(self) -> None:
        self.x = self.y = self.yaw = 0.0
        self.cmd = (0.0, 0.0, 0.0)
        self.teleports = 0

    def teleport(self, xy: Any, yaw: float) -> None:
        self.x, self.y = float(xy[0]), float(xy[1])
        self.yaw = float(yaw)
        self.cmd = (0.0, 0.0, 0.0)
        self.teleports += 1

    def set_body_velocity(self, vx: float, vy: float, wz: float) -> None:
        self.cmd = (float(vx), float(vy), float(wz))

    def integrate(self, dt: float) -> None:
        vx, vy, wz = self.cmd
        self.x += (vx * np.cos(self.yaw) - vy * np.sin(self.yaw)) * dt
        self.y += (vx * np.sin(self.yaw) + vy * np.cos(self.yaw)) * dt
        self.yaw += wz * dt

    def pose(self) -> tuple[np.ndarray, float]:
        return np.array([self.x, self.y], dtype=np.float64), self.yaw

    def rgb(self) -> np.ndarray:
        return np.full((48, 64, 3), 128, dtype=np.uint8)


class _FakeApp:
    """Advances the authoritative simulation clock exactly as IsaacApp.step() does."""

    def __init__(self, robot: _FakeRobot) -> None:
        self._t = 0.0
        self._robot = robot
        self.config = SimConfig(hz=HZ, headless=True)
        self.steps = 0

    def step(self) -> float:
        self._robot.integrate(DT)
        self._t += DT
        self.steps += 1
        return self._t

    def sim_time(self) -> float:
        return self._t


def _spy_writer_class(record: list[dict[str, Any]]):
    """A TrajectoryWriter subclass that records how it was used, then behaves normally."""

    class _Spy(collect_mod.TrajectoryWriter):  # type: ignore[misc,name-defined]
        constructions: ClassVar[list[Path]] = []

        def __init__(self, path: Path, **kw: Any) -> None:
            type(self).constructions.append(Path(path))
            super().__init__(path, **kw)

        def append(self, image: Any, position_xy: Any, yaw: float, **extras: Any) -> int:
            record.append(dict(extras))
            return super().append(image, position_xy, yaw, **extras)

    _Spy.constructions = []
    return _Spy


def _run_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, record_transitions: bool
) -> tuple[Any, list[dict[str, Any]], Any, Path]:
    appends: list[dict[str, Any]] = []
    spy = _spy_writer_class(appends)
    monkeypatch.setattr(collect_mod, "TrajectoryWriter", spy)

    out_dir = tmp_path / "out"
    cfg = CollectConfig(scenes=["probe.usd"], episodes=1, max_steps=400, seed=0)
    collector = Collector(
        out_dir, cfg, SimConfig(hz=HZ, headless=True), M3PRO,
        RandomizationConfig(enabled=False),
    )
    robot = _FakeRobot()
    collector._robot = robot          # type: ignore[assignment]
    collector._app = _FakeApp(robot)  # type: ignore[assignment]
    collector._grid = OccupancyGrid(np.zeros((120, 120), dtype=bool), 0.10, (0.0, 0.0))
    collector.record_transitions = record_transitions

    start = np.array([1.0, 1.0])
    goal = np.array([5.0, 1.0])
    path = np.array([[1.0 + 0.1 * i, 1.0] for i in range(41)], dtype=np.float64)
    collector.fixed_route = (start, 0.0, goal, path)

    result = collector.run_episode(0, "probe")
    return result, appends, spy, out_dir


def _loaded(out_dir: Path) -> dict[str, Any]:
    pkl = next(out_dir.glob("*/traj_data.pkl"))
    with pkl.open("rb") as fh:
        return pickle.load(fh)


# --------------------------------------------------------------------------
# the default path
# --------------------------------------------------------------------------

def test_record_transitions_is_off_by_default() -> None:
    """The engineering branch must be opt-in at the attribute level."""
    collector = Collector(
        Path("/nonexistent"), CollectConfig(), SimConfig(hz=HZ, headless=True),
        M3PRO, RandomizationConfig(enabled=False),
    )
    assert collector.record_transitions is False


def test_default_path_constructs_trajectory_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _appends, spy, _out = _run_episode(
        tmp_path, monkeypatch, record_transitions=False)
    assert result.accepted is True, result.reason
    assert len(spy.constructions) == 1, "the default path did not construct TrajectoryWriter"


def test_default_path_appends_sim_time_on_every_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, appends, _spy, _out = _run_episode(
        tmp_path, monkeypatch, record_transitions=False)
    assert result.accepted is True, result.reason
    assert appends, "no frame was appended"
    assert all("sim_time" in kw for kw in appends)
    assert not any("transition" in kw for kw in appends)
    times = [kw["sim_time"] for kw in appends]
    assert all(isinstance(t, float) for t in times)
    assert times == sorted(times)
    assert times[0] > 0.0


def test_default_traj_data_carries_the_legacy_sim_time_array(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The serialised default record keeps sim_time and metadata in the pickle.

    This is the legacy shape. docs/DATA_CONTRACT.md asks for two keys with
    provenance beside them, and the engineering writer complies with that; the
    default writer does not, and changing it is out of scope here. This test
    pins the default shape so a future change to it is deliberate.
    """
    result, _appends, _spy, out_dir = _run_episode(
        tmp_path, monkeypatch, record_transitions=False)
    assert result.accepted is True, result.reason
    data = _loaded(out_dir)
    assert "sim_time" in data
    assert len(data["sim_time"]) == len(data["position"]) == result.n_frames
    assert np.all(np.diff(np.asarray(data["sim_time"], dtype=np.float64)) > 0)
    assert "metadata" in data
    assert "recording_schema" not in data.get("metadata", {})
    assert data["metadata"].get("run_class") != "ENGINEERING_COLLECTION_VALIDATION"


# --------------------------------------------------------------------------
# discriminating control
# --------------------------------------------------------------------------

def test_engineering_mode_is_the_counterfactual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both default-path detectors fire when the engineering branch is taken.

    Engineering mode is real production behaviour, so this proves the two tests
    above are discriminating without modifying production code to manufacture a
    failure: here TrajectoryWriter is never constructed, no append carries
    sim_time, and the pickle has neither sim_time nor metadata.
    """
    result, appends, spy, out_dir = _run_episode(
        tmp_path, monkeypatch, record_transitions=True)
    assert result.accepted is True, result.reason
    # TrajectoryWriter is never constructed, so the spy sees no construction and
    # no append at all -- the engineering writer is a different class entirely.
    assert len(spy.constructions) == 0
    assert appends == []
    data = _loaded(out_dir)
    assert set(data) == {"position", "yaw"}
    assert "sim_time" not in data
    assert "metadata" not in data
    # the transitions live in the sidecar instead
    sidecar = json.loads(
        next(out_dir.glob("*/transitions.json")).read_text())
    assert sidecar["schema"] == "navfm_transition_recording_v1"
    assert len(sidecar["records"]) == result.n_frames
