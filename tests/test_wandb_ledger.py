"""Tests for the evidence ledger.

The ledger's job is to stay honest when the repository changes, so the tests are
about the two ways it could quietly stop doing that: publishing a table that
silently fails, and letting a run that makes no model claim be read as one.

Nothing here contacts Weights & Biases. The parts that matter -- visual
generation, the claimability rule, epoch accounting -- are ordinary Python and
are tested as such.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image as PILImage

from navfm.wandb_ledger import CLAIMABLE, TrainingRunLogger, motion_trace_plot, trajectory_gif


class TestVisuals:
    """A claim about a viewpoint should be lookable-at."""

    def _frames(self, d, n=8):
        for i in range(n):
            arr = np.full((24, 32, 3), i * 12, dtype=np.uint8)
            PILImage.fromarray(arr).save(d / f"{i}.jpg", quality=90)

    def test_a_trajectory_animates(self, tmp_path) -> None:
        self._frames(tmp_path)
        out = trajectory_gif(tmp_path, tmp_path / "out.gif")
        assert out is not None and out.is_file() and out.stat().st_size > 0
        with PILImage.open(out) as im:
            assert getattr(im, "n_frames", 1) > 1, "a still image is not evidence of motion"

    def test_no_frames_returns_none_rather_than_raising(self, tmp_path) -> None:
        """A missing visual must not take down a publish."""
        assert trajectory_gif(tmp_path, tmp_path / "out.gif") is None

    def test_non_numeric_filenames_are_ignored(self, tmp_path) -> None:
        """`goal.jpg` sits beside the numbered frames and is not part of the run."""
        self._frames(tmp_path, 4)
        PILImage.fromarray(np.zeros((24, 32, 3), np.uint8)).save(tmp_path / "goal.jpg")
        out = trajectory_gif(tmp_path, tmp_path / "o.gif")
        assert out is not None
        with PILImage.open(out) as im:
            assert im.n_frames == 4

    def test_the_path_plot_is_drawn_from_recorded_poses(self, tmp_path) -> None:
        pos = np.stack([np.linspace(0, 5, 40), np.linspace(0, 0.8, 40)], axis=1)
        yaw = np.linspace(0.0, 0.66, 40)
        out = motion_trace_plot(pos, yaw, tmp_path / "trace.png", title="pilot")
        assert out.is_file() and out.stat().st_size > 1000


class TestClaimability:
    """A smoke test must not become a results row by being described differently."""

    def test_only_two_classes_may_back_a_claim(self) -> None:
        assert {"baseline_evaluation", "registered_experiment"} == CLAIMABLE

    @pytest.mark.parametrize("cls", ["baseline_evaluation", "registered_experiment"])
    def test_claimable_classes_are_marked_claimable(self, cls: str) -> None:
        assert TrainingRunLogger(model="vint", dataset="go_stanford",
                                 evidence_class=cls, total_epochs=1).claimable is True

    @pytest.mark.parametrize(
        "cls", ["pipeline_smoke_test", "random_init_control", "checkpoint_sanity",
                "diagnostic_unregistered"],
    )
    def test_engineering_classes_are_not_claimable(self, cls: str) -> None:
        assert TrainingRunLogger(model="vint", dataset="go_stanford",
                                 evidence_class=cls, total_epochs=1).claimable is False

    def test_an_undeclared_class_is_refused_at_construction(self) -> None:
        """Refused when the run is defined, not when its output is reviewed."""
        with pytest.raises(ValueError, match="unknown evidence class"):
            TrainingRunLogger(model="vint", dataset="go_stanford",
                              evidence_class="looks_fine", total_epochs=1)

    def test_a_typo_is_refused_rather_than_silently_downgraded(self) -> None:
        with pytest.raises(ValueError):
            TrainingRunLogger(model="vint", dataset="go_stanford",
                              evidence_class="baseline_eval", total_epochs=1)


class _FakeRun:
    def __init__(self):
        self.logged = []
        self.summary = {}

    def log(self, payload):
        self.logged.append(payload)


class TestEpochAccounting:
    """Wall-clock and remaining time are recorded, not reconstructed afterwards."""

    def _logger(self, epochs=10):
        lg = TrainingRunLogger(model="vint", dataset="go_stanford",
                               evidence_class="pipeline_smoke_test", total_epochs=epochs)
        lg.run = _FakeRun()
        import time

        lg._t0 = time.time() - 5.0
        lg.epoch_start()
        return lg

    def test_an_epoch_records_losses_under_its_split(self) -> None:
        lg = self._logger()
        p = lg.log_epoch(0, losses={"total_loss": 1.5, "action_loss": 0.4}, learning_rate=1e-4)
        assert p["train/total_loss"] == 1.5
        assert p["train/action_loss"] == 0.4
        assert p["learning_rate"] == 1e-4
        assert p["epoch"] == 0

    def test_elapsed_and_remaining_are_both_present(self) -> None:
        """Elapsed alone does not tell an operator whether to wait or to stop."""
        lg = self._logger(epochs=10)
        p = lg.log_epoch(0, losses={"total_loss": 1.0})
        assert p["time/elapsed_seconds"] >= 5.0
        assert "time/estimated_remaining_hours" in p
        assert p["time/estimated_remaining_hours"] >= 0.0

    def test_the_last_epoch_estimates_zero_remaining(self) -> None:
        lg = self._logger(epochs=3)
        p = lg.log_epoch(2, losses={"total_loss": 1.0})
        assert p["time/estimated_remaining_hours"] == pytest.approx(0.0)

    def test_throughput_is_recorded_when_sample_count_is_known(self) -> None:
        lg = self._logger()
        p = lg.log_epoch(0, losses={"total_loss": 1.0}, samples=4000)
        assert p["throughput/samples_per_second"] > 0

    def test_eval_metrics_go_under_their_own_split(self) -> None:
        lg = self._logger()
        lg.log_eval(3, {"total_loss": 0.18}, split="test")
        assert lg.run.logged[-1]["test/total_loss"] == pytest.approx(0.18)
        assert lg.run.logged[-1]["epoch"] == 3
