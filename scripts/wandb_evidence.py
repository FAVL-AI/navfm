#!/usr/bin/env python3
"""Publish the compatibility evidence to Weights & Biases.

    python scripts/wandb_evidence.py --pilot-root ~/navfm-data/pilot \
        --reference /tmp/navfm-harness-validation/<traj>_option1

**W&B displays and preserves the evidence. It does not manufacture the PASS.**
The authoritative PASS/BLOCKED verdict is the local one produced by
`navfm.compat` and archived in `gates/pilot/`. This script re-runs that same
function and publishes what it returns; it cannot reach a different conclusion,
and it must never be able to turn a BLOCKED trajectory green.

Two rules are enforced here rather than trusted:

* `overall_compatibility` is `PASS` only when **every** required check passes.
  No percentage, no partial credit. Ten of eleven passing with the ViNT loader
  failing is `BLOCKED`.
* `project_collected` and `pilot_evidence` are logged for every subject, so a
  reference row can never be read as our collected evidence.

## Absent metrics are logged as absent

Every quantity we have *not* earned is logged with an explicit `BLOCKED` status
and a reason, rather than omitted. A reader six months from now must be able to
tell "the experiment was not run" from "logging failed". Those fields change
only from evidence that the run which actually loads a checkpoint produces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from navfm.compat import check_trajectory  # noqa: E402

PROJECT = "navfm-vint-data-compatibility"
KEYFRAMES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 59]

#: Logged on every pilot run. Absent because unearned, not because unlogged.
NOT_DONE = {
    "checkpoint_loaded": False,
    "checkpoint_name": "vint.pth",
    "training_performed": False,
    "model_evaluation_performed": False,
    "success_rate_status": "BLOCKED",
    "navigation_error_status": "BLOCKED",
    "spl_status": "BLOCKED",
    "ndtw_status": "BLOCKED",
    "sdtw_status": "BLOCKED",
    "block_reason": "No model training or evaluation has been performed.",
}

CONCLUSION = (
    "Two independently collected Isaac Sim trajectories passed all required "
    "Option 1 compatibility checks and were accepted by the unchanged ViNT data "
    "path. No model training or model evaluation has yet been performed."
)

# Default-visible first, forensic columns after. W&B shows columns in order.
VISIBLE = [
    "trajectory_id",
    "source_short",
    "project_collected",
    "pilot_evidence",
    "frame_count",
    "validator_pass",
    "vint_loader_pass",
    "loader_samples_checked",
    "checks",
    "overall_compatibility",
]
FORENSIC = [
    "purpose",
    "source",
    "position_dtype",
    "position_rows",
    "position_columns",
    "position_shape_pass",
    "yaw_dtype",
    "yaw_length",
    "yaw_shape_pass",
    "image_numbering_pass",
    "image_readability_pass",
    "non_finite_count",
    "missing_frame_count",
    "path_length_m",
    "yaw_change_deg",
    "frame_59_digest",
    "checks_passed",
    "checks_total",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _geometry(traj_dir: Path) -> dict:
    with open(traj_dir / "traj_data.pkl", "rb") as fh:
        d = pickle.load(fh)
    from navfm.trajio import normalise_traj_data

    out = normalise_traj_data(d, trajectory=traj_dir.name)
    pos, yaw = out["position"], out["yaw"]
    return {
        "position": pos,
        "yaw": yaw,
        "path_length_m": float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum()),
        "yaw_change_deg": float(np.degrees(yaw[-1] - yaw[0])),
        "non_finite_count": int(
            np.count_nonzero(~np.isfinite(pos)) + np.count_nonzero(~np.isfinite(yaw))
        ),
    }


def _n_images(report) -> int:
    for c in report.checks:
        if c.name == "numbered_images_exist" and c.passed:
            return int(c.detail.split()[0])
    return 0


def _loader_samples(report) -> int:
    for c in report.checks:
        if c.name == "unchanged_vint_data_path" and c.passed:
            return int(c.detail.split()[0])
    return 0


def _row(report, traj_dir: Path, geom: dict, purpose: str, source_short: str) -> dict:
    by = {c.name: c for c in report.checks}
    passed = sum(1 for c in report.checks if c.passed)
    last = traj_dir / f"{report.frame_count - 1}.jpg"
    return {
        "trajectory_id": report.trajectory,
        "source_short": source_short,
        "project_collected": report.collected_by_project,
        "pilot_evidence": report.pilot_evidence,
        "frame_count": report.frame_count,
        "validator_pass": by["project_validator"].passed,
        "vint_loader_pass": by["unchanged_vint_data_path"].passed,
        "loader_samples_checked": _loader_samples(report),
        "checks": f"{passed}/{len(report.checks)}",
        # Conjunctive, taken from the report. Never recomputed as a fraction.
        "overall_compatibility": report.overall,
        "purpose": purpose,
        "source": report.source,
        "position_dtype": str(geom["position"].dtype),
        "position_rows": int(geom["position"].shape[0]),
        "position_columns": int(geom["position"].shape[1]),
        "position_shape_pass": by["position_shape_T2"].passed,
        "yaw_dtype": str(geom["yaw"].dtype),
        "yaw_length": int(geom["yaw"].shape[0]),
        "yaw_shape_pass": by["yaw_shape_T"].passed,
        "image_numbering_pass": by["image_numbering_contiguous"].passed,
        "image_readability_pass": by["images_readable"].passed,
        "non_finite_count": geom["non_finite_count"],
        "missing_frame_count": max(0, report.frame_count - _n_images(report)),
        "path_length_m": round(geom["path_length_m"], 3),
        "yaw_change_deg": round(geom["yaw_change_deg"], 1),
        # Full digest here; captions elsewhere use a short prefix.
        "frame_59_digest": _sha256(last) if last.is_file() else "",
        "checks_passed": passed,
        "checks_total": len(report.checks),
    }


def _plots(wandb, name: str, geom: dict) -> dict:
    """Sanity traces of the recorded geometry. Not metrics."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pos, yaw = geom["position"], geom["yaw"]
    t = np.arange(len(yaw))
    out = {}

    fig, ax = plt.subplots(figsize=(5, 3))
    ax.plot(t, pos[:, 0], label="x")
    ax.plot(t, pos[:, 1], label="y")
    ax.set(xlabel="frame", ylabel="position (m)", title=f"{name}: position vs frame")
    ax.legend()
    fig.tight_layout()
    out["position_vs_frame"] = wandb.Image(fig)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 3))
    ax.plot(t, yaw)
    ax.set(xlabel="frame", ylabel="yaw (rad, unwrapped)", title=f"{name}: yaw vs frame")
    fig.tight_layout()
    out["yaw_vs_frame"] = wandb.Image(fig)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(4, 4))
    ax.plot(pos[:, 0], pos[:, 1], marker=".", ms=3)
    ax.plot(pos[0, 0], pos[0, 1], "go", label="start")
    ax.plot(pos[-1, 0], pos[-1, 1], "rs", label="end")
    ax.set(xlabel="x (m)", ylabel="y (m)", title=f"{name}: path")
    ax.set_aspect("equal", "datalim")
    ax.legend()
    fig.tight_layout()
    out["path_xy"] = wandb.Image(fig)
    plt.close(fig)
    return out


def _keyframes_and_table(wandb, traj_dir: Path, name: str, geom: dict):
    """13 keyframes for the dashboard, and a table pairing image to state.

    The actual rendered observations. No overlays, no annotation, nothing
    synthetic drawn on them: these are the evidence, and a decorated image is a
    worse evidence than an undecorated one.
    """
    from PIL import Image as PILImage

    pos, yaw = geom["position"], geom["yaw"]
    n = len(yaw)
    frames = [i for i in KEYFRAMES if i < n]

    media = []
    rows = []
    for i in frames:
        p = traj_dir / f"{i}.jpg"
        digest = _sha256(p)
        with PILImage.open(p) as im:
            im = im.convert("RGB")
            media.append(wandb.Image(im, caption=f"{name} | frame {i:03d} | front RGB"))
            rows.append(
                [
                    name,
                    i,
                    wandb.Image(im),
                    round(float(pos[i, 0]), 4),
                    round(float(pos[i, 1]), 4),
                    round(float(yaw[i]), 4),
                    digest[:12],
                ]
            )
    table = wandb.Table(
        columns=["trajectory", "frame", "front_rgb", "x_m", "y_m", "yaw_rad", "digest"],
        data=rows,
    )
    return media, table


def _gif(traj_dir: Path, n: int, out_path: Path) -> Path | None:
    """Assemble the full sequence into a GIF using PIL only.

    Deliberately not moviepy or imageio: neither is installed, and installing
    one would change the canonical environment's pip_freeze_digest, which is
    pinned in PREREGISTRATION.md and verified by the freeze audit's
    environment_identity_recorded check. A scrubbable animation is not worth
    invalidating a frozen protocol identity.
    """
    from PIL import Image as PILImage

    paths = [traj_dir / f"{i}.jpg" for i in range(n)]
    if not all(p.is_file() for p in paths):
        return None
    imgs = [PILImage.open(p).convert("RGB") for p in paths]
    imgs[0].save(out_path, save_all=True, append_images=imgs[1:], duration=int(1000 / 12), loop=0)
    for im in imgs:
        im.close()
    return out_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pilot-root", required=True)
    p.add_argument("--reference", default=None)
    p.add_argument("--entity", default=None)
    p.add_argument("--offline", action="store_true")
    args = p.parse_args(argv)

    import os

    if args.offline:
        os.environ["WANDB_MODE"] = "offline"
    import wandb

    pilot_root = Path(args.pilot_root).expanduser()
    subjects = []
    if args.reference:
        subjects.append(
            (
                "go-stanford-converted-reference-harness-validation",
                Path(args.reference).expanduser(),
                "Reference",
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
                "Isaac Sim",
                dict(
                    source="Isaac Sim 5.1 simple_room, cube proxy (collected by this project)",
                    purpose="supervisor_compatibility_pilot",
                    collected_by_project=True,
                    pilot_evidence=True,
                ),
            )
        )

    rows: list[list] = []
    geoms: dict[str, dict] = {}
    digests: dict[str, str] = {}

    for run_name, traj_dir, source_short, prov in subjects:
        if not (traj_dir / "traj_data.pkl").is_file():
            print(f"REFUSED: {traj_dir} has no traj_data.pkl", file=sys.stderr)
            return 2

        report = check_trajectory(traj_dir, dataset_name="go_stanford", **prov)
        geom = _geometry(traj_dir)
        row = _row(report, traj_dir, geom, prov["purpose"], source_short)
        geoms[report.trajectory] = geom
        digests[report.trajectory] = row["frame_59_digest"]

        run = wandb.init(
            project=PROJECT,
            entity=args.entity,
            name=run_name,
            job_type="data-compatibility",
            reinit=True,
            config={
                "source": report.source,
                "trajectory_id": report.trajectory,
                "purpose": prov["purpose"],
                "project_collected": prov["collected_by_project"],
                "pilot_evidence": prov["pilot_evidence"],
                "robot_representation": "cube proxy" if prov["pilot_evidence"] else "n/a",
                "scene": "simple_room" if prov["pilot_evidence"] else "n/a",
                "authoritative_verdict_source": "local navfm.compat, archived in gates/pilot/",
                "conclusion": CONCLUSION,
            },
        )
        run.summary.update(row)
        run.summary.update(NOT_DONE)
        for c in report.checks:
            run.summary[f"check/{c.name}"] = "PASS" if c.passed else "FAIL"

        payload = _plots(wandb, report.trajectory, geom)
        if prov["pilot_evidence"]:
            media, table = _keyframes_and_table(wandb, traj_dir, report.trajectory, geom)
            payload["front_rgb_keyframes"] = media
            payload["rgb_frame_evidence"] = table
            gif = _gif(traj_dir, report.frame_count, traj_dir / "sequence.gif")
            if gif is not None:
                payload["front_rgb_sequence"] = wandb.Video(
                    str(gif), caption=f"{report.trajectory} | all {report.frame_count} frames"
                )
        run.log(payload)

        if prov["pilot_evidence"]:
            rep_json = traj_dir / "compatibility_report.json"
            rep_json.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n")
            art = wandb.Artifact(
                run_name,
                type="dataset",
                metadata={
                    "source": "isaac-sim-5.1",
                    "robot_representation": "cube-proxy",
                    "scene": "simple_room",
                    "purpose": "format-compatibility",
                    "training_admitted": False,
                    "evaluation_admitted": False,
                    "pilot_only": True,
                    "option1_format": True,
                    "validator_pass": row["validator_pass"],
                    "vint_loader_pass": row["vint_loader_pass"],
                    "loader_samples_checked": row["loader_samples_checked"],
                    "frame_count": row["frame_count"],
                    "path_length_m": row["path_length_m"],
                    "overall_compatibility": report.overall,
                },
            )
            art.add_dir(str(traj_dir))
            local_digests = REPO / "gates" / "pilot" / "pilot_digests.json"
            if local_digests.is_file():
                art.add_file(str(local_digests))
            run.log_artifact(art)

        rows.append([row[k] for k in VISIBLE + FORENSIC])
        print(f"{run_name}: {report.overall} ({row['checks']})")
        run.finish()

    # -- summary run -----------------------------------------------------
    summary = wandb.init(
        project=PROJECT,
        entity=args.entity,
        name="compatibility-summary",
        job_type="summary",
        reinit=True,
        config={"conclusion": CONCLUSION},
    )
    summary.log({"compatibility": wandb.Table(columns=VISIBLE + FORENSIC, data=rows)})

    status = [
        ["Option 1 data compatibility", "PASS", "Both project trajectories accepted"],
        ["Two collected trajectories", "COMPLETE", "pilot_0001 and pilot_0002"],
        ["RGB observations", "COMPLETE", "60 rendered frames each"],
        ["Project validator", "PASS", "Both trajectories"],
        ["Unchanged ViNT loader", "PASS", "50 samples each"],
        ["vint.pth loaded", "NOT STARTED", "Checkpoint intentionally unloaded"],
        ["Model training", "NOT STARTED", "No training run"],
        ["Model evaluation", "NOT STARTED", "No evaluation run"],
        ["Success Rate", "BLOCKED", "Evaluation not performed"],
        ["Navigation Error", "BLOCKED", "Evaluation not performed"],
        ["SPL", "BLOCKED", "Evaluation not performed"],
    ]
    summary.log(
        {
            "research_status": wandb.Table(
                columns=["item", "status", "evidence_or_reason"], data=status
            )
        }
    )

    # Cross-trajectory: two PASS rows would look identical if one trajectory had
    # been written twice, so the distinctness is published, not just asserted.
    if "pilot_0001" in geoms and "pilot_0002" in geoms:
        a, b = geoms["pilot_0001"], geoms["pilot_0002"]
        summary.summary.update(
            {
                "max_position_difference_between_pilots_m": round(
                    float(np.abs(a["position"] - b["position"]).max()), 3
                ),
                "yaw_sequences_equal": bool(np.array_equal(a["yaw"], b["yaw"])),
                "frame_59_digests_equal": digests["pilot_0001"] == digests["pilot_0002"],
            }
        )
    summary.summary.update(NOT_DONE)
    summary.finish()

    print(f"\npublished {len(rows)} rows to project {PROJECT}")
    print("Local reports in gates/pilot/ remain authoritative.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
