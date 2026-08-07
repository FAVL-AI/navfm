#!/usr/bin/env python3
"""Publish the compatibility evidence to Weights & Biases.

    python scripts/wandb_evidence.py --pilot-root ~/navfm-data/pilot

**W&B is a provenance and inspection layer, not the decision.** The authoritative
PASS/BLOCKED verdict is the local one produced by `navfm.compat` and archived in
`gates/pilot/`. This script re-runs that same function and publishes what it
returns; it cannot reach a different conclusion, and it must never be able to
turn a BLOCKED trajectory green.

Two rules are enforced here rather than trusted:

* `overall_compatibility` is `PASS` only when **every** required check passes.
  There is no percentage and no partial credit. Ten of eleven passing with the
  ViNT loader failing is `BLOCKED`.
* `project_collected` and `pilot_evidence` are logged for every subject, so the
  GO Stanford reference rows cannot be read as our collected evidence.

No model-performance quantity is logged -- no loss, success rate, navigation
error or SPL -- because no model experiment has been performed. The plots are
sanity traces of the recorded geometry, not metrics.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.compat import check_trajectory  # noqa: E402

PROJECT = "navfm-vint-data-compatibility"


def _row(report, purpose: str) -> dict:
    """The declared field set, derived from the local report only."""
    by = {c.name: c for c in report.checks}
    passed = sum(1 for c in report.checks if c.passed)

    position = yaw = None
    try:
        with open(Path(report_dir_of(report)) / "traj_data.pkl", "rb") as fh:
            raw = pickle.load(fh)
        from navfm.trajio import normalise_traj_data

        out = normalise_traj_data(raw)
        position, yaw = out["position"], out["yaw"]
    except Exception:
        pass

    non_finite = 0
    if position is not None and yaw is not None:
        non_finite = int(
            np.count_nonzero(~np.isfinite(position)) + np.count_nonzero(~np.isfinite(yaw))
        )

    return {
        "source": report.source,
        "trajectory_id": report.trajectory,
        "project_collected": report.collected_by_project,
        "pilot_evidence": report.pilot_evidence,
        "purpose": purpose,
        "frame_count": report.frame_count,
        "image_numbering_pass": by["image_numbering_contiguous"].passed,
        "image_readability_pass": by["images_readable"].passed,
        "position_dtype": str(position.dtype) if position is not None else "unreadable",
        "position_rows": int(position.shape[0]) if position is not None else 0,
        "position_columns": int(position.shape[1])
        if position is not None and position.ndim == 2
        else 0,
        "position_shape_pass": by["position_shape_T2"].passed,
        "yaw_dtype": str(yaw.dtype) if yaw is not None else "unreadable",
        "yaw_length": int(yaw.shape[0]) if yaw is not None else 0,
        "yaw_shape_pass": by["yaw_shape_T"].passed,
        "non_finite_count": non_finite,
        "missing_frame_count": max(0, report.frame_count - _n_images(report)),
        "validator_pass": by["project_validator"].passed,
        "vint_loader_pass": by["unchanged_vint_data_path"].passed,
        "checks_passed": passed,
        "checks_total": len(report.checks),
        # The one rule that matters: conjunctive, never a percentage.
        "overall_compatibility": report.overall,
    }


_DIRS: dict[str, str] = {}


def report_dir_of(report) -> str:
    return _DIRS[report.trajectory]


def _n_images(report) -> int:
    for c in report.checks:
        if c.name == "numbered_images_exist" and c.passed:
            return int(c.detail.split()[0])
    return 0


def _plots(wandb, traj_dir: Path, name: str) -> dict:
    """Three sanity traces. Not metrics -- they show the geometry changes
    consistently over time, which a table of PASSes does not."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with open(traj_dir / "traj_data.pkl", "rb") as fh:
        d = pickle.load(fh)
    pos, yaw = np.asarray(d["position"]), np.asarray(d["yaw"])
    t = np.arange(len(yaw))
    out = {}

    fig, ax = plt.subplots(figsize=(5, 3))
    ax.plot(t, pos[:, 0], label="x")
    ax.plot(t, pos[:, 1], label="y")
    ax.set_xlabel("frame")
    ax.set_ylabel("position (m)")
    ax.set_title(f"{name}: position vs frame")
    ax.legend()
    fig.tight_layout()
    out["position_vs_frame"] = wandb.Image(fig)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 3))
    ax.plot(t, yaw)
    ax.set_xlabel("frame")
    ax.set_ylabel("yaw (rad, unwrapped)")
    ax.set_title(f"{name}: yaw vs frame")
    fig.tight_layout()
    out["yaw_vs_frame"] = wandb.Image(fig)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(4, 4))
    ax.plot(pos[:, 0], pos[:, 1], marker=".", ms=3)
    ax.plot(pos[0, 0], pos[0, 1], "go", label="start")
    ax.plot(pos[-1, 0], pos[-1, 1], "rs", label="end")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_aspect("equal", "datalim")
    ax.set_title(f"{name}: path")
    ax.legend()
    fig.tight_layout()
    out["path_xy"] = wandb.Image(fig)
    plt.close(fig)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pilot-root", required=True)
    p.add_argument("--reference", default=None, help="converted GO Stanford trajectory dir")
    p.add_argument("--entity", default=None)
    p.add_argument("--offline", action="store_true")
    args = p.parse_args(argv)

    import wandb

    if args.offline:
        import os

        os.environ["WANDB_MODE"] = "offline"

    pilot_root = Path(args.pilot_root).expanduser()
    subjects = []
    if args.reference:
        subjects.append(
            (
                "go-stanford-harness-validation",
                Path(args.reference).expanduser(),
                dict(
                    source="GO Stanford reference dataset (converted to Option 1 via navfm.trajio)",
                    purpose="harness_validation",
                    collected_by_project=False,
                    pilot_evidence=False,
                ),
            )
        )
    for n in ("pilot_0001", "pilot_0002"):
        subjects.append(
            (
                f"pilot-trajectory-{n.split('_')[1]}",
                pilot_root / n,
                dict(
                    source="Isaac Sim 5.1 simple_room, cube proxy (collected by this project)",
                    purpose="supervisor_compatibility_pilot",
                    collected_by_project=True,
                    pilot_evidence=True,
                ),
            )
        )

    rows = []
    columns = None
    for run_name, traj_dir, prov in subjects:
        if not (traj_dir / "traj_data.pkl").is_file():
            print(f"REFUSED: {traj_dir} has no traj_data.pkl", file=sys.stderr)
            return 2

        report = check_trajectory(traj_dir, dataset_name="go_stanford", **prov)
        _DIRS[report.trajectory] = str(traj_dir)
        row = _row(report, prov["purpose"])

        run = wandb.init(
            project=PROJECT,
            entity=args.entity,
            name=run_name,
            job_type="data-compatibility",
            reinit=True,
            config={
                **{k: row[k] for k in ("source", "trajectory_id", "purpose")},
                "project_collected": prov["collected_by_project"],
                "pilot_evidence": prov["pilot_evidence"],
                "authoritative_verdict_source": "local navfm.compat, archived in gates/pilot/",
                "note": (
                    "W&B is a provenance and inspection layer. The local report is "
                    "authoritative. No model has been trained or evaluated; no "
                    "performance metric is logged."
                ),
            },
        )
        run.summary.update(row)
        for c in report.checks:
            run.summary[f"check/{c.name}"] = "PASS" if c.passed else "FAIL"

        if prov["pilot_evidence"]:
            run.log(_plots(wandb, traj_dir, report.trajectory))
            art = wandb.Artifact(
                run_name,
                type="dataset",
                metadata={
                    "source": "isaac-sim-5.1",
                    "robot_representation": "cube-proxy",
                    "scene": "simple_room",
                    "purpose": "format-compatibility",
                    "training_admitted": False,
                    "overall_compatibility": report.overall,
                },
            )
            art.add_dir(str(traj_dir))
            rep_json = traj_dir / "compatibility_report.json"
            rep_json.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n")
            art.add_file(str(rep_json))
            run.log_artifact(art)

        columns = list(row.keys())
        rows.append([row[k] for k in columns])
        print(f"{run_name}: {report.overall} ({row['checks_passed']}/{row['checks_total']})")
        run.finish()

    summary = wandb.init(
        project=PROJECT,
        entity=args.entity,
        name="compatibility-summary",
        job_type="summary",
        reinit=True,
    )
    summary.log({"compatibility": wandb.Table(columns=columns, data=rows)})
    summary.finish()
    print(f"\npublished {len(rows)} rows to project {PROJECT}")
    print("Local reports in gates/pilot/ remain authoritative.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
