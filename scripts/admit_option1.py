"""Admit strictly verified moving demonstrations and exercise official loaders."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pickle
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--collection", type=Path, action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--expected-trajectories", type=int, default=10)
    p.add_argument("--spacing", type=float, help="freeze previously registered TRAIN unit")
    args = p.parse_args()
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(REPO):
        p.error("output must be new and external")
    candidates = []
    for collection_root in args.collection:
        if (collection_root / "PROVENANCE_INVALID.json").exists():
            p.error("collection explicitly marked provenance-invalid")
        collection = json.loads((collection_root / "collection.json").read_text())
        if collection["status"] != "COMPLETED":
            p.error("every collection must finish before admission")
        candidates.extend((collection_root, item) for item in collection["episodes"])
    out.mkdir(parents=True)
    import numpy as np
    import torch
    import yaml
    from PIL import Image

    from navfm import upstream
    from navfm.collection.dataset_admission import image_quality, motion_quality, split_routes
    from navfm.evalpairs import build, save
    from navfm.schema import TrajectorySpec
    from navfm.validate import validate_trajectory

    name = "option1_m3pro"
    data = out / "data" / name
    data.mkdir(parents=True)
    report = {
        "scope": "DATASET_ENGINEERING_CHECK",
        "attempted": len(candidates),
        "collections": [str(p) for p in args.collection],
        "trajectories": [],
    }
    routes = []
    training_steps = []
    for collection_root, item in candidates:
        episode = collection_root / item["id"]
        manifest = json.loads((episode / "runtime_manifest.json").read_text())
        errors = []
        if manifest["status"] != "PASS":
            errors.append(manifest.get("error", "recording failed"))
        else:
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "scripts/verify_rgb_feasibility.py"),
                    "--manifest",
                    str(episode / "runtime_manifest.json"),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode:
                errors.append(result.stderr.strip().splitlines()[-1])
        row = {"id": item["id"], "collection": str(collection_root), "errors": errors}
        if not errors:
            route = manifest["route"]
            raw = episode / "trajectory"
            poses = pickle.loads((raw / "traj_data.pkl").read_bytes())
            quality = []
            for i in range(manifest["frames"]):
                with Image.open(raw / f"{i}.jpg") as image:
                    quality.append(image_quality(np.asarray(image.convert("RGB"))))
            motion = motion_quality(poses["position"], poses["yaw"])
            if not motion["usable"]:
                errors.append("insufficient motion or pose discontinuity")
            bad = sum(not q["usable"] for q in quality)
            if bad:
                errors.append(f"{bad} unusable images")
            if (
                manifest["termination"] != "teacher_goal"
                or manifest["captures"][-1]["distance_to_goal_m"] > 0.2
            ):
                errors.append("teacher did not finish route within0.2m")
            if manifest["contacts"]:
                errors.append("reported obstacle contact")
            if any(r["id"] == item["id"] for r in routes):
                errors.append("duplicate route already admitted; retain without replacement")
            row.update(
                scene=route["scene"],
                route_id=route["route_id"],
                split=route["split"],
                raw_frames=manifest["frames"],
                motion=motion,
                image_usability={
                    "frames": len(quality),
                    "bad_frames": bad,
                    "min_contrast": min(q["contrast_p95_p05"] for q in quality),
                    "min_gradient": min(q["gradient_mean"] for q in quality),
                    "max_extreme_fraction": max(q["extreme_fraction"] for q in quality),
                },
                final_goal_distance_m=manifest["captures"][-1]["distance_to_goal_m"],
                collector_loop_p95_ms=float(
                    np.percentile([c["wall_loop_ms"] for c in manifest["captures"]], 95)
                ),
            )
            if not errors:
                indices = np.arange(2, manifest["frames"], 3, dtype=int)
                target = data / item["id"]
                target.mkdir()
                for new, old in enumerate(indices):
                    shutil.copyfile(raw / f"{old}.jpg", target / f"{new}.jpg")
                processed = {
                    "position": np.asarray(poses["position"])[indices].astype(np.float64),
                    "yaw": np.unwrap(np.asarray(poses["yaw"], dtype=np.float64))[indices],
                }
                (target / "traj_data.pkl").write_bytes(pickle.dumps(processed))
                mapping = {
                    "source_manifest": str(episode / "runtime_manifest.json"),
                    "source_manifest_sha256": digest(episode / "runtime_manifest.json"),
                    "raw_indices": indices.tolist(),
                    "simulation_times": [
                        manifest["captures"][i]["simulation_time"] for i in indices
                    ],
                    "processing": "every third12HzRGB capture renamed; JPEG bytes unchanged; float64 position and unwrapped yaw",
                    "image_size": [320, 240],
                    "cadence_hz": 4,
                    "route": route,
                }
                (target / "processing.json").write_text(json.dumps(mapping, indent=2) + "\n")
                validation = validate_trajectory(
                    target, TrajectorySpec.for_model("vint"), check_images_decodable=True
                )
                if not validation.ok:
                    raise ValueError(validation.errors)
                # Verify every processed image and label maps exactly to the raw capture.
                for new, old in enumerate(indices):
                    assert digest(target / f"{new}.jpg") == digest(raw / f"{old}.jpg")
                    assert np.array_equal(processed["position"][new], poses["position"][old])
                row.update(
                    processed_frames=len(indices), candidate_observations=validation.n_samples
                )
                routes.append(route)
                if route["split"] == "train":
                    training_steps.extend(
                        np.linalg.norm(np.diff(processed["position"], axis=0), axis=1).tolist()
                    )
        row["admitted"] = not errors
        report["trajectories"].append(row)
    splits = split_routes(routes)
    for split, names in splits.items():
        directory = out / "splits" / name / split
        directory.mkdir(parents=True)
        (directory / "traj_names.txt").write_text("".join(n + "\n" for n in names))
    report.update(
        admitted=len(routes),
        rejected=report["attempted"] - len(routes),
        splits=splits,
        status="LOADER_PENDING",
    )
    (out / "admission.json").write_text(json.dumps(report, indent=2) + "\n")
    if not all(splits.values()) or not training_steps:
        raise ValueError(
            "insufficient admitted training/development/test coverage; see admission.json rejections"
        )
    # A private training-source snapshot avoids modifying the existing dirty upstream clone.
    source = upstream.upstream_root()
    snapshot = out / "upstream"
    snapshot.mkdir()
    files = subprocess.check_output(
        ["git", "-C", str(source), "ls-files", "train"], text=True
    ).splitlines()
    source_hashes = {}
    for relative in files:
        origin = source / relative
        if origin.is_file():
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, destination)
            source_hashes[relative] = digest(origin)
    base_commit = upstream.upstream_commit()
    (snapshot / "source_identity.json").write_text(
        json.dumps(
            {
                "base_commit": base_commit,
                "source_root": str(source),
                "copied_worktree_sha256": source_hashes,
                "registration_change": "data_config.yaml adds option1_m3pro only",
            },
            indent=2,
        )
        + "\n"
    )
    spacing = (
        args.spacing
        if args.spacing is not None
        else float(np.median([x for x in training_steps if x > 0.001]))
    )
    cfgfile = snapshot / "train/vint_train/data/data_config.yaml"
    cfg = yaml.safe_load(cfgfile.read_text())
    cfg[name] = {"metric_waypoint_spacing": spacing}
    cfgfile.write_text(yaml.safe_dump(cfg, sort_keys=False))
    # Point navfm to the isolated snapshot before importing the dataset class.
    import os

    os.environ["NAVFM_UPSTREAM"] = str(snapshot)
    upstream.upstream_root.cache_clear()
    upstream.data_config.cache_clear()
    upstream.ensure_upstream()
    modelcfg = upstream.model_config("vint")
    pristine = snapshot / "train/vint_train/data/pristine_loader.py"
    pristine.write_bytes(
        subprocess.check_output(
            [
                "git",
                "-C",
                str(source),
                "show",
                f"{base_commit}:train/vint_train/data/vint_dataset.py",
            ]
        )
    )
    spec = importlib.util.spec_from_file_location("pristine_official_loader", pristine)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_class = module.ViNT_Dataset
    from vint_train.data import vint_dataset

    loader_results = {}
    dataset_hashes = {
        str(f.relative_to(data)): digest(f) for f in sorted(data.rglob("*")) if f.is_file()
    }
    dataset_digest = hashlib.sha256(json.dumps(dataset_hashes, sort_keys=True).encode()).hexdigest()
    for split in splits:
        if not splits[split]:
            continue
        kwargs = dict(
            data_folder=data,
            split_folder=out / "splits" / name / split,
            cfg=modelcfg,
            dataset_name=name,
        )
        ds = upstream.build_dataset(**kwargs)
        vint_dataset.navfm_seed_sampling(711)
        pairs = []
        valid_action_pairs = 0
        sampled_goals = []
        original_sampler = ds._sample_goal

        def record_goal(*args, original_sampler=original_sampler, sampled_goals=sampled_goals):
            value = original_sampler(*args)
            sampled_goals.append([value[0], int(value[1]), bool(value[2])])
            return value

        ds._sample_goal = record_goal
        for i in range(len(ds)):
            sample = ds[i]
            if len(sample) != 7 or not all(torch.isfinite(t).all() for t in sample):
                raise ValueError("nonfinite official loader sample")
            pairs.append(vint_dataset._NAVFM_REALISED_PAIRS[-1])
            valid_action_pairs += int(float(sample[-1]) > 0)
        split_digest = digest(out / "splits" / name / split / "traj_names.txt")
        frozen = build(
            pairs,
            generation_command="scripts/admit_option1.py",
            population_seed=711,
            dataset_digest=dataset_digest,
            split_digest=split_digest,
            trajectory_count=len(splits[split]),
        )
        save(frozen, out / f"{split}_pairs_manifest.json")
        (out / f"{split}_sampled_goals.json").write_text(json.dumps(sampled_goals) + "\n")
        (out / f"{split}_pairs.json").write_text(json.dumps(pairs) + "\n")
        # Release LMDB handle before opening the same cache with pristine code.
        ds._image_cache.close()
        patched_class = vint_dataset.ViNT_Dataset
        vint_dataset.ViNT_Dataset = original_class
        try:
            np.random.seed(711)
            pure = upstream.build_dataset(**kwargs)
            for i in range(len(pure)):
                sample = pure[i]
                if len(sample) != 7 or not all(torch.isfinite(t).all() for t in sample):
                    raise ValueError("pristine official loader sample invalid")
            pure._image_cache.close()
        finally:
            vint_dataset.ViNT_Dataset = patched_class
        loader_results[split] = {
            "trajectories": len(splits[split]),
            "observation_goal_pairs": len(pairs),
            "valid_action_pairs": valid_action_pairs,
            "negative_goal_pairs": sum(bool(g[2]) for g in sampled_goals),
            "patched_official_samples_finite": True,
            "pristine_official_samples_finite": True,
            "pair_sha256": frozen.sha256,
        }
    report.update(
        status="PASS" if len(routes) == args.expected_trajectories else "PARTIAL",
        admitted=len(routes),
        rejected=report["attempted"] - len(routes),
        admission_rate=len(routes) / report["attempted"],
        splits=splits,
        loader=loader_results,
        metric_waypoint_spacing_m=spacing,
        spacing_definition="median nonstationary processed step distance in TRAIN ONLY;4Hz",
        dataset_digest=dataset_digest,
        dataset_file_sha256=dataset_hashes,
        upstream_base_commit=base_commit,
        pristine_loader_sha256=digest(pristine),
        upstream_snapshot=str(snapshot),
        effective_training_source_sha256={
            str(p.relative_to(snapshot)): digest(p)
            for p in sorted(snapshot.rglob("*"))
            if p.is_file() and p.suffix in {".py", ".yaml", ".yml", ".json"}
        },
        collision_positive_control_verified=False,
    )
    (out / "admission.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "attempted",
                    "admitted",
                    "rejected",
                    "loader",
                    "metric_waypoint_spacing_m",
                ]
            },
            indent=2,
        )
    )
    return 0 if len(routes) == args.expected_trajectories else 1


if __name__ == "__main__":
    raise SystemExit(main())
