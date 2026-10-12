"""One four-role synthetic component qualification; no pairs, labels or scores."""

import argparse
import io
import json
from pathlib import Path

from native_adaptation_contracts_v1 import capture_rng, state_digest
from native_dependency_closure_v2 import verify_native_dependencies
from native_multiseed_worker_v1 import verify_upstream
from offline_evaluation_contracts_v1 import atomic_snapshot
from prospective_data_contracts_v1 import content_sha, safe_raw
from vint_interface_v1 import (
    native_config,
    predict_isolated,
    preprocess,
    strict_load,
    validate_outputs,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    report = dict(status="STARTED", scope="SYNTHETIC_COMPONENT_ONLY", roles=[])
    provenance = {}
    atomic_snapshot(args.out / "report.json", report)
    try:
        from nomad_dependency_boundary_v6 import install_boundary, verify_loaded_dependencies

        install_boundary(cfg["diffusion_root"], cfg["diffusion_files"])
        import numpy as np
        import torch
        from PIL import Image

        from navfm import upstream

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA required before native model construction")
        torch.manual_seed(4080)
        torch.cuda.manual_seed_all(4080)
        report["runtime_seed"] = 4080
        upstream.ensure_upstream()
        mc = upstream.model_config("vint")
        native_config(mc)
        histories = []
        goals = []

        def image(case, tick):
            y, x = np.indices((96, 128))
            pixels = np.stack(
                [
                    (x + 17 * tick + 13 * case) % 256,
                    (2 * y + 7 * tick + 29 * case) % 256,
                    (x + y + 11 * tick + 31 * case) % 256,
                ],
                axis=-1,
            ).astype(np.uint8)
            stream = io.BytesIO()
            Image.fromarray(pixels).save(stream, format="PNG")
            return stream.getvalue()

        for case in range(2):
            histories.append([dict(tick=t, png=image(case, t)) for t in range(6)])
            goals.append(image(case, 9))
        obs, goal = preprocess(histories, goals, mc)
        obs = obs.cuda()
        goal = goal.cuda()
        report["input"] = dict(
            obs_shape=list(obs.shape),
            goal_shape=list(goal.shape),
            obs_sha256=state_digest(obs),
            goal_sha256=state_digest(goal),
            cases=2,
            synthetic_history="distinct chronological ticks0..5; goal9; fixed RGB ramps",
        )
        manifest = json.loads(Path(cfg["installed_dependency_manifest"]).read_text())
        provenance.update(
            before=verify_loaded_dependencies(manifest),
            native_before=verify_native_dependencies(cfg),
            upstream_before=verify_upstream(cfg),
        )
        atomic_snapshot(args.out / "provenance.json", provenance)
        for role in cfg["vint_checkpoints"]:
            model = upstream.build_model("vint", mc)
            strict_load(model, role["path"], role["sha256"], role["role"] == "release")
            model.cuda().eval()
            before = state_digest(model.state_dict())
            rng_before = state_digest(capture_rng())
            dp, ap = predict_isolated(model, obs, goal)
            torch.cuda.synchronize()
            raw = safe_raw(
                dict(distance=dp.detach().cpu().tolist(), actions=ap.detach().cpu().tolist())
            )
            row = dict(role=role, raw=raw, raw_sha256=content_sha(raw), strict_load=True)
            report["roles"].append(row)
            atomic_snapshot(args.out / "report.json", report)
            validate_outputs(raw["distance"], raw["actions"], 2)
            if (
                state_digest(model.state_dict()) != before
                or state_digest(capture_rng()) != rng_before
            ):
                raise ValueError("model or RNG evaluation fence failed")
            clone = upstream.build_model("vint", mc)
            strict_load(clone, role["path"], role["sha256"], role["role"] == "release")
            clone.cuda().eval()
            if state_digest(clone.state_dict()) != before:
                raise ValueError("strict reload state differs")
            dp2, ap2 = predict_isolated(clone, obs, goal)
            torch.cuda.synchronize()
            if not torch.equal(dp, dp2) or not torch.equal(ap, ap2):
                raise ValueError("strict reload forward differs")
            row.update(
                status="PASS",
                strict_reload=True,
                state_fence=True,
                rng_fence=True,
                output_distance_shape=list(dp.shape),
                output_action_shape=list(ap.shape),
            )
            atomic_snapshot(args.out / "report.json", report)
            del model, clone, dp, ap, dp2, ap2
        provenance.update(
            after=verify_loaded_dependencies(manifest),
            native_after=verify_native_dependencies(cfg),
            upstream_after=verify_upstream(cfg),
        )
        report["status"] = "PASS"
    except BaseException as exc:
        report.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        try:
            provenance["native_final"] = verify_native_dependencies(cfg)
        except BaseException as exc:
            report.update(status="FAIL", provenance_error_type=type(exc).__name__)
        atomic_snapshot(args.out / "provenance.json", provenance)
        atomic_snapshot(args.out / "report.json", report)


if __name__ == "__main__":
    main()
