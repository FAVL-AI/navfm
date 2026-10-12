import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from development_qualification_contracts_v1 import sha
from offline_evaluation_contracts_v1 import summarize
from prospective_data_contracts_v1 import preserve_raw_draw
from prospective_vint_score_v1 import worker_namespace
from vint_scoring_contracts_v1 import verify_continuation, vint_output_metrics


def test_viNT_raw_heading_and_xy_metric_no_second_cumsum():
    raw = [[[1, 0, 1, 0] for _ in range(5)]]
    report = {"rows": [{}]}
    measured = preserve_raw_draw(report, vint_output_metrics)(
        raw, [[2]], [[0, 0] for _ in range(5)], 2, True, 0.05, 5
    )
    assert measured["ADE_m"] == pytest.approx(0.05) and measured["FDE_m"] == pytest.approx(0.05)
    assert report["rows"][-1]["raw_prediction"]["actions"] == raw
    raw[0][0][2:] = [0, 0]
    invalid = preserve_raw_draw(report, vint_output_metrics)(
        raw, [[2]], [[0, 0] for _ in range(5)], 2, True, 0.05, 5
    )
    assert invalid["valid"] is False and invalid["ADE_m"] is None
    assert report["rows"][-1]["raw_prediction"]["actions"] == raw


def test_vint_fixed_population_missing_pair_null():
    cfg = {
        "model": "vint",
        "checkpoints": {"vint": [{"role": "release", "seed": None}]},
        "pairs": {
            "development": [
                {"trajectory": "a", "negative": False},
                {"trajectory": "b", "negative": False},
            ]
        },
        "evaluation": {"draws": {"vint": 1}},
    }
    rows = [
        {
            "role": cfg["checkpoints"]["vint"][0],
            "pair_index": 0,
            "pair": cfg["pairs"]["development"][0],
            "draw": 0,
            "returned": True,
            "metrics": {
                "valid": True,
                "action_valid": True,
                "ADE_m": 1,
                "FDE_m": 1,
                "distance_MAE_steps": 0,
            },
            "inference_ms": 1,
            "preprocessing_ms": 1,
        }
    ]
    result = summarize(rows, cfg)
    assert sum(r["expected_draws"] for r in result) == 2
    missing = next(r for r in result if r["trajectory"] == "b")
    assert missing["missing_draws"] == 1 and missing["ADE_m"]["mean"] is None


def test_qualified_binding_tamper_and_role_drift(tmp_path, monkeypatch):
    import vint_scoring_contracts_v1 as contracts

    monkeypatch.setattr(contracts, "verify_prior_scores", lambda *a: None)
    monkeypatch.setattr(contracts, "verify_bound_dataset", lambda *a: {"status": "PASS"})
    roles = [
        {"role": "release" if s is None else "prior-selected-epoch20", "seed": s}
        for s in [None, 0, 11, 22]
    ]
    report = {"status": "PASS", "roles": [{"role": r, "status": "PASS"} for r in roles]}
    root = tmp_path / "q"
    root.mkdir()
    (root / "report.json").write_text(json.dumps(report))
    ledger = {
        "freeze": contracts.QUALIFICATION_FREEZE,
        "status": "PASS",
        "child_exit_code": 0,
        "timeout": False,
        "child_reaped": True,
        "artifacts": {"report.json": sha(root / "report.json")},
    }
    (root / "ledger.json").write_text(json.dumps(ledger))
    (root / "qualification_complete.json").write_text(
        json.dumps({"ledger_sha256": sha(root / "ledger.json")})
    )
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            [
                {
                    "status": "PASS",
                    "ledger_sha256": sha(root / "ledger.json"),
                    "marker_sha256": sha(root / "qualification_complete.json"),
                }
            ]
        )
    )
    prior = tmp_path / "pilot.json"
    prior.write_text(json.dumps([{"model": "gnm"}, {"model": "nomad"}]))
    cfg = {
        "evaluation": {"draws": {"gnm": 1, "nomad": 4, "vint": 1}},
        "checkpoints": {"vint": roles},
        "vint_qualification": {
            "out": str(root),
            "registry": str(registry),
            "identity": {
                n: sha(registry if n == "registry" else root / n)
                for n in ["ledger.json", "qualification_complete.json", "registry"]
            },
        },
        "completed_pilot_registry": str(prior),
    }
    assert verify_continuation(cfg)["status"] == "PASS"
    (root / "report.json").write_text("{}")
    with pytest.raises(ValueError):
        verify_continuation(cfg)
    (root / "report.json").write_text(json.dumps(report))
    cfg["evaluation"]["draws"]["vint"] = 4
    with pytest.raises(ValueError):
        verify_continuation(cfg)


def test_reused_worker_qualified_forward_binding():
    ns = worker_namespace()
    assert ns["run"].__globals__["predict_isolated"] is ns["predict_isolated"]
    assert ns["run"].__globals__["SimpleNamespace"] is ns["SimpleNamespace"]


def test_transformed_native_load_trust_release_only():
    import ast

    ns = worker_namespace()
    tree = ast.parse(ns["integration_source"])
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "load_checkpoint"
    ]
    assert len(calls) == 1
    expression = next(k.value for k in calls[0].keywords if k.arg == "trust_checkpoint")
    code = compile(ast.Expression(expression), "<transformed-trust-binding>", "eval")
    roles = [{"role": "release", "seed": None}] + [
        {"role": "prior-selected-epoch20", "seed": s} for s in [0, 11, 22]
    ]
    assert [eval(code, {}, {"role": role}) for role in roles] == [True, False, False, False]
