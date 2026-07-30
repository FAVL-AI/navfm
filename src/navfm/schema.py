"""Authoritative schema for the GNM / ViNT / NoMaD on-disk trajectory format.

The format is defined by the reference implementation
(``robodhruv/visualnav-transformer``) rather than by any written specification.
Every constraint encoded here was derived by reading the loader
(``train/vint_train/data/vint_dataset.py``) and the preprocessing scripts
(``train/process_bags.py``, ``train/process_recon.py``) at commit
``dca79815b704e5aa9c6bdc3082351f9e3b2848c2``.

On-disk layout::

    <dataset_root>/
      <trajectory_name>/
        0.jpg
        1.jpg
        ...
        <T-1>.jpg
        traj_data.pkl

``traj_data.pkl`` is a ``pickle`` of a ``dict`` with exactly two required keys:

``position``
    ``np.ndarray`` of shape ``(T, 2)``, dtype float, metres, in a fixed
    world/odometry frame. Column order is ``(x, y)``.
``yaw``
    ``np.ndarray`` of shape ``(T,)`` (a ``(T, 1)`` column is tolerated by the
    loader and squeezed), dtype float, radians, heading in the same frame,
    measured counter-clockwise from ``+x``.

Constraints the loader depends on, in order of how loudly they fail:

1. ``len(traj_data["position"]) == number_of_jpg_files``. The loader indexes
   images by integer timestep taken from the length of ``position``; a mismatch
   surfaces as a ``FileNotFoundError`` deep inside a worker process.
2. Image filenames are ``{t}.jpg`` for ``t`` in ``range(T)`` with **no
   zero-padding**. ``_load_image`` builds the path with ``f"{time}.jpg"``.
3. ``T`` must exceed ``context_size * waypoint_spacing + len_traj_pred *
   waypoint_spacing + end_slack``, otherwise the trajectory contributes zero
   samples and is silently dropped from the index.
4. Yaw must be *continuous* (unwrapped). ``_compute_actions`` computes
   ``yaw[1:] - yaw[0]`` with no angle wrapping, so a trajectory that crosses the
   +/-pi branch cut produces action labels with a spurious ``2*pi`` jump. The
   reference preprocessing scripts do not unwrap; this is a latent data bug that
   any new collection pipeline should avoid rather than replicate.

This module contains no I/O. See :mod:`navfm.writer` for writing and
:mod:`navfm.validate` for checking.
"""

from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

__all__ = [
    "IMAGE_ASPECT_RATIO",
    "IMAGE_EXTENSION",
    "IMAGE_NAME_RE",
    "MODEL_IMAGE_SIZES",
    "REQUIRED_KEYS",
    "TRAJ_DATA_FILENAME",
    "DatasetSpec",
    "TrajectorySchemaError",
    "TrajectorySpec",
    "check_traj_data",
    "min_length_for",
]

#: Reference loader hard-codes ``.jpg``; PNG is silently unreadable.
IMAGE_EXTENSION = ".jpg"

#: Unpadded integer stem, e.g. ``0.jpg``, ``17.jpg``. ``007.jpg`` is invalid.
IMAGE_NAME_RE = re.compile(r"^(0|[1-9]\d*)\.jpg$")

TRAJ_DATA_FILENAME = "traj_data.pkl"

REQUIRED_KEYS = ("position", "yaw")

#: ``data_utils.resize_and_aspect_crop`` centre-crops every image to 4:3 before
#: resizing. Collecting at a different aspect ratio silently discards pixels.
IMAGE_ASPECT_RATIO = 4.0 / 3.0

#: ``image_size`` from the reference configs, as ``(width, height)``.
MODEL_IMAGE_SIZES: Mapping[str, tuple[int, int]] = {
    "gnm": (85, 64),
    "vint": (85, 64),
    "nomad": (96, 96),
}


class TrajectorySchemaError(ValueError):
    """Raised when data violates the GNM on-disk contract."""


@dataclasses.dataclass(frozen=True)
class TrajectorySpec:
    """Sampling geometry that a trajectory must satisfy to yield training pairs.

    Mirrors the arithmetic in ``ViNT_Dataset._build_index``::

        begin_time = context_size * waypoint_spacing
        end_time   = traj_len - end_slack - len_traj_pred * waypoint_spacing
        samples    = max(0, end_time - begin_time)
    """

    context_size: int
    len_traj_pred: int
    waypoint_spacing: int = 1
    end_slack: int = 0

    def __post_init__(self) -> None:
        if self.context_size < 0:
            raise ValueError("context_size must be >= 0")
        if self.len_traj_pred < 1:
            raise ValueError("len_traj_pred must be >= 1")
        if self.waypoint_spacing < 1:
            raise ValueError("waypoint_spacing must be >= 1")
        if self.end_slack < 0:
            raise ValueError("end_slack must be >= 0")

    @property
    def min_length(self) -> int:
        """Smallest ``T`` that yields at least one training sample."""
        return (
            self.context_size * self.waypoint_spacing
            + self.len_traj_pred * self.waypoint_spacing
            + self.end_slack
            + 1
        )

    def num_samples(self, traj_len: int) -> int:
        begin = self.context_size * self.waypoint_spacing
        end = traj_len - self.end_slack - self.len_traj_pred * self.waypoint_spacing
        return max(0, end - begin)

    @classmethod
    def for_model(cls, model: str, **overrides: Any) -> TrajectorySpec:
        """Spec matching the released config for ``gnm``, ``vint`` or ``nomad``."""
        presets = {
            "gnm": dict(context_size=5, len_traj_pred=5),
            "vint": dict(context_size=5, len_traj_pred=5),
            "nomad": dict(context_size=3, len_traj_pred=8),
        }
        key = model.lower()
        if key not in presets:
            raise KeyError(f"unknown model {model!r}; expected one of {sorted(presets)}")
        params: dict[str, Any] = dict(presets[key])
        params.update(overrides)
        return cls(**params)


@dataclasses.dataclass(frozen=True)
class DatasetSpec:
    """Per-dataset constants that live in ``vint_train/data/data_config.yaml``.

    ``metric_waypoint_spacing`` is the mean Euclidean distance in metres between
    consecutive recorded frames. It is the *only* thing that makes the action
    labels commensurate across robots: ``_compute_actions`` divides local-frame
    waypoints by ``metric_waypoint_spacing * waypoint_spacing``, so a normalised
    displacement of 1.0 means "one nominal inter-frame step for this platform".

    Getting it wrong does not crash anything -- it silently rescales the action
    distribution and destroys transfer from the pretrained checkpoint.
    """

    name: str
    metric_waypoint_spacing: float
    camera_height: float | None = None
    camera_x_offset: float | None = None
    camera_matrix: Mapping[str, float] | None = None
    dist_coeffs: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if not self.name or not re.match(r"^[a-z0-9_]+$", self.name):
            raise ValueError(
                f"dataset name {self.name!r} must be lowercase alphanumeric/underscore "
                "(it becomes a YAML key and a directory name)"
            )
        if not math.isfinite(self.metric_waypoint_spacing) or self.metric_waypoint_spacing <= 0:
            raise ValueError("metric_waypoint_spacing must be a positive finite float")

    def to_data_config_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "metric_waypoint_spacing": float(self.metric_waypoint_spacing)
        }
        if self.camera_height is not None or self.camera_matrix is not None:
            metrics: dict[str, Any] = {}
            if self.camera_height is not None:
                metrics["camera_height"] = float(self.camera_height)
            if self.camera_x_offset is not None:
                metrics["camera_x_offset"] = float(self.camera_x_offset)
            if self.camera_matrix is not None:
                metrics["camera_matrix"] = {k: float(v) for k, v in self.camera_matrix.items()}
            if self.dist_coeffs is not None:
                metrics["dist_coeffs"] = {k: float(v) for k, v in self.dist_coeffs.items()}
            entry["camera_metrics"] = metrics
        return entry


def min_length_for(model: str, **overrides: Any) -> int:
    """Convenience: minimum usable trajectory length for a named model."""
    return TrajectorySpec.for_model(model, **overrides).min_length


def check_traj_data(
    traj_data: Mapping[str, Any],
    *,
    n_images: int | None = None,
    max_yaw_jump: float = math.pi,
    require_unwrapped: bool = True,
) -> list[str]:
    """Validate an in-memory ``traj_data`` mapping. Returns a list of problems.

    An empty list means the trajectory satisfies every constraint the reference
    loader relies on. This function never raises for data problems -- it reports
    them -- so callers can aggregate across a whole dataset.
    """
    problems: list[str] = []

    for key in REQUIRED_KEYS:
        if key not in traj_data:
            problems.append(f"missing required key {key!r}")
    if problems:
        return problems

    position = np.asarray(traj_data["position"])
    yaw = np.asarray(traj_data["yaw"])

    if position.ndim != 2 or position.shape[1] != 2:
        problems.append(f"position must have shape (T, 2), got {position.shape}")
    if not np.issubdtype(position.dtype, np.floating):
        problems.append(f"position dtype must be floating, got {position.dtype}")
    if position.size and not np.all(np.isfinite(position)):
        problems.append("position contains non-finite values")

    if yaw.ndim == 2 and yaw.shape[1] == 1:
        yaw = yaw[:, 0]  # tolerated: the loader squeezes this shape
    if yaw.ndim != 1:
        problems.append(f"yaw must have shape (T,) or (T, 1), got {np.asarray(traj_data['yaw']).shape}")
    if not np.issubdtype(yaw.dtype, np.floating):
        problems.append(f"yaw dtype must be floating, got {yaw.dtype}")
    if yaw.size and not np.all(np.isfinite(yaw)):
        problems.append("yaw contains non-finite values")

    if problems:
        return problems

    if position.shape[0] != yaw.shape[0]:
        problems.append(
            f"length mismatch: position has {position.shape[0]} rows, yaw has {yaw.shape[0]}"
        )
    if position.shape[0] == 0:
        problems.append("trajectory is empty")
        return problems

    if n_images is not None and n_images != position.shape[0]:
        problems.append(
            f"image count {n_images} != trajectory length {position.shape[0]}; "
            "the loader indexes images by timestep and will raise FileNotFoundError"
        )

    if require_unwrapped and yaw.shape[0] > 1:
        jumps = np.abs(np.diff(yaw))
        bad = np.flatnonzero(jumps > max_yaw_jump)
        if bad.size:
            problems.append(
                f"yaw is not unwrapped: {bad.size} step(s) exceed {max_yaw_jump:.3f} rad "
                f"(first at index {int(bad[0])}, magnitude {float(jumps[bad[0]]):.3f}). "
                "_compute_actions subtracts raw yaw values without wrapping, so this "
                "injects ~2*pi errors into the orientation labels"
            )

    return problems


def check_image_names(names: Sequence[str]) -> list[str]:
    """Validate a directory listing of image filenames against the loader's rules."""
    problems: list[str] = []
    indices: list[int] = []
    for name in names:
        if not IMAGE_NAME_RE.match(name):
            problems.append(
                f"invalid image filename {name!r}: expected unpadded '<t>.jpg' "
                "(the loader builds paths with f'{time}.jpg')"
            )
        else:
            indices.append(int(name[: -len(IMAGE_EXTENSION)]))
    if problems:
        return problems
    indices.sort()
    expected = list(range(len(indices)))
    if indices != expected:
        missing = sorted(set(expected) - set(indices))
        extra = sorted(set(indices) - set(expected))
        detail = []
        if missing:
            detail.append(f"missing timesteps {missing[:10]}{'...' if len(missing) > 10 else ''}")
        if extra:
            detail.append(f"unexpected timesteps {extra[:10]}{'...' if len(extra) > 10 else ''}")
        problems.append("image indices are not contiguous 0..T-1: " + "; ".join(detail))
    return problems
