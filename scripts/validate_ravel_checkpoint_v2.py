"""Frozen CPU native/raw versus guarded canonical constructor parity; no forwards."""

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
from ravel_fixed_graph_v1 import (
    CANONICAL_POLICY_V2,
    canonicalize_lightglue_transport_v2,
    configure_native_matcher_constructors,
    invoke_native_lightglue_constructor_v2,
    load_native,
    verify_matcher_assets,
)
from ravel_fixed_graph_v1 import CONFIG as GRAPH_CONFIG
from recorded_rgb_stop_v1 import reject_python_network, verify_file

CONFIG = Path(__file__).resolve().parents[1] / "configs/eval/ravel_checkpoint_validation_v2.json"


def validate_protocol(cfg):
    if cfg["caps"] != dict(
        worker_cpu_wall_s=60,
        parent_wall_s=120,
        raw_bytes=16777216,
        constructor_attempts=6,
        forwards=0,
        GPU_calls=0,
    ):
        raise ValueError("frozen CPU validation budget changed")


def validate_constructors(graph, emit):
    import torch

    verify_matcher_assets(graph)
    policy = json.loads(CANONICAL_POLICY_V2.read_text())
    weight = graph["weights"]["superpoint_lightglue.pth"]
    state = torch.load(weight["local_path"], map_location="cpu", weights_only=True)
    effective = policy["effective_config"]
    for case in (
        "wrong_source",
        "wrong_asset",
        "wrong_config",
        "legacy_shape",
        "legacy_dtype",
        "legacy_nonfinite",
    ):
        cfg = copy.deepcopy(graph)
        candidate = dict(state)
        conf = dict(effective)
        if case == "wrong_source":
            cfg["sources"]["lightglue"]["sha256"] = "0" * 64
        elif case == "wrong_asset":
            cfg["weights"]["superpoint_lightglue.pth"]["sha256"] = "0" * 64
        elif case == "wrong_config":
            conf["n_layers"] = 10
        elif case == "legacy_shape":
            candidate["log_assignment.0.r"] = torch.zeros(2)
        elif case == "legacy_dtype":
            candidate["log_assignment.0.r"] = state["log_assignment.0.r"].double()
        else:
            candidate["log_assignment.0.r"] = torch.full((1,), float("nan"))
        try:
            canonicalize_lightglue_transport_v2(candidate, cfg, conf, lambda row: None)
        except ValueError as exc:
            emit(dict(event="PRECONSTRUCTOR_CONTROL_REFUSED", case=case, reason=str(exc)))
        else:
            raise AssertionError("invalid binding/legacy state admitted")
    native = load_native(graph)
    stats = dict(superpoint=0, lightglue=0, technical_failures=0)
    zero_caps = dict(superpoint=0, lightglue=0)
    configure_native_matcher_constructors(native, graph, emit, stats, forward_caps=zero_caps)
    raw = invoke_native_lightglue_constructor_v2(
        native, graph, native.lg.LightGlue, emit, "raw_native_oracle"
    )
    emit(dict(event="RAW_NATIVE_ORACLE_RETURNED", adapter_admission=False))
    _, guarded = configure_native_matcher_constructors(
        native, graph, emit, stats, forward_caps=zero_caps, canonicalize_lightglue=True
    )
    canonical = invoke_native_lightglue_constructor_v2(
        native, graph, guarded, emit, "canonical_guarded"
    )
    comparisons = {}
    for kind, accessor in (("parameters", "named_parameters"), ("buffers", "named_buffers")):
        before, after = dict(getattr(raw, accessor)()), dict(getattr(canonical, accessor)())
        assert before.keys() == after.keys()
        mismatch = [
            name
            for name in before
            if before[name].dtype != after[name].dtype
            or before[name].shape != after[name].shape
            or not torch.equal(before[name], after[name])
            or not torch.equal(
                before[name].detach().contiguous().view(torch.uint8),
                after[name].detach().contiguous().view(torch.uint8),
            )
        ]
        if mismatch:
            raise AssertionError("native/canonical state values differ")
        comparisons[kind] = len(before)
    assert comparisons == dict(parameters=251, buffers=1)
    emit(
        dict(
            event="BITWISE_STATE_PARITY",
            **comparisons,
            mismatches=0,
            forwards=0,
            dtype_shape_and_tensor_bytes_equal=True,
        )
    )
    negative_messages = {
        "missing_parameter": "native final checkpoint coverage incomplete",
        "unknown_extra": "native final checkpoint coverage incomplete",
        "wrong_shape": "size mismatch",
        "remap_collision": "native remap collision refused",
    }
    for case, expected in negative_messages.items():
        _, controlled = configure_native_matcher_constructors(
            native,
            graph,
            emit,
            stats,
            forward_caps=zero_caps,
            canonicalize_lightglue=True,
            validation_case=case,
        )
        try:
            invoke_native_lightglue_constructor_v2(native, graph, controlled, emit, case)
        except (ValueError, RuntimeError) as exc:
            if expected not in str(exc):
                raise
            emit(
                dict(
                    event="ACTUAL_NATIVE_CONTROL_REFUSED",
                    case=case,
                    exception_type=type(exc).__name__,
                    reason=str(exc)[:500],
                )
            )
        else:
            raise AssertionError("derived negative state admitted")
    assert stats["superpoint"] == stats["lightglue"] == 0
    return comparisons


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
    if (
        cfg["status"] != "FROZEN_CPU_CHECKPOINT_VALIDATION_V2"
        or os.environ.get("CUDA_VISIBLE_DEVICES") != ""
    ):
        raise ValueError("frozen CPU-only contract required")
    folder = args.out.parent
    if args.worker:
        started = time.monotonic()
        events = []

        def emit(row):
            events.append(row)
            with (folder / "partial.jsonl").open("a") as stream:
                stream.write(json.dumps(row, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

        try:
            sys.addaudithook(reject_python_network)
            import torch

            assert not torch.cuda.is_available()
            verify_file(GRAPH_CONFIG, cfg["graph_config_sha256"])
            verify_file(CANONICAL_POLICY_V2, cfg["canonical_policy_sha256"])
            graph = json.loads(GRAPH_CONFIG.read_text())
            for case in ("missing_asset", "tampered_asset"):
                changed = copy.deepcopy(graph)
                path = folder / (case + ".pth")
                if case == "tampered_asset":
                    path.write_bytes(b"\x00")
                changed["weights"]["superpoint_lightglue.pth"]["local_path"] = str(path)
                try:
                    verify_matcher_assets(changed)
                except (ValueError, FileNotFoundError):
                    emit(dict(event="AUTHENTICITY_CONTROL_REFUSED", case=case))
                else:
                    raise AssertionError("invalid asset admitted")
            parity = validate_constructors(graph, emit)
            counts = {
                name: sum(row["event"] == name for row in events)
                for name in (
                    "CONSTRUCTOR_ATTEMPT",
                    "FORWARD_COMPLETE",
                    "MODEL_CONSTRUCTED",
                    "ACTUAL_NATIVE_CONTROL_REFUSED",
                )
            }
            assert counts["CONSTRUCTOR_ATTEMPT"] == 6 and counts["FORWARD_COMPLETE"] == 0
            assert counts["ACTUAL_NATIVE_CONTROL_REFUSED"] == 4
            write_json(
                args.out,
                dict(
                    status="PASS_CPU_CANONICAL_CONSTRUCTOR_PARITY_ONLY",
                    freeze=head,
                    counts=counts,
                    bitwise_parity=parity,
                    GPU_calls=0,
                    forwards=0,
                    wall_s=time.monotonic() - started,
                ),
            )
            write_json(folder / "worker_status.json", dict(status="PASS", freeze=head))
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
            configuration_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
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
            == dict(status="PASS", freeze=head)
            and json.loads(args.out.read_text()).get("freeze") == head
        )
    valid = (
        valid
        and sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
        <= cfg["caps"]["raw_bytes"]
    )
    outcome.update(
        status="PASS" if valid and outcome["exit_code"] == 0 and not outcome["timeout"] else "FAIL",
        freeze=head,
    )
    write_json(folder / "parent_status.json", outcome)
    print(json.dumps(outcome))
    raise SystemExit(0 if outcome["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
