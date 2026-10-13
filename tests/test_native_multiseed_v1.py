"""Finite budget, actual catalog sampling and development selection controls."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from native_multiseed_contracts_v1 import (
    CHECKPOINTS,
    batch_indices,
    catalog_from_lengths,
    select_checkpoint,
    validate_schedule,
)


def config():
    return {
        "seeds": [0, 11, 22],
        "checkpoint_updates": list(CHECKPOINTS),
        "caps": {
            "optimizer_updates": 4720,
            "batch_size": 4,
            "wall_seconds": 3600,
            "processes": 6,
            "aggregate_reserved_seconds": 21600,
        },
        "runs": [{"model": m, "seed": s} for s in [0, 11, 22] for m in ["gnm", "nomad"]],
    }


def test_ceiling_no_extension_and_exact_run_population():
    c = config()
    validate_schedule(c)
    for field in c["caps"]:
        altered = copy.deepcopy(c)
        altered["caps"][field] += 1
        with pytest.raises(ValueError, match="budget"):
            validate_schedule(altered)
    c["runs"].append({"model": "gnm", "seed": 33})
    with pytest.raises(ValueError, match="identities"):
        validate_schedule(c)


def test_catalog_full_anchors_and_negative_partition_fence():
    names = ["train_a", "train_b"]
    lengths = {n: 22 for n in names}
    hashes = {f"{n}/{i}.jpg": "hash" for n in names for i in range(22)}
    hashes.update({f"{n}/traj_data.pkl": "hash" for n in names})
    rows = catalog_from_lengths(names, lengths, hashes)
    assert len(rows) == 36 and {p["negative"] for p in rows} == {True, False}
    assert all(p["current"] >= 5 and p["current"] + 8 < 22 for p in rows)
    with pytest.raises(ValueError, match="partition"):
        catalog_from_lengths(names, {**lengths, "dev": 22}, hashes)
    del hashes["train_b/11.jpg"]
    with pytest.raises(ValueError, match="unadmitted"):
        catalog_from_lengths(names, lengths, hashes)


def test_sampler_cycles_and_resume_identity_without_native_rng():
    count = 12
    first = [i for step in range(3) for i in batch_indices(11, step, count)]
    assert sorted(first) == list(range(count))
    assert batch_indices(11, 3, count) == batch_indices(11, 3, count)
    assert first != [i for step in range(3) for i in batch_indices(22, step, count)]
    with pytest.raises(ValueError):
        batch_indices(33, 0, count)


def test_selection_uses_development_not_train_latest_tie():
    rows = [
        {"update": 236, "complete": True, "train_loss": 0, "development": {"loss": 2}},
        {"update": 472, "complete": True, "train_loss": 99, "development": {"loss": 1}},
        {"update": 1180, "complete": False, "development": {"loss": 0}},
        {"update": 2360, "complete": True, "development": {"loss": 1}},
    ]
    assert select_checkpoint(rows, "nomad")["update"] == 2360
    rows[-1]["development"]["loss"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        select_checkpoint(rows, "gnm")
    assert select_checkpoint([{"complete": False}], "gnm") is None


def test_failed_reservation_consumed_and_shared_failure_blocks():
    from native_multiseed_contracts_v1 import reserve_run

    c = config()
    prior = reserve_run(c, [], "gnm", 0, "freeze")
    assert prior[0]["reserved_seconds"] == 3600
    with pytest.raises(ValueError, match="consumed"):
        reserve_run(c, prior, "gnm", 0, "freeze")
    prior[0].update(status="TIMEOUT", shared_integrity="NOT_ESTABLISHED")
    with pytest.raises(ValueError, match="integrity"):
        reserve_run(c, prior, "nomad", 0, "freeze")
    prior[0].update(status="MODEL_FAIL", shared_integrity="PASS")
    assert len(reserve_run(c, prior, "nomad", 0, "freeze")) == 2


def test_checkpoint_cuda_shadow_continuation_and_device_rejection():
    from types import SimpleNamespace

    from native_multiseed_contracts_v1 import restore_checkpoint

    parameter = SimpleNamespace(device="cuda")
    model = SimpleNamespace(parameters=lambda: iter([parameter]))
    ema = SimpleNamespace(shadow_params=[])
    calls = []

    def load(path, **kwargs):
        calls.append(kwargs)
        return {"shadow": SimpleNamespace(device=kwargs["map_location"])}

    def restore(model, optimizer, scheduler, target, saved):
        target.shadow_params = [saved["shadow"]]

    restore_checkpoint("resume", model, None, None, ema, SimpleNamespace(load=load), restore)
    assert calls == [{"map_location": "cuda", "weights_only": True}]
    assert ema.shadow_params[0].device == parameter.device

    def wrong_load(path, **kwargs):
        return {"shadow": SimpleNamespace(device="cpu")}

    with pytest.raises(ValueError, match="device mismatch"):
        restore_checkpoint(
            "resume", model, None, None, ema, SimpleNamespace(load=wrong_load), restore
        )


def test_completed_transaction_durable_before_checkpoint_failure():
    from native_multiseed_contracts_v1 import persist_complete

    events = []
    transaction = {"step": 236, "phase": "EMA_APPLIED"}

    def journal(row):
        events.append(dict(row))

    def checkpoint():
        assert events == [{"step": 236, "phase": "COMPLETE"}]
        raise TimeoutError("checkpoint interrupted")

    with pytest.raises(TimeoutError):
        persist_complete(transaction, journal, checkpoint)
    assert events[0]["phase"] == "COMPLETE"
