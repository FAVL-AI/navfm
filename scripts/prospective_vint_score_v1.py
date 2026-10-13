"""Reuse unchanged native worker with only ViNT build/forward/load bindings."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from offline_evaluation_contracts_v1 import atomic_snapshot, summarize
from prospective_data_contracts_v1 import preserve_raw_draw
from vint_interface_v1 import predict_isolated
from vint_scoring_contracts_v1 import verify_continuation, vint_output_metrics


def worker_namespace():
    path = Path(__file__).with_name("offline_evaluation_worker_v1.py")
    source = path.read_text()
    replacements = {
        'wrapper = importlib.import_module(f"adapt_{args.model}_native_v1")': 'wrapper = SimpleNamespace(build=lambda cfg: upstream.build_model("vint", cfg))',
        'trust_checkpoint=args.model == "gnm"': 'trust_checkpoint=role["role"] == "release"',
        'if args.model == "gnm":\n                    return target(batch[0], batch[1])': 'if args.model == "vint":\n                    return predict_isolated(target, batch[0], batch[1])',
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError("frozen worker integration anchor changed")
        source = source.replace(old, new)
    ns = dict(
        __name__="vint_scoring_reused_worker",
        SimpleNamespace=SimpleNamespace,
        predict_isolated=predict_isolated,
    )
    exec(compile(source, str(path), "exec"), ns)
    ns["integration_source"] = source
    return ns


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model", choices=["vint"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    binding = {"before": verify_continuation(cfg)}
    report = dict(status="STARTED", stage="imports", model="vint", rows=[], roles=[])
    provenance = {}
    atomic_snapshot(args.out / "report.json", report)
    ns = worker_namespace()
    ns["output_metrics"] = preserve_raw_draw(report, vint_output_metrics)
    try:
        ns["run"](args, cfg, report, provenance)
    except BaseException as exc:
        report.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        try:
            provenance["native_final"] = ns["verify_native_dependencies"](cfg)
            binding["after"] = verify_continuation(cfg)
        except BaseException as exc:
            report.update(status="FAIL", provenance_error_type=type(exc).__name__)
        report["by_trajectory_role_seed"] = summarize(report["rows"], dict(cfg, model="vint"))
        atomic_snapshot(args.out / "dataset_binding.json", binding)
        atomic_snapshot(args.out / "report.json", report)
        atomic_snapshot(args.out / "provenance.json", provenance)


if __name__ == "__main__":
    main()
