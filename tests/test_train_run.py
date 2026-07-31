"""Tests for :mod:`navfm.train.run`.

The training *objective* is not tested here, because it is not implemented
here: the driver calls ``train_utils._compute_losses`` directly, and that
function's semantics are pinned in ``tests/test_upstream_losses.py``. What is
worth testing is everything around it that could silently corrupt a run:

* the accumulation arithmetic (a loss not divided by the window scales the
  effective learning rate by the accumulation factor);
* the BatchNorm freeze surviving ``model.train()`` at the top of each epoch;
* replay batch composition, including the rounding edges;
* trajectory-level (not sample-level) subsetting for the G3.c overfit gate;
* checkpoint round-trip, since a resume that loses optimizer state is a
  different experiment wearing the same run name.
"""

from __future__ import annotations

import numpy as np
import pytest

from navfm.train.finetune import FinetuneConfig
from navfm.train.run import overfit_subset, replay_batch_sizes

torch = pytest.importorskip("torch")
pytestmark = pytest.mark.torch


# ------------------------------------------------------------------ replay mix


@pytest.mark.parametrize(
    ("micro", "ratio", "expect"),
    [
        (64, 0.0, (64, 0)),
        (64, 0.25, (48, 16)),
        (64, 0.5, (32, 32)),
        (256, 0.25, (192, 64)),
        (4, 0.25, (3, 1)),
        (4, 1.0, (0, 4)),
    ],
)
def test_replay_batch_sizes(micro, ratio, expect):
    assert replay_batch_sizes(micro, ratio) == expect


def test_a_configured_replay_ratio_never_rounds_away_to_zero():
    """0.1 replay at micro-batch 4 rounds to 0 samples. A run that reports
    'replay: 10%' while doing no replay at all is the E3 arm silently becoming
    its own control."""
    target, replay = replay_batch_sizes(4, 0.1)
    assert replay == 1
    assert target == 3


def test_a_configured_replay_ratio_never_starves_the_target():
    target, replay = replay_batch_sizes(8, 0.99)
    assert target == 1 and replay == 7


@pytest.mark.parametrize("ratio", [-0.1, 1.5])
def test_replay_ratio_out_of_range_is_rejected(ratio):
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        replay_batch_sizes(64, ratio)


# ------------------------------------------------------------------- overfit-n


class _FakeDataset(torch.utils.data.Dataset):
    """Stands in for ViNT_Dataset: what matters is ``index_to_data``."""

    def __init__(self, trajectories, per_traj):
        self.index_to_data = [
            (f"traj{t}", i, i + 1) for t in range(trajectories) for i in range(per_traj)
        ]

    def __len__(self):
        return len(self.index_to_data)

    def __getitem__(self, i):
        return self.index_to_data[i]


def test_overfit_subset_selects_whole_trajectories():
    ds = _FakeDataset(trajectories=5, per_traj=10)
    sub = overfit_subset(ds, 2)
    assert len(sub) == 20
    names = {ds.index_to_data[i][0] for i in sub.indices}
    assert names == {"traj0", "traj1"}, "must keep whole trajectories, not a sample sample"


def test_overfit_subset_asking_for_more_than_exists_keeps_everything():
    ds = _FakeDataset(trajectories=3, per_traj=4)
    assert len(overfit_subset(ds, 10)) == 12


def test_overfit_subset_rejects_a_dataset_without_the_index():
    with pytest.raises(TypeError, match="index_to_data"):
        overfit_subset(object(), 3)


# ------------------------------------------------------------ the training loop


class _TinyModel(torch.nn.Module):
    """Emits ViNT-shaped outputs from a trivially differentiable path, and
    carries a BatchNorm so the freeze can be observed."""

    def __init__(self, horizon=5, params=4):
        super().__init__()
        self.horizon, self.params = horizon, params
        self.bn = torch.nn.BatchNorm2d(3)
        self.head = torch.nn.Linear(3, horizon * params)
        self.dist = torch.nn.Linear(3, 1)

    def forward(self, obs, goal):
        x = self.bn(obs[:, :3])
        x = x.mean(dim=(2, 3))
        return self.dist(x), self.head(x).reshape(-1, self.horizon, self.params)


def _fake_batch(batch=4, horizon=5, size=8):
    return (
        torch.randn(batch, 18, size, size),
        torch.randn(batch, 3, size, size),
        torch.randn(batch, horizon, 4),
        torch.randint(0, 20, (batch,)),
        torch.randn(batch, 2),
        torch.zeros(batch, dtype=torch.long),
        torch.ones(batch),
    )


def _run_and_delta(batches, *, micro, effective):
    """Train one epoch from a fixed init and return the parameter delta."""
    from navfm.train.run import train_one_epoch

    torch.manual_seed(0)
    model = _TinyModel()
    before = [p.detach().clone() for p in model.parameters()]
    cfg = FinetuneConfig(
        micro_batch_size=micro, effective_batch_size=effective, freeze_bn=True, amp_dtype="none"
    )
    opt = torch.optim.SGD(model.parameters(), lr=1.0)
    train_one_epoch(
        model, opt, batches, cfg=cfg, device="cpu", alpha=0.5, learn_angle=True, progress=False
    )
    return [a - b for a, b in zip(before, model.parameters(), strict=True)]


@pytest.mark.upstream
def test_accumulation_matches_one_full_batch():
    """Two micro-batches of 4 at accumulation 2 must move the parameters exactly
    as one batch of 8 does.

    This is the arithmetic that a missing ``/ accum`` breaks: the accumulated
    gradient would be the *sum* rather than the mean, scaling the effective
    learning rate by the accumulation factor -- 4x on the shipped config. The
    equality is exact here because every mask is all-ones, which makes
    ``action_reduce`` linear in the batch (it divides by ``1 + 1e-2`` either
    way); with partial masks the two are close but not identical, which is
    itself a property of the reference reduction rather than of this loop.
    BatchNorm is frozen so it cannot make the two batch sizes differ.
    """
    pytest.importorskip("vint_train.training.train_utils")

    torch.manual_seed(99)
    a, b = _fake_batch(batch=4), _fake_batch(batch=4)
    joint = tuple(torch.cat([x, y], dim=0) for x, y in zip(a, b, strict=True))

    split = _run_and_delta([a, b], micro=4, effective=8)
    whole = _run_and_delta([joint], micro=8, effective=8)

    assert any(d.abs().sum() > 0 for d in whole), "the control must actually move"
    for d_split, d_whole in zip(split, whole, strict=True):
        torch.testing.assert_close(d_split, d_whole, atol=1e-6, rtol=1e-5)


@pytest.mark.upstream
def test_accumulation_is_not_a_sum():
    """The negative control for the test above: summing instead of averaging
    would double the step at accumulation 2, so the delta must not match a
    double-length single batch run at twice the rate."""
    pytest.importorskip("vint_train.training.train_utils")

    torch.manual_seed(99)
    a, b = _fake_batch(batch=4), _fake_batch(batch=4)
    joint = tuple(torch.cat([x, y], dim=0) for x, y in zip(a, b, strict=True))

    split = _run_and_delta([a, b], micro=4, effective=8)
    whole = _run_and_delta([joint], micro=8, effective=8)
    doubled = [2 * d for d in whole]

    assert not all(
        torch.allclose(s, d, atol=1e-6, rtol=1e-5) for s, d in zip(split, doubled, strict=True)
    )


@pytest.mark.upstream
def test_batchnorm_stays_frozen_across_epochs():
    """model.train() at the top of every epoch would put BN back into training
    mode. The freeze has to be re-applied inside the epoch, not once at setup --
    otherwise epoch 2 onwards drifts the pretrained statistics, which is exactly
    the failure docs/WORKFLOW.md 3.2 tells you to watch for."""
    pytest.importorskip("vint_train.training.train_utils")
    from navfm.train.run import train_one_epoch

    torch.manual_seed(0)
    model = _TinyModel()
    cfg = FinetuneConfig(
        micro_batch_size=4, effective_batch_size=4, freeze_bn=True, amp_dtype="none"
    )
    opt = torch.optim.SGD(model.parameters(), lr=1e-3)

    before = model.bn.running_mean.clone()
    for epoch in range(3):
        model.train()  # what the caller does at the top of an epoch
        train_one_epoch(
            model,
            opt,
            [_fake_batch()],
            cfg=cfg,
            device="cpu",
            alpha=0.5,
            learn_angle=True,
            progress=False,
            epoch=epoch,
        )
    torch.testing.assert_close(model.bn.running_mean, before)
    assert not model.bn.weight.requires_grad


@pytest.mark.upstream
def test_partial_accumulation_window_is_dropped_not_applied():
    """Three micro-batches at accumulation 2 leaves one orphan. Stepping on it
    would apply a gradient computed at half the effective batch size."""
    pytest.importorskip("vint_train.training.train_utils")
    from navfm.train.run import train_one_epoch

    torch.manual_seed(0)
    cfg = FinetuneConfig(
        micro_batch_size=4, effective_batch_size=8, freeze_bn=False, amp_dtype="none"
    )
    model = _TinyModel()
    opt = torch.optim.SGD(model.parameters(), lr=1e-2)
    out = train_one_epoch(
        model,
        opt,
        [_fake_batch() for _ in range(3)],
        cfg=cfg,
        device="cpu",
        alpha=0.5,
        learn_angle=True,
        progress=False,
    )
    assert out["micro_batches"] == 3
    assert out["optimizer_steps"] == 1
    assert out["dropped_partial_window"] == 1


@pytest.mark.upstream
def test_replay_batches_are_merged_into_the_micro_batch():
    pytest.importorskip("vint_train.training.train_utils")
    from navfm.train.run import _cycle, train_one_epoch

    torch.manual_seed(0)
    cfg = FinetuneConfig(
        micro_batch_size=6, effective_batch_size=6, freeze_bn=False, amp_dtype="none"
    )
    seen: list[int] = []

    class _Spy(_TinyModel):
        def forward(self, obs, goal):
            seen.append(obs.shape[0])
            return super().forward(obs, goal)

    model = _Spy()
    opt = torch.optim.SGD(model.parameters(), lr=0.0)
    train_one_epoch(
        model,
        opt,
        [_fake_batch(batch=4)],
        cfg=cfg,
        device="cpu",
        alpha=0.5,
        learn_angle=True,
        progress=False,
        replay_iter=_cycle([_fake_batch(batch=2)]),
    )
    assert seen == [6], "the model must see target+replay as one batch"


# ------------------------------------------------------------------ checkpoints


def test_checkpoint_round_trip_restores_optimizer_and_rng(tmp_path):
    from navfm.train.run import load_checkpoint_for_resume
    from navfm.train.run import save_resume_state as save_checkpoint

    torch.manual_seed(0)
    cfg = FinetuneConfig(micro_batch_size=4, effective_batch_size=4)
    model = _TinyModel()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=10)

    # Take a real step so the optimizer has non-trivial state to lose.
    model(torch.randn(4, 18, 8, 8), torch.randn(4, 3, 8, 8))[1].sum().backward()
    opt.step()
    sched.step()
    save_checkpoint(
        tmp_path / "latest.pth", model=model, optimizer=opt, scheduler=sched, epoch=3, cfg=cfg
    )

    model2, opt2 = _TinyModel(), None
    opt2 = torch.optim.AdamW(model2.parameters(), lr=1e-3)
    sched2 = torch.optim.lr_scheduler.CosineAnnealingLR(opt2, T_max=10)
    next_epoch = load_checkpoint_for_resume(
        tmp_path / "latest.pth", model=model2, optimizer=opt2, scheduler=sched2
    )

    assert next_epoch == 4, "resume continues after the saved epoch, not on it"
    torch.testing.assert_close(model2.head.weight, model.head.weight)
    assert opt2.state_dict()["state"], "optimizer moments must survive the round trip"
    assert sched2.last_epoch == sched.last_epoch


def test_resume_refuses_a_changed_epoch_count(tmp_path):
    """A scheduler's state_dict round-trips T_max, so rebuilding it with a new
    epoch count and then restoring silently reinstates the old schedule -- which
    for a completed cosine means the extra epochs train at lr 0 and the run
    looks finished rather than broken. Observed on the M1 smoke run."""
    from navfm.train.run import load_checkpoint_for_resume, save_resume_state

    cfg = FinetuneConfig(micro_batch_size=4, effective_batch_size=4, epochs=2)
    model = _TinyModel()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=2)
    save_resume_state(
        tmp_path / "l.pth", model=model, optimizer=opt, scheduler=sched, epoch=1, cfg=cfg
    )

    with pytest.raises(SystemExit, match="annealed to zero"):
        load_checkpoint_for_resume(
            tmp_path / "l.pth", model=model, optimizer=opt, scheduler=sched, epochs=20
        )
    # The same epoch count is the normal crash-recovery path and must work.
    assert (
        load_checkpoint_for_resume(
            tmp_path / "l.pth", model=model, optimizer=opt, scheduler=sched, epochs=2
        )
        == 2
    )


def test_epoch_checkpoints_load_without_trusting_anything(tmp_path):
    """Finding F5 in reverse. The reference saves *live* ViNT and optimizer
    objects, so loading a released checkpoint executes arbitrary code and fails
    under torch >= 2.6's weights_only default. Our epoch_N.pth is a bare
    state_dict, so `navfm.eval.offline --checkpoint runs/<run>/epoch_N.pth`
    works with no --trust-checkpoint. If this ever regresses, the fine-tuned
    arms of the matrix become as awkward to consume as the released ones."""
    from navfm.train.run import save_weights

    model = _TinyModel()
    save_weights(tmp_path / "epoch_0.pth", model)

    state = torch.load(tmp_path / "epoch_0.pth", weights_only=True)
    assert all(isinstance(v, torch.Tensor) for v in state.values())

    from navfm.models.loader import extract_state_dict

    assert set(extract_state_dict(state)) == set(model.state_dict())


def test_resume_state_carries_no_custom_classes(tmp_path):
    """latest.pth is not weights_only-loadable -- numpy's RNG state is a tuple
    of plain objects, not a tensor -- which is exactly why it is a separate file
    from the weights. It must still contain no third-party classes, so loading
    it executes nothing."""
    from navfm.train.run import save_resume_state

    cfg = FinetuneConfig(micro_batch_size=4, effective_batch_size=4)
    model = _TinyModel()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    save_resume_state(
        tmp_path / "latest.pth", model=model, optimizer=opt, scheduler=None, epoch=0, cfg=cfg
    )

    state = torch.load(tmp_path / "latest.pth", weights_only=False)
    assert all(isinstance(v, torch.Tensor) for v in state["model"].values())
    assert isinstance(state["config"], dict)
    assert isinstance(state["rng"]["numpy"], tuple | np.ndarray | list)
    assert not isinstance(state["optimizer"], torch.optim.Optimizer), (
        "must be a state_dict, not an object"
    )
