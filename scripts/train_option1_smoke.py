"""Bounded ViNT fine-tuning engineering check, fixed-pair evaluation and reload."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
EXPECTED_CHECKPOINT = "155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=REPO / "configs/train/option1_vint_smoke.yaml"
    )
    parser.add_argument("--steps", type=int, default=6)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--train-names", type=Path, help="fixed nested training subset; dev/test unchanged"
    )
    parser.add_argument("--development-only", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(REPO) or args.steps < 1:
        parser.error("new external output and positive step count required")
    admission = json.loads((args.dataset / "admission.json").read_text())
    if admission["admitted"] < 10:
        parser.error("ten admitted trajectories required")
    os.environ["NAVFM_UPSTREAM"] = admission["upstream_snapshot"]
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import numpy as np
    import torch

    from navfm import upstream

    upstream.ensure_upstream()
    import vint_train

    if not Path(vint_train.__file__).resolve().is_relative_to(Path(admission["upstream_snapshot"])):
        raise RuntimeError("ViNT import is outside the admitted training source snapshot")
    from navfm.evalpairs import load, verify
    from navfm.models.loader import extract_state_dict, load_checkpoint, sha256
    from navfm.provenance import environment_identity
    from navfm.train.finetune import (
        FinetuneConfig,
        apply_freeze,
        build_optimizer,
        freeze_batchnorm,
        set_seed,
    )
    from navfm.train.run import save_weights, train_one_epoch

    cfg = FinetuneConfig.from_yaml(args.config)
    if args.seed is not None:
        cfg = dataclasses.replace(cfg, seed=args.seed)
    set_seed(cfg.seed, deterministic=cfg.deterministic)
    if sha256(cfg.checkpoint) != EXPECTED_CHECKPOINT:
        raise ValueError("intended pretrained checkpoint digest mismatch")
    # Check the processed corpus has not changed since admission.
    data = args.dataset / "data/option1_m3pro"
    for name, expected in admission["dataset_file_sha256"].items():
        if sha256(data / name) != expected:
            raise ValueError(f"admitted dataset changed: {name}")
    for name, expected in admission["effective_training_source_sha256"].items():
        if sha256(Path(admission["upstream_snapshot"]) / name) != expected:
            raise ValueError(f"admitted training source changed: {name}")
    out.mkdir(parents=True)
    result = {
        "status": "RUNNING",
        "scope": "TRAINING_ENGINEERING_CURVE"
        if args.train_names
        else "TRAINING_ENGINEERING_SMOKE_ONLY",
        "steps_requested": args.steps,
        "admission_digest": sha256(args.dataset / "admission.json"),
        "baseline_sha256": EXPECTED_CHECKPOINT,
        "finetune_config": cfg.to_dict(),
        "upstream_base_commit": admission["upstream_base_commit"],
        "upstream_source_identity": json.loads(
            (Path(admission["upstream_snapshot"]) / "source_identity.json").read_text()
        ),
    }

    def save():
        (out / "training_report.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n"
        )

    save()
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        result["environment"] = dataclasses.asdict(environment_identity(REPO))
        result["interpreter"] = sys.executable
        modelcfg = upstream.model_config("vint")
        model = upstream.build_model("vint", modelcfg)
        state = extract_state_dict(
            load_checkpoint(
                cfg.checkpoint, trust_checkpoint=True, expected_sha256=EXPECTED_CHECKPOINT
            )
        )
        model.load_state_dict(state, strict=True)
        del state
        model.to(device)

        def dataset(split):
            split_folder = args.dataset / "splits/option1_m3pro" / split
            if split == "train" and args.train_names:
                names = args.train_names.read_text().splitlines()
                available = (split_folder / "traj_names.txt").read_text().splitlines()
                if len(names) != len(set(names)) or not set(names) <= set(available):
                    raise ValueError("invalid training subset")
                split_folder = out / "training_subset"
                split_folder.mkdir()
                (split_folder / "traj_names.txt").write_text("\n".join(names) + "\n")
                result["training_trajectory_count"] = len(names)
                result["training_subset_sha256"] = sha256(args.train_names)
            return upstream.build_dataset(
                dataset_name="option1_m3pro",
                data_folder=data,
                split_folder=split_folder,
                cfg=modelcfg,
            )

        from vint_train.data import vint_dataset

        train = dataset("train")
        dev = dataset("dev")
        test = dataset("test")
        transform = upstream.reference_transform()
        spacing = admission["metric_waypoint_spacing_m"]

        def evaluate_fixed(model, split, ds):
            pairs = json.loads((args.dataset / f"{split}_pairs.json").read_text())
            goals = json.loads((args.dataset / f"{split}_sampled_goals.json").read_text())
            manifest = load(args.dataset / f"{split}_pairs_manifest.json")
            error = []
            final_error = []
            latency = []
            realised = []
            model.eval()
            for i, pair in enumerate(pairs):
                frozen_goal = goals[i]

                def goal_sampler(obs_traj, obs_time, max_dist, pair=pair, frozen_goal=frozen_goal):
                    if [obs_traj, int(obs_time)] != pair[:2]:
                        raise ValueError("fixed pair observation mismatch")
                    return frozen_goal[0], frozen_goal[1], frozen_goal[2]

                ds._sample_goal = goal_sampler
                if device == "cuda":
                    torch.cuda.synchronize()
                start = time.perf_counter()
                sample = ds[i]
                realised.append(vint_dataset._NAVFM_REALISED_PAIRS[-1])
                obs, goal, label, _, _, _, mask = sample
                obs, goal = upstream.apply_reference_transform(
                    obs.unsqueeze(0), goal.unsqueeze(0), transform, device
                )
                with torch.inference_mode():
                    distance, actions = model(obs, goal)
                if not torch.isfinite(actions).all() or not torch.isfinite(distance).all():
                    raise ValueError("nonfinite evaluation predictions")
                if float(mask) > 0:
                    errors = (
                        torch.linalg.vector_norm(actions[0, :, :2].cpu() - label[:, :2], dim=-1)
                        * spacing
                    )
                    error.append(float(errors.mean()))
                    final_error.append(float(errors[-1]))
                if device == "cuda":
                    torch.cuda.synchronize()
                latency.append((time.perf_counter() - start) * 1000)
            verify(manifest, realised)
            return {
                "pairs": len(pairs),
                "action_valid_pairs": len(error),
                "waypoint_ade_m": float(np.mean(error)) if error else None,
                "waypoint_fde_m": float(np.mean(final_error)) if error else None,
                "offline_full_loop_p95_ms": float(np.percentile(latency, 95)),
                "pair_sha256": manifest.sha256,
                "sampled_goal_flags_sha256": sha256(args.dataset / f"{split}_sampled_goals.json"),
            }

        result.update(
            device=device,
            model_config=modelcfg,
            pretrained_dev=evaluate_fixed(model, "dev", dev),
            pretrained_test=None if args.development_only else evaluate_fixed(model, "test", test),
        )
        save()
        result["freeze"] = apply_freeze(model, cfg.freeze)
        result["frozen_bn"] = freeze_batchnorm(model) if cfg.freeze_bn else 0
        optimizer = build_optimizer(model, cfg)
        # Retain the original loss and gradients; guard every scalar against NaN/Inf.
        upstream.ensure_upstream()
        from vint_train.training import train_utils

        original_loss = train_utils._compute_losses

        def finite_loss(*a, **kw):
            values = original_loss(*a, **kw)
            if not all(torch.isfinite(value).all() for value in values.values()):
                raise ValueError("nonfinite upstream loss")
            return values

        train_utils._compute_losses = finite_loss
        original_step = optimizer.step

        def finite_step(*a, **kw):
            for parameter in model.parameters():
                if parameter.grad is not None and not torch.isfinite(parameter.grad).all():
                    raise ValueError("nonfinite gradient")
            return original_step(*a, **kw)

        optimizer.step = finite_step
        loader = torch.utils.data.DataLoader(
            train,
            batch_size=cfg.micro_batch_size,
            shuffle=True,
            num_workers=0,
            drop_last=True,
            generator=torch.Generator().manual_seed(cfg.seed),
        )

        vint_dataset.navfm_seed_sampling(cfg.seed)
        before = {
            name: p.detach().cpu().clone()
            for name, p in model.named_parameters()
            if p.requires_grad
        }
        start = time.perf_counter()
        metrics = train_one_epoch(
            model,
            optimizer,
            loader,
            cfg=cfg,
            device=device,
            alpha=float(modelcfg["alpha"]),
            learn_angle=bool(modelcfg["learn_angle"]),
            grad_clip=cfg.grad_clip,
            progress=False,
            max_steps=args.steps,
        )
        train_utils._compute_losses = original_loss
        if (
            not metrics
            or not all(np.isfinite(v) for v in metrics.values())
            or metrics["optimizer_steps"] < 1
        ):
            raise ValueError("no finite optimization steps")
        changed = sum(
            not torch.equal(before[name], p.detach().cpu())
            for name, p in model.named_parameters()
            if name in before
        )
        if not changed:
            raise ValueError("optimization changed no weights")
        del before
        result["optimization_wall_s"] = time.perf_counter() - start
        result.update(
            training_metrics=metrics,
            changed_parameter_tensors=changed,
            stage="TRAINED_AWAITING_CHECKPOINT_RELOAD",
        )
        save()
        checkpoint = out / "smoke_weights.pth"
        save_weights(checkpoint, model)
        reloaded = upstream.build_model("vint", modelcfg)
        reloaded.load_state_dict(
            torch.load(checkpoint, map_location="cpu", weights_only=True), strict=True
        )
        reloaded.to(device).eval()
        model.eval()
        for key, value in model.state_dict().items():
            if not torch.equal(value.cpu(), reloaded.state_dict()[key].cpu()):
                raise ValueError("checkpoint reload weight mismatch")
        first_goal = json.loads((args.dataset / "dev_sampled_goals.json").read_text())[0]
        dev._sample_goal = lambda *args: (first_goal[0], first_goal[1], first_goal[2])
        sample = dev[0]
        obs, goal = upstream.apply_reference_transform(
            sample[0].unsqueeze(0), sample[1].unsqueeze(0), transform, device
        )
        with torch.inference_mode():
            first = model(obs, goal)
            second = reloaded(obs, goal)
        for a, b in zip(first, second, strict=True):
            torch.testing.assert_close(a, b, rtol=0, atol=0)
        result.update(
            status="PASS",
            stage="VERIFIED",
            training_metrics=metrics,
            training_wall_s=time.perf_counter() - start,
            changed_parameter_tensors=changed,
            checkpoint=str(checkpoint),
            checkpoint_sha256=sha256(checkpoint),
            strict_checkpoint_reload=True,
            reload_prediction_equality=True,
            finetuned_dev=evaluate_fixed(reloaded, "dev", dev),
            finetuned_test=None
            if args.development_only
            else evaluate_fixed(reloaded, "test", test),
            navigation_evaluation="NOT_RUN",
            improvement_claim=False,
        )
        sources = {Path(__file__).resolve(), args.config.resolve()}
        for name, module in list(sys.modules.items()):
            file = getattr(module, "__file__", None)
            if file and name.startswith(("navfm", "vint_train")):
                sources.add(Path(file).resolve())
        result["source_sha256"] = {str(p): sha256(p) for p in sorted(sources)}
        save()
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in [
                        "status",
                        "training_metrics",
                        "strict_checkpoint_reload",
                        "pretrained_test",
                        "finetuned_test",
                    ]
                },
                indent=2,
            )
        )
    except Exception as exc:
        result.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
        save()
        raise


if __name__ == "__main__":
    main()
