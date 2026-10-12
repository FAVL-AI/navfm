"""Frozen CPU-only actual matcher constructor diagnostic; no forward or graph calls."""

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from qualify_pinned_stop_interfaces_v1 import supervise_worker, write_json
from ravel_fixed_graph_v1 import CONFIG as GRAPH_CONFIG
from ravel_fixed_graph_v1 import (
    load_native,
    native_matcher_constructor_preflight,
    verify_matcher_assets,
)
from recorded_rgb_stop_v1 import reject_python_network, verify_file

CONFIG = Path(__file__).resolve().parents[1] / "configs/eval/ravel_checkpoint_diagnostic_v1.json"


def validate_protocol(cfg):
    if cfg["caps"] != dict(
        worker_cpu_wall_s=30,
        parent_wall_s=60,
        raw_bytes=16777216,
        constructor_attempts=2,
        forwards=0,
        GPU_calls=0,
    ):
        raise ValueError("frozen CPU diagnostic budget changed")
    if cfg["device"] != "cpu" or cfg["fit"] is not False:
        raise ValueError("CPU no-fit contract changed")


def targeted_diagnostic_complete(events):
    target = [row for row in events if row.get("kind") == "lightglue"]
    return (
        sum(row["event"] == "CONSTRUCTOR_ATTEMPT" for row in target) == 1
        and [row["sequence"] for row in target if row["event"] == "STATE_LOAD_DIAGNOSTIC"] == [1, 2]
        and [row["sequence"] for row in target if row["event"] == "STATE_LOAD_RESULT"] == [1, 2]
        and sum(row["event"] == "FINAL_ADMISSION_DIAGNOSTIC" for row in target) == 1
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text())
    validate_protocol(cfg)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != args.freeze or subprocess.check_output(["git", "status", "--porcelain"], text=True):
        raise ValueError("exact clean freeze required")
    if cfg["status"] != "FROZEN_CPU_CHECKPOINT_DIAGNOSTIC_V1":
        raise ValueError("CPU diagnostic protocol not frozen")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise ValueError("CUDA must be hidden")
    folder = args.out.parent
    if args.worker:
        started = time.monotonic()
        events = []

        def emit(event):
            events.append(event)
            with (folder / "partial.jsonl").open("a") as stream:
                stream.write(json.dumps(event, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

        try:
            sys.addaudithook(reject_python_network)
            import torch

            if torch.cuda.is_available():
                raise ValueError("GPU access outside diagnostic contract")
            verify_file(GRAPH_CONFIG, cfg["graph_config_sha256"])
            graph = json.loads(GRAPH_CONFIG.read_text())
            for name in ("missing", "tampered"):
                altered = copy.deepcopy(graph)
                path = folder / (name + ".pth")
                if name == "tampered":
                    path.write_bytes(b"\x00")
                altered["weights"]["superpoint_lightglue.pth"]["local_path"] = str(path)
                try:
                    verify_matcher_assets(altered)
                except (FileNotFoundError, ValueError) as exc:
                    emit(
                        dict(
                            event="AUTHENTICITY_NEGATIVE_REFUSED",
                            case=name,
                            exception_type=type(exc).__name__,
                        )
                    )
                else:
                    raise AssertionError("invalid checkpoint admitted")
            verify_matcher_assets(graph)
            native = load_native(graph)
            refused = None
            try:
                native_matcher_constructor_preflight(native, graph, emit)
            except ValueError as exc:
                if str(exc) != "native final checkpoint coverage incomplete":
                    raise
                refused = str(exc)
                emit(dict(event="UNCHANGED_GUARD_REFUSAL", reason=refused))
            counts = {
                event: sum(row["event"] == event for row in events)
                for event in (
                    "CONSTRUCTOR_ATTEMPT",
                    "MODEL_CONSTRUCTED",
                    "FORWARD_COMPLETE",
                    "STATE_LOAD_DIAGNOSTIC",
                    "STATE_LOAD_RESULT",
                )
            }
            assert counts["CONSTRUCTOR_ATTEMPT"] <= 2 and counts["FORWARD_COMPLETE"] == 0
            if not targeted_diagnostic_complete(events):
                raise ValueError("targeted LightGlue final-load diagnosis incomplete")
            result = dict(
                status="DIAGNOSTIC_CAPTURED_GUARD_REFUSAL"
                if refused
                else "PASS_CPU_CONSTRUCTORS_ONLY",
                freeze=head,
                counts=counts,
                GPU_calls=0,
                forwards=0,
                wall_s=time.monotonic() - started,
                graph_config_sha256=cfg["graph_config_sha256"],
                production_loader_sha256=hashlib.sha256(
                    Path(__file__).with_name("ravel_fixed_graph_v1.py").read_bytes()
                ).hexdigest(),
            )
            write_json(args.out, result)
            write_json(folder / "worker_status.json", dict(status="COMPLETE", freeze=head))
        except BaseException as exc:
            write_json(
                folder / "worker_status.json",
                dict(
                    status="FAIL",
                    freeze=head,
                    exception_type=type(exc).__name__,
                    reason=str(exc)[:500],
                ),
            )
            raise SystemExit(1) from None
        return
    folder.mkdir(parents=True, exist_ok=False)
    write_json(
        folder / "attempt.json",
        dict(
            status="STARTED",
            freeze=head,
            config_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
            caps=cfg["caps"],
        ),
    )
    with (folder / "worker.log").open("x") as log:
        outcome = supervise_worker(
            [sys.executable, __file__, "--worker", "--freeze", head, "--out", str(args.out)],
            log,
            cfg["caps"]["worker_cpu_wall_s"],
        )
    valid = args.out.exists() and (folder / "worker_status.json").exists()
    if valid:
        valid = (
            json.loads((folder / "worker_status.json").read_text())
            == dict(status="COMPLETE", freeze=head)
            and json.loads(args.out.read_text()).get("freeze") == head
        )
    valid = (
        valid
        and sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
        <= cfg["caps"]["raw_bytes"]
    )
    outcome.update(
        status="COMPLETE"
        if valid and outcome["exit_code"] == 0 and not outcome["timeout"]
        else "FAIL",
        freeze=head,
    )
    write_json(folder / "parent_status.json", outcome)
    print(json.dumps(outcome))
    raise SystemExit(0 if outcome["status"] == "COMPLETE" else 1)


if __name__ == "__main__":
    main()
