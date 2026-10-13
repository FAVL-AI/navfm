"""Preparation-only callable worker: native inference, no optimizer or selection."""

import argparse
import importlib
import json
import time
from pathlib import Path

from development_qualification_contracts_v1 import sha
from native_adaptation_contracts_v1 import state_digest
from native_dependency_closure_v2 import verify_native_dependencies
from native_multiseed_worker_v1 import fixed_batch, verify_upstream
from offline_evaluation_contracts_v1 import (
    atomic_snapshot as write,
)
from offline_evaluation_contracts_v1 import (
    draw_seed,
    latency,
    output_metrics,
    retained_attempt,
    summarize,
    validate,
)


def run(args, cfg, report, provenance):
    from nomad_dependency_boundary_v6 import install_boundary, verify_loaded_dependencies

    install_boundary(cfg["diffusion_root"], cfg["diffusion_files"])
    import torch

    from navfm import upstream
    from navfm.models.loader import extract_state_dict, load_checkpoint

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required before model construction")
    upstream.ensure_upstream()
    model_config = upstream.model_config(args.model)
    wrapper = importlib.import_module(f"adapt_{args.model}_native_v1")
    manifest = json.loads(Path(cfg["installed_dependency_manifest"]).read_text())
    provenance.update(
        {
            "before": verify_loaded_dependencies(manifest),
            "upstream_before": verify_upstream(cfg),
        }
    )
    pairs = cfg["pairs"]["development"]
    report["stage"] = "batches"
    batches = []
    for pair in pairs:
        local = dict(cfg, pairs={"development": [pair]})
        started = time.perf_counter()
        batch, identity = fixed_batch(local, model_config, "development", torch, device="cpu")
        preprocessing_ms = latency(started, time.perf_counter())
        batches.append((tuple(t.cuda() for t in batch), identity, preprocessing_ms))
    write(args.out / "report.json", report)
    provenance["native_before"] = verify_native_dependencies(cfg)
    write(args.out / "provenance.json", provenance)
    report["stage"] = "checkpoints"
    for role in cfg["checkpoints"][args.model]:
        if sha(Path(role["path"])) != role["sha256"]:
            raise ValueError("checkpoint drift")
        report["stage"] = "checkpoint_load"
        model = wrapper.build(model_config)
        state = extract_state_dict(
            load_checkpoint(
                role["path"], trust_checkpoint=args.model == "gnm", expected_sha256=role["sha256"]
            )
        )
        model.load_state_dict(state, strict=True)
        del state
        model.cuda().eval()
        before = state_digest(model.state_dict())

        def predict(batch, target=model):
            with torch.no_grad():
                if args.model == "gnm":
                    return target(batch[0], batch[1])
                return wrapper.predict(target, batch)

        report["stage"] = "warmups"
        for _ in range(cfg["evaluation"]["warmups"]):
            torch.manual_seed(draw_seed(0, 0))
            torch.cuda.manual_seed_all(draw_seed(0, 0))
            predict(batches[0][0])
        torch.cuda.synchronize()
        report["stage"] = "prediction"
        for index, (batch, identity, preprocessing_ms) in enumerate(batches):
            for draw in range(cfg["evaluation"]["draws"][args.model]):
                seed = draw_seed(index, draw)
                identity_row = dict(
                    role=role,
                    pair_index=index,
                    pair=pairs[index],
                    draw=draw,
                    draw_seed=seed,
                    batch_identity=identity,
                    preprocessing_ms=preprocessing_ms,
                )

                def callback(batch=batch, seed=seed, predict=predict):
                    torch.manual_seed(seed)
                    torch.cuda.manual_seed_all(seed)
                    torch.cuda.synchronize()
                    started = time.perf_counter()
                    dp, ap = predict(batch)
                    torch.cuda.synchronize()
                    duration_ms = latency(started, time.perf_counter())
                    metrics = output_metrics(
                        ap.detach().cpu().tolist(),
                        dp.detach().cpu().tolist(),
                        batch[2][0].cpu().tolist(),
                        float(batch[3][0]),
                        bool(batch[4][0]),
                        cfg["metric_spacing_m"],
                        model_config["len_traj_pred"],
                    )
                    return dict(metrics=metrics, inference_ms=duration_ms)

                retained_attempt(
                    report, identity_row, callback, lambda: write(args.out / "report.json", report)
                )
        if state_digest(model.state_dict()) != before:
            raise ValueError("evaluation mutated model state")
        report["roles"].append(dict(role=role, strict_load=True, state_fence=True))
        del model
    provenance.update(
        after=verify_loaded_dependencies(manifest), upstream_after=verify_upstream(cfg)
    )
    provenance["native_after"] = verify_native_dependencies(cfg)
    write(args.out / "provenance.json", provenance)
    report["by_trajectory_role_seed"] = summarize(report["rows"], dict(cfg, model=args.model))
    report["status"] = "PASS"
    write(args.out / "report.json", report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model", choices=["gnm", "nomad"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    validate(cfg, json.loads(Path(cfg["admission"]).read_text()))
    report = dict(status="STARTED", stage="imports", model=args.model, rows=[], roles=[])
    provenance = {}
    write(args.out / "report.json", report)
    try:
        run(args, cfg, report, provenance)
    except BaseException as exc:
        report.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        try:
            provenance["native_final"] = verify_native_dependencies(cfg)
        except BaseException as exc:
            provenance["native_final_error"] = type(exc).__name__
            report["status"] = "FAIL"
        try:
            from nomad_dependency_boundary_v6 import verify_loaded_dependencies

            provenance["selected_final"] = verify_loaded_dependencies(
                json.loads(Path(cfg["installed_dependency_manifest"]).read_text())
            )
            provenance["upstream_final"] = verify_upstream(cfg)
        except BaseException as exc:
            provenance["selected_upstream_final_error"] = type(exc).__name__
            report["status"] = "FAIL"
        report["by_trajectory_role_seed"] = summarize(report["rows"], dict(cfg, model=args.model))
        write(args.out / "provenance.json", provenance)
        write(args.out / "report.json", report)


if __name__ == "__main__":
    main()
