"""Exact authenticated persistent-source addition; no verifier rule changes."""

import json
from pathlib import Path

from development_qualification_contracts_v1 import sha
from offline_evaluation_contracts_v1 import atomic_snapshot

RELATIVE = "train/vint_train/models/vint/vint.py"
EXPECTED_SHA = "1af3afb275f6f52d643df792cf39d8bb77e0fe00f06d7ceb9c152a408554ad37"


def extend_manifest(previous, upstream, pinned_upstream_files, project_files):
    origin = (Path(upstream) / RELATIVE).resolve()
    pins = {x["path"]: x["sha256"] for x in pinned_upstream_files}
    if pins.get(RELATIVE) != EXPECTED_SHA or sha(origin) != EXPECTED_SHA:
        raise ValueError("persistent ViNT source does not match existing upstream pin")
    result = json.loads(json.dumps(previous))
    paths = {x["path"] for x in result["files"]}
    additions = [{"path": str(origin), "sha256": EXPECTED_SHA}]
    additions += [{"path": str(Path(p).resolve()), "sha256": sha(Path(p))} for p in project_files]
    for row in additions:
        if row["path"] in paths:
            raise ValueError("new exact source already listed")
        result["files"].append(row)
        paths.add(row["path"])
    result["vint_manifest_v2_additions"] = additions
    return result


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("new versioned manifest path required")
    cfg = json.loads(args.config.read_text())
    result = extend_manifest(
        json.loads(args.previous.read_text()),
        cfg["upstream"],
        cfg["upstream_files"],
        [__file__, str(Path(__file__).with_name("run_vint_interface_qualification_v2.py"))],
    )
    args.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_snapshot(args.out, result)


if __name__ == "__main__":
    main()
