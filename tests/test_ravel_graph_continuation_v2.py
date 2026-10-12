"""Hermetic stale/tampered constructor-proof and unchanged graph-input bindings."""

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qualify_ravel_graph_continuation_v2 import (
    QUALIFIED_FREEZE,
    load_bound_json,
    validate_proof_semantics,
)


def proof_fixture():
    result = dict(
        status="PASS_CPU_CANONICAL_CONSTRUCTOR_PARITY_ONLY",
        freeze=QUALIFIED_FREEZE,
        GPU_calls=0,
        forwards=0,
        counts=dict(
            CONSTRUCTOR_ATTEMPT=6,
            FORWARD_COMPLETE=0,
            MODEL_CONSTRUCTED=1,
            ACTUAL_NATIVE_CONTROL_REFUSED=4,
        ),
        bitwise_parity=dict(parameters=251, buffers=1),
    )
    parent = dict(status="PASS", freeze=QUALIFIED_FREEZE, exit_code=0, timeout=False, reaped=True)
    events = [
        dict(
            event="BITWISE_STATE_PARITY",
            parameters=251,
            buffers=1,
            mismatches=0,
            forwards=0,
            dtype_shape_and_tensor_bytes_equal=True,
        )
    ]
    events += [
        dict(event="ACTUAL_NATIVE_CONTROL_REFUSED", case=case)
        for case in ("missing_parameter", "unknown_extra", "wrong_shape", "remap_collision")
    ]
    events += [
        dict(event="PRECONSTRUCTOR_CONTROL_REFUSED", case=case)
        for case in (
            "missing_asset",
            "tampered_asset",
            "wrong_source",
            "wrong_asset",
            "wrong_config",
            "legacy_shape",
            "legacy_dtype",
            "legacy_nonfinite",
        )
    ]
    return result, parent, events


@pytest.mark.parametrize(
    "case", ["stale_freeze", "timeout", "unreaped", "missing_negative", "missing_parity"]
)
def test_constructor_proof_semantics_refuse_stale_or_incomplete_evidence(case):
    result, parent, events = proof_fixture()
    validate_proof_semantics(result, parent, events, QUALIFIED_FREEZE)
    if case == "stale_freeze":
        result["freeze"] = "0" * 40
    elif case == "timeout":
        parent["timeout"] = True
    elif case == "unreaped":
        parent["reaped"] = False
    elif case == "missing_negative":
        events = [r for r in events if r.get("case") != "missing_parameter"]
    else:
        events = [r for r in events if r["event"] != "BITWISE_STATE_PARITY"]
    with pytest.raises(ValueError):
        validate_proof_semantics(result, parent, events, QUALIFIED_FREEZE)


def test_modified_CPU_proof_bytes_are_rejected_before_semantic_admission(tmp_path):
    result, _, _ = proof_fixture()
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result))
    bound = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert load_bound_json(bound) == result
    result["forwards"] = 1
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="digest mismatch"):
        load_bound_json(bound)


@pytest.mark.parametrize("field", ["references", "native_mode", "caps"])
def test_changed_graph_inputs_parameters_or_budget_break_qualified_binding(tmp_path, field):
    source = Path(__file__).resolve().parents[1] / "configs/eval/ravel_fixed_graph_v1.json"
    cfg = json.loads(source.read_text())
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(cfg))
    bound = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    changed = copy.deepcopy(cfg)
    if field == "references":
        changed[field][0]["sha256"] = "0" * 64
    elif field == "native_mode":
        changed[field]["radius"] = 4.0
    else:
        changed[field]["pairs"] = 29
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="digest mismatch"):
        load_bound_json(bound)
