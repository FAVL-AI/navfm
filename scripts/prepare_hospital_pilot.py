"""Prepare matched engineering pilot pairs; refuse to label incomplete arms ready."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-manifest", required=True)
    parser.add_argument("--admission", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--baseline-checkpoint")
    parser.add_argument("--layer-entrypoint")
    args = parser.parse_args()
    out = Path(args.out).expanduser().resolve()
    if out.exists() or out.is_relative_to(REPO):
        parser.error("pilot manifest must be new and outside the repository")
    runtime_file = Path(args.runtime_manifest)
    runtime = json.loads(runtime_file.read_text())
    if runtime.get("status") != "PASS" or not runtime.get("preflight", {}).get("SCIENTIFIC_COLLECTION_PERMITTED"):
        parser.error("runtime instrumentation smoke has not passed")
    admission_file = Path(args.admission)
    route = json.loads(admission_file.read_text())["selected_route"]
    blocked = ["semantic visibility and navigation route admission require prospective review",
               "RGB-only layer input-boundary audit not yet performed"]
    frozen = {}
    for name, supplied in (("baseline_checkpoint", args.baseline_checkpoint),
                           ("layer_entrypoint", args.layer_entrypoint)):
        if supplied is None:
            blocked.append(f"{name} not supplied")
            frozen[name] = None
        else:
            file = Path(supplied).expanduser().resolve()
            frozen[name] = {"path": str(file), "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
    # Three seeds are an engineering repetition budget, not a publication sample
    # size or an estimate of statistical power.
    pairs = [{"pair_id": f"hospital_pilot_{seed:02d}", "seed": seed,
              "evaluation_fixture": {"start_pose": route["start_pose"], "goal_pose": route["goal_pose"]},
              "order": ["baseline", "layer"] if seed % 2 == 0 else ["layer", "baseline"],
              "shared_policy_inputs": ["rgb_history", "goal_rgb"],
              "ground_truth_access": "isolated evaluator only",
              "arms": [{"arm": arm, "run_id": f"hospital_pilot_{seed:02d}_{arm}"}
                       for arm in ("baseline", "layer")]} for seed in range(3)]
    manifest = {"status": "BLOCKED_PENDING_FREEZE", "blockers": blocked,
                "scope": "matched engineering pilot; no publication results",
                "runtime_manifest_sha256": hashlib.sha256(runtime_file.read_bytes()).hexdigest(),
                "runtime_manifest": str(runtime_file.resolve()),
                "admission_sha256": hashlib.sha256(admission_file.read_bytes()).hexdigest(),
                "requested_runtime": runtime["requested"],
                "observed_runtime": runtime["observations"],
                "frozen_arms": frozen, "pairs": pairs,
                "publication_protocol": str(REPO / "docs/HOSPITAL_PUBLICATION_PILOT.md")}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x") as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Prepared {len(pairs)} matched pairs: {out}; status={manifest['status']}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
