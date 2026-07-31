"""Strict validator for GNM-format datasets.

Run before every training job. It answers the only question that matters
before you burn GPU-hours: *will the reference loader read this without
silently dropping or mislabelling anything?*

    python -m navfm.validate /data/isaac_m3pro --model vint --json report.json

Exit codes: ``0`` clean, ``1`` errors found, ``2`` usage error.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pickle
import sys
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np

from .kinematics import arc_length, mean_step_distance
from .schema import (
    IMAGE_EXTENSION,
    TRAJ_DATA_FILENAME,
    TrajectorySpec,
    check_image_names,
    check_traj_data,
)

__all__ = ["DatasetReport", "TrajectoryReport", "validate_dataset", "validate_trajectory"]


@dataclasses.dataclass
class TrajectoryReport:
    name: str
    n_frames: int = 0
    n_images: int = 0
    errors: list[str] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)
    n_samples: int = 0
    path_length_m: float = 0.0
    mean_step_m: float = 0.0
    duration_hint_s: float | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclasses.dataclass
class DatasetReport:
    root: str
    model: str
    spec: dict[str, Any]
    trajectories: list[TrajectoryReport] = dataclasses.field(default_factory=list)
    dataset_errors: list[str] = dataclasses.field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.dataset_errors and all(t.ok for t in self.trajectories)

    def summary(self) -> dict[str, Any]:
        good = [t for t in self.trajectories if t.ok]
        usable = [t for t in good if t.n_samples > 0]
        steps = np.array([t.mean_step_m for t in usable if t.mean_step_m > 0])
        return {
            "n_trajectories": len(self.trajectories),
            "n_valid": len(good),
            "n_usable": len(usable),
            "n_invalid": len(self.trajectories) - len(good),
            "total_frames": int(sum(t.n_frames for t in good)),
            "total_samples": int(sum(t.n_samples for t in good)),
            "total_path_length_m": float(sum(t.path_length_m for t in good)),
            "metric_waypoint_spacing_estimate": float(steps.mean()) if steps.size else None,
            "metric_waypoint_spacing_std": float(steps.std()) if steps.size else None,
            "ok": self.ok,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "model": self.model,
            "spec": self.spec,
            "summary": self.summary(),
            "dataset_errors": self.dataset_errors,
            "trajectories": [dataclasses.asdict(t) for t in self.trajectories],
        }


def _load_pickle(path: Path) -> Any:
    with open(path, "rb") as fh:
        return pickle.load(fh)


def validate_trajectory(
    traj_dir: str | Path,
    spec: TrajectorySpec,
    *,
    check_images_decodable: bool = False,
    max_step_m: float = 2.0,
) -> TrajectoryReport:
    """Validate a single trajectory directory."""
    traj_dir = Path(traj_dir)
    report = TrajectoryReport(name=traj_dir.name)

    pkl_path = traj_dir / TRAJ_DATA_FILENAME
    if not pkl_path.is_file():
        report.errors.append(f"missing {TRAJ_DATA_FILENAME}")
        return report

    try:
        traj_data = _load_pickle(pkl_path)
    except Exception as exc:
        report.errors.append(f"cannot unpickle {TRAJ_DATA_FILENAME}: {exc!r}")
        return report

    if not isinstance(traj_data, dict):
        report.errors.append(
            f"{TRAJ_DATA_FILENAME} must contain a dict, got {type(traj_data).__name__}"
        )
        return report

    image_names = [p.name for p in traj_dir.iterdir() if p.suffix == IMAGE_EXTENSION]
    report.n_images = len(image_names)
    report.errors.extend(check_image_names(image_names))

    stray = [
        p.name
        for p in traj_dir.iterdir()
        if p.name != TRAJ_DATA_FILENAME and p.suffix != IMAGE_EXTENSION
    ]
    if stray:
        report.warnings.append(f"unexpected files present: {sorted(stray)[:5]}")

    report.errors.extend(check_traj_data(traj_data, n_images=len(image_names)))
    if report.errors:
        return report

    position = np.asarray(traj_data["position"], dtype=np.float64)
    report.n_frames = int(position.shape[0])
    report.n_samples = spec.num_samples(report.n_frames)
    report.path_length_m = arc_length(position)
    report.mean_step_m = mean_step_distance(position)

    if report.n_samples == 0:
        report.warnings.append(
            f"contributes 0 training samples: length {report.n_frames} < "
            f"minimum {spec.min_length} for this spec -- the loader will drop it silently"
        )

    if report.n_frames > 1:
        steps = np.linalg.norm(np.diff(position, axis=0), axis=1)
        n_big = int((steps > max_step_m).sum())
        if n_big:
            report.warnings.append(
                f"{n_big} inter-frame jump(s) exceed {max_step_m} m "
                f"(max {steps.max():.2f} m) -- likely a dropped frame or odometry reset"
            )
        n_zero = int((steps < 1e-6).sum())
        if n_zero > 0.5 * steps.size:
            report.warnings.append(
                f"{n_zero}/{steps.size} steps are ~zero: the robot was mostly stationary, "
                "which biases the action distribution towards the trivial solution"
            )

    if check_images_decodable:
        from PIL import Image  # local import: only needed for the slow path

        for name in sorted(image_names, key=lambda n: int(n[: -len(IMAGE_EXTENSION)])):
            try:
                with Image.open(traj_dir / name) as im:
                    im.verify()
            except Exception as exc:
                report.errors.append(f"undecodable image {name}: {exc!r}")
                break

    return report


def _validate_one(args: tuple[str, dict[str, Any], bool]) -> TrajectoryReport:
    path, spec_kwargs, decode = args
    return validate_trajectory(path, TrajectorySpec(**spec_kwargs), check_images_decodable=decode)


def validate_dataset(
    root: str | Path,
    *,
    model: str = "vint",
    spec: TrajectorySpec | None = None,
    check_images_decodable: bool = False,
    workers: int = 0,
    trajectory_names: Iterable[str] | None = None,
) -> DatasetReport:
    """Validate every trajectory directory under ``root``."""
    root = Path(root)
    spec = spec or TrajectorySpec.for_model(model)
    report = DatasetReport(root=str(root), model=model, spec=dataclasses.asdict(spec))

    if not root.is_dir():
        report.dataset_errors.append(f"{root} is not a directory")
        return report

    if trajectory_names is not None:
        dirs = [root / n for n in trajectory_names]
        missing = [str(d) for d in dirs if not d.is_dir()]
        if missing:
            report.dataset_errors.append(f"named trajectories not found: {missing[:10]}")
        dirs = [d for d in dirs if d.is_dir()]
    else:
        dirs = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))

    if not dirs:
        report.dataset_errors.append(
            f"no trajectory directories under {root} "
            "(expected <root>/<traj_name>/{0.jpg,...,traj_data.pkl})"
        )
        return report

    partial = [p.name for p in root.iterdir() if p.name.startswith(".partial-")]
    if partial:
        report.dataset_errors.append(
            f"{len(partial)} staging directories left behind by an interrupted collector: "
            f"{sorted(partial)[:5]} -- remove them before training"
        )

    spec_kwargs = dataclasses.asdict(spec)
    if workers and workers > 1:
        payload = [(str(d), spec_kwargs, check_images_decodable) for d in dirs]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_validate_one, item) for item in payload]
            report.trajectories = [f.result() for f in as_completed(futures)]
        report.trajectories.sort(key=lambda t: t.name)
    else:
        report.trajectories = [
            validate_trajectory(d, spec, check_images_decodable=check_images_decodable)
            for d in dirs
        ]

    return report


def _format_human(report: DatasetReport, *, verbose: bool) -> str:
    lines: list[str] = []
    s = report.summary()
    lines.append(f"dataset : {report.root}")
    lines.append(f"spec    : {report.model} {report.spec}")
    lines.append(
        f"counts  : {s['n_valid']}/{s['n_trajectories']} valid, "
        f"{s['n_usable']} usable, {s['total_frames']} frames, {s['total_samples']} samples"
    )
    lines.append(f"path    : {s['total_path_length_m']:.1f} m total")
    if s["metric_waypoint_spacing_estimate"] is not None:
        lines.append(
            "spacing : metric_waypoint_spacing ~ "
            f"{s['metric_waypoint_spacing_estimate']:.4f} m "
            f"(sd {s['metric_waypoint_spacing_std']:.4f} across trajectories)"
        )
    for err in report.dataset_errors:
        lines.append(f"ERROR   : {err}")
    for t in report.trajectories:
        if t.errors or (verbose and t.warnings):
            lines.append(f"  {t.name}")
            for e in t.errors:
                lines.append(f"    ERROR   {e}")
            for w in t.warnings:
                lines.append(f"    warning {w}")
    n_warn = sum(len(t.warnings) for t in report.trajectories)
    if n_warn and not verbose:
        lines.append(f"({n_warn} warnings suppressed; pass -v to show)")
    lines.append("RESULT  : " + ("PASS" if report.ok else "FAIL"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m navfm.validate",
        description="Validate a GNM/ViNT/NoMaD-format dataset directory.",
    )
    p.add_argument("root", help="dataset root containing <traj_name>/ subdirectories")
    p.add_argument("--model", default="vint", choices=["gnm", "vint", "nomad"])
    p.add_argument("--waypoint-spacing", type=int, default=1)
    p.add_argument("--end-slack", type=int, default=0)
    p.add_argument("--decode-images", action="store_true", help="verify every JPEG (slow)")
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--json", metavar="PATH", help="write the full report as JSON")
    p.add_argument("-v", "--verbose", action="store_true", help="show warnings")
    args = p.parse_args(argv)

    spec = TrajectorySpec.for_model(
        args.model, waypoint_spacing=args.waypoint_spacing, end_slack=args.end_slack
    )
    report = validate_dataset(
        args.root,
        model=args.model,
        spec=spec,
        check_images_decodable=args.decode_images,
        workers=args.workers,
    )

    print(_format_human(report, verbose=args.verbose))
    if args.json:
        Path(args.json).write_text(json.dumps(report.to_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
