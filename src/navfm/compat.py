"""Compatibility harness: does one trajectory satisfy the Option 1 contract?

    python -m navfm.compat <trajectory_dir> --source "GO Stanford reference dataset"

Answers exactly one question, for exactly one trajectory directory: **would the
unchanged ViNT data path accept this?** Twelve checks, every one required. There
is no "green if most passed" — one required failure makes the overall result
``BLOCKED``, because a partially compatible trajectory is not compatible.

The last two checks are the ones that matter, and they are deliberately not
reimplementations. Check 11 runs `navfm.validate`; check 12 constructs the
reference ``ViNT_Dataset`` over a split containing only this trajectory and
draws a sample through it. Everything before them is diagnostic: it exists so
that a failure at 11 or 12 arrives with a located cause instead of a traceback.

**This harness reports; it never repairs.** It does not write to the trajectory,
does not coerce a failing field, and does not downgrade a required check to a
warning. If the data is wrong, the correct output is ``BLOCKED`` with the reason
named.

## Provenance is part of the result, not a footnote

Every report carries ``source``, ``purpose``, ``collected_by_project`` and
``pilot_evidence``. A report over the GO Stanford reference corpus proves the
*harness* works; it is not evidence that this project can collect compatible
data, and a reader finding the file later must not be able to mistake it for
that. The fields are mandatory for that reason and are printed at the top.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

__all__ = [
    "CheckResult",
    "CompatibilityReport",
    "check_trajectory",
    "format_report",
]

IMAGE_RE = re.compile(r"^(\d+)\.jpg$")
TRAJ_DATA = "traj_data.pkl"


@dataclasses.dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.name,
            "result": "PASS" if self.passed else "FAIL",
            "detail": self.detail,
        }


@dataclasses.dataclass
class CompatibilityReport:
    trajectory: str
    source: str
    purpose: str
    collected_by_project: bool
    pilot_evidence: bool
    frame_count: int
    checks: list[CheckResult]
    dataset_digest: str = ""

    @property
    def overall(self) -> str:
        return "PASS" if all(c.passed for c in self.checks) else "BLOCKED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "trajectory": self.trajectory,
            "source": self.source,
            "purpose": self.purpose,
            "collected_by_project": self.collected_by_project,
            "pilot_evidence": self.pilot_evidence,
            "frame_count": self.frame_count,
            "dataset_digest": self.dataset_digest,
            "checks": [c.as_dict() for c in self.checks],
            "overall": self.overall,
        }


def _images(traj_dir: Path) -> list[tuple[int, Path]]:
    out = []
    for p in traj_dir.iterdir():
        m = IMAGE_RE.match(p.name)
        if m:
            out.append((int(m.group(1)), p))
    return sorted(out)


def _vint_data_path(traj_dir: Path, dataset_name: str) -> tuple[bool, str]:
    """Draw a sample through the reference ``ViNT_Dataset``.

    Builds a split containing only this trajectory, in a temporary tree, so the
    check exercises the real loader rather than a description of it. No
    checkpoint is loaded and no model is constructed: this asks whether the data
    path accepts the data, which is a question about the data.
    """
    from navfm import upstream

    tmp = Path(tempfile.mkdtemp(prefix="navfm-compat-"))
    try:
        data_folder = tmp / "data"
        data_folder.mkdir()
        # Symlink rather than copy: the harness must not be able to alter the
        # trajectory it is judging, and a copy invites a silent divergence.
        (data_folder / traj_dir.name).symlink_to(traj_dir.resolve())

        split_folder = tmp / "split"
        split_folder.mkdir()
        (split_folder / "traj_names.txt").write_text(traj_dir.name + "\n")

        cfg = upstream.model_config("vint")
        dataset = upstream.build_dataset(
            dataset_name=dataset_name,
            data_folder=data_folder,
            split_folder=split_folder,
            cfg=cfg,
            negative_mining=False,
        )
        if len(dataset) == 0:
            return False, (
                f"the reference loader built successfully but yielded 0 samples from "
                f"{traj_dir.name}; a trajectory too short for context_size + "
                f"len_traj_pred produces no training pair and cannot be used"
            )
        sample = dataset[0]
        shapes = ", ".join(f"{tuple(x.shape)}" for x in sample if hasattr(x, "shape"))
        return True, f"{len(dataset)} samples; first sample tensors {shapes}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_trajectory(
    traj_dir: str | Path,
    *,
    source: str,
    purpose: str,
    collected_by_project: bool,
    pilot_evidence: bool,
    dataset_name: str = "go_stanford",
    dataset_digest: str = "",
) -> CompatibilityReport:
    """Run all twelve required checks. Every one must pass for overall PASS."""
    traj_dir = Path(traj_dir)
    checks: list[CheckResult] = []
    frame_count = 0

    def add(name: str, passed: bool, detail: str) -> bool:
        checks.append(CheckResult(name, passed, detail))
        return passed

    # 1: the pickle exists.
    pkl = traj_dir / TRAJ_DATA
    have_pkl = add(
        "traj_data_pkl_exists",
        pkl.is_file(),
        str(pkl) if pkl.is_file() else f"missing {TRAJ_DATA} in {traj_dir}",
    )

    # 2-3: numbered images, contiguous from 0.
    images = _images(traj_dir) if traj_dir.is_dir() else []
    add(
        "numbered_images_exist",
        bool(images),
        f"{len(images)} images" if images else f"no <n>.jpg files in {traj_dir}",
    )
    expected = list(range(len(images)))
    actual = [i for i, _ in images]
    add(
        "image_numbering_contiguous",
        bool(images) and actual == expected,
        "0.." + str(len(images) - 1) + " with no gaps"
        if images and actual == expected
        else f"numbering is not 0..N-1 contiguous: got {actual[:8]}{'...' if len(actual) > 8 else ''}",
    )

    # 4: every image decodes. A file that exists but will not decode fails at
    # training time, hours in, not here.
    unreadable: list[str] = []
    try:
        from PIL import Image

        for _, p in images:
            try:
                with Image.open(p) as im:
                    im.load()
            except Exception as exc:
                unreadable.append(f"{p.name}: {type(exc).__name__}")
    except ImportError:
        unreadable.append("Pillow unavailable, so image readability was not checked")
    add(
        "images_readable",
        bool(images) and not unreadable,
        f"all {len(images)} decode"
        if images and not unreadable
        else "; ".join(unreadable[:5]) or "no images to read",
    )

    # 5-9: the fields, through the approved normalisation boundary.
    position = yaw = None
    if have_pkl:
        import pickle

        from navfm.trajio import TrajectoryContractError, normalise_traj_data

        try:
            with open(pkl, "rb") as fh:
                raw = pickle.load(fh)
            out = normalise_traj_data(raw, trajectory=traj_dir.name)
            position, yaw = out["position"], out["yaw"]
            norm_ok, norm_detail = True, "navfm.trajio accepted the trajectory"
        except (TrajectoryContractError, Exception) as exc:
            norm_ok, norm_detail = False, f"{type(exc).__name__}: {exc}"
    else:
        norm_ok, norm_detail = False, f"no {TRAJ_DATA} to read"

    add(
        "position_numeric",
        norm_ok and position is not None and position.dtype.kind == "f",
        f"dtype {position.dtype}" if norm_ok and position is not None else norm_detail,
    )
    add(
        "position_shape_T2",
        position is not None and position.ndim == 2 and position.shape[1] == 2,
        f"shape {position.shape}" if position is not None else norm_detail,
    )
    add(
        "yaw_numeric",
        norm_ok and yaw is not None and yaw.dtype.kind == "f",
        f"dtype {yaw.dtype}" if norm_ok and yaw is not None else norm_detail,
    )
    add(
        "yaw_shape_T",
        yaw is not None and yaw.ndim == 1,
        f"shape {yaw.shape}" if yaw is not None else norm_detail,
    )
    finite = (
        position is not None
        and yaw is not None
        and bool(np.isfinite(position).all())
        and bool(np.isfinite(yaw).all())
    )
    add(
        "finite_values",
        finite,
        "all position and yaw values finite" if finite else norm_detail,
    )

    # 10: the images and the pose arrays must index the same frames.
    if position is not None:
        frame_count = int(position.shape[0])
    consistent = bool(images) and position is not None and len(images) == frame_count
    add(
        "sequence_consistency",
        consistent,
        f"{len(images)} images == {frame_count} poses"
        if consistent
        else f"{len(images)} images vs {frame_count} poses -- image t.jpg must be the "
        f"observation at position[t], yaw[t]",
    )

    # 11: the project validator, not a reimplementation of it.
    try:
        from navfm import upstream
        from navfm.schema import TrajectorySpec
        from navfm.validate import validate_trajectory

        # Geometry is read from the reference config, not hardcoded: the
        # validator and the loader must agree about what a usable trajectory is,
        # and a second copy of these numbers is a second thing to drift.
        vcfg = upstream.model_config("vint")
        spec = TrajectorySpec(
            context_size=int(vcfg["context_size"]),
            len_traj_pred=int(vcfg["len_traj_pred"]),
        )
        rep = validate_trajectory(traj_dir, spec, check_images_decodable=True)
        add(
            "project_validator",
            rep.ok,
            f"{rep.n_frames} frames, {rep.n_images} images, path {rep.path_length_m:.2f} m"
            if rep.ok
            else "; ".join(rep.errors[:3]),
        )
    except Exception as exc:
        add("project_validator", False, f"{type(exc).__name__}: {exc}")

    # 12: the reference loader itself. This is the check the pilot exists to run.
    ok, detail = _vint_data_path(traj_dir, dataset_name)
    add("unchanged_vint_data_path", ok, detail)

    return CompatibilityReport(
        trajectory=traj_dir.name,
        source=source,
        purpose=purpose,
        collected_by_project=collected_by_project,
        pilot_evidence=pilot_evidence,
        frame_count=frame_count,
        checks=checks,
        dataset_digest=dataset_digest,
    )


def format_report(report: CompatibilityReport) -> str:
    width = max(len(c.name) for c in report.checks) + 2
    lines = [
        "Compatibility Harness Report",
        "=" * 28,
        "",
        f"Trajectory                   : {report.trajectory}",
        f"Source                       : {report.source}",
        f"Purpose                      : {report.purpose}",
        f"Project-collected trajectory : {'Yes' if report.collected_by_project else 'No'}",
        f"Pilot evidence               : {'Yes' if report.pilot_evidence else 'No'}",
        f"Frame count                  : {report.frame_count}",
    ]
    if report.dataset_digest:
        lines.append(f"Dataset digest               : {report.dataset_digest}")
    lines += ["", "Required checks (all must pass):", ""]
    for c in report.checks:
        lines.append(f"  {c.name:<{width}} {'PASS' if c.passed else 'FAIL'}  {c.detail}")
    failed = [c.name for c in report.checks if not c.passed]
    lines += ["", f"Overall: {report.overall}"]
    if failed:
        lines.append(f"Failed required checks: {', '.join(failed)}")
        lines.append(
            "BLOCKED is the correct result for a trajectory that fails any required "
            "check. The data must not be modified to make this pass."
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("trajectory")
    p.add_argument("--source", required=True, help="where this trajectory came from")
    p.add_argument("--purpose", required=True)
    p.add_argument("--collected-by-project", action="store_true")
    p.add_argument("--pilot-evidence", action="store_true")
    p.add_argument("--dataset-name", default="go_stanford")
    p.add_argument("--dataset-digest", default="")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    report = check_trajectory(
        args.trajectory,
        source=args.source,
        purpose=args.purpose,
        collected_by_project=args.collected_by_project,
        pilot_evidence=args.pilot_evidence,
        dataset_name=args.dataset_name,
        dataset_digest=args.dataset_digest,
    )
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(format_report(report), end="")
    return 0 if report.overall == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
