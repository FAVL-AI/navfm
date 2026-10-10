"""Frozen offline CUDA numerical diagnostic; no simulator dependency."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import sys
import traceback
from pathlib import Path

from initialization_diagnostic import REPO, git, sha
from replay_recovery_contracts import COUNTERS, equivalent, snapshot
from replay_recovery_contracts_v2 import frozen as protected

CONFIG = REPO / "configs/eval/offline_numerical_v1.json"


def frozen(commit: str, launch: bool = False) -> dict:
    cfg = json.loads(CONFIG.read_text())
    protected(cfg["protected_freeze"])
    if launch and (
        git("status", "--porcelain") or git("rev-parse", "HEAD").decode().strip() != commit
    ):
        raise ValueError("Clean exact freeze required")
    for name in cfg["files"]:
        if (REPO / name).read_bytes() != git("show", f"{commit}:{name}"):
            raise ValueError("Source drift: " + name)
    for name, digest in cfg["asset_sha256"].items():
        if sha(Path(name)) != digest:
            raise ValueError("Asset drift: " + name)
    return cfg


def schedule() -> list[dict]:
    return [
        dict(mode="isolated", step=i, arm=arm, repeat=rep)
        for i in range(7)
        for rep in range(2)
        for arm in ["reference", "replay"]
    ] + [
        dict(mode="sequence", step=i, arm=arm, repeat=0)
        for arm in ["reference", "replay"]
        for i in range(7)
    ]


def restore(policy, value: dict) -> None:
    current = snapshot(policy)
    for key in ["state_class", "confirmation", "backend", "checkpoint", "config", "chain_length"]:
        if current[key] != value[key]:
            raise ValueError("Unsupported restoration contract: " + key)
    if set(current["state"]) != set(value["state"]) or set(value["counters"]) != set(COUNTERS):
        raise ValueError("Unknown state/counter schema")
    for key, item in value["state"].items():
        if key in ["bounded", "recovery"]:
            if current["state"][key] != item:
                raise ValueError("Configuration state drift")
        else:
            setattr(policy.state, key, copy.deepcopy(item))
    for key in COUNTERS:
        setattr(policy, key, copy.deepcopy(value["counters"][key]))
    if snapshot(policy) != value:
        raise ValueError("Full restored state/window mismatch")


def discrete(value):
    if isinstance(value, float):
        return "<numeric>"
    if isinstance(value, dict):
        return {k: discrete(v) for k, v in value.items()}
    if isinstance(value, list):
        return [discrete(v) for v in value]
    return value


def comparison(a: dict, b: dict, cfg: dict) -> dict:
    return dict(
        tensors_identical=a["entry"] == b["entry"],
        restored_state_identical=a["before"] == b["before"],
        rng_identical=a["rng_before"] == b["rng_before"],
        raw_outputs_identical=a["raw_hashes"] == b["raw_hashes"],
        numerical=all(
            equivalent(a[k], b[k], atol=cfg["atol"], rtol=cfg["rtol"])
            for k in ["prediction", "after", "raw"]
        ),
        discrete=all(discrete(a[k]) == discrete(b[k]) for k in ["prediction", "after"]),
        command=equivalent(
            a["prediction"]["command"],
            b["prediction"]["command"],
            atol=cfg["atol"],
            rtol=cfg["rtol"],
        ),
    )


def margins(pred: dict, policy) -> dict:
    d = sorted(pred["window_distances"])
    return dict(
        argmin_runner_up_gap=None if len(d) < 2 else d[1] - d[0],
        minimum_minus_close=d[0] - policy.topomap_cfg.close_threshold,
        minimum_minus_lost_enter=d[0] - policy.bounded.lost_enter,
        minimum_minus_lost_exit=d[0] - policy.bounded.lost_exit,
        minimum_minus_recovery_exit=d[0] - policy.recovery.exit,
        requested_goal_minus_close=pred["requested_goal_distance"]
        - policy.topomap_cfg.close_threshold,
    )


def analyse(workers: list[dict], cfg: dict) -> dict:
    if len(workers) != 2 or any(w["status"] != "PASS" or len(w["calls"]) != 42 for w in workers):
        raise ValueError("Incomplete manifest")

    if workers[0]["settings"] != workers[1]["settings"]:
        raise ValueError("Runtime settings differ across workers")
    for worker in workers:
        if [
            {k: x[k] for k in ["mode", "step", "arm", "repeat"]} for x in worker["calls"]
        ] != schedule():
            raise ValueError("Manifest order mismatch")

    def get(w, mode, step, arm, rep=0):
        values = [
            x
            for x in w["calls"]
            if all(x[k] == v for k, v in dict(mode=mode, step=step, arm=arm, repeat=rep).items())
        ]
        if len(values) != 1:
            raise ValueError("Ambiguous manifest cell")
        return values[0]

    rows = []
    for wi, w in enumerate(workers):
        for step in range(7):
            for arm in ["reference", "replay"]:
                rows.append(
                    dict(
                        kind="within_process_identical_input",
                        worker=wi,
                        step=step,
                        arm=arm,
                        **comparison(
                            get(w, "isolated", step, arm, 0), get(w, "isolated", step, arm, 1), cfg
                        ),
                    )
                )
            for rep in range(2):
                rows.append(
                    dict(
                        kind="same_state_input_contrast",
                        worker=wi,
                        step=step,
                        repeat=rep,
                        **comparison(
                            get(w, "isolated", step, "reference", rep),
                            get(w, "isolated", step, "replay", rep),
                            cfg,
                        ),
                    )
                )
            rows.append(
                dict(
                    kind="full_sequence_input_contrast",
                    worker=wi,
                    step=step,
                    **comparison(
                        get(w, "sequence", step, "reference"),
                        get(w, "sequence", step, "replay"),
                        cfg,
                    ),
                )
            )
    for step in range(7):
        for arm in ["reference", "replay"]:
            for rep in range(2):
                rows.append(
                    dict(
                        kind="fresh_process_identical_input",
                        step=step,
                        arm=arm,
                        repeat=rep,
                        **comparison(
                            get(workers[0], "isolated", step, arm, rep),
                            get(workers[1], "isolated", step, arm, rep),
                            cfg,
                        ),
                    )
                )
            rows.append(
                dict(
                    kind="fresh_process_full_sequence",
                    step=step,
                    arm=arm,
                    **comparison(
                        get(workers[0], "sequence", step, arm),
                        get(workers[1], "sequence", step, arm),
                        cfg,
                    ),
                )
            )
    same = [
        x
        for x in rows
        if x["kind"] in ["within_process_identical_input", "fresh_process_identical_input"]
    ]
    if any(
        not all(x[k] for k in ["tensors_identical", "restored_state_identical", "rng_identical"])
        for x in same
    ):
        raise ValueError("Identical-input comparison integrity failure")
    return dict(
        scope="OFFLINE_TWO_PROCESS_DIAGNOSTIC_ONLY",
        calls=84,
        comparisons=rows,
        same_input_numerical_stable=all(x["numerical"] for x in same),
        existing_handover_gate_unchanged=True,
        efficacy_claim=False,
        further_runs_authorized=False,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", required=True)
    p.add_argument("--process-id", required=True)
    args = p.parse_args()
    cfg = frozen(args.freeze, launch=True)
    if args.process_id not in cfg["process_ids"] or sys.executable != cfg["python"]:
        p.error("Undeclared process/runtime")
    out = Path(cfg["output_root"]) / args.process_id
    out.mkdir(parents=True, exist_ok=False)
    report = dict(status="RUNNING", process_id=args.process_id, freeze=args.freeze, calls=[])

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")

    save()
    try:
        os.environ["NAVFM_UPSTREAM"] = cfg["upstream"]
        sys.path.insert(0, str(REPO / "src"))
        import numpy as np
        import torch
        from PIL import Image

        from navfm.collection.rgb_baseline import RGBTopomapBaseline, topomap_components

        torch.set_num_threads(4)
        torch.manual_seed(0)
        spec = json.loads((REPO / "configs/eval/prospective_r2_recovery_v1.json").read_text())
        policy = RGBTopomapBaseline(
            Path(cfg["checkpoint"]),
            radius=4,
            close_threshold=3.0,
            **topomap_components(spec["variants"]["R2_recover"], start_lost=False),
            action_scale_m=0.049994826316833496,
            stop_enabled=True,
            max_v=0.1,
            control_period_s=0.5,
        )
        if policy.device != "cuda" or policy.model.training:
            raise ValueError("CUDA eval required")
        nodes = json.loads(Path(cfg["chain_json"]).read_text())["routes"][cfg["case"]]["nodes"]
        policy.set_chain([np.asarray(Image.open(n["source"]).convert("RGB")) for n in nodes])
        goal = np.asarray(Image.open(cfg["goal"]).convert("RGB"))
        traces = {k: json.loads(Path(v).read_text()) for k, v in cfg["traces"].items()}
        common = dict(
            py=random.getstate(),
            np=np.random.get_state(),
            cpu=torch.get_rng_state(),
            cuda=torch.cuda.get_rng_state_all(),
        )

        def reset_rng():
            random.setstate(common["py"])
            np.random.set_state(common["np"])
            torch.set_rng_state(common["cpu"])
            torch.cuda.set_rng_state_all(common["cuda"])

        def rng_digest():
            ns = np.random.get_state()
            return hashlib.sha256(
                repr((random.getstate(), ns[0], *ns[2:])).encode()
                + ns[1].tobytes()
                + torch.get_rng_state().numpy().tobytes()
                + b"".join(x.cpu().numpy().tobytes() for x in torch.cuda.get_rng_state_all())
            ).hexdigest()

        def tensor_record(t):
            x = t.detach().cpu().contiguous()
            return dict(
                shape=list(x.shape),
                dtype=str(x.dtype),
                sha256=hashlib.sha256(x.numpy().tobytes()).hexdigest(),
            )

        entries = []
        raws = []
        raw_hashes = []

        def before_model(module, inputs):
            if len(inputs) != 2:
                raise ValueError("Unknown model entry")
            entries.append([tensor_record(x) for x in inputs])

        def after_model(module, inputs, outputs):
            raw_hashes.append([tensor_record(x) for x in outputs])
            values = [x.detach().cpu().tolist() for x in outputs]
            if not all(bool(torch.isfinite(x).all()) for x in outputs):
                raws.append(repr(values))
                raise ValueError("Nonfinite model output")
            raws.append(values)

        policy.model.register_forward_pre_hook(before_model)
        policy.model.register_forward_hook(after_model)
        report["settings"] = dict(
            python=sys.executable,
            torch=torch.__version__,
            cuda=torch.version.cuda,
            gpu=torch.cuda.get_device_name(0),
            threads=torch.get_num_threads(),
            model_training=policy.model.training,
            cudnn_benchmark=torch.backends.cudnn.benchmark,
            cudnn_deterministic=torch.backends.cudnn.deterministic,
            deterministic_algorithms=torch.are_deterministic_algorithms_enabled(),
            deterministic_warn_only=torch.is_deterministic_algorithms_warn_only_enabled(),
            cuda_matmul_tf32=torch.backends.cuda.matmul.allow_tf32,
            cudnn_tf32=torch.backends.cudnn.allow_tf32,
            matmul_precision=torch.get_float32_matmul_precision(),
            cublas_workspace_config=os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
            checkpoint=policy.digest,
            seed_cpu_cuda=0,
            python_numpy_rng="captured/restored process initial state",
        )
        # Python/NumPy process-initial random states must be identical across workers.
        random.seed(0)
        np.random.seed(0)
        common["py"] = random.getstate()
        common["np"] = np.random.get_state()
        report["settings"]["python_numpy_rng"] = (
            "seed0 captured/restored; used only for offline repeat control"
        )
        for cell in schedule():
            step = cell["step"]
            arm = cell["arm"]
            saved = traces["reference"]["learned_invocations"][step]
            if cell["mode"] == "isolated" or step == 0:
                restore(policy, saved["before"])
                reset_rng()
            call = dict(cell, before=snapshot(policy), rng_before=rng_digest())
            hist = traces[arm]["learned_invocations"][step]["history"]
            images = [
                np.asarray(Image.open(Path(cfg["traces"][arm]).parent / h["image"]).convert("RGB"))
                for h in hist
            ]
            entries.clear()
            raws.clear()
            raw_hashes.clear()
            report["active_call"] = dict(
                call,
                measured_entries=entries,
                measured_raw_outputs=raws,
                measured_raw_hashes=raw_hashes,
            )
            save()
            pred = policy.step(images, goal)
            pred.pop("latency_ms", None)
            if len(entries) != 1 or len(raws) != 1:
                raise ValueError("Missing/extra model call")
            call.update(
                entry=entries[0],
                raw=raws[0],
                raw_hashes=raw_hashes[0],
                prediction=pred,
                after=snapshot(policy),
                margins=margins(pred, policy),
                rng_after=rng_digest(),
            )
            report["calls"].append(call)
            report.pop("active_call", None)
            save()
        frozen(args.freeze, launch=True)
        report.update(status="PASS", postflight=True)
        save()
    except Exception:
        report.update(status="FAIL", error=traceback.format_exc())
        save()
        raise


if __name__ == "__main__":
    main()
