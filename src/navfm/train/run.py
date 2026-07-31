"""Fine-tuning driver for ViNT / GNM on a single 16 GB GPU.

    python -m navfm.train.run --config configs/train/vint_finetune_4080s.yaml

Every optimisation component already lives in :mod:`navfm.train.finetune`; this
is the loop that wires them to the reference model, the reference dataset and
the reference objective. Its whole job is to be boring in the places where
being interesting would invalidate the results.

**The objective is not reimplemented.** ``_step`` calls
``vint_train.training.train_utils._compute_losses`` -- the reference function
itself -- so the weighting ``alpha * 1e-2 * dist + (1 - alpha) * action_reduce(mse)``
and the mask semantics cannot drift from the specification through a plausible
misreading. A wrong objective trains beautifully and is invisible in the loss
curve, so this is the one place worth spending a hard dependency on upstream
internals. ``navfm.eval.metrics.reference_losses`` is a numpy port of the same
function, proven equal to it in ``tests/test_upstream_losses.py``; the trainer
uses the original because it needs gradients.

**Gradient accumulation reaches the published batch, but BatchNorm does not.**
BN statistics are a function of the *micro*-batch, so accumulating 64x4 to an
effective 256 gives the published optimisation and 64-sample BN statistics.
That is exactly the drift ``freeze_bn`` exists to stop, and a rising validation
loss in epoch 1 is its signature (docs/WORKFLOW.md 3.2). The freeze is applied
after every ``model.train()`` call, not once at construction, because
``.train()`` would otherwise put the BN modules straight back into training
mode at the top of epoch 2.

**The scheduler steps once per epoch**, unlike ``train_eval_loop_nomad``, which
steps twice and so completes a ``T_max=epochs`` cosine at ``epochs/2`` before
climbing back (finding F8). The run's ``config.json`` records which schedule it
used.

**Replay mixing is per micro-batch, not per epoch.** ``replay_ratio: 0.25``
composes every micro-batch from 75 % target data and 25 % replay, which is what
"25 % replay" has to mean if it is to guard against catastrophic forgetting
within an epoch rather than between epochs.

Outputs, under ``runs/<run_name>/``: ``epoch_N.pth``, ``latest.pth``,
``config.json``, ``git_sha.txt``, ``metrics_epoch_N.json``. ``--resume``
continues from ``latest.pth``, restoring optimizer, scheduler and RNG state so
a resumed run is the run it would have been.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import random
import sys
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from navfm import upstream
from navfm.eval.offline import REFERENCE_KEYS, cell_and_seed, evaluate, git_describe
from navfm.provenance import environment_identity
from navfm.runid import compare, identity_digest, run_identity
from navfm.train.finetune import (
    FinetuneConfig,
    amp_context,
    apply_freeze,
    build_optimizer,
    build_scheduler,
    freeze_batchnorm,
    set_seed,
)

__all__ = [
    "build_argparser",
    "main",
    "overfit_subset",
    "replay_batch_sizes",
    "save_resume_state",
    "save_weights",
    "train_one_epoch",
]


def replay_batch_sizes(micro_batch: int, replay_ratio: float) -> tuple[int, int]:
    """Split a micro-batch into (target, replay) counts.

    Rounds the replay share to the nearest whole sample and then guarantees at
    least one of each whenever the ratio is strictly between 0 and 1 -- a
    configured 10 % replay at micro-batch 4 must not silently become 0 %, and a
    configured 90 % must not starve the target data entirely.
    """
    if not 0.0 <= replay_ratio <= 1.0:
        raise ValueError(f"replay_ratio must be in [0, 1], got {replay_ratio}")
    if micro_batch < 1:
        raise ValueError(f"micro_batch must be >= 1, got {micro_batch}")
    if replay_ratio == 0.0:
        return micro_batch, 0
    if replay_ratio == 1.0:
        return 0, micro_batch
    n_replay = int(round(micro_batch * replay_ratio))
    n_replay = min(max(n_replay, 1), micro_batch - 1) if micro_batch > 1 else 1
    return micro_batch - n_replay, n_replay


def overfit_subset(dataset: Any, n_trajectories: int) -> Any:
    """Restrict a ``ViNT_Dataset`` to samples from its first N trajectories.

    Gate G3.c: "train on 10 trajectories only; the model must drive train loss
    near zero. If it can't, the pipeline (not the model) is broken." Subsetting
    by *trajectory* rather than by sample index is the point -- a random sample
    subset still spans every trajectory and would not be an overfit test.
    """
    import torch

    index = getattr(dataset, "index_to_data", None)
    if index is None:
        raise TypeError(
            f"--overfit-n needs a dataset exposing index_to_data; got {type(dataset).__name__}"
        )
    keep: dict[str, None] = {}
    for f_curr, *_ in index:
        if f_curr not in keep and len(keep) >= n_trajectories:
            continue
        keep.setdefault(f_curr, None)
    chosen = [i for i, (f_curr, *_) in enumerate(index) if f_curr in keep]
    if not chosen:
        raise RuntimeError("--overfit-n selected zero samples; is the split empty?")
    print(f"overfit mode: {len(keep)} trajectories, {len(chosen)} samples")
    return torch.utils.data.Subset(dataset, chosen)


def _split_digest(splits_root: Path, dataset_names: Sequence[str]) -> str | None:
    """Digest the split files this run reads, or None if none are readable.

    Identity must cover *which trajectories* a run saw. Two runs over the same
    dataset name and different split files are different experiments, and the
    dataset name alone cannot tell them apart.
    """
    parts: list[str] = []
    for name in sorted(set(dataset_names)):
        for split in ("train", "test"):
            path = Path(splits_root) / name / split / "traj_names.txt"
            if path.is_file():
                parts.append(f"{name}/{split}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest() if parts else None


def _cycle(loader: Any) -> Iterator[Any]:
    """Infinite iterator over a loader, re-shuffling each pass.

    The replay stream is consumed at a different rate from the target stream and
    must never run dry mid-epoch.
    """
    while True:
        yield from loader


def _merge(target: Any, replay: Any | None) -> Any:
    """Concatenate two ViNT 7-tuples into one micro-batch."""
    import torch

    if replay is None:
        return target
    return tuple(torch.cat([a, b], dim=0) for a, b in zip(target, replay, strict=True))


def train_one_epoch(
    model: Any,
    optimizer: Any,
    loader: Any,
    *,
    cfg: FinetuneConfig,
    device: Any,
    alpha: float,
    learn_angle: bool,
    replay_iter: Iterator[Any] | None = None,
    grad_clip: float | None = None,
    epoch: int = 0,
    progress: bool = True,
    max_steps: int | None = None,
) -> dict[str, float]:
    """One epoch of accumulated fine-tuning. Returns mean training metrics.

    The accumulation window is ``cfg.accumulation_steps`` micro-batches; each
    micro-batch's loss is divided by that count so the accumulated gradient is
    the gradient of the mean over the effective batch, not its sum. Getting this
    wrong scales the effective learning rate by the accumulation factor.
    """
    import torch
    from vint_train.training.train_utils import _compute_losses

    transform = upstream.reference_transform()
    accum = cfg.accumulation_steps
    model.train()
    if cfg.freeze_bn:
        # Re-applied after every .train(): otherwise epoch 2 silently un-freezes.
        freeze_batchnorm(model)

    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    n_micro = 0
    optimizer.zero_grad(set_to_none=True)

    iterator = loader
    if progress:
        with contextlib.suppress(ImportError):
            import tqdm

            iterator = tqdm.tqdm(
                loader, dynamic_ncols=True, desc=f"train epoch {epoch}", leave=False
            )

    for step, target_batch in enumerate(iterator):
        if max_steps is not None and step >= max_steps:
            break
        batch = _merge(target_batch, next(replay_iter) if replay_iter is not None else None)
        (obs_image, goal_image, action_label, dist_label, _goal_pos, _ds_index, action_mask) = batch

        obs_image, goal_image = upstream.apply_reference_transform(
            obs_image, goal_image, transform, device
        )
        with amp_context(cfg):
            dist_pred, action_pred = model(obs_image, goal_image)
            losses = _compute_losses(
                dist_label=dist_label.to(device),
                action_label=action_label.to(device),
                dist_pred=dist_pred,
                action_pred=action_pred,
                alpha=alpha,
                learn_angle=learn_angle,
                action_mask=action_mask.to(device),
            )
        (losses["total_loss"] / accum).backward()

        for key, value in losses.items():
            v = float(value.detach())
            if not math.isnan(v):
                sums[key] = sums.get(key, 0.0) + v
                counts[key] = counts.get(key, 0) + 1
        n_micro += 1

        if n_micro % accum == 0:
            if grad_clip:
                torch.nn.utils.clip_grad_norm_(
                    [p for p in model.parameters() if p.requires_grad], grad_clip
                )
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)

    # A trailing partial window would apply an under-scaled gradient at a
    # different effective batch size than every other step. Drop it and say so.
    leftover = n_micro % accum
    if leftover:
        optimizer.zero_grad(set_to_none=True)

    out = {k: sums[k] / counts[k] for k in sums}
    out["micro_batches"] = float(n_micro)
    out["optimizer_steps"] = float(n_micro // accum)
    out["dropped_partial_window"] = float(leftover)
    return out


# ----------------------------------------------------------------- checkpoints


def save_weights(path: Path, model: Any) -> None:
    """``epoch_N.pth``: a bare state_dict and nothing else.

    Deliberately separate from the resume bundle. Finding F5 is that the
    reference saves *live* ``ViNT`` and optimizer objects, so loading a released
    checkpoint executes arbitrary code and fails outright under torch >= 2.6's
    ``weights_only`` default. A file we produce and then feed to
    ``navfm.eval.offline`` must not inherit that: this one loads with
    ``weights_only=True`` and therefore needs no ``--trust-checkpoint``.
    """
    import torch

    torch.save(model.state_dict(), path)


def save_resume_state(
    path: Path,
    *,
    model,
    optimizer,
    scheduler,
    epoch: int,
    cfg: FinetuneConfig,
    identity: dict[str, Any] | None = None,
) -> None:
    """``latest.pth``: everything needed to continue the run as if uninterrupted.

    Optimizer moments, scheduler position and all three RNG streams. This one is
    *not* ``weights_only``-loadable -- ``numpy.random.get_state()`` is a tuple of
    plain types, not a tensor -- which is why it is a separate file from the
    weights. It contains no custom classes, so loading it still executes no
    third-party code.
    """
    import torch

    torch.save(
        {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict() if scheduler is not None else None,
            "identity": identity,
            "epoch": epoch,
            "config": cfg.to_dict(),
            "rng": {
                "python": random.getstate(),
                "numpy": np.random.get_state(),
                "torch": torch.get_rng_state(),
            },
        },
        path,
    )


def load_checkpoint_for_resume(
    path: Path,
    *,
    model,
    optimizer,
    scheduler,
    epochs: int | None = None,
    identity: dict[str, Any] | None = None,
) -> int:
    """Restore a run and return the epoch to continue *from*.

    Refuses to resume into a different epoch count. ``_LRScheduler.state_dict``
    round-trips ``T_max``, so a scheduler rebuilt with ``epochs=20`` and then
    restored from a checkpoint written at ``epochs=2`` silently reverts to the
    two-epoch cosine -- which has already annealed to zero. The resumed epochs
    then train at ``lr = 0`` and the run looks finished rather than broken.
    Observed, not hypothesised; it is why this check exists.
    """
    import torch

    state = torch.load(path, map_location="cpu", weights_only=False)

    # A resume must continue the SAME experiment. latest.pth will happily
    # restore into a run pointed at another dataset, batch size, checkpoint or
    # environment, and the result is one runs/ directory describing a
    # population that was never one experiment.
    prior_identity = state.get("identity")
    if identity is not None and prior_identity is not None:
        mismatches = compare(prior_identity, identity)
        if mismatches:
            detail = "\n".join(f"    {m}" for m in mismatches)
            raise SystemExit(
                f"refusing to resume {path.name}: the requested run is not the run that "
                f"was interrupted.\n{detail}\n"
                f"  to continue the original run:  match the fields above\n"
                f"  to run a variant deliberately: start a new --run-name, which records "
                f"its lineage back to this one rather than overwriting it"
            )

    saved_epochs = (state.get("config") or {}).get("epochs")
    if epochs is not None and saved_epochs is not None and epochs != saved_epochs:
        raise SystemExit(
            f"refusing to resume {path.name}: it was written by a run of {saved_epochs} "
            f"epochs, and you asked for {epochs}. The LR schedule is restored from the "
            f"checkpoint, so the extra epochs would run on the OLD {saved_epochs}-epoch "
            f"cosine -- already annealed to zero.\n"
            f"  to continue the original run:  drop --epochs (or pass --epochs {saved_epochs})\n"
            f"  to train longer:               start a new run_name from epoch_N.pth as "
            f"the config's `checkpoint:`, which gives it a fresh schedule and its own "
            f"runs/ directory"
        )
    model.load_state_dict(state["model"])
    optimizer.load_state_dict(state["optimizer"])
    if scheduler is not None and state.get("scheduler") is not None:
        scheduler.load_state_dict(state["scheduler"])
    rng = state.get("rng") or {}
    with contextlib.suppress(Exception):
        random.setstate(rng["python"])
        np.random.set_state(rng["numpy"])
        torch.set_rng_state(rng["torch"])
    return int(state["epoch"]) + 1


# -------------------------------------------------------------------------- CLI


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m navfm.train.run",
        description="Fine-tune ViNT/GNM on a single GPU against the reference objective.",
    )
    p.add_argument("--config", required=True, help="a navfm.train.finetune.FinetuneConfig YAML")
    p.add_argument("--data-root", default="/data", help="dataset lives at <data-root>/<name>")
    p.add_argument("--splits-root", default=None, help="defaults to the reference data_splits dir")
    p.add_argument(
        "--eval-dataset", default=None, help="dataset to eval on (default: the first target)"
    )
    p.add_argument("--eval-split", default="test", choices=["train", "test"])
    p.add_argument(
        "--eval-batch-size", type=int, default=400, help="metrics are batch-size dependent"
    )
    p.add_argument("--eval-limit-batches", type=int, default=None)
    p.add_argument(
        "--overfit-n",
        type=int,
        default=None,
        metavar="N",
        help="train on N trajectories only -- gate G3.c; the model must reach near-zero train loss",
    )
    p.add_argument("--epochs", type=int, default=None, help="override the config")
    p.add_argument("--micro-batch-size", type=int, default=None, help="override the config")
    p.add_argument(
        "--max-steps", type=int, default=None, help="cap micro-batches per epoch (smoke tests)"
    )
    p.add_argument("--device", default=None)
    p.add_argument(
        "--run-name", default=None, help="override the config; also sets the table cell id"
    )
    p.add_argument("--resume", action="store_true", help="continue from runs/<run_name>/latest.pth")
    p.add_argument(
        "--trust-checkpoint", action="store_true", help="required for vint.pth / gnm.pth"
    )
    p.add_argument(
        "--evidence-class",
        default="registered_experiment",
        help=(
            "what kind of evidence this run produces; part of the run identity, so "
            "resuming under a different class is refused"
        ),
    )
    p.add_argument(
        "--allow-partial-load",
        action="store_true",
        help="permit a checkpoint that fills <90%% of the model; recorded in the run manifest",
    )
    p.add_argument("--no-progress", action="store_true")
    return p


def _make_loader(
    dataset: Any, batch_size: int, *, shuffle: bool, workers: int, seed: int, drop_last: bool
):
    import torch

    if batch_size < 1:
        return None
    return torch.utils.data.DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=workers,
        drop_last=drop_last,
        generator=torch.Generator().manual_seed(seed),
        persistent_workers=workers > 0,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    import torch

    cfg = FinetuneConfig.from_yaml(args.config)
    if args.epochs is not None:
        cfg.epochs = args.epochs
    if args.micro_batch_size is not None:
        cfg.micro_batch_size = args.micro_batch_size
        cfg.__post_init__()  # re-validate the accumulation arithmetic
    if args.run_name:
        cfg.run_name = args.run_name

    set_seed(cfg.seed, deterministic=cfg.deterministic)
    upstream.ensure_upstream()
    model_cfg = upstream.model_config(cfg.model_type)
    alpha = float(model_cfg["alpha"])
    learn_angle = bool(model_cfg["learn_angle"])
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")

    # ---------------------------------------------------------------- model
    model = upstream.build_model(cfg.model_type, model_cfg)
    missing: list[str] = []
    load_census: dict[str, object] | None = None
    unexpected: list[str] = []
    if cfg.checkpoint:
        from navfm.models.loader import load_into, sha256

        checkpoint_sha: str | None = sha256(cfg.checkpoint)
        missing, unexpected = load_into(
            model,
            cfg.checkpoint,
            trust_checkpoint=args.trust_checkpoint,
            strict=False,
            verbose=True,
        )
        # strict=False cannot fail: a checkpoint matching nothing would train
        # from random init under this checkpoint's SHA. Refuse before step 1.
        from navfm.models.loader import CheckpointLoadError, audit_load

        try:
            load_census = audit_load(
                model, missing, unexpected, allow_partial=args.allow_partial_load
            )
        except CheckpointLoadError as exc:
            raise SystemExit(str(exc)) from exc
    else:
        checkpoint_sha = None
        print(
            "no checkpoint in the config: training FROM SCRATCH. This is the E3 "
            "scratch arm; if you meant to fine-tune, set `checkpoint:`.",
            file=sys.stderr,
        )
    model.to(device)

    freeze_info = apply_freeze(model, cfg.freeze)
    n_bn = freeze_batchnorm(model) if cfg.freeze_bn else 0
    print(
        f"freeze={cfg.freeze}: {freeze_info['trainable']:,} trainable / "
        f"{freeze_info['frozen']:,} frozen params; {n_bn} BatchNorm modules frozen"
    )

    # ----------------------------------------------------------------- data
    splits_root = Path(args.splits_root) if args.splits_root else upstream.default_splits_root()

    def _dataset(name: str, split: str) -> Any:
        opts = upstream.dataset_options(model_cfg, name)
        return upstream.build_dataset(
            dataset_name=name,
            data_folder=Path(args.data_root) / name,
            split_folder=splits_root / name / split,
            cfg=model_cfg,
            end_slack=opts["end_slack"],
            waypoint_spacing=opts["waypoint_spacing"],
            negative_mining=opts["negative_mining"],
            goals_per_obs=opts["goals_per_obs"],
        )

    train_sets = [_dataset(n, "train") for n in cfg.datasets]
    train_set: Any = (
        train_sets[0] if len(train_sets) == 1 else torch.utils.data.ConcatDataset(train_sets)
    )
    if args.overfit_n:
        if len(train_sets) > 1:
            raise SystemExit("--overfit-n expects a single target dataset")
        train_set = overfit_subset(train_set, args.overfit_n)

    n_target, n_replay = replay_batch_sizes(cfg.micro_batch_size, cfg.replay_ratio)
    if n_target == 0:
        raise SystemExit(
            "replay_ratio 1.0 leaves no target data in the batch; that is not a "
            "fine-tune. Use the replay corpus as `datasets:` if that is what you meant."
        )
    replay_iter = None
    if n_replay:
        if not cfg.replay_datasets:
            raise SystemExit("replay_ratio > 0 but replay_datasets is empty")
        replay_sets = [_dataset(n, "train") for n in cfg.replay_datasets]
        replay_set = (
            replay_sets[0] if len(replay_sets) == 1 else torch.utils.data.ConcatDataset(replay_sets)
        )
        replay_loader = _make_loader(
            replay_set,
            n_replay,
            shuffle=True,
            workers=cfg.num_workers,
            seed=cfg.seed + 1,
            drop_last=True,
        )
        replay_iter = _cycle(replay_loader)
        print(
            f"replay: {n_replay}/{cfg.micro_batch_size} samples per micro-batch from {cfg.replay_datasets}"
        )

    train_loader = _make_loader(
        train_set, n_target, shuffle=True, workers=cfg.num_workers, seed=cfg.seed, drop_last=True
    )
    if len(train_loader) == 0:
        raise SystemExit(
            f"the training split yields {len(train_set)} samples, fewer than one "
            f"micro-batch of {n_target} (drop_last is on, so every step sees a "
            f"constant batch). Lower --micro-batch-size or check the split."
        )

    eval_name = args.eval_dataset or cfg.datasets[0]
    eval_opts = upstream.dataset_options(model_cfg, eval_name)
    eval_set = _dataset(eval_name, args.eval_split)
    eval_loader = _make_loader(
        eval_set, args.eval_batch_size, shuffle=True, workers=0, seed=cfg.seed, drop_last=False
    )
    metres_per_unit = upstream.metric_waypoint_spacing(eval_name) * eval_opts["waypoint_spacing"]

    # ------------------------------------------------------------ optimiser
    optimizer = build_optimizer(model, cfg)
    steps_per_epoch = max(len(train_loader) // cfg.accumulation_steps, 1)
    scheduler = build_scheduler(optimizer, cfg, steps_per_epoch)

    run_dir = Path(cfg.log_dir) / cfg.run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    # The identity a resume must match. Built before the resume so the guard
    # runs before any state is restored.
    identity = run_identity(
        checkpoint_sha256=checkpoint_sha,
        dataset_split_digest=_split_digest(splits_root, [*cfg.datasets, eval_name]),
        evaluator_commit=git_describe(),
        config_digest=hashlib.sha256(
            json.dumps(cfg.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        metric_set_version=hashlib.sha256(",".join(sorted(REFERENCE_KEYS)).encode()).hexdigest()[
            :16
        ],
        seed_set=[cfg.seed],
        batch_size=cfg.effective_batch_size,
        environment_id=environment_identity().environment_id,
        evidence_class=args.evidence_class,
        architecture=cfg.model_type,
    )

    start_epoch = 0
    latest = run_dir / "latest.pth"
    if args.resume:
        if not latest.is_file():
            raise SystemExit(f"--resume given but {latest} does not exist")
        start_epoch = load_checkpoint_for_resume(
            latest,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            epochs=cfg.epochs,
            identity=identity,
        )
        print(f"resumed from {latest}; continuing at epoch {start_epoch}")

    cell, seed = cell_and_seed(cfg.run_name)
    config_record = {
        "kind": "train",
        "finetune_config": cfg.to_dict(),
        "config_path": str(args.config),
        "model_config": model_cfg,
        "alpha": alpha,
        "argv": list(argv) if argv is not None else sys.argv[1:],
        "data_root": str(args.data_root),
        "splits_root": str(splits_root),
        "eval_dataset": eval_name,
        "eval_split": args.eval_split,
        "eval_batch_size": args.eval_batch_size,
        "metres_per_unit": metres_per_unit,
        "micro_batch_split": {"target": n_target, "replay": n_replay},
        "freeze": freeze_info,
        "frozen_batchnorm_modules": n_bn,
        "checkpoint": cfg.checkpoint,
        "checkpoint_sha256": checkpoint_sha,
        "checkpoint_load": load_census,
        "run_identity": identity,
        "run_identity_digest": identity_digest(identity),
        "checkpoint_missing_keys": missing,
        "checkpoint_unexpected_keys": unexpected,
        "overfit_n": args.overfit_n,
        "scheduler_steps_per_epoch": 1,
        "scheduler_note": "stepped once per epoch; the reference nomad loop steps twice (F8)",
        "device": device,
        "upstream_commit": upstream.upstream_commit(),
        "cell": cell,
        "seed_from_run_name": seed,
    }
    (run_dir / "config.json").write_text(json.dumps(config_record, indent=2, sort_keys=True) + "\n")
    (run_dir / "git_sha.txt").write_text(
        f"navfm    {git_describe(Path(__file__).resolve().parents[3])}\n"
        f"upstream {upstream.upstream_commit()}\n"
    )

    # ----------------------------------------------------------------- loop
    print(
        f"\n{cfg.run_name}: {cfg.epochs} epochs, micro {cfg.micro_batch_size} x "
        f"{cfg.accumulation_steps} = effective {cfg.effective_batch_size}, "
        f"lr {cfg.lr}, {device}\n"
    )
    history: list[dict[str, Any]] = []
    for epoch in range(start_epoch, cfg.epochs):
        t0 = time.time()
        train_metrics = train_one_epoch(
            model,
            optimizer,
            train_loader,
            cfg=cfg,
            device=device,
            alpha=alpha,
            learn_angle=learn_angle,
            replay_iter=replay_iter,
            grad_clip=cfg.grad_clip,
            epoch=epoch,
            progress=not args.no_progress,
            max_steps=args.max_steps,
        )
        train_s = time.time() - t0

        record: dict[str, Any] = {
            "epoch": epoch,
            "lr": float(optimizer.param_groups[0]["lr"]),
            "train": train_metrics,
            "train_seconds": round(train_s, 2),
            "run_name": cfg.run_name,
            "cell": cell,
            "seed": cfg.seed if seed is None else seed,
            "kind": "train",
            "eval_dataset": eval_name,
            "eval_split": args.eval_split,
            "eval_batch_size": args.eval_batch_size,
        }

        if cfg.eval_every and (epoch + 1) % cfg.eval_every == 0:
            t1 = time.time()
            record["eval"] = evaluate(
                model,
                eval_loader,
                device=device,
                alpha=alpha,
                learn_angle=learn_angle,
                metres_per_unit=metres_per_unit,
                limit_batches=args.eval_limit_batches,
                amp=amp_context(cfg),
                progress=not args.no_progress,
            )
            record["eval_seconds"] = round(time.time() - t1, 2)

        if scheduler is not None:
            # Once per epoch. train_eval_loop_nomad steps twice; see F8.
            if cfg.scheduler == "plateau":
                scheduler.step(record.get("eval", {}).get("strict", {}).get("total_loss", 0.0))
            else:
                scheduler.step()

        (run_dir / f"metrics_epoch_{epoch}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
        history.append(record)

        if cfg.save_every and (epoch + 1) % cfg.save_every == 0:
            # Bare weights: `--checkpoint runs/<run>/epoch_N.pth` needs no trust flag.
            save_weights(run_dir / f"epoch_{epoch}.pth", model)
        save_resume_state(
            latest,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            epoch=epoch,
            cfg=cfg,
            identity=identity,
        )

        tl = train_metrics.get("total_loss", float("nan"))
        el = record.get("eval", {}).get("strict", {}).get("total_loss", float("nan"))
        print(
            f"epoch {epoch:>3}  train_total {tl:.6f}  eval_total {el:.6f}  "
            f"lr {record['lr']:.2e}  {train_s:.1f}s"
        )
        if epoch == start_epoch and len(history) == 1 and cfg.freeze_bn is False:
            print(
                "  note: freeze_bn is off. A RISING validation loss over the next "
                "epochs is the BatchNorm-drift signature (docs/WORKFLOW.md 3.2).",
                file=sys.stderr,
            )

    print(f"\n-> {run_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
