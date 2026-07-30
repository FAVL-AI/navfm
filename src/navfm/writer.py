"""Atomic writer for GNM-format trajectories.

Design constraints:

* **Crash-safe.** A trajectory is written into a ``.partial-`` staging
  directory and renamed into place only after ``traj_data.pkl`` is fsynced.
  A killed collector therefore never leaves a half-written trajectory that
  ``data_split.py`` would happily index (it selects directories merely by the
  presence of ``traj_data.pkl``).
* **Streaming.** Images are encoded and flushed as they arrive, so a 20-minute
  episode does not have to fit in RAM.
* **Format-exact.** JPEG, unpadded integer stems, 4:3 centre crop applied at
  write time so the trainer's crop is a no-op, yaw unwrapped on close.
"""

from __future__ import annotations

import os
import pickle
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .kinematics import mean_step_distance, unwrap_yaw
from .schema import (
    IMAGE_ASPECT_RATIO,
    IMAGE_EXTENSION,
    TRAJ_DATA_FILENAME,
    TrajectorySchemaError,
    check_traj_data,
)

__all__ = ["TrajectoryWriter", "center_crop_to_aspect"]


def center_crop_to_aspect(img: Image.Image, aspect: float = IMAGE_ASPECT_RATIO) -> Image.Image:
    """Centre-crop to ``aspect`` (width / height).

    Byte-for-byte equivalent to ``data_utils.resize_and_aspect_crop``'s crop
    step. Applying it at collection time means the trainer's crop is idempotent
    and the field of view we choose in simulation is the field of view the model
    actually sees -- otherwise a 16:9 capture silently loses ~25% of its width.
    """
    w, h = img.size
    if w > h * aspect:
        target_w = round(h * aspect)
        left = (w - target_w) // 2
        return img.crop((left, 0, left + target_w, h))
    if w < h * aspect:
        target_h = round(w / aspect)
        top = (h - target_h) // 2
        return img.crop((0, top, w, top + target_h))
    return img


class TrajectoryWriter:
    """Incrementally write one GNM-format trajectory.

    Usage::

        with TrajectoryWriter(root / "traj_0007") as w:
            for frame in episode:
                w.append(frame.rgb, frame.position_xy, frame.yaw)
        # directory now exists and is guaranteed complete

    ``append`` accepts either a ``PIL.Image`` or an ``H x W x 3`` uint8 array.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        jpeg_quality: int = 95,
        crop_to_aspect: bool = True,
        aspect: float = IMAGE_ASPECT_RATIO,
        resize_to: tuple[int, int] | None = None,
        metadata: dict[str, Any] | None = None,
        unwrap: bool = True,
    ) -> None:
        self.path = Path(path)
        self.jpeg_quality = int(jpeg_quality)
        self.crop_to_aspect = bool(crop_to_aspect)
        self.aspect = float(aspect)
        self.resize_to = resize_to
        self.metadata = dict(metadata or {})
        self.unwrap = bool(unwrap)

        self._positions: list[tuple[float, float]] = []
        self._yaws: list[float] = []
        self._extras: dict[str, list[Any]] = {}
        self._staging: Path | None = None
        self._closed = False
        self._aborted = False

    # -- context manager -------------------------------------------------

    def __enter__(self) -> TrajectoryWriter:
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.abort()
        elif not self._closed:
            self.close()

    # -- lifecycle -------------------------------------------------------

    def open(self) -> None:
        if self._staging is not None:
            raise RuntimeError("writer already opened")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._staging = Path(
            tempfile.mkdtemp(prefix=f".partial-{self.path.name}-", dir=self.path.parent)
        )

    @property
    def n_frames(self) -> int:
        return len(self._positions)

    def append(
        self,
        image: Any,
        position_xy: Any,
        yaw: float,
        **extras: Any,
    ) -> int:
        """Append one synchronised (image, pose) sample. Returns its timestep."""
        if self._staging is None:
            raise RuntimeError("writer not opened")
        if self._closed:
            raise RuntimeError("writer already closed")

        pos = np.asarray(position_xy, dtype=np.float64).reshape(-1)
        if pos.shape[0] == 3:
            pos = pos[:2]
        if pos.shape[0] != 2:
            raise TrajectorySchemaError(
                f"position must be 2-D (x, y) or 3-D (x, y, z), got shape {np.shape(position_xy)}"
            )
        if not np.all(np.isfinite(pos)):
            raise TrajectorySchemaError("non-finite position")
        yaw_f = float(yaw)
        if not np.isfinite(yaw_f):
            raise TrajectorySchemaError("non-finite yaw")

        t = len(self._positions)
        img = self._to_pil(image)
        if self.crop_to_aspect:
            img = center_crop_to_aspect(img, self.aspect)
        if self.resize_to is not None:
            img = img.resize(self.resize_to, Image.Resampling.LANCZOS)
        img.save(
            self._staging / f"{t}{IMAGE_EXTENSION}",
            format="JPEG",
            quality=self.jpeg_quality,
            subsampling=0,
            optimize=True,
        )

        self._positions.append((float(pos[0]), float(pos[1])))
        self._yaws.append(yaw_f)
        for key, value in extras.items():
            self._extras.setdefault(key, []).append(value)
        return t

    def abort(self) -> None:
        """Discard everything written so far. Idempotent."""
        self._aborted = True
        if self._staging is not None and self._staging.exists():
            shutil.rmtree(self._staging, ignore_errors=True)
        self._staging = None
        self._closed = True

    def close(self) -> Path:
        """Finalise: write ``traj_data.pkl``, fsync, atomically rename into place."""
        if self._closed:
            if self._aborted:
                raise RuntimeError("writer was aborted")
            return self.path
        if self._staging is None:
            raise RuntimeError("writer not opened")

        position = np.asarray(self._positions, dtype=np.float64).reshape(-1, 2)
        yaw = np.asarray(self._yaws, dtype=np.float64)
        if self.unwrap and yaw.size:
            yaw = unwrap_yaw(yaw)

        traj_data: dict[str, Any] = {"position": position, "yaw": yaw}
        for key, values in self._extras.items():
            if key in ("position", "yaw"):
                continue
            traj_data[key] = np.asarray(values)
        if self.metadata:
            meta = dict(self.metadata)
            meta.setdefault("n_frames", int(position.shape[0]))
            meta.setdefault("mean_step_distance_m", mean_step_distance(position))
            traj_data["metadata"] = meta

        problems = check_traj_data(traj_data, n_images=position.shape[0])
        if problems:
            self.abort()
            raise TrajectorySchemaError(
                "refusing to write invalid trajectory:\n  - " + "\n  - ".join(problems)
            )

        pkl_path = self._staging / TRAJ_DATA_FILENAME
        with open(pkl_path, "wb") as fh:
            pickle.dump(traj_data, fh, protocol=pickle.HIGHEST_PROTOCOL)
            fh.flush()
            os.fsync(fh.fileno())

        dir_fd = os.open(self._staging, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        if self.path.exists():
            shutil.rmtree(self.path)
        os.replace(self._staging, self.path)
        self._staging = None
        self._closed = True
        return self.path

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _to_pil(image: Any) -> Image.Image:
        if isinstance(image, Image.Image):
            return image.convert("RGB")
        arr = np.asarray(image)
        if arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[:, :, :3]
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise TrajectorySchemaError(
                f"expected an H x W x 3 (or x4) image array, got shape {arr.shape}"
            )
        if arr.dtype != np.uint8:
            if np.issubdtype(arr.dtype, np.floating):
                arr = np.clip(arr * 255.0 if arr.max() <= 1.0 else arr, 0, 255)
            arr = arr.astype(np.uint8)
        return Image.fromarray(arr, mode="RGB")
