"""Actual split, normalization, optimizer/EMA mutation and reload fault controls."""

import ast
import copy
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from native_adaptation_contracts_v1 import (  # noqa: E402
    can_continue_independent,
    capture_rng,
    evaluate_fenced,
    restore_training_state,
    shared_metric,
    state_digest,
    validate_pair,
)


def pair():
    return {
        "trajectory": "train_a",
        "current": 8,
        "goal_trajectory": "train_a",
        "goal_time": 14,
        "negative": False,
    }


def files():
    return {f"{n}/{i}.jpg": "digest" for n in ["train_a", "train_b", "dev"] for i in range(20)} | {
        f"{n}/traj_data.pkl": "digest" for n in ["train_a", "train_b", "dev"]
    }


def test_native_context_and_label_endpoints_are_explicit():
    got = validate_pair(pair(), ["train_a", "train_b"], files(), 5, 8)
    assert got["history"] == [3, 4, 5, 6, 7, 8] and got["labels"] == list(range(9, 17))


@pytest.mark.parametrize("negative", [False, True])
def test_positive_and_negative_development_goal_leak_rejected(negative):
    p = pair()
    p.update(goal_trajectory="dev", negative=negative)
    with pytest.raises(ValueError, match="leakage"):
        validate_pair(p, ["train_a"], files(), 5, 8)


def test_history_anchor_leak_rejected_even_training_goal():
    p = pair()
    p["trajectory"] = "dev"
    with pytest.raises(ValueError, match="leakage"):
        validate_pair(p, ["train_a"], files(), 5, 8)


def test_nonadmitted_history_and_boolean_time_rejected():
    hashes = files()
    del hashes["train_a/3.jpg"]
    with pytest.raises(ValueError, match="unadmitted"):
        validate_pair(pair(), ["train_a"], hashes, 5, 5)
    p = pair()
    p["current"] = True
    with pytest.raises(ValueError, match="time"):
        validate_pair(p, ["train_a"], files(), 5, 5)


@pytest.mark.torch
@pytest.mark.parametrize("mutation", ["optimizer", "batchnorm", "ema"])
def test_development_fence_detects_actual_mutations(mutation):
    import torch

    model = torch.nn.Sequential(torch.nn.Linear(2, 2), torch.nn.BatchNorm1d(2))
    opt = torch.optim.Adam(model.parameters(), lr=0.01)

    class EMA:
        value = 0

        def state_dict(self):
            return {"updates": self.value}

    ema = EMA()

    def evaluate():
        if mutation == "optimizer":
            with torch.enable_grad():
                model(torch.ones(4, 2)).sum().backward()
                opt.step()
        elif mutation == "batchnorm":
            model.train()
            model(torch.ones(4, 2))
        else:
            ema.value += 1

    with pytest.raises(ValueError, match="mutated"):
        evaluate_fenced(model, opt, ema, evaluate)


@pytest.mark.torch
def test_development_eval_preserves_state_modes_and_rng():
    import torch

    model = torch.nn.Sequential(torch.nn.Linear(2, 2), torch.nn.BatchNorm1d(2))
    model.train()
    opt = torch.optim.Adam(model.parameters())
    rng = torch.get_rng_state().clone()
    before = state_digest(model.state_dict())
    evaluate_fenced(model, opt, None, lambda: model(torch.randn(4, 2)))
    assert before == state_digest(model.state_dict()) and model.training
    assert torch.equal(rng, torch.get_rng_state())


@pytest.mark.torch
def test_resume_restores_real_optimizer_and_rejects_missing_model_key():
    import torch

    model = torch.nn.Linear(2, 2)
    opt = torch.optim.Adam(model.parameters())
    sch = torch.optim.lr_scheduler.LambdaLR(opt, lambda _: 1.0)
    model(torch.ones(4, 2)).sum().backward()
    opt.step()
    sch.step()
    resume = copy.deepcopy(
        {
            "raw_model": model.state_dict(),
            "optimizer": opt.state_dict(),
            "scheduler": sch.state_dict(),
            "ema": None,
            **capture_rng(),
        }
    )
    with torch.no_grad():
        model.weight.add_(1)
    restore_training_state(model, opt, sch, None, resume)
    assert state_digest(model.state_dict()) == state_digest(resume["raw_model"])
    del resume["raw_model"]["bias"]
    with pytest.raises(RuntimeError, match="Missing key"):
        restore_training_state(model, opt, sch, None, resume)


@pytest.mark.torch
def test_common_metric_uses_same_five_physical_steps_and_masks():
    import torch

    labels = torch.zeros(3, 8, 2)
    pred = labels.clone()
    pred[0, :5, 0] = 1
    pred[1, :, 0] = 100
    pred[2, 5:, 0] = 999
    metric = shared_metric(pred, labels, torch.tensor([1, 0, 1]), 0.05)
    assert metric["ADE_m"] == pytest.approx(0.025) and metric["FDE_m"] == pytest.approx(0.025)
    assert metric["eligible_pairs"] == 2


@pytest.mark.torch
@pytest.mark.upstream
def test_nomad_native_nonclipped_delta_normalization_roundtrip(monkeypatch):
    import numpy as np
    import torch

    cfg = __import__("json").loads(
        (ROOT / "configs/train/native_adaptation_smoke_v1.json").read_text()
    )
    source = Path(cfg["upstream"]) / "train/vint_train/training/train_utils.py"
    tree = ast.parse(source.read_text())
    selected = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name in {"get_delta", "normalize_data", "unnormalize_data", "get_action"}
    ]
    module = types.ModuleType("vint_train.training.train_utils")
    module.__dict__.update(
        np=np,
        torch=torch,
        to_numpy=lambda t: t.detach().cpu().numpy(),
        from_numpy=lambda a: torch.from_numpy(a).float(),
        ACTION_STATS={"min": np.array([-0.2, -0.1]), "max": np.array([0.5, 0.3])},
    )
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), module.__dict__)
    monkeypatch.setitem(sys.modules, "vint_train", types.ModuleType("vint_train"))
    monkeypatch.setitem(sys.modules, "vint_train.training", types.ModuleType("vint_train.training"))
    monkeypatch.setitem(sys.modules, "vint_train.training.train_utils", module)
    from adapt_nomad_native_v1 import normalized_actions

    actions = torch.tensor([[[1.0, 0.2], [1.5, -0.5], [2.0, -0.1]]])
    norm = normalized_actions(actions)
    assert norm.max() > 1  # no silent clipping fitted to this corpus
    assert torch.allclose(module.get_action(norm), actions, atol=1e-5, rtol=0)
    with pytest.raises(ValueError, match="roundtrip"):
        normalized_actions(actions * float("nan"))


def test_launcher_has_exact_watchdog_and_source_frozen_contract():
    source = (ROOT / "scripts/run_native_adaptation_smoke_v1.py").read_text()
    tree = ast.parse(source)
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "run_bounded"
    ]
    assert (
        len(calls) == 1
        and isinstance(calls[0].args[-1], ast.Constant)
        and calls[0].args[-1].value == 150
    )


@pytest.mark.torch
def test_complete_rng_optimizer_scheduler_ema_restore_controls():
    import random

    import numpy as np
    import torch

    model = torch.nn.Linear(2, 2)
    opt = torch.optim.Adam(model.parameters(), lr=0.01)
    scheduler = torch.optim.lr_scheduler.StepLR(opt, step_size=1, gamma=0.5)

    class EMA:
        value = 4

        def state_dict(self):
            return {"updates": self.value}

        def load_state_dict(self, state):
            self.value = state["updates"]

    ema = EMA()
    model(torch.ones(4, 2)).sum().backward()
    opt.step()
    scheduler.step()
    resume = copy.deepcopy(
        {
            "raw_model": model.state_dict(),
            "optimizer": opt.state_dict(),
            "scheduler": scheduler.state_dict(),
            "ema": ema.state_dict(),
            **capture_rng(),
        }
    )
    expected_draws = (random.random(), float(np.random.rand()), torch.rand(3))
    if torch.cuda.is_available():
        expected_cuda = torch.rand(3, device="cuda")
    with torch.no_grad():
        model.weight.add_(2)
    opt.param_groups[0]["lr"] = 99
    scheduler.step()
    ema.value = 99
    random.seed(99)
    np.random.seed(99)
    torch.manual_seed(99)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(99)
    restore_training_state(model, opt, scheduler, ema, resume)
    assert random.random() == expected_draws[0] and float(np.random.rand()) == expected_draws[1]
    assert torch.equal(torch.rand(3), expected_draws[2])
    if torch.cuda.is_available():
        assert torch.equal(torch.rand(3, device="cuda"), expected_cuda)
    assert (
        ema.value == 4 and opt.param_groups[0]["lr"] == resume["optimizer"]["param_groups"][0]["lr"]
    )
    assert scheduler.state_dict() == resume["scheduler"]
    del resume["python_rng"]
    with pytest.raises(ValueError, match="RNG field missing"):
        restore_training_state(model, opt, scheduler, ema, resume)


@pytest.mark.parametrize("outcome", ["PASS", "FAIL"])
def test_independent_second_smoke_uses_shared_integrity_not_model_outcome(outcome):
    record = {
        "model": "gnm",
        "freeze": "commit",
        "status": outcome,
        "shared_integrity": "PASS",
        "child_reaped": True,
    }
    can_continue_independent(record, "commit")
    for key, value in [("shared_integrity", "FAIL"), ("child_reaped", False), ("freeze", "other")]:
        bad = record | {key: value}
        with pytest.raises(ValueError, match="shared integrity"):
            can_continue_independent(bad, "commit")
