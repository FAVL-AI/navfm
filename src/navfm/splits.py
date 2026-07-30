"""Deterministic, reproducible train/test splits.

The reference ``train/data_split.py`` calls ``random.shuffle`` with no seed, so
every invocation produces a different split and no published result can be
reproduced exactly. Worse, for simulation data a random split leaks: two
trajectories recorded in the same scene share the same walls, textures and
lighting, so a random split measures memorisation of the scene rather than
generalisation.

This module fixes both:

* splits are a pure function of the trajectory (or group) name via a stable
  BLAKE2b hash, so they are identical on any machine and in any order;
* an optional ``group_by`` callable holds out whole scenes/environments, which
  is the split an evaluation claim should rest on.

See :func:`split_names` for why the grouped and ungrouped cases use different
algorithms — thresholding a hash is right for hundreds of trajectories and
badly wrong for a handful of scenes.

    python -m navfm.splits /data/isaac_m3pro --name isaac_m3pro \\
        --out train/vint_train/data/data_splits --split 0.8 --group-by scene
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from .schema import TRAJ_DATA_FILENAME

__all__ = ["scene_of", "split_names", "stable_fraction", "write_splits"]


def stable_fraction(key: str, *, salt: str = "") -> float:
    """Map a string to a uniform float in ``[0, 1)``, deterministically.

    BLAKE2b rather than ``hash()`` because CPython's string hash is salted per
    process (``PYTHONHASHSEED``) and would break reproducibility.
    """
    digest = hashlib.blake2b((salt + "\x00" + key).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(1 << 64)


def scene_of(name: str) -> str:
    """Default grouping key: the leading non-numeric component of a name.

    ``office_a_run_0003`` -> ``office_a``. Collector-generated names follow
    ``<scene>_run_<n>`` by construction (see :mod:`navfm.isaac.collect`).
    """
    m = re.match(r"^(.*?)_run_\d+$", name)
    if m:
        return m.group(1)
    m = re.match(r"^(.*?)[_-]?\d+$", name)
    return m.group(1) if m else name


def split_names(
    names: Iterable[str],
    *,
    split: float = 0.8,
    salt: str = "",
    group_by: Callable[[str], str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return ``(train, test)`` name lists. ``split`` is the *train* fraction.

    Two different algorithms, because the right one depends on how many
    independent units there are:

    **Ungrouped** (hundreds of trajectories): threshold each name's stable hash
    against ``split``. The realised fraction concentrates on ``split`` by the
    law of large numbers, and — the property that matters — adding new
    trajectories never moves an existing one, so a split stays valid as a
    dataset grows.

    **Grouped** (typically 3-10 scenes): thresholding fails here. With 3 scenes
    and ``split=0.8`` there is a 51 % chance that *every* scene hashes below the
    threshold and the test set is empty; changing the salt is a coin flip, not a
    fix. So we instead *rank* the groups by their stable hash and take the first
    ``round(split · n)`` as train, clamped so both sides get at least one group.
    Still deterministic and salt-controllable, and the split proportion is
    guaranteed. The cost is that adding a new scene can reshuffle the
    assignment — record the group lists in your paper rather than the salt.
    """
    if not 0.0 < split < 1.0:
        raise ValueError("split must be strictly between 0 and 1")
    names = sorted(set(names))

    if group_by is None:
        train = [n for n in names if stable_fraction(n, salt=salt) < split]
        test = [n for n in names if stable_fraction(n, salt=salt) >= split]
        return train, test

    groups = sorted({group_by(n) for n in names})
    if len(groups) < 2:
        raise ValueError(
            f"grouped splitting needs at least 2 groups, found {groups}. "
            "Collect from more scenes, or drop --group-by and accept that the "
            "split measures within-scene generalisation only."
        )
    ranked = sorted(groups, key=lambda g: stable_fraction(g, salt=salt))
    n_train = min(len(groups) - 1, max(1, round(split * len(groups))))
    train_groups = set(ranked[:n_train])

    train = [n for n in names if group_by(n) in train_groups]
    test = [n for n in names if group_by(n) not in train_groups]
    return train, test


def discover_trajectories(root: str | Path) -> list[str]:
    root = Path(root)
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and (p / TRAJ_DATA_FILENAME).is_file()
    )


def write_splits(
    out_dir: str | Path,
    dataset_name: str,
    train: Sequence[str],
    test: Sequence[str],
) -> tuple[Path, Path]:
    """Write ``<out_dir>/<dataset_name>/{train,test}/traj_names.txt``."""
    out_dir = Path(out_dir)
    train_dir = out_dir / dataset_name / "train"
    test_dir = out_dir / dataset_name / "test"
    for d in (train_dir, test_dir):
        d.mkdir(parents=True, exist_ok=True)
    train_path = train_dir / "traj_names.txt"
    test_path = test_dir / "traj_names.txt"
    train_path.write_text("".join(f"{n}\n" for n in train))
    test_path.write_text("".join(f"{n}\n" for n in test))
    return train_path, test_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m navfm.splits",
        description="Write deterministic train/test splits in the reference layout.",
    )
    p.add_argument("root")
    p.add_argument("--name", required=True)
    p.add_argument("--out", required=True, help="data_splits directory")
    p.add_argument("--split", type=float, default=0.8, help="train fraction")
    p.add_argument("--salt", default="", help="change to resample without touching names")
    p.add_argument(
        "--group-by",
        choices=["none", "scene"],
        default="scene",
        help="scene-level holdout prevents same-environment leakage (default)",
    )
    args = p.parse_args(argv)

    names = discover_trajectories(args.root)
    if not names:
        print(f"no trajectories found under {args.root}", file=sys.stderr)
        return 1

    group_by = scene_of if args.group_by == "scene" else None
    train, test = split_names(names, split=args.split, salt=args.salt, group_by=group_by)
    train_path, test_path = write_splits(args.out, args.name, train, test)

    if group_by is not None:
        groups = defaultdict(list)
        for n in names:
            groups[group_by(n)].append(n)
        train_groups = sorted({group_by(n) for n in train})
        test_groups = sorted({group_by(n) for n in test})
        print(f"groups   : {len(groups)} -> train {train_groups}, test {test_groups}")

    print(f"train    : {len(train)} trajectories -> {train_path}")
    print(f"test     : {len(test)} trajectories -> {test_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
