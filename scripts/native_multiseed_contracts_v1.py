"""Finite run identities, partition-confined catalog and checkpoint selection."""

from __future__ import annotations

import math
import random

SEEDS = (0, 11, 22)
MODELS = ("gnm", "nomad")
CHECKPOINTS = (236, 472, 1180, 2360, 4720)


def validate_schedule(cfg):
    if cfg["seeds"] != list(SEEDS) or cfg["checkpoint_updates"] != list(CHECKPOINTS):
        raise ValueError("declared seed/checkpoint schedule drift")
    caps = cfg["caps"]
    if caps != {
        "optimizer_updates": 4720,
        "batch_size": 4,
        "wall_seconds": 3600,
        "processes": 6,
        "aggregate_reserved_seconds": 21600,
    }:
        raise ValueError("finite budget drift")
    expected = [{"model": model, "seed": seed} for seed in SEEDS for model in MODELS]
    if cfg["runs"] != expected:
        raise ValueError("run identities/order drift")


def catalog_from_lengths(allowed, lengths, hashes):
    """One six-step positive and one cross-trajectory negative per eligible anchor."""
    if len(allowed) < 2 or set(lengths) != set(allowed) or len(set(allowed)) != len(allowed):
        raise ValueError("training catalog partition mismatch")
    from native_adaptation_contracts_v1 import validate_pair

    rows = []
    for i, name in enumerate(allowed):
        other = allowed[(i + 1) % len(allowed)]
        for current in range(5, lengths[name] - 8):
            for negative in (False, True):
                goal_name = other if negative else name
                goal_time = min(current + 6, lengths[other] - 1) if negative else current + 6
                pair = {
                    "trajectory": name,
                    "current": current,
                    "goal_trajectory": goal_name,
                    "goal_time": goal_time,
                    "negative": negative,
                }
                validate_pair(pair, allowed, hashes, 5, 8)
                # Labels are admitted trajectory positions, while all RGB endpoints are pinned.
                if current + 8 >= lengths[name] or goal_time < 0:
                    raise ValueError("label endpoint outside trajectory")
                rows.append(pair)
    if not rows:
        raise ValueError("empty training catalog")
    return rows


def batch_indices(seed, step, count):
    if seed not in SEEDS or type(step) is not int or step < 0 or count < 4:
        raise ValueError("invalid sampling identity")
    result = []
    orders = {}
    for draw in range(step * 4, step * 4 + 4):
        epoch, offset = divmod(draw, count)
        if epoch not in orders:
            order = list(range(count))
            random.Random(seed + 1000003 * epoch).shuffle(order)
            orders[epoch] = order
        result.append(orders[epoch][offset])
    return result


def select_checkpoint(rows, model):
    if model not in MODELS:
        raise ValueError("unknown model")
    eligible = []
    for row in rows:
        if row.get("complete") is not True:
            continue
        step, objective = row["update"], row["development"]["loss"]
        if type(step) is not int or step not in CHECKPOINTS or isinstance(objective, bool):
            raise ValueError("checkpoint identity/objective malformed")
        if not math.isfinite(objective):
            raise ValueError("nonfinite development objective")
        eligible.append(row)
    if not eligible:
        return None
    return min(eligible, key=lambda row: (row["development"]["loss"], -row["update"]))


def reserve_run(cfg, prior, model, seed, freeze):
    validate_schedule(cfg)
    if {"model": model, "seed": seed} not in cfg["runs"]:
        raise ValueError("undeclared run")
    if any(x["model"] == model and x["seed"] == seed for x in prior):
        raise ValueError("run already consumed")
    if any(x["freeze"] != freeze or x.get("shared_integrity") != "PASS" for x in prior):
        raise ValueError("prior shared identity/integrity not established")
    if len(prior) >= 6 or sum(x["reserved_seconds"] for x in prior) + 3600 > 21600:
        raise ValueError("aggregate reservation exceeded")
    return [
        *prior,
        {
            "model": model,
            "seed": seed,
            "freeze": freeze,
            "reserved_seconds": 3600,
            "status": "STARTED",
        },
    ]


def restore_checkpoint(path, model, optimizer, scheduler, ema, torch, restore):
    # Qualified CUDA resume path; RNG restoration explicitly converts RNG tensors to CPU.
    saved = torch.load(path, map_location="cuda", weights_only=True)
    restore(model, optimizer, scheduler, ema, saved)
    if ema and any(
        shadow.device != parameter.device
        for shadow, parameter in zip(ema.shadow_params, model.parameters(), strict=True)
    ):
        raise ValueError("restored EMA/model device mismatch")
    return saved


def persist_complete(transaction, journal, checkpoint=None):
    transaction["phase"] = "COMPLETE"
    journal(transaction)
    if checkpoint is not None:
        checkpoint()
