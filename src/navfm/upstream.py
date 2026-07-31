"""Locating and driving the reference ``visualnav-transformer`` package.

Both ``navfm.eval.offline`` and ``navfm.train.run`` have to reach into the
reference implementation for three things that only it can supply:

* the **model geometry**, which lives in ``train/config/{defaults,vint,gnm}.yaml``
  and not in any paper (``mha_num_attention_layers: 4`` contradicts the ViNT
  class default of 2, and the released ``vint.pth`` was trained with the config);
* the **dataset class**, ``ViNT_Dataset`` -- reproducing its sampling would
  reproduce our reading of it, which is exactly what this project refuses to do;
* the **normalisation constants** in ``vint_train/data/data_config.yaml``,
  notably ``metric_waypoint_spacing``, which is what converts a normalised ADE
  into metres.

Resolution order for the clone: ``$NAVFM_UPSTREAM`` → ``third_party/
visualnav-transformer`` next to this repo → ``~/vnt`` → an installed
``vint_train`` package. This mirrors ``tests/test_upstream_compat.py`` so that
the code and its compatibility proof can never disagree about *which* upstream
they are talking to.

Two deliberate non-features:

* We do not vendor or re-declare any upstream constant. Everything is read from
  the clone at run time and echoed into the run's ``config.json``, so a run
  record says which values it used.
* We do not patch the clone from here. ``scripts/patch_upstream.py`` owns that,
  is idempotent and reversible, and its diff is gate G0 evidence.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "MODEL_CONFIGS",
    "UpstreamNotFound",
    "apply_reference_transform",
    "build_dataset",
    "build_model",
    "data_config",
    "default_splits_root",
    "ensure_upstream",
    "metric_waypoint_spacing",
    "model_config",
    "reference_transform",
    "upstream_commit",
    "upstream_root",
]

#: Shipped training config per model type, relative to ``train/``. These are the
#: geometry of record: the released checkpoints were trained from them.
MODEL_CONFIGS: dict[str, str] = {
    "vint": "config/vint.yaml",
    "gnm": "config/gnm.yaml",
    "nomad": "config/nomad.yaml",
}

_DEFAULTS = "config/defaults.yaml"


class UpstreamNotFound(RuntimeError):
    """The reference implementation could not be located."""


def _candidates() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("NAVFM_UPSTREAM")
    if env:
        out.append(Path(env).expanduser())
    out.append(Path(__file__).resolve().parents[2] / "third_party" / "visualnav-transformer")
    out.append(Path.home() / "vnt")
    return out


@lru_cache(maxsize=1)
def upstream_root() -> Path:
    """Path to the reference clone (the repo root, not its ``train/`` subdir)."""
    for c in _candidates():
        if (c / "train" / "vint_train" / "data" / "vint_dataset.py").is_file():
            return c.resolve()
    raise UpstreamNotFound(
        "could not find robodhruv/visualnav-transformer. Set NAVFM_UPSTREAM to a "
        "clone, or clone it to third_party/visualnav-transformer:\n"
        "  git clone https://github.com/robodhruv/visualnav-transformer.git "
        "third_party/visualnav-transformer\n"
        "  python scripts/patch_upstream.py third_party/visualnav-transformer"
    )


def ensure_upstream() -> Path:
    """Make ``vint_train`` importable and return the clone root.

    Prefers an explicit clone over an installed distribution, because a run must
    be able to say which *commit* produced its numbers, and a wheel cannot.
    """
    root = upstream_root()
    train_dir = str(root / "train")
    if train_dir not in sys.path:
        sys.path.insert(0, train_dir)
    return root


def upstream_commit() -> str:
    """Short SHA of the reference clone, or ``"unknown"``. Goes in run records."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(upstream_root()), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except Exception:  # pragma: no cover - only when git or the clone is absent
        return "unknown"
    return out.stdout.strip()


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text()) or {}


@lru_cache(maxsize=1)
def data_config() -> dict[str, Any]:
    """``vint_train/data/data_config.yaml`` as a dict.

    Note that it defines ``carla_intvns`` twice; ``yaml.safe_load`` keeps the
    last, which is also what upstream gets. Documented in docs/REPRODUCTION.md.
    """
    return _load_yaml(upstream_root() / "train" / "vint_train" / "data" / "data_config.yaml")


def metric_waypoint_spacing(dataset_name: str) -> float:
    """Metres per normalised waypoint unit for ``dataset_name``.

    This is the only route from a normalised ADE to a number in metres, and a
    wrong value silently rescales every distance we report -- so an unregistered
    dataset is an error, never a default. ``scripts/register_dataset.py`` adds
    new entries.
    """
    cfg = data_config()
    entry = cfg.get(dataset_name)
    if not isinstance(entry, dict) or "metric_waypoint_spacing" not in entry:
        known = sorted(k for k, v in cfg.items() if isinstance(v, dict) and "metric_waypoint_spacing" in v)
        raise KeyError(
            f"dataset {dataset_name!r} has no metric_waypoint_spacing in the reference "
            f"data_config.yaml. Register it first:\n"
            f"  python scripts/register_dataset.py {upstream_root()} --name {dataset_name} "
            f"--spacing <value from `python -m navfm.stats`>\n"
            f"known datasets: {known}"
        )
    return float(entry["metric_waypoint_spacing"])


def model_config(model_type: str) -> dict[str, Any]:
    """Shipped training config for ``model_type``, layered over ``defaults.yaml``.

    Upstream's ``train.py`` does exactly this layering, so the geometry we build
    is the geometry the released checkpoint was trained with -- including the
    places where the config contradicts both the paper and the class defaults
    (``mha_num_attention_layers: 4`` vs the ``ViNT.__init__`` default of 2).
    """
    if model_type not in MODEL_CONFIGS:
        raise ValueError(f"unknown model_type {model_type!r}; expected one of {sorted(MODEL_CONFIGS)}")
    train_dir = upstream_root() / "train"
    cfg = _load_yaml(train_dir / _DEFAULTS)
    cfg.update(_load_yaml(train_dir / MODEL_CONFIGS[model_type]))
    return cfg


def build_model(model_type: str, cfg: dict[str, Any] | None = None) -> Any:
    """Instantiate ViNT or GNM from the shipped config, as ``train.py`` does.

    Kept deliberately in lockstep with ``train.py``'s construction block: the
    argument lists below are copied from it, not inferred from the class
    signatures, because the two differ (``ViNT`` defaults to 2 attention heads
    and layers; the config says 4).
    """
    ensure_upstream()
    cfg = model_config(model_type) if cfg is None else cfg

    if model_type == "vint":
        from vint_train.models.vint.vint import ViNT

        return ViNT(
            context_size=cfg["context_size"],
            len_traj_pred=cfg["len_traj_pred"],
            learn_angle=cfg["learn_angle"],
            obs_encoder=cfg["obs_encoder"],
            obs_encoding_size=cfg["obs_encoding_size"],
            late_fusion=cfg["late_fusion"],
            mha_num_attention_heads=cfg["mha_num_attention_heads"],
            mha_num_attention_layers=cfg["mha_num_attention_layers"],
            mha_ff_dim_factor=cfg["mha_ff_dim_factor"],
        )
    if model_type == "gnm":
        from vint_train.models.gnm.gnm import GNM

        return GNM(
            cfg["context_size"],
            cfg["len_traj_pred"],
            cfg["learn_angle"],
            cfg["obs_encoding_size"],
            cfg["goal_encoding_size"],
        )
    raise NotImplementedError(
        f"model_type {model_type!r} is not wired here. NoMaD needs a diffusion "
        "sampling loop for evaluation (train_utils._compute_losses_nomad), which "
        "is a separate entrypoint -- see docs/EXPERIMENTS.md E1.3."
    )


def default_splits_root() -> Path:
    """Where ``navfm.splits --out`` writes by default, per docs/REPRODUCTION.md."""
    return upstream_root() / "train" / "vint_train" / "data" / "data_splits"


def build_dataset(
    *,
    dataset_name: str,
    data_folder: str | Path,
    split_folder: str | Path,
    cfg: dict[str, Any],
    end_slack: int = 0,
    waypoint_spacing: int = 1,
    negative_mining: bool = True,
    goals_per_obs: int = 1,
) -> Any:
    """Construct the reference ``ViNT_Dataset`` for one dataset/split.

    Every argument is passed positionally-by-name exactly as ``train.py`` passes
    it. ``negative_mining`` and ``goals_per_obs`` are accepted because the class
    requires them, but both are dead upstream (docs/METHODOLOGY.md §5) -- they
    are recorded in the run config so a reader can see we did not rely on them.
    """
    ensure_upstream()
    from vint_train.data.vint_dataset import ViNT_Dataset

    split_folder = Path(split_folder)
    names = split_folder / "traj_names.txt"
    if not names.is_file():
        raise FileNotFoundError(
            f"no traj_names.txt under {split_folder}. Generate splits first:\n"
            f"  python -m navfm.splits {data_folder} --name {dataset_name} "
            f"--out {default_splits_root()} --group-by scene"
        )

    return ViNT_Dataset(
        data_folder=str(data_folder),
        data_split_folder=str(split_folder),
        dataset_name=dataset_name,
        image_size=cfg["image_size"],
        waypoint_spacing=waypoint_spacing,
        min_dist_cat=cfg["distance"]["min_dist_cat"],
        max_dist_cat=cfg["distance"]["max_dist_cat"],
        min_action_distance=cfg["action"]["min_dist_cat"],
        max_action_distance=cfg["action"]["max_dist_cat"],
        negative_mining=negative_mining,
        len_traj_pred=cfg["len_traj_pred"],
        learn_angle=cfg["learn_angle"],
        context_size=cfg["context_size"],
        context_type=cfg.get("context_type", "temporal"),
        end_slack=end_slack,
        goals_per_obs=goals_per_obs,
        normalize=cfg["normalize"],
        goal_type=cfg["goal_type"],
    )


def reference_transform() -> Any:
    """The image normalisation upstream applies in ``train``/``evaluate``.

    ``train.py`` builds ``transforms.Normalize(ImageNet mean/std)`` and applies
    it **per 3-channel frame**, not to the stacked 18-channel tensor -- see
    :func:`apply_reference_transform`. Same numbers either way for Normalize
    specifically, but the split/cat is preserved so that any future upstream
    transform that is not channel-wise stays faithful.
    """
    from torchvision import transforms

    return transforms.Compose(
        [transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])]
    )


def apply_reference_transform(obs_image: Any, goal_image: Any, transform: Any, device: Any) -> tuple[Any, Any]:
    """Port of the four lines every upstream train/eval loop repeats.

    ``obs_image`` arrives as ``(B, 3*(P+1), H, W)``; upstream splits it into
    ``P+1`` three-channel frames, transforms each, and concatenates back. The
    goal image is transformed on its own.
    """
    import torch

    frames = torch.split(obs_image, 3, dim=1)
    obs = torch.cat([transform(f).to(device) for f in frames], dim=1)
    goal = transform(goal_image).to(device)
    return obs, goal
