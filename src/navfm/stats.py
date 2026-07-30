"""Derive the two dataset constants that the reference repo hard-codes.

Upstream ships ``metric_waypoint_spacing`` per dataset and a single global
``action_stats`` (``min: [-2.5, -4]``, ``max: [5, 4]``) in
``vint_train/data/data_config.yaml``, with no derivation and no script. Three
open issues on the reference repo (#45, #64, #67) ask where they came from and
none was ever answered.

They matter:

* ``metric_waypoint_spacing`` is the divisor that makes actions commensurate
  across embodiments. Set it wrong and the fine-tuned policy drives at the
  wrong scale.
* ``action_stats`` is the ``[-1, 1]`` normalisation range for NoMaD's diffusion
  head, and the DDPM scheduler runs with ``clip_sample=True``. Deltas outside
  the range are *clipped*, not merely squashed -- so an under-sized range
  silently truncates fast motion, and an over-sized range wastes resolution.

This module computes both from data and reports the coverage you would get by
keeping the published constants, so the choice is evidence-based.

    python -m navfm.stats /data/isaac_m3pro --name isaac_m3pro --len-traj-pred 8
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

from .kinematics import compute_actions, mean_step_distance
from .schema import TRAJ_DATA_FILENAME, DatasetSpec

__all__ = [
    "PUBLISHED_ACTION_STATS",
    "PUBLISHED_METRIC_WAYPOINT_SPACING",
    "estimate_action_stats",
    "estimate_metric_waypoint_spacing",
    "iter_trajectories",
]

#: ``data_config.yaml -> action_stats``. Units are normalised waypoints.
PUBLISHED_ACTION_STATS: dict[str, list[float]] = {
    "min": [-2.5, -4.0],
    "max": [5.0, 4.0],
}

#: ``data_config.yaml``, metres per recorded frame.
PUBLISHED_METRIC_WAYPOINT_SPACING: dict[str, float] = {
    "recon": 0.25,
    "scand": 0.38,
    "tartan_drive": 0.72,
    "go_stanford": 0.12,
    "cory_hall": 0.06,
    "seattle": 0.35,
    "racer": 0.38,
    "sacson": 0.255,
    "carla": 1.59,
    "carla_cil": 1.27,
    "carla_intvns": 1.39,
}


def iter_trajectories(root: str | Path) -> Iterator[tuple[str, np.ndarray, np.ndarray]]:
    """Yield ``(name, position, yaw)`` for every valid trajectory under ``root``."""
    root = Path(root)
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        pkl = d / TRAJ_DATA_FILENAME
        if not pkl.is_file():
            continue
        with open(pkl, "rb") as fh:
            data = pickle.load(fh)
        position = np.asarray(data["position"], dtype=np.float64)
        yaw = np.asarray(data["yaw"], dtype=np.float64)
        if yaw.ndim == 2 and yaw.shape[1] == 1:
            yaw = yaw[:, 0]
        yield d.name, position, yaw


def estimate_metric_waypoint_spacing(root: str | Path) -> dict[str, Any]:
    """Frame-weighted mean inter-frame displacement, plus its spread.

    Frame-weighted (not trajectory-weighted) because the constant is applied
    per *sample*, and long trajectories contribute proportionally more samples.
    """
    per_traj: list[float] = []
    all_steps: list[np.ndarray] = []
    for _name, position, _yaw in iter_trajectories(root):
        if position.shape[0] < 2:
            continue
        steps = np.linalg.norm(np.diff(position, axis=0), axis=1)
        all_steps.append(steps)
        per_traj.append(mean_step_distance(position))

    if not all_steps:
        raise ValueError(f"no usable trajectories under {root}")

    steps = np.concatenate(all_steps)
    return {
        "metric_waypoint_spacing": float(steps.mean()),
        "n_steps": int(steps.size),
        "n_trajectories": len(per_traj),
        "median": float(np.median(steps)),
        "std": float(steps.std()),
        "p01": float(np.percentile(steps, 1)),
        "p99": float(np.percentile(steps, 99)),
        "max": float(steps.max()),
        "frac_stationary": float((steps < 1e-4).mean()),
        "trajectory_mean_spread": float(np.std(per_traj)) if len(per_traj) > 1 else 0.0,
    }


def estimate_action_stats(
    root: str | Path,
    *,
    len_traj_pred: int = 8,
    waypoint_spacing: int = 1,
    metric_waypoint_spacing: float,
    context_size: int = 3,
    end_slack: int = 0,
    quantile: float = 0.999,
    stride: int = 1,
    max_samples: int | None = 500_000,
) -> dict[str, Any]:
    """Empirical ``[min_dx, min_dy] / [max_dx, max_dy]`` over first-order deltas.

    Reproduces the exact quantity NoMaD normalises: ``get_delta`` of the
    normalised local-frame waypoints, i.e. per-step displacement in units of
    ``metric_waypoint_spacing``.

    Reports both a symmetric quantile range (robust; recommended) and the hard
    min/max, plus the fraction of deltas that the *published* range would clip.
    """
    deltas: list[np.ndarray] = []
    n = 0
    for _name, position, yaw in iter_trajectories(root):
        traj_len = position.shape[0]
        begin = context_size * waypoint_spacing
        end = traj_len - end_slack - len_traj_pred * waypoint_spacing
        for t in range(begin, max(begin, end), stride):
            actions = compute_actions(
                position,
                yaw,
                t,
                len_traj_pred=len_traj_pred,
                waypoint_spacing=waypoint_spacing,
                metric_waypoint_spacing=metric_waypoint_spacing,
                learn_angle=False,
                normalize=True,
            )
            # get_delta: prepend the origin, then first-order difference.
            extended = np.concatenate([np.zeros((1, 2)), actions], axis=0)
            deltas.append(extended[1:] - extended[:-1])
            n += 1
            if max_samples is not None and n >= max_samples:
                break
        if max_samples is not None and n >= max_samples:
            break

    if not deltas:
        raise ValueError(f"no samples produced from {root}; trajectories may be too short")

    d = np.concatenate(deltas, axis=0)  # (N * len_traj_pred, 2)
    lo_q = float((1.0 - quantile) / 2.0)
    hi_q = 1.0 - lo_q

    pub_lo = np.asarray(PUBLISHED_ACTION_STATS["min"])
    pub_hi = np.asarray(PUBLISHED_ACTION_STATS["max"])
    clipped = np.logical_or(d < pub_lo, d > pub_hi).any(axis=1)

    return {
        "n_samples": int(n),
        "n_deltas": int(d.shape[0]),
        "quantile": quantile,
        "recommended": {
            "min": [float(np.quantile(d[:, 0], lo_q)), float(np.quantile(d[:, 1], lo_q))],
            "max": [float(np.quantile(d[:, 0], hi_q)), float(np.quantile(d[:, 1], hi_q))],
        },
        "hard": {
            "min": [float(d[:, 0].min()), float(d[:, 1].min())],
            "max": [float(d[:, 0].max()), float(d[:, 1].max())],
        },
        "mean": [float(d[:, 0].mean()), float(d[:, 1].mean())],
        "std": [float(d[:, 0].std()), float(d[:, 1].std())],
        "published": PUBLISHED_ACTION_STATS,
        "frac_clipped_by_published": float(clipped.mean()),
        "lateral_energy_ratio": float(
            np.abs(d[:, 1]).mean() / max(np.abs(d[:, 0]).mean(), 1e-9)
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m navfm.stats",
        description="Derive metric_waypoint_spacing and action_stats from a dataset.",
    )
    p.add_argument("root")
    p.add_argument("--name", required=True, help="dataset key for data_config.yaml")
    p.add_argument("--len-traj-pred", type=int, default=8, help="8 for NoMaD, 5 for ViNT/GNM")
    p.add_argument("--context-size", type=int, default=3)
    p.add_argument("--waypoint-spacing", type=int, default=1)
    p.add_argument("--stride", type=int, default=5, help="subsample start times")
    p.add_argument("--json", metavar="PATH")
    args = p.parse_args(argv)

    spacing = estimate_metric_waypoint_spacing(args.root)
    stats = estimate_action_stats(
        args.root,
        len_traj_pred=args.len_traj_pred,
        context_size=args.context_size,
        waypoint_spacing=args.waypoint_spacing,
        metric_waypoint_spacing=spacing["metric_waypoint_spacing"],
        stride=args.stride,
    )
    spec = DatasetSpec(name=args.name, metric_waypoint_spacing=spacing["metric_waypoint_spacing"])

    out = {"dataset": args.name, "spacing": spacing, "action_stats": stats}
    print(json.dumps(out, indent=2))
    print("\n# paste into vint_train/data/data_config.yaml:", file=sys.stderr)
    print(f"{args.name}:", file=sys.stderr)
    print(
        f"  metric_waypoint_spacing: {spec.metric_waypoint_spacing:.4f}",
        file=sys.stderr,
    )
    if stats["frac_clipped_by_published"] > 0.001:
        print(
            f"# WARNING: the published action_stats clip {stats['frac_clipped_by_published']:.2%} "
            "of deltas on this dataset. Either retain them for checkpoint compatibility and "
            "accept the truncation, or retrain the diffusion head with the recommended range.",
            file=sys.stderr,
        )
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
