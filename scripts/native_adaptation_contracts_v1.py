"""Fixed endpoint partitions and state-fenced native smoke evaluation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def validate_pair(pair, allowed, file_hashes, context, horizon):
    if type(pair["negative"]) is not bool:
        raise ValueError("negative flag must be bool")
    for field in ("current", "goal_time"):
        if type(pair[field]) is not int or pair[field] < 0:
            raise ValueError("invalid endpoint time")
    if pair["trajectory"] not in allowed or pair["goal_trajectory"] not in allowed:
        raise ValueError("partition endpoint leakage")
    current = pair["current"]
    if current < context:
        raise ValueError("history before trajectory")
    if not pair["negative"] and (
        pair["goal_trajectory"] != pair["trajectory"] or pair["goal_time"] - current != 6
    ):
        raise ValueError("positive goal distance must be six chronological steps")
    names = [f"{pair['trajectory']}/{i}.jpg" for i in range(current - context, current + 1)]
    names += [f"{pair['goal_trajectory']}/{pair['goal_time']}.jpg"]
    names += [f"{n}/traj_data.pkl" for n in {pair["trajectory"], pair["goal_trajectory"]}]
    if any(n not in file_hashes for n in names):
        raise ValueError("unadmitted endpoint")
    return {
        "history": list(range(current - context, current + 1)),
        "labels": list(range(current + 1, current + horizon + 1)),
        "files": sorted(set(names)),
    }


def state_digest(value):
    h = hashlib.sha256()

    def visit(x):
        if hasattr(x, "detach"):
            t = x.detach().cpu().contiguous()
            h.update(str((str(t.dtype), list(t.shape))).encode())
            h.update(t.numpy().tobytes())
        elif isinstance(x, dict):
            for k in sorted(x, key=str):
                h.update(repr(k).encode())
                visit(x[k])
        elif isinstance(x, (tuple, list)):
            for y in x:
                visit(y)
        else:
            h.update(repr(x).encode())

    visit(value)
    return h.hexdigest()


def capture_rng():
    import random

    import numpy as np
    import torch

    state = np.random.get_state()
    return {
        "python_rng": random.getstate(),
        "numpy_rng": {
            "name": state[0],
            "keys": state[1].tolist(),
            "position": state[2],
            "has_gauss": state[3],
            "cached_gaussian": state[4],
        },
        "torch_rng": torch.get_rng_state(),
        "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
    }


def restore_rng(saved):
    import random

    import numpy as np
    import torch

    keys = ("python_rng", "numpy_rng", "torch_rng", "cuda_rng")
    if any(k not in saved for k in keys):
        raise ValueError("required resume RNG field missing")
    state = saved["numpy_rng"]
    random.setstate(saved["python_rng"])
    np.random.set_state(
        (
            state["name"],
            np.array(state["keys"], dtype=np.uint32),
            state["position"],
            state["has_gauss"],
            state["cached_gaussian"],
        )
    )
    torch.set_rng_state(saved["torch_rng"].cpu())
    if saved["cuda_rng"]:
        if not torch.cuda.is_available():
            raise ValueError("saved CUDA RNG requires CUDA")
        torch.cuda.set_rng_state_all([x.cpu() for x in saved["cuda_rng"]])
    elif torch.cuda.is_available():
        raise ValueError("CUDA resume RNG list missing")
    expected = {k: saved[k] for k in keys}
    if state_digest(capture_rng()) != state_digest(expected):
        raise ValueError("restored RNG readbacks differ")


def can_continue_independent(record, freeze):
    if (
        record.get("model") != "gnm"
        or record.get("freeze") != freeze
        or record.get("status") not in {"PASS", "FAIL"}
        or record.get("shared_integrity") != "PASS"
        or record.get("child_reaped") is not True
    ):
        raise ValueError("shared integrity or child reaping not established; halt")


def evaluate_fenced(model, optimizer, ema, evaluate):
    import torch

    before = [
        state_digest(model.state_dict()),
        state_digest(optimizer.state_dict()),
        state_digest(ema.state_dict()) if ema else None,
    ]
    modes = [(m, m.training) for m in model.modules()]
    rng = capture_rng()
    try:
        model.eval()
        with torch.no_grad():
            result = evaluate()
        after = [
            state_digest(model.state_dict()),
            state_digest(optimizer.state_dict()),
            state_digest(ema.state_dict()) if ema else None,
        ]
        if before != after:
            raise ValueError("development evaluation mutated training state")
        return result
    finally:
        for m, mode in modes:
            m.training = mode
        restore_rng(rng)


def shared_metric(prediction, labels, masks, spacing):
    import torch

    if prediction.shape[1] < 5 or labels.shape[1] < 5 or prediction.shape[0] != labels.shape[0]:
        raise ValueError("common five-waypoint geometry missing")
    errors = torch.linalg.vector_norm((prediction[:, :5, :2] - labels[:, :5, :2]) * spacing, dim=-1)
    eligible = masks.bool()
    if not torch.isfinite(errors).all() or not eligible.any():
        raise ValueError("nonfinite or empty common metric")
    return {
        "eligible_pairs": int(eligible.sum()),
        "horizon_waypoints": 5,
        "spacing_m": spacing,
        "ADE_m": float(errors[eligible].mean()),
        "FDE_m": float(errors[eligible, -1].mean()),
    }


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def restore_training_state(model, optimizer, scheduler, ema, resume):
    restore_rng(resume)
    model.load_state_dict(resume["raw_model"], strict=True)
    optimizer.load_state_dict(resume["optimizer"])
    scheduler.load_state_dict(resume["scheduler"])
    if ema is not None:
        if resume["ema"] is None:
            raise ValueError("EMA state missing")
        ema.load_state_dict(resume["ema"])
    elif resume["ema"] is not None:
        raise ValueError("unexpected EMA state")
    actual = {
        "raw_model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict(),
        "ema": ema.state_dict() if ema else None,
    }
    expected = {k: resume[k] for k in actual}
    if state_digest(actual) != state_digest(expected):
        raise ValueError("restored training state differs")
