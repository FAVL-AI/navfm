"""Thin fixed-mode graph continuation consuming existing authenticated CPU proof."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from qualify_pinned_stop_interfaces_v1 import supervise_worker, write_json
from ravel_fixed_graph_v1 import accept_worker_outcome, run_graph, validate_contract
from recorded_rgb_stop_v1 import reject_python_network, verify_file

CONFIG = Path(__file__).resolve().parents[1] / "configs/eval/ravel_fixed_graph_continuation_v2.json"
QUALIFIED_FREEZE = "63b482203f24cbd6cfda707073e2763ee6851b4a"


def load_bound_json(row):
    verify_file(row["path"], row["sha256"])
    return json.loads(Path(row["path"]).read_text())


def validate_proof_semantics(result, parent, events, expected_freeze):
    if (
        expected_freeze != QUALIFIED_FREEZE
        or result.get("freeze") != expected_freeze
        or parent.get("freeze") != expected_freeze
    ):
        raise ValueError("constructor proof freeze mismatch")
    if (
        parent.get("status") != "PASS"
        or parent.get("exit_code") != 0
        or parent.get("timeout") is not False
        or parent.get("reaped") is not True
    ):
        raise ValueError("constructor proof parent outcome not qualified")
    if (
        result.get("status") != "PASS_CPU_CANONICAL_CONSTRUCTOR_PARITY_ONLY"
        or result.get("GPU_calls") != 0
        or result.get("forwards") != 0
        or result.get("counts")
        != dict(
            CONSTRUCTOR_ATTEMPT=6,
            FORWARD_COMPLETE=0,
            MODEL_CONSTRUCTED=1,
            ACTUAL_NATIVE_CONTROL_REFUSED=4,
        )
        or result.get("bitwise_parity") != dict(parameters=251, buffers=1)
    ):
        raise ValueError("constructor proof state/call contract mismatch")
    parity = [row for row in events if row["event"] == "BITWISE_STATE_PARITY"]
    if (
        len(parity) != 1
        or parity[0].get("parameters") != 251
        or parity[0].get("buffers") != 1
        or parity[0].get("mismatches") != 0
        or parity[0].get("forwards") != 0
        or parity[0].get("dtype_shape_and_tensor_bytes_equal") is not True
    ):
        raise ValueError("constructor proof byte-parity evidence missing")
    negatives = {
        row.get("case") for row in events if row["event"] == "ACTUAL_NATIVE_CONTROL_REFUSED"
    }
    if negatives != {"missing_parameter", "unknown_extra", "wrong_shape", "remap_collision"}:
        raise ValueError("constructor proof actual negative controls incomplete")
    pre = {
        row.get("case")
        for row in events
        if row["event"] in {"PRECONSTRUCTOR_CONTROL_REFUSED", "AUTHENTICITY_CONTROL_REFUSED"}
    }
    if pre != {
        "missing_asset",
        "tampered_asset",
        "wrong_source",
        "wrong_asset",
        "wrong_config",
        "legacy_shape",
        "legacy_dtype",
        "legacy_nonfinite",
    }:
        raise ValueError("constructor proof preconstructor controls incomplete")
    if any(row["event"] == "FORWARD_COMPLETE" for row in events):
        raise ValueError("constructor proof contains inference")


def consume_constructor_proof(cfg):
    if cfg["qualified_freeze"] != QUALIFIED_FREEZE:
        raise ValueError("qualified source revision changed")
    verify_file(cfg["production_code"]["path"], cfg["production_code"]["sha256"])
    graph = load_bound_json(cfg["graph_config"])
    policy = load_bound_json(cfg["canonical_policy"])
    validation = load_bound_json(cfg["CPU_validation_config"])
    if (
        validation["graph_config_sha256"] != cfg["graph_config"]["sha256"]
        or validation["canonical_policy_sha256"] != cfg["canonical_policy"]["sha256"]
    ):
        raise ValueError("qualified CPU graph/policy binding changed")
    validate_contract(graph)
    if (
        policy["source_sha256"] != graph["sources"]["lightglue"]["sha256"]
        or policy["checkpoint_sha256"] != graph["weights"]["superpoint_lightglue.pth"]["sha256"]
    ):
        raise ValueError("canonical source/asset binding changed")
    proof = cfg["proof"]
    result = load_bound_json(proof["result"])
    parent = load_bound_json(proof["parent_status"])
    attempt = load_bound_json(proof["attempt"])
    if (
        attempt["freeze"] != QUALIFIED_FREEZE
        or attempt["configuration_sha256"] != cfg["CPU_validation_config"]["sha256"]
    ):
        raise ValueError("constructor proof attempt/config binding changed")
    verify_file(proof["partial"]["path"], proof["partial"]["sha256"])
    events = [json.loads(line) for line in Path(proof["partial"]["path"]).read_text().splitlines()]
    validate_proof_semantics(result, parent, events, cfg["qualified_freeze"])
    return graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != args.freeze or subprocess.check_output(["git", "status", "--porcelain"], text=True):
        raise ValueError("exact clean freeze required")
    if cfg["status"] != "FROZEN_NATIVE_FIXED_GRAPH_CONTINUATION_V2":
        raise ValueError("continuation must be frozen")
    folder = args.out.parent
    if args.worker:
        started = time.monotonic()
        sys.addaudithook(reject_python_network)

        def emit(event):
            with (folder / "partial.jsonl").open("a") as stream:
                stream.write(json.dumps(event) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

        try:
            graph = consume_constructor_proof(cfg)
            emit(
                dict(
                    event="QUALIFIED_CPU_CONSTRUCTOR_PROOF_CONSUMED",
                    qualified_freeze=QUALIFIED_FREEZE,
                    result_sha256=cfg["proof"]["result"]["sha256"],
                    extra_CPU_constructor_calls=0,
                )
            )
            stats = run_graph(graph, folder, emit)
            write_json(
                args.out,
                dict(
                    status="PASS_NATIVE_FIXED_GRAPH_ONLY",
                    freeze=head,
                    stats=stats,
                    wall_s=time.monotonic() - started,
                    qualified_CPU_freeze=QUALIFIED_FREEZE,
                    adaptive_RAVEL="NOT_QUALIFIED_NONDEFAULT_FIXED_MODE",
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
            status="PREFLIGHT_STARTED",
            freeze=head,
            configuration_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        ),
    )
    try:
        graph = consume_constructor_proof(cfg)
    except BaseException as exc:
        outcome = dict(
            status="FAIL",
            freeze=head,
            exit_code=None,
            timeout=False,
            reaped=False,
            worker_started=False,
            exception_type=type(exc).__name__,
            reason=str(exc)[:500],
        )
        write_json(folder / "parent_status.json", outcome)
        print(json.dumps(outcome))
        raise SystemExit(1) from None
    write_json(
        folder / "attempt.json",
        dict(
            status="STARTED",
            freeze=head,
            configuration_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
            caps=graph["caps"],
            qualified_constructor_freeze=QUALIFIED_FREEZE,
        ),
    )
    with (folder / "worker.log").open("x") as log:
        outcome = supervise_worker(
            [sys.executable, __file__, "--worker", "--freeze", head, "--out", str(args.out)],
            log,
            graph["caps"]["whole_worker_s"],
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
        <= graph["caps"]["raw_output_acceptance_bytes"]
    )
    outcome.update(status="PASS" if accept_worker_outcome(outcome, valid) else "FAIL", freeze=head)
    write_json(folder / "parent_status.json", outcome)
    print(json.dumps(outcome))
    raise SystemExit(0 if outcome["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
