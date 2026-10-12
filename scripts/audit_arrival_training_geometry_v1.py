"""Audit geometry coverage in the admitted training split without opening RGB."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import pickle
import re
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

SOURCE_COMMIT = "da14a76ac0e33b7f364dcf7c18e818f7b14f73ee"
PAIR_COLUMNS = (
    "trajectory_id",
    "route_id",
    "scene_id",
    "query_frame_index",
    "goal_frame_index",
    "query_x_m",
    "query_y_m",
    "goal_x_m",
    "goal_y_m",
    "distance_m",
    "query_minus_goal_heading_rad",
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class NumpyOnlyUnpickler(pickle.Unpickler):
    """Load NumPy trajectory arrays while refusing arbitrary pickle globals."""

    _NUMPY_GLOBALS: ClassVar[frozenset[tuple[str, str]]] = frozenset(
        {
            ("numpy", "ndarray"),
            ("numpy", "dtype"),
            ("numpy.core.multiarray", "_reconstruct"),
            ("numpy.core.multiarray", "scalar"),
            ("numpy._core.multiarray", "_reconstruct"),
            ("numpy._core.multiarray", "scalar"),
        }
    )

    def find_class(self, module: str, name: str) -> Any:
        if (module, name) not in self._NUMPY_GLOBALS:
            raise pickle.UnpicklingError(f"unapproved pickle global: {module}.{name}")
        if module in {"numpy.core.multiarray", "numpy._core.multiarray"}:
            multiarray = np.core.multiarray
            return getattr(multiarray, name)
        return getattr(np, name)


def wrapped_heading_difference(query_heading: float, goal_heading: float) -> float:
    """Return signed query-minus-goal angle in [-pi, pi], rejecting bad inputs."""
    values = np.asarray([query_heading, goal_heading], dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("heading inputs must be finite")
    delta = float(values[0] - values[1])
    return math.atan2(math.sin(delta), math.cos(delta))


def ordered_distinct_frame_pairs(
    trajectory_id: str,
    route_id: str,
    scene_id: str,
    position: np.ndarray,
    yaw: np.ndarray,
) -> list[dict[str, Any]]:
    """Build all ordered distinct frame pairs within one trajectory only."""
    xy = np.asarray(position, dtype=np.float64)
    heading = np.asarray(yaw, dtype=np.float64).reshape(-1)
    if xy.ndim != 2 or xy.shape[1] != 2 or len(xy) != len(heading):
        raise ValueError("position/yaw must have shapes (T,2)/(T,) with equal T")
    if len(xy) < 2:
        raise ValueError("at least two frames are required")
    if not np.isfinite(xy).all() or not np.isfinite(heading).all():
        raise ValueError("position and yaw must be finite")

    rows: list[dict[str, Any]] = []
    for query_index in range(len(xy)):
        for goal_index in range(len(xy)):
            if query_index == goal_index:
                continue
            delta = xy[query_index] - xy[goal_index]
            rows.append(
                {
                    "trajectory_id": trajectory_id,
                    "route_id": route_id,
                    "scene_id": scene_id,
                    "query_frame_index": query_index,
                    "goal_frame_index": goal_index,
                    "query_x_m": float(xy[query_index, 0]),
                    "query_y_m": float(xy[query_index, 1]),
                    "goal_x_m": float(xy[goal_index, 0]),
                    "goal_y_m": float(xy[goal_index, 1]),
                    "distance_m": float(np.hypot(delta[0], delta[1])),
                    "query_minus_goal_heading_rad": wrapped_heading_difference(
                        float(heading[query_index]), float(heading[goal_index])
                    ),
                }
            )
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_training_record(path: Path) -> dict[str, np.ndarray]:
    with path.open("rb") as stream:
        record = NumpyOnlyUnpickler(stream).load()
    if not isinstance(record, dict) or set(record) != {"position", "yaw"}:
        raise ValueError(f"{path.name}: expected exactly position and yaw fields")
    position = np.asarray(record["position"], dtype=np.float64)
    yaw = np.asarray(record["yaw"], dtype=np.float64).reshape(-1)
    if position.ndim != 2 or position.shape[1] != 2 or len(position) != len(yaw):
        raise ValueError(f"{path.name}: invalid position/yaw shapes")
    if len(position) < 2 or not np.isfinite(position).all() or not np.isfinite(yaw).all():
        raise ValueError(f"{path.name}: empty, short, or nonfinite pose record")
    return {"position": position, "yaw": yaw}


def _quantiles(values: list[float]) -> dict[str, float]:
    return {
        name: float(np.quantile(np.asarray(values, dtype=np.float64), q))
        for name, q in (
            ("min", 0.0),
            ("p10", 0.10),
            ("p25", 0.25),
            ("median", 0.50),
            ("p75", 0.75),
            ("p90", 0.90),
            ("max", 1.0),
        )
    }


def audit_training_geometry(admission_path: Path, dataset_root: Path) -> tuple[list[dict], dict]:
    admission_bytes = admission_path.read_bytes()
    admission = json.loads(admission_bytes)
    train_ids = admission.get("splits", {}).get("train")
    if not isinstance(train_ids, list) or len(train_ids) != 31 or len(set(train_ids)) != 31:
        raise ValueError("expected the frozen 31-record training split")
    trajectory_meta = {
        row["id"]: row for row in admission.get("trajectories", []) if row.get("split") == "train"
    }
    if set(trajectory_meta) != set(train_ids):
        raise ValueError("training identities disagree between manifest fields")
    file_hashes = admission.get("dataset_file_sha256", {})

    all_rows: list[dict] = []
    trajectory_report: dict[str, dict] = {}
    for trajectory_id in sorted(train_ids):
        if not isinstance(trajectory_id, str) or not _SAFE_ID.fullmatch(trajectory_id):
            raise ValueError("unsafe trajectory identity in training manifest")
        metadata = trajectory_meta[trajectory_id]
        route_id, scene_id = metadata.get("route_id"), metadata.get("scene")
        if not all(isinstance(v, str) and v for v in (route_id, scene_id)):
            raise ValueError(f"missing route/scene identity for {trajectory_id}")
        record_rel = f"{trajectory_id}/traj_data.pkl"
        expected_hash = file_hashes.get(record_rel)
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise ValueError(f"no admitted hash for {record_rel}")
        record_path = dataset_root / trajectory_id / "traj_data.pkl"
        actual_hash = _sha256(record_path)
        if actual_hash != expected_hash:
            raise ValueError(f"admission hash mismatch for {record_rel}")

        record = _load_training_record(record_path)
        frame_count = len(record["position"])
        # Inspect names only; never open/read image file contents.
        expected_names = {f"{i}.jpg" for i in range(frame_count)}
        found_names = {p.name for p in (dataset_root / trajectory_id).glob("*.jpg")}
        if found_names != expected_names:
            raise ValueError(f"image-index names do not match pose indices for {trajectory_id}")

        rows = ordered_distinct_frame_pairs(
            trajectory_id, route_id, scene_id, record["position"], record["yaw"]
        )
        all_rows.extend(rows)
        distances = [row["distance_m"] for row in rows]
        heading_differences = [row["query_minus_goal_heading_rad"] for row in rows]
        trajectory_report[trajectory_id] = {
            "route_id": route_id,
            "scene_id": scene_id,
            "frame_count": frame_count,
            "ordered_distinct_pair_count": len(rows),
            "position_dtype": str(record["position"].dtype),
            "yaw_dtype": str(record["yaw"].dtype),
            "record_sha256": actual_hash,
            "distance_quantiles_m": _quantiles(distances),
            "heading_difference_quantiles_rad": _quantiles(heading_differences),
        }

    scene_ids = sorted({v["scene_id"] for v in trajectory_report.values()})
    scene_report = {}
    for scene_id in scene_ids:
        scene_rows = [r for r in all_rows if r["scene_id"] == scene_id]
        scene_report[scene_id] = {
            "trajectory_count": sum(v["scene_id"] == scene_id for v in trajectory_report.values()),
            "trajectory_ids": sorted(
                k for k, v in trajectory_report.items() if v["scene_id"] == scene_id
            ),
            "ordered_distinct_pair_count": len(scene_rows),
            "distance_quantiles_m": _quantiles([r["distance_m"] for r in scene_rows]),
            "heading_difference_quantiles_rad": _quantiles(
                [r["query_minus_goal_heading_rad"] for r in scene_rows]
            ),
        }

    report = {
        "status": "PASS_GEOMETRY_AUDIT",
        "input_contract_commit": SOURCE_COMMIT,
        "admission_sha256": hashlib.sha256(admission_bytes).hexdigest(),
        "admission_path": str(admission_path.resolve()),
        "dataset_root": str(dataset_root.resolve()),
        "dataset_digest": admission.get("dataset_digest"),
        "pair_population": "all ordered pairs of distinct frame indices within each admitted training trajectory; no cross-trajectory pairs",
        "coordinate_units": {"position": "metres", "yaw": "radians"},
        "heading_difference": "wrapped signed query-minus-goal angle in [-pi, pi]",
        "trajectory_count": len(trajectory_report),
        "scene_count": len(scene_report),
        "frame_count": sum(v["frame_count"] for v in trajectory_report.values()),
        "pair_count": len(all_rows),
        "all_pair_distances_m": _quantiles([r["distance_m"] for r in all_rows]),
        "all_heading_differences_rad": _quantiles(
            [r["query_minus_goal_heading_rad"] for r in all_rows]
        ),
        "by_scene": scene_report,
        "by_trajectory": trajectory_report,
        "limitations": [
            "No timestamps or elapsed-time labels are inferred.",
            "Distances are within-trajectory geometry only; no cross-trajectory coordinate alignment is assumed.",
            "Continuous proximity does not label settled, collision-free successful arrival or physical STOP.",
            "No RGB was read and no visual aliasing or hard-negative coverage is assessed.",
            "Correlated ordered pairs are not independent samples; no arrival radius or sufficiency threshold is selected.",
        ],
    }
    return all_rows, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new external output directory")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error("output must be a new directory; preserving existing evidence")
    rows, report = audit_training_geometry(args.admission, args.dataset_root)
    args.out.mkdir(parents=True)
    with (args.out / "training_geometry_pairs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=PAIR_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    report["pair_table_sha256"] = _sha256(args.out / "training_geometry_pairs.csv")
    report["audit_tool_sha256"] = _sha256(Path(__file__).resolve())
    report_path = args.out / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    report["report_sha256"] = _sha256(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
