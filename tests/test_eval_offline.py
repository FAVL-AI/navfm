"""Tests for :mod:`navfm.eval.offline`.

The metric *definitions* are settled against the reference implementation in
``tests/test_upstream_losses.py``. What is left to test here is the plumbing
around them, and the plumbing is where the batch-size dependence lives, so it
gets its own tests with no torch and no reference package involved:

* per-batch, unweighted averaging (upstream ``Logger`` semantics);
* NaN batches dropped and counted, not propagated;
* the metres conversion using ``metric_waypoint_spacing * waypoint_spacing``;
* the run-name -> (cell, seed) parse that binds a run to a table row.

The end-to-end model+dataset path is exercised for real in the M1 gate evidence
(``gates/M1/``) rather than mocked here.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from navfm.eval import metrics as M
from navfm.eval.offline import MetricAccumulator, cell_and_seed, write_run_record


def _batch(rng, batch=8, horizon=5, mask_p=1.0):
    pred = rng.normal(size=(batch, horizon, 4))
    label = rng.normal(size=(batch, horizon, 4))
    dist_pred = rng.normal(size=(batch, 1))
    dist_label = rng.integers(0, 20, size=(batch,))
    mask = (rng.random(batch) < mask_p).astype(np.float64)
    return dict(
        dist_pred=dist_pred,
        dist_label=dist_label,
        action_pred=pred,
        action_label=label,
        action_mask=mask,
    )


# ------------------------------------------------------------------ aggregation


def test_single_batch_reproduces_reference_losses_exactly():
    rng = np.random.default_rng(0)
    b = _batch(rng)
    acc = MetricAccumulator()
    acc.update(**b)
    out = acc.result()

    expect = M.reference_losses(**b, alpha=0.5, learn_angle=True, strict=True)
    for key, value in expect.items():
        assert out["strict"][key] == pytest.approx(value, rel=1e-12)
    assert out["n_batches"] == 1
    assert out["n_samples"] == 8


def test_averaging_is_unweighted_over_batches_not_over_samples():
    """The trailing short batch counts as much as a full one, because upstream's
    Logger appends one value per batch and takes a plain mean. Getting this
    'right' instead would silently make our numbers incomparable to theirs."""
    rng = np.random.default_rng(1)
    big = _batch(rng, batch=100)
    small = _batch(rng, batch=2)

    acc = MetricAccumulator()
    acc.update(**big)
    acc.update(**small)
    got = acc.result()["strict"]["action_loss"]

    per_batch = [
        M.reference_losses(**b, strict=True)["action_loss"] for b in (big, small)
    ]
    assert got == pytest.approx(float(np.mean(per_batch)), rel=1e-12)

    sample_weighted = (100 * per_batch[0] + 2 * per_batch[1]) / 102
    assert got != pytest.approx(sample_weighted, rel=1e-6), "must not be sample-weighted"


def test_batch_size_changes_the_metric():
    """Upstream issue #51 in miniature: the same predictions scored as one batch
    of 64 and as sixteen batches of 4 give different numbers, because
    action_reduce's mask.mean() is computed within each batch."""
    rng = np.random.default_rng(2)
    b = _batch(rng, batch=64, mask_p=0.8)

    one = MetricAccumulator()
    one.update(**b)

    many = MetricAccumulator()
    for i in range(0, 64, 4):
        many.update(**{k: v[i : i + 4] for k, v in b.items()})

    assert one.result()["strict"]["action_loss"] != pytest.approx(
        many.result()["strict"]["action_loss"], rel=1e-6
    )


def test_nan_batches_are_dropped_and_counted():
    """A fully-masked-out batch makes the plain reduction NaN. Upstream's
    log_data skips NaN; we skip it too but record the count, so a run resting on
    half its batches cannot be mistaken for one that used all of them."""
    rng = np.random.default_rng(3)
    good = _batch(rng, mask_p=1.0)
    dead = _batch(rng)
    dead["action_mask"] = np.zeros_like(dead["action_mask"])

    acc = MetricAccumulator()
    acc.update(**good)
    acc.update(**dead)
    out = acc.result()

    assert np.isfinite(out["plain"]["action_loss"])
    assert out["n_batches"] == 2
    assert out["dropped_nan_batches"]["plain/action_loss"] == 1
    # The strict reduction has the +1e-2 guard, so it survives a zero mask.
    assert "strict/action_loss" not in out.get("dropped_nan_batches", {})


def test_metres_conversion_uses_spacing_times_waypoint_spacing():
    rng = np.random.default_rng(4)
    b = _batch(rng)
    acc = MetricAccumulator(metres_per_unit=0.12 * 3)
    acc.update(**b)
    out = acc.result()
    assert out["ade_m"] == pytest.approx(out["ade_normalized"] * 0.36, rel=1e-12)
    assert out["fde_m"] == pytest.approx(out["fde_normalized"] * 0.36, rel=1e-12)


def test_learn_angle_false_omits_orientation_columns():
    rng = np.random.default_rng(5)
    b = _batch(rng)
    b["action_pred"] = b["action_pred"][..., :2]
    b["action_label"] = b["action_label"][..., :2]
    acc = MetricAccumulator(learn_angle=False)
    acc.update(**b)
    assert "action_orien_cos_sim" not in acc.result()["strict"]


# ------------------------------------------------------------------ bookkeeping


@pytest.mark.parametrize(
    ("name", "cell", "seed"),
    [
        ("e2_nonholo_diff_seed0", "e2_nonholo_diff", 0),
        ("e2_holo_holo_seed12", "e2_holo_holo", 12),
        ("e3_0p25h_pretrained_replay_seed1", "e3_0p25h_pretrained_replay", 1),
        ("e0.2_vint_go_stanford", "e0.2_vint_go_stanford", None),
        ("eval_vint_go_stanford_test_20260731-120000", None, None),
    ],
)
def test_cell_and_seed_parse(name, cell, seed):
    assert cell_and_seed(name) == (cell, seed)


def test_write_run_record_emits_the_three_files(tmp_path):
    write_run_record(tmp_path, metrics={"a": 1.0}, config={"b": 2})
    assert json.loads((tmp_path / "metrics.json").read_text()) == {"a": 1.0}
    assert json.loads((tmp_path / "config.json").read_text()) == {"b": 2}
    sha = (tmp_path / "git_sha.txt").read_text()
    assert "navfm" in sha and "upstream" in sha


def test_empty_dataloader_is_an_error_with_the_likely_cause():
    torch = pytest.importorskip("torch")
    from navfm.eval.offline import evaluate

    class _Model(torch.nn.Module):
        def forward(self, obs, goal):  # pragma: no cover - never called
            raise AssertionError

    with pytest.raises(RuntimeError, match="context_size"):
        evaluate(_Model(), [], progress=False)
