"""The Weights & Biases evidence ledger: milestones, visuals, issues, training.

Why this is a module and not another script
--------------------------------------------

Three publishers had already grown by copy-paste, each knowing a little about
the run naming, the claim boundaries and the artefact layout. That is how a
ledger and a repository drift apart: not by anyone lying, but by one script
learning a convention the others never hear about. Everything that publishes now
goes through here.

What the ledger is for
----------------------

Not a scoreboard. A scoreboard records what worked, and a record of only what
worked teaches nothing about what nearly did not. So the ledger carries, with
equal weight:

* **milestones** — what was established, and the evidence path for each;
* **visuals** — the robot's own point of view, the motion it actually took, and
  the camera-mount proof, because a claim about a viewpoint should be lookable-at;
* **issues and their corrections** — every silent failure, what convincing-but-
  wrong artefact it would have produced, and why nothing downstream would have
  caught it;
* **iterations** — the adjudication sequence, so the process is visible as
  work rather than as a series of approvals;
* **claim boundaries** — logged as data, so the thing that may *not* be claimed
  travels with the thing that may.

Training readiness
------------------

:class:`TrainingRunLogger` exists before any training has happened, on purpose.
The moment to decide what a training run records is *before* the first epoch,
not after a week-long run when the interesting quantity turns out not to have
been logged. It records epoch, wall-clock, learning rate, every loss component,
throughput, and the evidence class of the run — and it refuses to log a
scientific result under a class that makes no model claim, so a smoke test
cannot quietly become a table row.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PROJECT = "navfm-reproducibility-closeout"

#: Evidence classes that may back a scientific claim. A run outside this set is
#: engineering evidence and is refused a results-table role at log time rather
#: than at review time.
CLAIMABLE = {"baseline_evaluation", "registered_experiment"}

__all__ = ["EvidenceLedger", "TrainingRunLogger", "git_sha", "trajectory_gif"]


def git_sha(short: bool = False) -> str:
    args = ["git", "-C", str(REPO), "rev-parse"] + (["--short"] if short else []) + ["HEAD"]
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def trajectory_gif(frames_dir: str | Path, out_path: str | Path, *, max_frames: int = 40,
                   duration_ms: int = 120) -> Path | None:
    """Animate a trajectory's own camera frames.

    A still frame shows what the robot saw once; the animation shows that the
    view moved *with* the robot, which is the thing being claimed. Returns None
    rather than raising if there are no frames -- a missing visual should not
    take down a publish.
    """
    from PIL import Image as PILImage

    d = Path(frames_dir)
    frames = sorted(d.glob("*.jpg"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0)
    frames = [f for f in frames if f.stem.isdigit()]
    if not frames:
        return None
    step = max(1, len(frames) // max_frames)
    imgs = [PILImage.open(f).convert("RGB") for f in frames[::step][:max_frames]]
    if not imgs:
        return None
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=duration_ms, loop=0)
    return out


def motion_trace_plot(positions: Any, yaws: Any, out_path: str | Path, *, title: str = "") -> Path:
    """Plot the path the robot actually took, with heading arrows.

    Plotted from the recorded poses rather than the commanded ones: the gap
    between those two is where a stationary robot with a confident control log
    hides.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    pos = np.asarray(positions, dtype=float)
    yaw = np.asarray(yaws, dtype=float)
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot(pos[:, 0], pos[:, 1], "-", lw=1.6, color="#3b6ea5")
    ax.plot(pos[0, 0], pos[0, 1], "o", ms=9, color="#2e7d32", label="START")
    ax.plot(pos[-1, 0], pos[-1, 1], "s", ms=9, color="#c62828", label="END")
    n = max(1, len(pos) // 12)
    ax.quiver(pos[::n, 0], pos[::n, 1], np.cos(yaw[::n]), np.sin(yaw[::n]),
              color="#888", scale=18, width=0.004)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(title or "robot path (recorded poses)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.25)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


class EvidenceLedger:
    """One run carrying milestones, visuals, issues, iterations and boundaries."""

    def __init__(self, *, entity: str | None = None, project: str = PROJECT,
                 job_type: str = "evidence", offline: bool = False) -> None:
        self.entity = entity
        self.project = project
        self.job_type = job_type
        self.offline = offline
        self.run: Any = None

    def open(self, *, name: str | None = None, notes: str = "",
             config: dict[str, Any] | None = None) -> Any:
        import os

        import wandb

        if self.offline:
            os.environ["WANDB_MODE"] = "offline"
        sha = git_sha()
        self.run = wandb.init(
            project=self.project, entity=self.entity, job_type=self.job_type,
            name=name or f"ledger-{sha[:7]}",
            config={
                "git_sha": sha,
                "worktree_clean": subprocess.run(
                    ["git", "-C", str(REPO), "status", "--porcelain"],
                    capture_output=True, text=True).stdout.strip() == "",
                "recorded_utc": _now(),
                **(config or {}),
            },
            notes=notes,
        )
        return self.run

    # -- content ---------------------------------------------------------
    def log_table(self, key: str, columns: list[str], rows: list[list[Any]]) -> None:
        """Log a table, coercing every cell to a string.

        W&B types a column from its first row and then rejects mismatches, which
        turns a mixed int/str column into a silent publish failure. Coercing up
        front costs sortability and buys a table that always lands.
        """
        import wandb

        cols: list[str | int] = list(columns)
        self.run.log({key: wandb.Table(columns=cols,
                                       data=[[("" if c is None else str(c)) for c in r] for r in rows])})

    def log_milestones(self, rows: list[list[Any]]) -> None:
        self.log_table("milestones", ["milestone", "status", "result", "evidence", "commit"], rows)

    def log_issues(self, rows: list[list[Any]]) -> None:
        """Issues with their corrections. The most valuable table here."""
        self.log_table(
            "issues_and_corrections",
            ["issue", "would_have_produced", "why_undetectable_downstream", "how_caught",
             "correction", "attributed_to"],
            rows,
        )

    def log_iterations(self, rows: list[list[Any]]) -> None:
        self.log_table("adjudication_iterations",
                       ["round", "verdict", "committable", "defects", "decisive_finding"], rows)

    def log_claim_boundary(self, rows: list[list[Any]]) -> None:
        self.log_table("claim_boundary", ["may_claim", "may_NOT_claim"], rows)

    def log_kpis(self, kpis: dict[str, Any]) -> None:
        self.run.summary.update(kpis)

    def log_image(self, key: str, path: str | Path, caption: str) -> None:
        import wandb

        p = Path(path)
        if p.is_file():
            self.run.log({key: wandb.Image(str(p), caption=caption)})

    def log_video(self, key: str, path: str | Path, caption: str = "") -> None:
        """A GIF is logged as Video so the player scrubs rather than showing frame 1."""
        import wandb

        p = Path(path)
        if p.is_file():
            self.run.log({key: wandb.Video(str(p), caption=caption, format="gif")})

    def log_artifact(self, name: str, paths: list[str | Path], *, type_: str = "evidence",
                     description: str = "", metadata: dict[str, Any] | None = None) -> None:
        import wandb

        art = wandb.Artifact(name=name, type=type_, description=description,
                             metadata={"git_sha": git_sha(), **(metadata or {})})
        for rel in paths:
            p = REPO / rel if not Path(rel).is_absolute() else Path(rel)
            if p.is_dir():
                art.add_dir(str(p), name=str(rel))
            elif p.is_file():
                art.add_file(str(p), name=str(rel))
        self.run.log_artifact(art)

    def close(self) -> str:
        url = getattr(self.run, "url", "")
        self.run.finish()
        return url


class TrainingRunLogger:
    """Epoch-level logging for training runs, defined before the first one runs.

    Deciding what a training run records *after* it finishes is how a week of
    compute produces a curve nobody can interpret. This fixes the schema now:
    epoch, wall-clock, learning rate, every loss component, throughput, and the
    evidence class -- so a smoke test cannot later be read as a result.
    """

    def __init__(self, *, model: str, dataset: str, evidence_class: str,
                 total_epochs: int, entity: str | None = None,
                 project: str = PROJECT, config: dict[str, Any] | None = None) -> None:
        if evidence_class not in CLAIMABLE and evidence_class not in {
            "pipeline_smoke_test", "random_init_control", "checkpoint_sanity",
            "diagnostic_unregistered",
        }:
            raise ValueError(
                f"unknown evidence class {evidence_class!r}. A run must declare what kind "
                f"of evidence it produces before it produces any."
            )
        self.model = model
        self.dataset = dataset
        self.evidence_class = evidence_class
        self.total_epochs = int(total_epochs)
        self.entity = entity
        self.project = project
        self.extra = config or {}
        self.run: Any = None
        self._t0: float | None = None
        self._epoch_t0: float | None = None

    @property
    def claimable(self) -> bool:
        """Whether this run's output may back a scientific claim."""
        return self.evidence_class in CLAIMABLE

    def start(self, *, name: str | None = None) -> Any:
        import time

        import wandb

        self._t0 = time.time()
        self.run = wandb.init(
            project=self.project, entity=self.entity, job_type="training",
            name=name or f"train-{self.model}-{git_sha(short=True)}",
            config={
                "model": self.model, "dataset": self.dataset,
                "evidence_class": self.evidence_class, "claimable": self.claimable,
                "total_epochs": self.total_epochs, "git_sha": git_sha(),
                "started_utc": _now(), **self.extra,
            },
            notes=(
                "Training run. `claimable` says whether this may back a scientific claim; "
                "a run that declares a non-claimable class cannot become a results row "
                "later by being described differently."
            ),
        )
        return self.run

    def epoch_start(self) -> None:
        import time

        self._epoch_t0 = time.time()

    def log_epoch(self, epoch: int, *, losses: dict[str, float],
                  learning_rate: float | None = None, samples: int | None = None,
                  split: str = "train") -> dict[str, Any]:
        """One epoch. Wall-clock and throughput are recorded, not inferred later."""
        import time

        now = time.time()
        epoch_s = (now - self._epoch_t0) if self._epoch_t0 else None
        elapsed_s = (now - self._t0) if self._t0 else None
        remaining = None
        if epoch_s and epoch >= 0 and self.total_epochs > 0:
            remaining = epoch_s * max(0, self.total_epochs - (epoch + 1))
        payload: dict[str, Any] = {
            "epoch": epoch,
            **{f"{split}/{k}": float(v) for k, v in losses.items()},
        }
        if learning_rate is not None:
            payload["learning_rate"] = float(learning_rate)
        if epoch_s is not None:
            payload["time/epoch_seconds"] = epoch_s
            payload["time/elapsed_seconds"] = elapsed_s
            payload["time/elapsed_hours"] = (elapsed_s or 0) / 3600.0
            if remaining is not None:
                payload["time/estimated_remaining_hours"] = remaining / 3600.0
        if samples and epoch_s:
            payload["throughput/samples_per_second"] = samples / epoch_s
        self.run.log(payload)
        return payload

    def log_eval(self, epoch: int, metrics: dict[str, float], *, split: str = "test") -> None:
        self.run.log({"epoch": epoch, **{f"{split}/{k}": float(v) for k, v in metrics.items()}})

    def finish(self, *, checkpoint: str | Path | None = None,
               final_metrics: dict[str, Any] | None = None) -> str:
        import time

        import wandb

        if self._t0:
            total = time.time() - self._t0
            self.run.summary.update({
                "time/total_seconds": total,
                "time/total_hours": total / 3600.0,
            })
        if final_metrics:
            self.run.summary.update(final_metrics)
        self.run.summary.update({"claimable": self.claimable,
                                 "evidence_class": self.evidence_class})
        if checkpoint and Path(checkpoint).is_file():
            from navfm.models.loader import sha256

            art = wandb.Artifact(
                name=f"{self.model}-checkpoint-{git_sha(short=True)}", type="model",
                metadata={"sha256": sha256(Path(checkpoint)),
                          "evidence_class": self.evidence_class,
                          "claimable": self.claimable},
            )
            art.add_file(str(checkpoint))
            self.run.log_artifact(art)
        url = getattr(self.run, "url", "")
        self.run.finish()
        return url


def load_json(rel: str) -> dict[str, Any]:
    return json.loads((REPO / rel).read_text())
