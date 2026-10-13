"""Reuse the reviewed native scorer, adding exact per-draw raw array retention only."""

import argparse
import json
from pathlib import Path

import offline_evaluation_worker_v1 as worker
from offline_evaluation_contracts_v1 import atomic_snapshot, summarize, validate
from prospective_data_contracts_v1 import preserve_raw_draw


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--model", choices=["gnm", "nomad"], required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    cfg = json.loads(args.config.read_text())
    validate(cfg, json.loads(Path(cfg["admission"]).read_text()))
    report = dict(status="STARTED", stage="imports", model=args.model, rows=[], roles=[])
    provenance = {}
    original = worker.output_metrics
    worker.output_metrics = preserve_raw_draw(report, original)
    try:
        worker.run(args, cfg, report, provenance)
    except BaseException as exc:
        report.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        worker.output_metrics = original
        from native_dependency_closure_v2 import verify_native_dependencies

        try:
            provenance["native_final"] = verify_native_dependencies(cfg)
        except BaseException as exc:
            report.update(status="FAIL", provenance_error_type=type(exc).__name__)
        report["by_trajectory_role_seed"] = summarize(report["rows"], dict(cfg, model=args.model))
        atomic_snapshot(args.out / "report.json", report)
        atomic_snapshot(args.out / "provenance.json", provenance)


if __name__ == "__main__":
    main()
