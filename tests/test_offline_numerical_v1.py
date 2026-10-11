"""Pure offline diagnostic contracts; no model/runtime invoked."""

import ast
import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from offline_numerical_v1 import comparison, discrete, restore, schedule
from replay_recovery_contracts import COUNTERS, snapshot

from navfm.collection.topomap import BoundedConfig, RecoveringTopomapState, TopomapConfig


def fake_policy():
    p = SimpleNamespace(
        state=RecoveringTopomapState(goal_node=6, bounded=BoundedConfig()),
        recovery=True,
        confirm=None,
        topomap_cfg=TopomapConfig(),
        device="cuda",
        digest="x",
        manifest={},
        chain=[0] * 7,
    )
    for k in COUNTERS:
        setattr(p, k, None if k == "abstained" else 0)
    return p


def test_schedule_finite_and_unique():
    s = schedule()
    assert len(s) == 42
    assert len({tuple(x.items()) for x in s}) == 42
    assert sum(x["mode"] == "isolated" for x in s) == 28
    assert [x["step"] for x in s if x["mode"] == "sequence" and x["arm"] == "reference"] == list(
        range(7)
    )


def test_restore_all_fields_and_no_alias():
    p = fake_policy()
    value = snapshot(p)
    value["state"].update(
        closest_node=2,
        lost=True,
        _far=2,
        _pending=[1, 2],
        attempts=3,
        _scan=4,
        history=[dict(distance=1.25)],
    )
    value["search_window"] = [0, 6]
    value["counters"].update(
        stop_count=2, stopped=True, abstained="test", verified_count=3, chain_reached_decisions=4
    )
    restore(p, value)
    assert snapshot(p) == value
    p.state.history[0]["distance"] = 2
    assert value["state"]["history"][0]["distance"] == 1.25


@pytest.mark.parametrize("change", ["unknown", "config", "window", "counter"])
def test_restore_rejects_unsupported(change):
    p = fake_policy()
    v = snapshot(p)
    if change == "unknown":
        v["state"]["new"] = 0
    if change == "config":
        v["state"]["bounded"]["lost_enter"] = 99
    if change == "window":
        v["search_window"] = [0, 1]
    if change == "counter":
        v["counters"]["new"] = 0
    with pytest.raises(ValueError):
        restore(p, v)


def sample():
    return dict(
        entry=[dict(sha256="a")],
        before={"x": 1.0},
        rng_before="r",
        raw=[[1.0]],
        raw_hashes=["hash"],
        prediction=dict(command=[0.1, 0.0, 0.2], node=1, distance=1.0),
        after=dict(node=1, distance=1.0),
    )


def test_numerical_failure_can_coexist_with_discrete_match():
    a = sample()
    b = copy.deepcopy(a)
    b["prediction"]["distance"] = 1.1
    result = comparison(a, b, dict(atol=0.001, rtol=0.00001))
    assert not result["numerical"] and result["discrete"] and result["command"]


def test_discrete_node_change_not_removed():
    assert discrete({"node": 1, "distance": 1.0}) != discrete({"node": 2, "distance": 1.1})


def test_tensor_identity_independent_of_output_agreement():
    a = sample()
    b = copy.deepcopy(a)
    b["entry"][0]["sha256"] = "b"
    result = comparison(a, b, dict(atol=0.001, rtol=0.00001))
    assert not result["tensors_identical"] and result["numerical"]


def test_no_simulator_imports():
    for file in ["offline_numerical_v1.py", "run_offline_numerical_v1.py"]:
        tree = ast.parse((Path(__file__).resolve().parents[1] / "scripts" / file).read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + [
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
        ]
        assert not any(
            s and s.split(".")[0] in ["isaacsim", "omni", "carb", "pxr"] for s in imports
        )


def worker():
    from offline_numerical_v1 import schedule

    return dict(status="PASS", settings={}, calls=[dict(sample(), **cell) for cell in schedule()])


def test_analysis_rejects_same_input_tensor_mismatch():
    from offline_numerical_v1 import analyse

    a, b = worker(), worker()
    b["calls"][0]["entry"][0]["sha256"] = "bad"
    with pytest.raises(ValueError, match="integrity"):
        analyse([a, b], dict(atol=0.001, rtol=0.00001))


def test_analysis_rejects_order_and_settings():
    from offline_numerical_v1 import analyse

    a, b = worker(), worker()
    b["calls"][0], b["calls"][1] = b["calls"][1], b["calls"][0]
    with pytest.raises(ValueError, match="order"):
        analyse([a, b], dict(atol=0.001, rtol=0.00001))
    b = worker()
    b["settings"]["precision"] = "changed"
    with pytest.raises(ValueError, match="settings"):
        analyse([a, b], dict(atol=0.001, rtol=0.00001))


def test_analysis_count_and_weaker_criteria():
    from offline_numerical_v1 import analyse

    a, b = worker(), worker()
    b["calls"][0]["raw"] = [[1.1]]
    result = analyse([a, b], dict(atol=0.001, rtol=0.00001))
    assert result["calls"] == 84 and len(result["comparisons"]) == 112
    assert not result["same_input_numerical_stable"]
    assert all(x["discrete"] for x in result["comparisons"])
