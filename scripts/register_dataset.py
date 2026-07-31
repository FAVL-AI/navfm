#!/usr/bin/env python3
"""Register a new dataset in the reference ``data_config.yaml``.

``ViNT_Dataset.__init__`` asserts the dataset name is a key in
``vint_train/data/data_config.yaml`` and derives ``dataset_index`` from the
*sorted* key order. Two consequences most people discover the hard way:

1. You cannot train on a dataset that is not registered -- the assertion fires
   before anything else.
2. Adding a key **renumbers** ``dataset_index`` for every alphabetically later
   dataset. ``dataset_index`` is returned in every batch and is what GNM uses to
   look up per-robot normalisation. If you add a dataset and reuse an old
   checkpoint's index mapping, the mapping is silently wrong. This script prints
   the before/after index table so the change is visible.

Usage::

    python scripts/register_dataset.py third_party/visualnav-transformer \\
        --name isaac_m3pro --spacing 0.088 \\
        --camera-height 0.28 --camera-x-offset 0.16 --hfov 64
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from navfm.schema import DatasetSpec


def index_table(config: dict) -> dict[str, int]:
    names = sorted(k for k in config if k != "action_stats")
    return {n: i for i, n in enumerate(names)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("root", help="path to a visualnav-transformer clone")
    p.add_argument("--name", required=True)
    p.add_argument("--spacing", type=float, required=True, help="metric_waypoint_spacing, metres")
    p.add_argument("--camera-height", type=float, default=None)
    p.add_argument("--camera-x-offset", type=float, default=None)
    p.add_argument("--hfov", type=float, default=None, help="horizontal FOV, degrees")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    cfg_path = Path(args.root) / "train" / "vint_train" / "data" / "data_config.yaml"
    if not cfg_path.is_file():
        print(f"not found: {cfg_path}", file=sys.stderr)
        return 2

    config = yaml.safe_load(cfg_path.read_text()) or {}
    before = index_table(config)

    camera_matrix = None
    if args.hfov is not None:
        f = 0.5 * args.width / math.tan(math.radians(args.hfov) / 2.0)
        camera_matrix = {"fx": f, "fy": f, "cx": args.width / 2.0, "cy": args.height / 2.0}

    spec = DatasetSpec(
        name=args.name,
        metric_waypoint_spacing=args.spacing,
        camera_height=args.camera_height,
        camera_x_offset=args.camera_x_offset,
        camera_matrix=camera_matrix,
        dist_coeffs={"k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0, "k3": 0.0}
        if camera_matrix
        else None,
    )

    if args.name in config:
        print(f"note: {args.name} already registered; overwriting its entry")
    config[args.name] = spec.to_data_config_entry()
    after = index_table(config)

    shifted = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    print(f"registered {args.name} with metric_waypoint_spacing={args.spacing:.4f}")
    print(f"dataset_index for {args.name}: {after[args.name]}")
    if shifted:
        print("\nWARNING: adding this key renumbers dataset_index for existing datasets:")
        for k, (b, a) in sorted(shifted.items(), key=lambda kv: kv[1][0]):
            print(f"  {k:<16} {b} -> {a}")
        print(
            "dataset_index is returned in every batch. If you are resuming from a "
            "checkpoint that assumed the old numbering, this changes the meaning of "
            "that field."
        )

    if args.dry_run:
        print("\n(dry run; nothing written)")
        return 0

    backup = cfg_path.with_suffix(".yaml.navfm-backup")
    if not backup.exists():
        backup.write_text(cfg_path.read_text())
        print(f"\nbacked up original to {backup}")
    cfg_path.write_text(yaml.safe_dump(config, sort_keys=False, default_flow_style=False))
    print(f"wrote {cfg_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
