"""Explicit one-stage prospective pilot; publishing never starts a later stage."""

import argparse
import fcntl
import json
import os
import secrets
import signal
import time
from pathlib import Path

from development_qualification_contracts_v1 import ROOT, cancel_signal, frozen, run_bounded, sha
from offline_evaluation_contracts_v1 import atomic_snapshot as write
from offline_evaluation_contracts_v1 import pairs_from_metadata
from prospective_data_contracts_v1 import content_sha, specification, validate_seal

ORDER = ("seal", "qualify", "collect", "gnm", "nomad")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--freeze", required=True)
    p.add_argument("--stage", choices=ORDER, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    cfg = json.loads((ROOT / "configs/eval/prospective_data_v1.json").read_text())
    frozen(args.freeze, cfg)
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        raise ValueError("fresh external stage output required")
    registry = Path(cfg["prospective"]["registry"])
    registry.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (registry / "lock").open("a")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    ledger_path = registry / "stages.json"
    prior = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    if (
        [r["stage"] for r in prior] != list(ORDER[: len(prior)])
        or len(prior) >= len(ORDER)
        or ORDER[len(prior)] != args.stage
    ):
        raise ValueError("stage consumed/out of order")
    for r in prior:
        if r["freeze"] != args.freeze or r["status"] != "PASS":
            raise ValueError("prior stage failure/identity; halt")
        for path, digest in r["artifacts"].items():
            if sha(Path(r["out"]) / path) != digest:
                raise ValueError("prior evidence drift")
    out.mkdir(parents=True, mode=0o700)
    os.umask(0o077)
    record = dict(stage=args.stage, freeze=args.freeze, out=str(out), status="STARTED")
    prior.append(record)
    write(ledger_path, prior)
    start = time.monotonic()
    signal.signal(signal.SIGTERM, cancel_signal)
    try:
        if args.stage == "seal":
            spec = specification([secrets.randbits(64), secrets.randbits(64)])
            write(
                out / "seal.json",
                dict(
                    freeze=args.freeze,
                    specification=spec,
                    specification_sha256=content_sha(spec),
                    prior_content_access="NONE_DECLARED",
                    created_wall_s=time.time(),
                    usage="prospective offline prediction only",
                ),
            )
        else:
            spec = None
            if args.stage == "collect":
                seal = json.loads((Path(prior[0]["out"]) / "seal.json").read_text())
                spec = validate_seal(seal, cfg["prospective"]["known_trajectory_ids"], args.freeze)
                record["specification_access"] = "DECLASSIFIED_FOR_AUTHORIZED_COLLECTION"
            env = dict(
                os.environ,
                PYTHONPATH=str(ROOT / "src"),
                NAVFM_UPSTREAM=cfg["upstream"],
                PYTHONNOUSERSITE="1",
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
                WANDB_MODE="disabled",
                OMNICLIENT_HUB_MODE="disabled",
            )
            if args.stage in ("qualify", "collect"):
                write(
                    out / "specification.json",
                    specification([0, 1]) if args.stage == "qualify" else spec,
                )
                command = [
                    cfg["python"],
                    str(ROOT / "scripts/prospective_capture_v1.py"),
                    "--config",
                    str(ROOT / "configs/eval/prospective_data_v1.json"),
                    "--spec",
                    str(out / "specification.json"),
                    "--out",
                    str(out),
                ]
                if args.stage == "qualify":
                    command.append("--qualify")
                cap = 120
            else:
                collected = Path(prior[2]["out"])
                admission = json.loads((collected / "admission.json").read_text())
                names = admission["splits"]["dev"]
                local = dict(
                    cfg,
                    admission=str(collected / "admission.json"),
                    dataset=str(collected / "data"),
                    partitions={"train": [], "development": names},
                    pairs={"development": pairs_from_metadata(names, dict.fromkeys(names, 36), [])},
                )
                write(out / "evaluation.json", local)
                command = [
                    cfg["python"],
                    str(ROOT / "scripts/prospective_score_v1.py"),
                    "--config",
                    str(out / "evaluation.json"),
                    "--model",
                    args.stage,
                    "--out",
                    str(out),
                ]
                cap = 1800
            with (out / "process.log").open("w") as log:
                code = run_bounded(
                    command, env, ROOT, log, max(0, cap - (time.monotonic() - start) - 5)
                )
            record["child_reaped"] = True
            report = json.loads(
                (
                    out
                    / ("capture.json" if args.stage in ("qualify", "collect") else "report.json")
                ).read_text()
            )
            if code or report["status"] != "PASS":
                raise ValueError("stage incomplete")
            if args.stage in ("qualify", "collect"):
                expected = 19 if args.stage == "qualify" else 144
                if len(report["frames"]) != expected:
                    raise ValueError("capture population incomplete")
                if args.stage == "collect":
                    names = [r["id"] for x in spec["layouts"] for r in x["routes"]]
                    hashes = {
                        str(f.relative_to(out / "data")): sha(f)
                        for f in (out / "data").rglob("*")
                        if f.is_file()
                    }
                    write(
                        out / "admission.json",
                        dict(
                            status="PASS",
                            scope="prospective kinematic offline pilot",
                            splits={"train": [], "dev": names, "test": []},
                            dataset_file_sha256=hashes,
                            trajectories=[dict(id=n, processed_frames=36) for n in names],
                        ),
                    )
        frozen(args.freeze, cfg)
        record["status"] = "PASS"
    except BaseException as exc:
        record.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        record["occupied_wall_s"] = time.monotonic() - start
        record["artifacts"] = {
            str(f.relative_to(out)): sha(f) for f in out.rglob("*") if f.is_file()
        }
        write(out / "ledger.json", record)
        write(ledger_path, prior)


if __name__ == "__main__":
    main()
