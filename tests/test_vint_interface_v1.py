import copy
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from vint_interface_v1 import (
    native_config,
    predict_isolated,
    preprocess,
    strict_load,
    validate_outputs,
)


def native():
    return dict(
        image_size=[85, 64], context_size=5, len_traj_pred=5, learn_angle=True, normalize=True
    )


def output():
    return [[[1.0, 2.0, 1.0, 0.0] for _ in range(5)] for _ in range(2)]


def test_native_five_physical_xy_not_second_cumsum():
    result = validate_outputs([[6.0], [6.0]], output(), 2)
    assert result[0] == [[0.049994826316833496, 0.09998965263366699]] * 5


@pytest.mark.parametrize(
    "fault", ["context", "angle_config", "horizon", "heading_zero", "batch", "nonfinite"]
)
def test_native_interface_faults_rejected(fault):
    cfg = native()
    actions = output()
    distance = [[6.0], [6.0]]
    if fault == "context":
        cfg["context_size"] = 4
    if fault == "angle_config":
        cfg["learn_angle"] = False
    if fault == "horizon":
        actions[0].pop()
    if fault == "heading_zero":
        actions[0][0][2] = 0.0
    if fault == "batch":
        distance.pop()
    if fault == "nonfinite":
        actions[0][0][0] = float("nan")
    with pytest.raises(ValueError):
        native_config(cfg)
        validate_outputs(distance, actions, 2)


@pytest.mark.upstream
@pytest.mark.torch
def test_actual_native_preprocessing_context_and_normalization(monkeypatch):
    import torch
    from PIL import Image

    from navfm import upstream

    upstream.ensure_upstream()
    history = []
    for tick in range(6):
        stream = io.BytesIO()
        Image.new("RGB", (128, 96), (tick * 20, 40, 80)).save(stream, format="PNG")
        history.append(dict(tick=tick, png=stream.getvalue()))
    obs, goal = preprocess(
        [history, copy.deepcopy(history)], [history[-1]["png"], history[0]["png"]], native()
    )
    assert list(obs.shape) == [2, 18, 64, 85] and list(goal.shape) == [2, 3, 64, 85]
    assert torch.allclose(obs[0, 0], torch.full_like(obs[0, 0], (0 - 0.485) / 0.229))
    assert torch.allclose(obs[0, 15], torch.full_like(obs[0, 15], ((100 / 255) - 0.485) / 0.229))
    with pytest.raises(ValueError, match="chronological"):
        preprocess([list(reversed(history))], [history[0]["png"]], native())


@pytest.mark.torch
def test_actual_strict_checkpoint_failure_and_eval_rng_fence(tmp_path):
    import torch
    from development_qualification_contracts_v1 import sha
    from native_adaptation_contracts_v1 import capture_rng, state_digest

    model = torch.nn.Linear(2, 2)
    p = tmp_path / "toy.pth"
    torch.save(model.state_dict(), p)
    strict_load(model, p, sha(p))
    torch.save({"weight": model.weight.detach()}, p)
    with pytest.raises(RuntimeError):
        strict_load(model, p, sha(p))

    class NativeToy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer("counter", torch.zeros(1))
            self.mutate = False

        def forward(self, obs, goal):
            if self.mutate:
                self.counter.add_(1)
            return torch.rand(2, 1), torch.rand(2, 5, 4)

    toy = NativeToy()
    rng = state_digest(capture_rng())
    dp, ap = predict_isolated(toy, torch.zeros(2, 18, 64, 85), torch.zeros(2, 3, 64, 85))
    assert (
        state_digest(capture_rng()) == rng
        and toy.training
        and not dp.requires_grad
        and not ap.requires_grad
    )
    toy.mutate = True
    with pytest.raises(ValueError, match="mutated"):
        predict_isolated(toy, torch.zeros(2, 18, 64, 85), torch.zeros(2, 3, 64, 85))


def test_component_150_second_finalization_overrun_is_fail_closed(tmp_path):
    from offline_evaluation_contracts_v1 import atomic_snapshot
    from vint_interface_v1 import finalize_component

    registry = tmp_path.parent / (tmp_path.name + "-registry.json")
    prior = [dict(status="STARTED", model="vint-interface", freeze="test")]
    ledger = dict(status="PASS", model="vint-interface", freeze="test")
    clock = [149.0]

    def writer(path, value):
        atomic_snapshot(path, value)
        if path == registry:
            clock[0] = 150.01

    with pytest.raises(TimeoutError):
        finalize_component(tmp_path, registry, prior, ledger, 0, writer, lambda: clock[0])
    assert ledger["status"] == "FAIL" and prior[-1]["status"] == "FAIL"
    assert not (tmp_path / "qualification_complete.json").exists()
