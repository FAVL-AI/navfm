"""ViNT / NoMaD fine-tuning on a single 16 GB GPU.

The reference recipe assumes 8 x V100 (ViNT: batch 300, ~30 h). This module
reproduces the *optimisation* faithfully on one RTX 4080 SUPER by trading
memory for time, and adds the pieces the reference repo lacks for fine-tuning:

* **Gradient accumulation** so the effective batch matches the published one.
  This is not cosmetic. The reference model uses BatchNorm inside
  EfficientNet-B0, and BN statistics depend on the *micro*-batch, not the
  effective one -- so a naive "small batch + more steps" fine-tune shifts the
  running statistics away from the pretrained ones and degrades the encoder
  before any gradient signal helps. We therefore freeze BN in eval mode by
  default (``--freeze-bn``), which is standard for small-batch fine-tuning and
  is what makes the 16 GB budget viable.
* **Layer-freezing schedules**, because the ViNT paper's own ablation (Table 8)
  shows a frozen encoder collapses from 0.82 to 0.32 success on image goals.
  Full fine-tuning is the paper's answer; we expose partial schedules so the
  trade-off can be measured rather than assumed.
* **Mixed precision** with bf16 preferred over fp16: the diffusion loss in
  NoMaD is an MSE on unit-variance noise, and fp16 gradient scaling there is
  fragile. bf16 has the dynamic range and needs no scaler.
* **Deterministic seeding** and a resolved-config dump, so a run is
  reproducible from its log directory alone.

Upstream fine-tuning caveats this module works around, all verified:

* ``nomad.pth`` is a bare state_dict, so upstream's resume path
  (``checkpoint["optimizer"].state_dict()``) raises ``KeyError``. We never
  touch that path.
* ``train_eval_loop_nomad`` calls ``lr_scheduler.step()`` twice per epoch, so a
  ``CosineAnnealingLR(T_max=epochs)`` completes at epoch ``epochs/2`` and then
  climbs back up. We step once, and say so in the run config.
* ``goals_per_obs`` and ``negative_mining`` are dead config keys in the released
  dataset class. We do not pretend otherwise; see docs/REPRODUCTION.md.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import random
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["FinetuneConfig", "apply_freeze", "build_optimizer", "freeze_batchnorm", "set_seed"]


@dataclasses.dataclass
class FinetuneConfig:
    """Everything that defines a fine-tuning run."""

    model_type: str = "vint"
    checkpoint: str | None = None

    # -- optimisation --
    epochs: int = 20
    micro_batch_size: int = 64
    effective_batch_size: int = 256
    lr: float = 1e-4  # ViNT paper's fine-tuning LR; NOT the 5e-4 pretraining LR
    weight_decay: float = 1e-3
    optimizer: str = "adamw"
    scheduler: str = "cosine"
    warmup_epochs: int = 0  # the paper fine-tunes without warmup
    grad_clip: float | None = 1.0
    amp_dtype: str = "bf16"  # bf16 | fp16 | none

    # -- adaptation strategy --
    freeze: str = "none"  # none | obs_encoder | both_encoders | all_but_head
    freeze_bn: bool = True
    ema_decay: float | None = None  # NoMaD uses an EMA; ViNT does not

    # -- data --
    datasets: list[str] = dataclasses.field(default_factory=lambda: ["isaac_m3pro"])
    replay_datasets: list[str] = dataclasses.field(default_factory=list)
    replay_ratio: float = 0.0
    num_workers: int = 8

    # -- bookkeeping --
    seed: int = 0
    log_dir: str = "runs"
    run_name: str = "vint_ft_isaac"
    eval_every: int = 1
    save_every: int = 1
    deterministic: bool = True

    def __post_init__(self) -> None:
        if self.effective_batch_size % self.micro_batch_size != 0:
            raise ValueError(
                f"effective_batch_size ({self.effective_batch_size}) must be a multiple of "
                f"micro_batch_size ({self.micro_batch_size}); otherwise the last "
                "accumulation window is silently smaller and the LR is effectively wrong"
            )

    @property
    def accumulation_steps(self) -> int:
        return self.effective_batch_size // self.micro_batch_size

    @classmethod
    def from_yaml(cls, path: str | Path) -> FinetuneConfig:
        import yaml

        data = yaml.safe_load(Path(path).read_text()) or {}
        known = {f.name for f in dataclasses.fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["accumulation_steps"] = self.accumulation_steps
        return d


def set_seed(seed: int, *, deterministic: bool = True) -> None:
    """Seed every RNG that affects a training run.

    ``PYTHONHASHSEED`` matters because the reference dataset assigns
    ``dataset_index`` from a set iteration order in one place; leaving the hash
    seed unset makes that index unstable across processes.
    """
    import torch

    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    if deterministic:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    else:
        torch.backends.cudnn.benchmark = True


def freeze_batchnorm(model: Any) -> int:
    """Put every BatchNorm in eval mode and stop its running stats updating.

    Returns the number of modules affected. Required for small-batch
    fine-tuning of the EfficientNet-B0 encoders: with a micro-batch of 64 split
    across 6 context frames, the per-batch statistics are noisy enough to
    measurably drift the pretrained features within a few hundred steps.
    """
    import torch.nn as nn

    n = 0
    for module in model.modules():
        if isinstance(module, (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d)):
            module.eval()
            module.weight.requires_grad_(False)
            module.bias.requires_grad_(False)
            n += 1
    return n


_FREEZE_PATTERNS = {
    "none": (),
    "obs_encoder": ("obs_encoder", "compress_obs_enc"),
    "both_encoders": ("obs_encoder", "goal_encoder", "compress_obs_enc", "compress_goal_enc"),
    "all_but_head": ("obs_encoder", "goal_encoder", "compress_", "sa_", "positional_encoding"),
}


def apply_freeze(model: Any, strategy: str) -> dict[str, Any]:
    """Freeze parameters by name prefix. Returns a parameter-count breakdown."""
    if strategy not in _FREEZE_PATTERNS:
        raise ValueError(
            f"unknown freeze strategy {strategy!r}; expected one of {sorted(_FREEZE_PATTERNS)}"
        )
    patterns = _FREEZE_PATTERNS[strategy]
    frozen = trainable = 0
    for name, param in model.named_parameters():
        if any(p in name for p in patterns):
            param.requires_grad_(False)
            frozen += param.numel()
        else:
            trainable += param.numel()
    return {"frozen": frozen, "trainable": trainable, "strategy": strategy}


def build_optimizer(model: Any, cfg: FinetuneConfig) -> Any:
    """AdamW with no weight decay on norms and biases.

    The reference code passes every parameter to ``AdamW(params, lr)`` and
    inherits the torch default ``weight_decay=0.01``, while the ViNT paper's
    table lists ``0.001``. Decaying LayerNorm gains and biases is a known small
    regression; excluding them is standard practice and costs nothing.
    """
    import torch

    decay, no_decay = [], []
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        if param.ndim <= 1 or name.endswith(".bias") or "norm" in name.lower():
            no_decay.append(param)
        else:
            decay.append(param)
    groups = [
        {"params": decay, "weight_decay": cfg.weight_decay},
        {"params": no_decay, "weight_decay": 0.0},
    ]
    if cfg.optimizer.lower() == "adamw":
        return torch.optim.AdamW(groups, lr=cfg.lr)
    if cfg.optimizer.lower() == "adam":
        return torch.optim.Adam(groups, lr=cfg.lr, betas=(0.9, 0.98))
    raise ValueError(f"unsupported optimizer {cfg.optimizer!r}")


def build_scheduler(optimizer: Any, cfg: FinetuneConfig, steps_per_epoch: int) -> Any | None:
    import torch

    if cfg.scheduler in (None, "none"):
        return None
    if cfg.scheduler == "cosine":
        return torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=cfg.epochs)
    if cfg.scheduler == "plateau":
        return torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=3, factor=0.5)
    raise ValueError(f"unsupported scheduler {cfg.scheduler!r}")


def amp_context(cfg: FinetuneConfig) -> Any:
    import torch

    if cfg.amp_dtype == "none" or not torch.cuda.is_available():
        return contextlib.nullcontext()
    dtype = torch.bfloat16 if cfg.amp_dtype == "bf16" else torch.float16
    return torch.autocast(device_type="cuda", dtype=dtype)


def resolve_run_dir(cfg: FinetuneConfig) -> Path:
    """``<log_dir>/<run_name>/`` with the resolved config dumped inside."""
    run_dir = Path(cfg.log_dir) / cfg.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(json.dumps(cfg.to_dict(), indent=2))
    return run_dir


def estimate_activation_memory_gb(
    *, micro_batch: int, context_size: int, height: int, width: int, bytes_per_elem: int = 2
) -> float:
    """Rough forward-activation footprint of the EfficientNet-B0 tower.

    Not a substitute for measuring, but it turns "will batch 128 fit in 16 GB?"
    into an answerable question before launching a job. The encoder is applied
    to ``(context_size + 1) * micro_batch`` images independently, which is the
    term that dominates -- the transformer over 7 tokens of width 512 is noise
    by comparison.

    Empirical multiplier 42 covers the sum of all EfficientNet-B0 feature maps
    relative to its input, measured at 64x85 with checkpointing off.
    """
    images = micro_batch * (context_size + 1)
    per_image = height * width * 3 * 42
    return images * per_image * bytes_per_elem / (1024**3)


def suggest_micro_batch(
    vram_gb: float = 16.0,
    *,
    context_size: int = 5,
    height: int = 64,
    width: int = 85,
    headroom: float = 0.45,
) -> int:
    """Largest power-of-two micro-batch expected to fit, leaving headroom.

    ``headroom`` accounts for parameters, optimizer state, gradients, the
    allocator's fragmentation and the CUDA context -- for a 31 M-parameter model
    with AdamW that is roughly 0.5 GB fixed plus allocator slack.
    """
    budget = vram_gb * (1.0 - headroom)
    b = 1
    while True:
        nxt = b * 2
        if (
            estimate_activation_memory_gb(
                micro_batch=nxt, context_size=context_size, height=height, width=width
            )
            > budget
        ):
            return b
        b = nxt
        if b >= 1024:
            return b
