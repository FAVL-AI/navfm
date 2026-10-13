import copy
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from offline_evaluation_contracts_v1 import (
    atomic_snapshot,
    draw_seed,
    latency,
    measure,
    output_metrics,
    pairs_from_metadata,
    retained_attempt,
    summarize,
)


def test_pair_partition_and_full_label_horizon():
    names = ["a", "b", "c", "d"]
    pairs = pairs_from_metadata(names, dict.fromkeys(names, 30), ["train"])
    assert len(pairs) == 24
    assert all(p["current"] + 8 < 30 for p in pairs)
    assert all(p["goal_trajectory"] in names for p in pairs)
    with pytest.raises(ValueError, match="leakage"):
        pairs_from_metadata(names, dict.fromkeys(names, 30), ["d"])


def test_coupled_draw_identity():
    assert [draw_seed(2, d) for d in range(4)] == [20261019, 20261020, 20261021, 20261022]
    with pytest.raises(ValueError):
        draw_seed(2, 4)


def test_physical_units_and_negative_denominator():
    prediction, labels = [[2.0, 0.0]] * 8, [[0.0, 0.0]] * 8
    positive = measure(prediction, labels, 8.0, 6.0, True, 0.05)
    assert positive["ADE_m"] == pytest.approx(0.1)
    assert positive["distance_MAE_steps"] == 2
    negative = measure(prediction, labels, 8.0, 20.0, False, 0.05)
    assert negative["ADE_m"] is None and negative["distance_MAE_steps"] == 12


def fixture_cfg(row, draws=4, extra_pair=False):
    pairs = [row["pair"]]
    if extra_pair:
        pairs.append(dict(row["pair"], current=11))
    return dict(
        model="nomad",
        checkpoints={"nomad": [row["role"]]},
        pairs={"development": pairs},
        evaluation={"draws": {"nomad": draws}},
    )


def test_nonfinite_draw_retained_not_best_sample():
    metric = measure([[0.0, 0.0]] * 8, [[0.0, 0.0]] * 8, 6.0, 6.0, True, 0.05)
    row = dict(
        role=dict(role="selected", seed=0),
        pair=dict(trajectory="a", negative=False),
        pair_index=0,
        draw=0,
        returned=True,
        metrics=metric,
        inference_ms=1.0,
    )
    invalid = copy.deepcopy(row)
    invalid["draw"] = 1
    invalid["metrics"] = measure([[math.nan, 0.0]] * 8, [[0.0, 0.0]] * 8, 6.0, 6.0, True, 0.05)
    result = summarize([row, invalid], fixture_cfg(row, 2))[0]
    assert result["attempted_draws"] == 2 and result["invalid_attempts"] == 1
    assert result["ADE_m"] == dict(mean=None, eligible_pairs=1, complete_pairs=0)


def test_expected_draw_metric_not_oracle_minimum():
    rows = [
        dict(
            role=dict(role="release", seed=None),
            pair=dict(trajectory="a", negative=False),
            pair_index=0,
            draw=0,
            returned=True,
            metrics=dict(valid=True, action_valid=True, ADE_m=v, FDE_m=v, distance_MAE_steps=v),
            inference_ms=1.0,
        )
        for v in (1.0, 3.0)
    ]
    rows[1]["draw"] = 1
    assert summarize(rows, fixture_cfg(rows[0], 2))[0]["ADE_m"]["mean"] == 2


def test_timing_rejects_unsynchronized_invalid_interval():
    assert latency(1.0, 1.002) == pytest.approx(2.0)
    for a, b in [(2.0, 1.0), (math.nan, 1.0)]:
        with pytest.raises(ValueError):
            latency(a, b)


def test_missing_draw_pair_and_duplicate_population():
    row = dict(
        role=dict(role="selected", seed=0),
        pair=dict(trajectory="a", negative=False),
        pair_index=0,
        draw=0,
        returned=True,
        inference_ms=1.0,
        metrics=dict(valid=True, action_valid=True, ADE_m=1.0, FDE_m=1.0, distance_MAE_steps=1.0),
    )
    result = summarize([row], fixture_cfg(row, 4, extra_pair=True))[0]
    assert result["expected_draws"] == 8 and result["missing_draws"] == 7
    assert result["ADE_m"] == dict(mean=None, eligible_pairs=2, complete_pairs=0)
    with pytest.raises(ValueError, match="duplicate"):
        summarize([row, row], fixture_cfg(row))


def test_malformed_action_and_distance_retained_invalid():
    for actions, distances in [
        ([], [1.0]),
        ([[[0.0]] * 8], [1.0]),
        ([[[0.0, 0.0]] * 8], []),
        ([[[0.0, 0.0]] * 8], [1.0, 2.0]),
    ]:
        assert (
            output_metrics(actions, distances, [[0.0, 0.0]] * 8, 6.0, True, 0.05, 8)["valid"]
            is False
        )


def test_exception_mid_pair_preserves_attempts():
    report = {"rows": []}
    snapshots = []

    def persist():
        snapshots.append(copy.deepcopy(report))

    retained_attempt(report, dict(draw=0), lambda: dict(metrics={"valid": True}), persist)

    def fail():
        raise RuntimeError("controlled failure")

    with pytest.raises(RuntimeError):
        retained_attempt(report, dict(draw=1), fail, persist)
    assert len(snapshots[-1]["rows"]) == 2
    assert snapshots[-1]["rows"][0]["returned"] is True
    assert snapshots[-1]["rows"][1]["returned"] is False
    assert snapshots[-1]["rows"][1]["error_type"] == "RuntimeError"


def test_atomic_snapshot_interrupted_replace_preserves_prior(tmp_path, monkeypatch):
    import json

    import offline_evaluation_contracts_v1 as contracts

    target = tmp_path / "report.json"
    atomic_snapshot(target, {"rows": [1]})

    def interrupted(*args):
        raise OSError("controlled pre-replace failure")

    monkeypatch.setattr(contracts.os, "replace", interrupted)
    with pytest.raises(OSError):
        atomic_snapshot(target, {"rows": [1, 2]})
    assert json.loads(target.read_text()) == {"rows": [1]}
    assert json.loads(target.with_name("report.json.pending").read_text()) == {"rows": [1, 2]}
