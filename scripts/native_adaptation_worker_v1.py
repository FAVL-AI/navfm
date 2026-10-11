"""Six native training-only updates, development fence, and strict saved-state reload."""

from __future__ import annotations

import argparse
import copy
import importlib
import importlib.metadata
import json
import pickle
import random
import sys
import time
from pathlib import Path

from development_qualification_contracts_v1 import sha
from native_adaptation_contracts_v1 import (
    capture_rng,
    evaluate_fenced,
    restore_training_state,
    shared_metric,
    state_digest,
    validate_pair,
    write,
)


def fixed_batch(cfg, model_cfg, partition, torch):
    from vint_train.data.data_utils import img_path_to_data
    from vint_train.data.vint_dataset import ViNT_Dataset, navfm_normalise_traj_data

    admission = json.loads(Path(cfg["admission"]).read_text())
    expected_partitions = {
        "train": admission["splits"]["train"],
        "development": admission["splits"]["dev"] + admission["splits"]["test"],
    }
    if cfg["partitions"] != expected_partitions or set(expected_partitions["train"]) & set(
        expected_partitions["development"]
    ):
        raise ValueError("partition specification drift/overlap")
    allowed = cfg["partitions"][partition]
    pairs = cfg["pairs"][partition]
    root = Path(cfg["dataset"])
    records = []

    class Fixed(ViNT_Dataset):
        def __init__(self):
            self.image_size = model_cfg["image_size"]
            self.context_size = model_cfg["context_size"]
            self.len_traj_pred = model_cfg["len_traj_pred"]
            self.learn_angle = model_cfg["learn_angle"]
            self.num_action_params = 3 if self.learn_angle else 2
            self.waypoint_spacing = 1
            self.context_type = "temporal"
            self.normalize = True
            self.max_dist_cat = 20
            self.min_action_distance = model_cfg["action"]["min_dist_cat"]
            self.max_action_distance = model_cfg["action"]["max_dist_cat"]
            self.dataset_index = 0
            self.data_config = {"metric_waypoint_spacing": cfg["metric_spacing_m"]}
            self.index_to_data = [(p["trajectory"], p["current"], 20) for p in pairs]
            self.trajectory_cache = {}

        def _get_trajectory(self, name):
            if name not in allowed:
                raise ValueError("label partition leakage")
            if name not in self.trajectory_cache:
                f = root / name / "traj_data.pkl"
                if sha(f) != admission["dataset_file_sha256"][f"{name}/traj_data.pkl"]:
                    raise ValueError("trajectory source drift")
                with f.open("rb") as stream:
                    self.trajectory_cache[name] = navfm_normalise_traj_data(
                        pickle.load(stream), name
                    )
            return self.trajectory_cache[name]

        def _load_image(self, name, tick):
            if name not in allowed:
                raise ValueError("image partition leakage")
            f = root / name / f"{tick}.jpg"
            if sha(f) != admission["dataset_file_sha256"][f"{name}/{tick}.jpg"]:
                raise ValueError("image source drift")
            return img_path_to_data(str(f), self.image_size)

        def _sample_goal(self, *args):
            p = pairs[self.active]
            return p["goal_trajectory"], p["goal_time"], p["negative"]

        def __getitem__(self, index):
            self.active = index
            p = pairs[index]
            endpoints = validate_pair(
                p, allowed, admission["dataset_file_sha256"], self.context_size, self.len_traj_pred
            )
            N = len(self._get_trajectory(p["trajectory"])["position"])
            M = len(self._get_trajectory(p["goal_trajectory"])["position"])
            if p["current"] + self.len_traj_pred >= N or p["goal_time"] >= M:
                raise ValueError("native endpoint padding prohibited in fixed smoke")
            records.append({"pair": p, "endpoints": endpoints})
            return super().__getitem__(index)

    data = Fixed()
    samples = [data[i] for i in range(len(pairs))]
    obs, goal, actions, distance, _, _, mask = [
        torch.stack([s[i] for s in samples]) for i in range(7)
    ]
    mean = obs.new_tensor([0.485, 0.456, 0.406])[:, None, None]
    std = obs.new_tensor([0.229, 0.224, 0.225])[:, None, None]
    obs = torch.cat([(x - mean) / std for x in torch.split(obs, 3, dim=1)], dim=1)
    goal = (goal - mean) / std
    batch = (obs, goal, actions, distance, mask)
    if any(not torch.isfinite(x).all() for x in batch):
        raise ValueError("nonfinite native batch")
    return tuple(x.cuda() for x in batch), {
        "pairs": records,
        "tensor_sha256": [state_digest(x) for x in batch],
        "shapes": [list(x.shape) for x in batch],
    }


def verify_upstream(cfg):
    expected = {
        str((Path(cfg["upstream"]) / x["path"]).resolve()): x["sha256"]
        for x in cfg["upstream_files"]
    }
    records = []
    for name, module in sorted(list(sys.modules.items())):
        if not name.startswith("vint_train") or module is None:
            continue
        source = vars(module).get("__file__")
        if source is None:
            raise ImportError("unbound upstream module " + name)
        path = str(Path(source).resolve())
        digest = sha(Path(path))
        if expected.get(path) != digest:
            raise ImportError("upstream source origin/hash drift " + name)
        records.append({"module": name, "source": path, "sha256": digest})
    return records


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--model", choices=["gnm", "nomad"], required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    cfg = json.loads(a.config.read_text())
    out = a.out
    report = {"status": "STARTED", "model": a.model, "updates": []}
    provenance = {"status": "STARTED"}
    started = time.monotonic()
    manifest = None
    model = optimizer = scheduler = ema = None
    write(out / "report.json", report)
    try:
        from nomad_dependency_boundary_v6 import install_boundary, verify_loaded_dependencies

        install_boundary(cfg["diffusion_root"], cfg["diffusion_files"])
        import numpy as np
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA required before model construction")
        torch.manual_seed(0)
        torch.cuda.manual_seed_all(0)
        np.random.seed(0)
        random.seed(0)
        manifest = json.loads(Path(cfg["installed_dependency_manifest"]).read_text())
        for package in manifest["packages"]:
            if importlib.metadata.version(package["name"]) != package["version"]:
                raise ValueError("installed dependency version drift")
        from navfm import upstream
        from navfm.models.loader import extract_state_dict, load_checkpoint

        upstream.ensure_upstream()
        mc = upstream.model_config(a.model)
        wrapper = importlib.import_module(f"adapt_{a.model}_native_v1")
        train, train_record = fixed_batch(cfg, mc, "train", torch)
        dev, dev_record = fixed_batch(cfg, mc, "development", torch)
        write(out / "batches.json", {"train": train_record, "development": dev_record})
        provenance["before_training"] = verify_loaded_dependencies(manifest)
        provenance["upstream_before_training"] = verify_upstream(cfg)
        model = wrapper.build(mc)
        role = cfg["models"][a.model]
        state = extract_state_dict(
            load_checkpoint(
                role["checkpoint"],
                trust_checkpoint=a.model == "gnm",
                expected_sha256=role["sha256"],
            )
        )
        model.load_state_dict(state, strict=True)
        if any(not torch.isfinite(t).all() for t in model.state_dict().values()):
            raise ValueError("nonfinite released checkpoint")
        model.cuda()
        del state
        initial_parameters = {n: p.detach().cpu().clone() for n, p in model.named_parameters()}
        initial = state_digest(initial_parameters)
        optimizer = (
            torch.optim.Adam(model.parameters(), lr=7e-4, betas=(0.9, 0.98))
            if a.model == "gnm"
            else torch.optim.AdamW(model.parameters(), lr=1e-4)
        )
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lambda _: 1.0)
        ema = wrapper.make_ema(model) if a.model == "nomad" else None
        # Raw model and initial EMA are initialized from the same released EMA weights for NoMaD.
        report.update(
            strict_release_load=True,
            checkpoint_sha256=role["sha256"],
            checkpoint_path=role["checkpoint"],
            initial_parameter_digest=initial,
            raw_init="released checkpoint",
            ema_init="copy of released EMA into raw model and EMA shadow" if ema else None,
            model_config=mc,
            development_rng_seed=909,
            metric_spacing_m=cfg["metric_spacing_m"],
            device_type="cuda",
            device=torch.cuda.get_device_name(0),
            torch=torch.__version__,
            cuda=torch.version.cuda,
            scheduler="constant LR six-update smoke only",
            seed=0,
            deterministic_algorithms=torch.are_deterministic_algorithms_enabled(),
            cudnn_benchmark=torch.backends.cudnn.benchmark,
            cudnn_deterministic=torch.backends.cudnn.deterministic,
        )

        def evaluation(target):
            torch.manual_seed(909)
            torch.cuda.manual_seed_all(909)
            loss, dp, ap, details = wrapper.loss(target, dev, mc, training=False)
            if a.model == "nomad":
                dp, ap = wrapper.predict(target, dev)
            if (
                not torch.isfinite(loss)
                or not torch.isfinite(dp).all()
                or not torch.isfinite(ap).all()
            ):
                raise ValueError("nonfinite development output")
            return {
                "loss": float(loss),
                "distance_MAE_steps": float((dp.squeeze(-1) - dev[3]).abs().mean()),
                "common": shared_metric(ap, dev[2], dev[4], cfg["metric_spacing_m"]),
                "native": details,
                "native_horizon": mc["len_traj_pred"],
            }

        report["before_development"] = evaluate_fenced(
            model, optimizer, ema, lambda: evaluation(model)
        )
        for step in range(6):
            model.train()
            optimizer.zero_grad(set_to_none=True)
            loss, _, _, details = wrapper.loss(model, train, mc, training=True)
            if not torch.isfinite(loss):
                raise ValueError("nonfinite training loss")
            loss.backward()
            if any(
                p.grad is not None and not torch.isfinite(p.grad).all() for p in model.parameters()
            ):
                raise ValueError("nonfinite gradient")
            optimizer.step()
            scheduler.step()
            if ema:
                ema.step(model.parameters())
            if any(not torch.isfinite(t).all() for t in model.state_dict().values()):
                raise ValueError("nonfinite updated state")
            actual_steps = sorted({int(s["step"]) for s in optimizer.state.values() if "step" in s})
            if actual_steps != [step + 1]:
                raise ValueError("optimizer step readback differs")
            report["updates"].append(
                {
                    "step": step + 1,
                    "optimizer_step_readback": actual_steps,
                    "finite_gradients": True,
                    "loss": float(loss.detach()),
                    "native": details,
                }
            )
            write(out / "report.json", report)
        changed_count = sum(
            not torch.equal(initial_parameters[n], p.detach().cpu())
            for n, p in model.named_parameters()
        )
        changed = changed_count > 0
        if not changed:
            raise ValueError("optimizer did not change model parameters")
        evaluation_model = copy.deepcopy(model) if ema else model
        if ema:
            ema.copy_to(evaluation_model.parameters())
        report["after_development"] = evaluate_fenced(
            model,
            optimizer,
            ema,
            lambda: evaluate_fenced(
                evaluation_model, optimizer, ema, lambda: evaluation(evaluation_model)
            ),
        )
        resume = {
            "raw_model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "ema": ema.state_dict() if ema else None,
            **capture_rng(),
            "updates": 6,
        }
        torch.save(resume, out / "resume.pth")
        torch.save(evaluation_model.state_dict(), out / "deployment_weights.pth")
        reloaded = torch.load(out / "resume.pth", map_location="cuda", weights_only=True)
        restore_training_state(model, optimizer, scheduler, ema, reloaded)
        if state_digest(resume) != state_digest(reloaded):
            raise ValueError("resume state reload changed content")
        deployment = torch.load(
            out / "deployment_weights.pth", map_location="cuda", weights_only=True
        )
        evaluation_model.load_state_dict(deployment, strict=True)
        if state_digest(deployment) != state_digest(evaluation_model.state_dict()):
            raise ValueError("deployment strict reload changed content")
        report.update(
            status="PASS",
            parameters_changed=changed,
            changed_parameter_tensors=changed_count,
            strict_resume_reload=True,
            strict_deployment_reload=True,
            deployment_role="EMA" if ema else "raw",
            optimizer_updates=6,
            train_sample_draws=24,
            unique_training_anchors=2,
            unique_training_pairs=4,
            development_optimizer_updates=0,
        )
        provenance["status"] = "PASS"
    except BaseException as exc:
        report.update(status="FAIL", error_type=type(exc).__name__, error=str(exc))
        provenance.update(status="FAIL", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        try:
            if manifest is not None:
                from nomad_dependency_boundary_v6 import verify_loaded_dependencies

                provenance["after_training"] = verify_loaded_dependencies(manifest)
                provenance["upstream_after_training"] = verify_upstream(cfg)
        except BaseException as exc:
            report.update(
                status="FAIL", provenance_error_type=type(exc).__name__, provenance_error=str(exc)
            )
            provenance.update(status="FAIL", error_type=type(exc).__name__, error=str(exc))
        if model is not None and not (out / "resume.pth").exists():
            try:
                import torch

                torch.save(
                    {
                        "raw_model": model.state_dict(),
                        "optimizer": optimizer.state_dict() if optimizer else None,
                        "ema": ema.state_dict() if ema else None,
                        "completed_updates": len(report["updates"]),
                    },
                    out / "partial_state.pth",
                )
            except BaseException as exc:
                report["partial_state_error_type"] = type(exc).__name__
        provenance["shared_integrity"] = (
            "PASS"
            if all(
                k in provenance
                for k in [
                    "before_training",
                    "after_training",
                    "upstream_before_training",
                    "upstream_after_training",
                ]
            )
            and "provenance_error" not in report
            else "FAIL"
        )
        report["wall_s"] = time.monotonic() - started
        write(out / "provenance.json", provenance)
        write(out / "report.json", report)


if __name__ == "__main__":
    main()
