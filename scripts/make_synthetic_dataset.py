#!/usr/bin/env python3
"""Write a tiny GNM-format dataset, for smoke-testing the training/eval path.

The point is a dataset that is *real* as far as every downstream component is
concerned -- written through :class:`navfm.writer.TrajectoryWriter`, indexed by
the reference ``ViNT_Dataset``, split by :mod:`navfm.splits` -- but small enough
to run on a laptop CPU in seconds. It exists so that
``python -m navfm.eval.offline`` and ``python -m navfm.train.run`` can be shown
to work end to end before ``vint.pth`` and the real corpora are on disk (those
arrive in Phase 0; see docs/WORKFLOW.md).

It is **not** a substitute for data. The images are noise with a moving bar, so
nothing learned from it means anything. Runs against it are marked with a
random-initialisation or synthetic warning wherever they surface.

    python scripts/make_synthetic_dataset.py /tmp/synth --trajectories 6 --length 60
    python -m navfm.splits /tmp/synth --name recon --out /tmp/synth_splits --group-by scene

``--name recon`` borrows an already-registered dataset key so this never has to
mutate the reference clone's ``data_config.yaml``; the arc lengths below are
scaled to sit near ``recon``'s ``metric_waypoint_spacing`` of 0.25 m so the
normalised actions land in a realistic range.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from navfm.writer import TrajectoryWriter


def make_dataset(
    root: str | Path,
    *,
    n_trajectories: int = 6,
    length: int = 60,
    n_scenes: int = 2,
    spacing: float = 0.25,
    height: int = 96,
    width: int = 128,
    seed: int = 7,
) -> Path:
    """Write ``n_trajectories`` arcs of ``length`` frames into ``root``.

    Each trajectory is a circular arc of a different radius, traversed at a
    constant arc length per step of ``spacing`` metres, with the heading tangent
    to the path and already unwrapped (the writer unwraps again on close --
    docs/METHODOLOGY.md §5 constraint 5).

    The image is noise plus a vertical bar whose position advances with the
    frame index, so consecutive frames genuinely differ. A validator or a human
    can tell a stalled capture from a moving one.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    for k in range(n_trajectories):
        radius = 2.0 + 0.3 * k
        t = np.linspace(0.0, 2.0 * np.pi, length)
        pos = np.stack([radius * np.cos(t), radius * np.sin(t)], axis=1)
        pos *= spacing / (radius * (t[1] - t[0]))  # arc length per step -> spacing
        yaw = t + np.pi / 2.0  # tangent heading, monotone, so already unwrapped

        with TrajectoryWriter(root / f"scene{k % n_scenes}_run_{k:05d}") as w:
            for i in range(length):
                img = rng.integers(0, 96, (height, width, 3), dtype=np.uint8)
                bar = int((i / max(length - 1, 1)) * (width - 8))
                img[:, bar : bar + 8, :] = 255
                w.append(img, pos[i], yaw[i])
    return root


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="scripts/make_synthetic_dataset.py",
        description="Write a tiny GNM-format dataset for CPU smoke tests.",
    )
    p.add_argument("out", help="output directory")
    p.add_argument("--trajectories", type=int, default=6)
    p.add_argument("--length", type=int, default=60, help="frames per trajectory")
    p.add_argument("--scenes", type=int, default=2, help="distinct scene prefixes, for --group-by scene")
    p.add_argument("--spacing", type=float, default=0.25, help="metres of arc length per step")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args(argv)

    root = make_dataset(
        args.out,
        n_trajectories=args.trajectories,
        length=args.length,
        n_scenes=args.scenes,
        spacing=args.spacing,
        seed=args.seed,
    )
    names = sorted(d.name for d in root.iterdir() if d.is_dir())
    print(f"wrote {len(names)} trajectories x {args.length} frames to {root}")
    print("SYNTHETIC DATA -- images are noise; nothing learned from this means anything.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
