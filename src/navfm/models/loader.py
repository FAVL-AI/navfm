"""Robust loading of the released GNM / ViNT / NoMaD checkpoints.

The three published checkpoints are *not* in the same format, and neither the
README nor ``deployment/config/models.yaml`` says so. Loading them naively on a
2026 PyTorch fails in three different ways:

===========  =========================================  ==================================
checkpoint   on-disk contents                            failure without this module
===========  =========================================  ==================================
``vint.pth``  full training dict; ``["model"]`` is a     ``UnpicklingError`` on torch >= 2.6
              *live* ``vint_train...ViNT`` object        (``weights_only`` default flipped),
                                                         then ``ModuleNotFoundError`` unless
                                                         ``vint_train`` and
                                                         ``warmup_scheduler`` are importable
``gnm.pth``   same, with a ``GNM`` object                same, plus a torchvision import
``nomad.pth`` bare ``OrderedDict`` state_dict, 645 keys  loads fine, but has no ``epoch`` /
                                                         ``optimizer`` / ``scheduler``, so the
                                                         upstream resume path raises
                                                         ``KeyError`` -- this is the root of
                                                         upstream issue #10
===========  =========================================  ==================================

``models.yaml`` also names ``gnm_large.pth`` and ``vint_late_fusion.pth``.
Neither exists: the released GNM file is ``gnm.pth``, and the late-fusion
checkpoint was never published (the original ``drive-any-robot`` Drive folder
that hosted ``gnm_large.pth`` now returns 404).

Unpickling a live object executes arbitrary code. We therefore require an
explicit ``trust_checkpoint=True`` and verify a SHA-256 against a known-good
manifest when one is available, rather than silently passing
``weights_only=False``.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = [
    "CHECKPOINTS",
    "CheckpointInfo",
    "count_parameters",
    "extract_state_dict",
    "load_checkpoint",
    "sha256",
]


@dataclasses.dataclass(frozen=True)
class CheckpointInfo:
    name: str
    filename: str
    drive_id: str
    size_bytes: int
    format: str  # "training_dict" | "state_dict"
    notes: str = ""


#: Verified live on the official Drive folder ``1a9yWR2iooXFAqjQHetz263--4_2FFggg``
#: as of 2026-07-30. Sizes are exact byte counts from the download headers.
CHECKPOINTS: Mapping[str, CheckpointInfo] = {
    "vint": CheckpointInfo(
        "vint",
        "vint.pth",
        "1ckrceGb5m_uUtq3pD8KHwnqtJgPl6kF5",
        430_167_114,
        "training_dict",
        "run vint-5c, epoch 29, avg_total_test_loss 0.17398, context_size 5",
    ),
    "gnm": CheckpointInfo(
        "gnm",
        "gnm.pth",
        "1bzCPd_OsXjS2aGPTQladbI8ImxLZwrQh",
        104_806_886,
        "training_dict",
        "epoch 29, context_size 5, obs_encoding_size 1024; models.yaml calls this gnm_large.pth",
    ),
    "nomad": CheckpointInfo(
        "nomad",
        "nomad.pth",
        "1YJhkkMJAYOiKNyCaelbS_alpUpAJsOUb",
        76_473_631,
        "state_dict",
        "bare OrderedDict of 645 keys; these are the EMA weights, not the raw model",
    ),
}


def sha256(path: str | Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def load_checkpoint(
    path: str | Path,
    *,
    map_location: str = "cpu",
    trust_checkpoint: bool = False,
    expected_sha256: str | None = None,
) -> Any:
    """Load any of the three checkpoint formats on modern PyTorch.

    ``trust_checkpoint`` must be set explicitly for the pickled-object
    checkpoints (``vint.pth``, ``gnm.pth``) because loading them runs arbitrary
    code from the file. ``nomad.pth`` is a plain tensor dict and loads under
    ``weights_only=True`` without any trust.
    """
    import torch

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    if expected_sha256 is not None:
        actual = sha256(path)
        if actual != expected_sha256:
            raise ValueError(
                f"checkpoint hash mismatch for {path}:\n"
                f"  expected {expected_sha256}\n  actual   {actual}"
            )

    try:
        return torch.load(path, map_location=map_location, weights_only=True)
    except Exception as safe_exc:
        if not trust_checkpoint:
            raise RuntimeError(
                f"{path.name} is not a plain state_dict; it contains pickled Python "
                "objects (the reference repo saves live model and optimizer objects). "
                "Loading it executes arbitrary code from the file. Pass "
                "trust_checkpoint=True only for checkpoints you downloaded from the "
                "official Drive folder and whose SHA-256 you verified.\n"
                f"underlying error: {safe_exc!r}"
            ) from safe_exc

    _ensure_unpickle_deps()
    return torch.load(path, map_location=map_location, weights_only=False)


def _ensure_unpickle_deps() -> None:
    """Fail early and legibly if the modules the pickle references are missing."""
    missing: list[str] = []
    for module, hint in (
        ("vint_train", "pip install -e third_party/visualnav-transformer/train"),
        ("warmup_scheduler", "pip install git+https://github.com/ildoonet/pytorch-gradual-warmup-lr.git"),
        ("efficientnet_pytorch", "pip install efficientnet_pytorch"),
    ):
        try:
            __import__(module)
        except ImportError:
            missing.append(f"  {module}: {hint}")
    if missing:
        raise ImportError(
            "The released ViNT/GNM checkpoints pickle live objects, so the classes "
            "they reference must be importable before unpickling:\n" + "\n".join(missing)
        )


def extract_state_dict(obj: Any) -> dict[str, Any]:
    """Normalise any of the three formats to a plain ``{name: tensor}`` dict.

    Also strips a ``module.`` prefix, which the reference training loop leaves
    behind whenever it was run under ``nn.DataParallel`` (it always is -- see
    ``train.py``), and which makes ``load_state_dict`` fail silently under
    ``strict=False``.
    """
    import torch

    if isinstance(obj, torch.nn.Module):
        state = obj.state_dict()
    elif isinstance(obj, Mapping) and "model" in obj:
        model = obj["model"]
        state = model.state_dict() if isinstance(model, torch.nn.Module) else dict(model)
    elif isinstance(obj, Mapping):
        state = dict(obj)
    else:
        raise TypeError(f"cannot extract a state_dict from {type(obj).__name__}")

    if any(k.startswith("module.") for k in state):
        state = {k[len("module.") :] if k.startswith("module.") else k: v for k, v in state.items()}
    return state


def load_into(
    model: Any,
    checkpoint_path: str | Path,
    *,
    trust_checkpoint: bool = False,
    strict: bool = False,
    verbose: bool = True,
) -> tuple[list[str], list[str]]:
    """Load a checkpoint into an instantiated model; report what did not match.

    ``strict=False`` is the upstream default and it hides real problems -- a
    typo in a key name looks identical to an intentional architecture change.
    We therefore always print the mismatch summary.
    """
    obj = load_checkpoint(checkpoint_path, trust_checkpoint=trust_checkpoint)
    state = extract_state_dict(obj)
    result = model.load_state_dict(state, strict=strict)
    missing = list(getattr(result, "missing_keys", []))
    unexpected = list(getattr(result, "unexpected_keys", []))
    if verbose:
        print(
            f"loaded {Path(checkpoint_path).name}: "
            f"{len(state)} tensors, {len(missing)} missing, {len(unexpected)} unexpected"
        )
        for k in missing[:10]:
            print(f"  missing    {k}")
        for k in unexpected[:10]:
            print(f"  unexpected {k}")
    return missing, unexpected


def count_parameters(model: Any) -> dict[str, int]:
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return {"total": total, "trainable": trainable, "frozen": total - trainable}
