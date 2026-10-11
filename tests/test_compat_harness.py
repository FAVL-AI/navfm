"""The compatibility harness must fail on invalid input, not only pass on valid.

A harness that only ever reports PASS certifies nothing, and this one exists to
gate Prof. Bo's two pilot trajectories — the single point at which "our collected
data is compatible" becomes a claim. So every required check is exercised in
both directions: a compliant fixture passes it, and a fixture broken in exactly
that one way fails it and takes the overall result to BLOCKED.

These fixtures are constructed in `tmp_path` and are **not** trajectories. They
are not collected data, not pilot evidence, and none of them is written anywhere
a later reader could mistake for a dataset.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pytest

from navfm.compat import check_trajectory

FRAMES = 20


def _write(traj: Path, *, frames: int = FRAMES, position=None, yaw=None, images=True) -> Path:
    """A minimal Option 1 trajectory: numbered JPEGs plus position and yaw."""
    traj.mkdir(parents=True, exist_ok=True)
    if images:
        from PIL import Image

        for i in range(frames):
            Image.new("RGB", (85, 64), (i * 5 % 256, 90, 140)).save(traj / f"{i}.jpg")
    if position is None:
        position = np.stack([np.linspace(0.0, 2.0, frames), np.linspace(0.0, 0.4, frames)], axis=1)
    if yaw is None:
        yaw = np.linspace(0.0, 0.3, frames)
    with open(traj / "traj_data.pkl", "wb") as fh:
        pickle.dump({"position": np.asarray(position), "yaw": np.asarray(yaw)}, fh)
    return traj


def _run(traj: Path):
    return check_trajectory(
        traj,
        source="unit-test fixture",
        purpose="harness negative testing",
        collected_by_project=False,
        pilot_evidence=False,
    )


def _result(report, name: str) -> bool:
    matching = [c for c in report.checks if c.name == name]
    assert matching, f"no check named {name!r}; the harness lost a required check"
    return matching[0].passed


class TestAValidFixturePasses:
    """The control. Without it, the negatives below could pass vacuously."""

    @pytest.mark.upstream
    def test_compliant_trajectory_passes_every_data_check(self, tmp_path: Path) -> None:
        report = _run(_write(tmp_path / "t0"))
        for name in (
            "traj_data_pkl_exists",
            "numbered_images_exist",
            "image_numbering_contiguous",
            "images_readable",
            "position_numeric",
            "position_shape_T2",
            "yaw_numeric",
            "yaw_shape_T",
            "finite_values",
            "sequence_consistency",
            "project_validator",
        ):
            assert _result(report, name), f"{name} failed on a compliant fixture"

    def test_provenance_fields_are_carried_into_the_report(self, tmp_path: Path) -> None:
        """A report that loses its provenance can be mistaken for pilot evidence."""
        report = _run(_write(tmp_path / "t0"))
        assert report.collected_by_project is False
        assert report.pilot_evidence is False
        assert report.source == "unit-test fixture"
        assert "collected_by_project" in report.as_dict()


class TestRequiredChecksFailOnBrokenInput:
    """The eight mandated negatives, one broken thing each."""

    def test_missing_traj_data_pkl(self, tmp_path: Path) -> None:
        traj = _write(tmp_path / "t0")
        (traj / "traj_data.pkl").unlink()
        report = _run(traj)
        assert not _result(report, "traj_data_pkl_exists")
        assert report.overall == "BLOCKED"

    def test_missing_image(self, tmp_path: Path) -> None:
        """A hole in the middle: the images no longer index the poses."""
        traj = _write(tmp_path / "t0")
        (traj / "7.jpg").unlink()
        report = _run(traj)
        assert not _result(report, "image_numbering_contiguous")
        assert not _result(report, "sequence_consistency")
        assert report.overall == "BLOCKED"

    def test_bad_image_numbering(self, tmp_path: Path) -> None:
        """Numbering that starts at 1 loses frame 0 silently."""
        traj = _write(tmp_path / "t0")
        (traj / "0.jpg").rename(traj / f"{FRAMES}.jpg")
        report = _run(traj)
        assert not _result(report, "image_numbering_contiguous")
        assert report.overall == "BLOCKED"

    def test_wrong_position_shape(self, tmp_path: Path) -> None:
        traj = _write(tmp_path / "t0", position=np.zeros((FRAMES, 3)))
        report = _run(traj)
        assert not _result(report, "position_shape_T2")
        assert report.overall == "BLOCKED"

    def test_wrong_yaw_shape(self, tmp_path: Path) -> None:
        traj = _write(tmp_path / "t0", yaw=np.zeros((FRAMES, 3)))
        report = _run(traj)
        assert not _result(report, "yaw_shape_T")
        assert report.overall == "BLOCKED"

    @pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
    def test_non_finite_values(self, tmp_path: Path, bad: float) -> None:
        yaw = np.linspace(0.0, 0.3, FRAMES)
        yaw[3] = bad
        report = _run(_write(tmp_path / "t0", yaw=yaw))
        assert not _result(report, "finite_values")
        assert report.overall == "BLOCKED"

    def test_multi_valued_scalar_cell(self, tmp_path: Path) -> None:
        """The truncation case: a cell holding two values must not yield one.

        This is the defect `navfm.trajio` refuses rather than repairs, reached
        here through the harness so that the refusal is visible in a report
        rather than only in a library exception.
        """
        yaw = np.empty(FRAMES, dtype=object)
        for i in range(FRAMES):
            yaw[i] = np.array([float(i) / FRAMES])
        yaw[4] = np.array([1.0, 99.0])
        report = _run(_write(tmp_path / "t0", yaw=yaw))
        assert not _result(report, "yaw_numeric")
        assert report.overall == "BLOCKED"

    def test_unreadable_image(self, tmp_path: Path) -> None:
        """A file that exists and is named correctly but is not a JPEG."""
        traj = _write(tmp_path / "t0")
        (traj / "9.jpg").write_bytes(b"this is not a JPEG")
        report = _run(traj)
        assert not _result(report, "images_readable")
        assert report.overall == "BLOCKED"


class TestOverallIsConjunctive:
    def test_a_majority_of_passes_does_not_produce_pass(self, tmp_path: Path) -> None:
        """No "green if most passed". This is the whole point of the harness.

        One corrupt frame out of twenty leaves most checks passing and still
        must yield BLOCKED. The count is asserted loosely on purpose: image
        decodability is deliberately checked twice — once by the harness and
        again by `navfm.validate` — so a single corrupt file fails two checks,
        and pinning an exact number here would encode that overlap as a
        requirement rather than an artefact of it.
        """
        traj = _write(tmp_path / "t0")
        (traj / "9.jpg").write_bytes(b"not a JPEG")
        report = _run(traj)
        passed = sum(1 for c in report.checks if c.passed)
        assert passed >= len(report.checks) - 3, "expected most checks to still pass"
        assert passed < len(report.checks)
        assert report.overall == "BLOCKED"

    def test_released_go_stanford_representation_is_refused(self, tmp_path: Path) -> None:
        """The released corpus layout is object-dtype and does NOT satisfy Option 1
        (F13, `docs/DATA_CONTRACT.md`). The harness must say so rather than
        quietly accepting it, because the pilot's claim is about Option 1."""
        position = np.empty((FRAMES, 2), dtype=object)
        for i in range(FRAMES):
            for j in range(2):
                position[i, j] = np.float64(i + j)
        yaw = np.empty(FRAMES, dtype=object)
        for i in range(FRAMES):
            yaw[i] = np.array([float(i) / FRAMES])
        report = _run(_write(tmp_path / "t0", position=position, yaw=yaw))
        assert not _result(report, "project_validator")
        assert report.overall == "BLOCKED"
