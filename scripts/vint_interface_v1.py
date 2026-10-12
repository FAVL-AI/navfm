"""Native ViNT input/output adapter; no dataset scoring or checkpoint selection."""

import io
import math
from types import SimpleNamespace

from development_qualification_contracts_v1 import sha
from native_adaptation_contracts_v1 import evaluate_fenced

SPACING_M = 0.049994826316833496


def native_config(cfg):
    expected = dict(
        image_size=[85, 64], context_size=5, len_traj_pred=5, learn_angle=True, normalize=True
    )
    if any(cfg.get(k) != v for k, v in expected.items()):
        raise ValueError("native ViNT configuration mismatch")


def preprocess(histories, goals, cfg):
    import torch
    from vint_train.data.data_utils import img_path_to_data

    native_config(cfg)
    if len(histories) != len(goals) or not histories:
        raise ValueError("batch denominator mismatch")
    obs = []
    goal = []
    for history, image in zip(histories, goals, strict=True):
        if [x["tick"] for x in history] != list(range(6)):
            raise ValueError("chronological five-history plus current required")
        obs.append(
            torch.cat([img_path_to_data(io.BytesIO(x["png"]), cfg["image_size"]) for x in history])
        )
        goal.append(img_path_to_data(io.BytesIO(image), cfg["image_size"]))
    obs = torch.stack(obs)
    goal = torch.stack(goal)
    mean = obs.new_tensor([0.485, 0.456, 0.406])[:, None, None]
    std = obs.new_tensor([0.229, 0.224, 0.225])[:, None, None]
    obs = torch.cat([(x - mean) / std for x in torch.split(obs, 3, dim=1)], dim=1)
    goal = (goal - mean) / std
    if (
        list(obs.shape) != [len(histories), 18, 64, 85]
        or list(goal.shape) != [len(histories), 3, 64, 85]
        or not torch.isfinite(obs).all()
        or not torch.isfinite(goal).all()
    ):
        raise ValueError("native input shape/finite contract")
    return obs, goal


def strict_load(model, path, digest, trusted=False):
    from navfm.models.loader import extract_state_dict, load_checkpoint

    model.load_state_dict(
        extract_state_dict(load_checkpoint(path, trust_checkpoint=trusted, expected_sha256=digest)),
        strict=True,
    )


def predict_isolated(model, obs, goal):
    return evaluate_fenced(
        model, SimpleNamespace(state_dict=lambda: {}), None, lambda: model(obs, goal)
    )


def validate_outputs(distance, actions, batch_size):
    if (
        type(batch_size) is not int
        or batch_size < 1
        or len(distance) != batch_size
        or len(actions) != batch_size
    ):
        raise ValueError("native output batch denominator")
    for dp, trajectory in zip(distance, actions, strict=True):
        if len(dp) != 1 or len(trajectory) != 5:
            raise ValueError("native distance/horizon shape")
        for row in trajectory:
            if len(row) != 4 or any(
                type(v) not in (float, int) or not math.isfinite(v) for v in row
            ):
                raise ValueError("native XY/cos/sin output")
            if abs(math.hypot(row[2], row[3]) - 1) > 1e-5:
                raise ValueError("zero/nonunit heading vector")
        if type(dp[0]) not in (float, int) or not math.isfinite(dp[0]):
            raise ValueError("native temporal distance nonfinite")
    return [[[v * SPACING_M for v in row[:2]] for row in trajectory] for trajectory in actions]


def finalize_component(out, reservations, prior, ledger, started, writer=None, now=None):
    import time

    from offline_evaluation_contracts_v1 import atomic_snapshot

    writer = atomic_snapshot if writer is None else writer
    now = time.monotonic if now is None else now
    marker = out / "qualification_complete.json"

    def deadline():
        elapsed = now() - started
        ledger["occupied_wall_s"] = elapsed
        if elapsed < 0 or elapsed > 150:
            raise TimeoutError("component whole process deadline")

    try:
        deadline()
        ledger["artifacts"] = {
            str(p.relative_to(out)): sha(p)
            for p in out.rglob("*")
            if p.is_file() and p.name not in ("ledger.json", "qualification_complete.json")
        }
        deadline()
        writer(out / "ledger.json", ledger)
        deadline()
        if ledger["status"] == "PASS":
            digest = sha(out / "ledger.json")
            writer(
                marker,
                dict(
                    status="COMPLETE",
                    freeze=ledger["freeze"],
                    model=ledger["model"],
                    ledger_sha256=digest,
                ),
            )
            deadline()
            prior[-1].update(
                status="PASS",
                out=str(out),
                ledger_sha256=digest,
                marker_sha256=sha(marker),
                occupied_wall_s=ledger["occupied_wall_s"],
            )
        else:
            prior[-1].update(status="FAIL", occupied_wall_s=ledger["occupied_wall_s"])
        writer(reservations, prior)
        deadline()
    except BaseException as exc:
        ledger.update(status="FAIL", finalization_error_type=type(exc).__name__)
        prior[-1].update(status="FAIL")
        for key in ("ledger_sha256", "marker_sha256"):
            prior[-1].pop(key, None)
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            ledger["failure_cleanup_storage_error"] = True
        for path, value in [(out / "ledger.json", ledger), (reservations, prior)]:
            try:
                writer(path, value)
            except BaseException:
                ledger["failure_record_storage_error"] = True
        raise
