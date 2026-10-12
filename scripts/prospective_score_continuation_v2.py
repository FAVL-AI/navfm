"""Reuse unchanged prospective native scorer after exact dataset transaction verification."""

import argparse
import json
from pathlib import Path

from offline_evaluation_contracts_v1 import atomic_snapshot
from prospective_scoring_contracts_v2 import verify_bound_dataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model", choices=["gnm", "nomad"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    binding = dict(before=verify_bound_dataset(cfg))
    atomic_snapshot(args.out / "dataset_binding.json", binding)
    try:
        import prospective_score_v1

        prospective_score_v1.main()
    finally:
        try:
            binding["after"] = verify_bound_dataset(cfg)
        except BaseException as exc:
            binding["after"] = dict(status="FAIL", error_type=type(exc).__name__)
            raise
        finally:
            atomic_snapshot(args.out / "dataset_binding.json", binding)


if __name__ == "__main__":
    main()
