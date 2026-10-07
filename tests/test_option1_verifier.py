import hashlib
import importlib.util
import json
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def verifier():
    spec = importlib.util.spec_from_file_location(
        "option1_verifier", ROOT / "scripts/verify_option1_dataset.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_count_summary_cannot_hide_missing_trajectories(tmp_path):
    (tmp_path / "admission.json").write_text(
        json.dumps({"status": "PASS", "admitted": 10, "trajectories": []})
    )
    with pytest.raises(ValueError, match="rows do not match"):
        verifier().verify(tmp_path)


def test_yaw_mapping_tamper_rejected_even_if_processed_hash_is_updated(tmp_path):
    module = verifier()
    raw = tmp_path / "raw"
    (raw / "trajectory").mkdir(parents=True)
    positions = np.column_stack([np.arange(4) * 0.02, np.zeros(4)])
    yaw = np.arange(4) * 0.03
    (raw / "trajectory/traj_data.pkl").write_bytes(
        pickle.dumps({"position": positions, "yaw": yaw})
    )
    source = raw / "runtime_manifest.json"
    source.write_text(json.dumps({"captures": [{"simulation_time": i / 12} for i in range(4)]}))
    for i in (0, 3):
        Image.new("RGB", (32, 24), (80, 90, 100)).save(raw / "trajectory" / f"{i}.jpg")
    report = {"status": "PASS", "admitted": 10, "trajectories": [], "dataset_file_sha256": {}}
    for i in range(10):
        name = f"trajectory{i}"
        target = tmp_path / "data/option1_m3pro" / name
        target.mkdir(parents=True)
        for new, old in enumerate([0, 3]):
            (target / f"{new}.jpg").write_bytes((raw / "trajectory" / f"{old}.jpg").read_bytes())
        (target / "traj_data.pkl").write_bytes(
            pickle.dumps({"position": positions[[0, 3]], "yaw": yaw[[0, 3]]})
        )
        (target / "processing.json").write_text(
            json.dumps(
                {
                    "source_manifest": str(source),
                    "source_manifest_sha256": module.sha(source),
                    "raw_indices": [0, 3],
                    "simulation_times": [0, 0.25],
                }
            )
        )
        report["trajectories"].append({"id": name, "admitted": True})
        for f in target.iterdir():
            report["dataset_file_sha256"][str(f.relative_to(tmp_path / "data/option1_m3pro"))] = (
                module.sha(f)
            )
    manifest = tmp_path / "admission.json"
    manifest.write_text(json.dumps(report))
    assert module.verify(tmp_path)["processed_frames"] == 20
    changed = tmp_path / "data/option1_m3pro/trajectory0/traj_data.pkl"
    changed.write_bytes(pickle.dumps({"position": positions[[0, 3]], "yaw": np.array([0.0, 0.7])}))
    report["dataset_file_sha256"][str(changed.relative_to(tmp_path / "data/option1_m3pro"))] = (
        hashlib.sha256(changed.read_bytes()).hexdigest()
    )
    manifest.write_text(json.dumps(report))
    with pytest.raises(AssertionError):
        module.verify(tmp_path)


def test_partial_dataset_cannot_start_training(tmp_path):
    (tmp_path / "admission.json").write_text(json.dumps({"admitted": 9}))
    output = tmp_path / "training"
    run = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/train_option1_smoke.py"),
            "--dataset",
            str(tmp_path),
            "--out",
            str(output),
        ],
        text=True,
        capture_output=True,
    )
    assert run.returncode == 2
    assert "ten admitted trajectories required" in run.stderr
    assert not output.exists()
