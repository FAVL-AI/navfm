"""Read back frozen processed RGB, position/yaw and raw timestamp mappings."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root, expected_trajectories=10):
    report = json.loads((root / "admission.json").read_text())
    if report["status"] != "PASS" or report["admitted"] != expected_trajectories:
        raise ValueError("declared admitted trajectory count and admission PASS required")
    if sum(bool(row["admitted"]) for row in report["trajectories"]) != expected_trajectories:
        raise ValueError("admitted trajectory rows do not match declared summary")
    data = root / "data/option1_m3pro"
    for name, expected in report["dataset_file_sha256"].items():
        if sha(data / name) != expected:
            raise ValueError(f"admitted file changed: {name}")
    frames = 0
    for row in report["trajectories"]:
        if not row["admitted"]:
            continue
        path = data / row["id"]
        mapping = json.loads((path / "processing.json").read_text())
        source = Path(mapping["source_manifest"])
        if sha(source) != mapping["source_manifest_sha256"]:
            raise ValueError("raw manifest changed")
        original = pickle.loads((source.parent / "trajectory/traj_data.pkl").read_bytes())
        processed = pickle.loads((path / "traj_data.pkl").read_bytes())
        indices = mapping["raw_indices"]
        np.testing.assert_array_equal(processed["position"], original["position"][indices])
        np.testing.assert_array_equal(processed["yaw"], np.unwrap(original["yaw"])[indices])
        if not np.all(np.abs(np.diff(mapping["simulation_times"]) - 0.25) <= 1e-8):
            raise ValueError("processed4Hz timestamps do not match unchanged tolerance")
        manifest = json.loads(source.read_text())
        for i, raw_i in enumerate(indices):
            if sha(path / f"{i}.jpg") != sha(source.parent / "trajectory" / f"{raw_i}.jpg"):
                raise ValueError("processed image mapping changed")
            if mapping["simulation_times"][i] != manifest["captures"][raw_i]["simulation_time"]:
                raise ValueError("processed timestamp mapping changed")
        frames += len(indices)
    return {
        "status": "PASS",
        "trajectories": expected_trajectories,
        "processed_frames": frames,
        "position_yaw_images_timestamps_exactly_mapped": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--expected-trajectories", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(verify(args.dataset, args.expected_trajectories), indent=2))


if __name__ == "__main__":
    main()
