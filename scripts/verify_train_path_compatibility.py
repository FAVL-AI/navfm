"""TRAIN_PATH_COMPATIBILITY -- can each model actually train on our data?

Loader compatibility proves a dataset can be *read*. It does not prove the
training pipeline can form labels from it, execute the model, compute the
model's own losses and backpropagate. Those are different claims, and the gap
between them is where a dataset that opens cleanly turns out to be untrainable.

This runs, per model, on a fresh Yahboom Option 1 trajectory:

    official dataset class -> official sample construction -> DataLoader/collate
      -> one genuine batch -> model.train() -> forward -> the model's OWN loss
      -> finite scalar -> backward -> finite non-zero gradients -> optimizer.step()
      -> a named parameter measurably changed -> released checkpoint untouched

Three principles decide what this file does, each bought with a defect:

**The losses are imported or transcribed from the pinned source, never invented.**
A loss written to make ``backward()`` succeed proves the harness works. GNM and
ViNT call upstream ``_compute_losses`` directly. NoMaD's *training* loss has no
standalone function -- it is inline in ``train_nomad`` -- so it is transcribed
line-for-line with its source range recorded, including the parts that are easy
to skip: action deltas, normalisation against ``ACTION_STATS``, the real DDPM
scheduler, goal masking, and the masked reductions. An earlier draft of this file
used ``noisy = actions + noise * 0.1`` and a plain MSE. It passed. It was wrong in
every respect, which is the entire argument for this rule.

**Verify the effect, not the invocation.** ``optimizer.step()`` returning is not
evidence the model changed, exactly as a commanded 0.45 m/s was not evidence the
Yahboom moved -- it had moved 0.001 m. Both are the same error. So this measures
per-parameter deltas, counts gradients that are finite *and* non-zero, and names
every tensor the step did not move.

**A check that cannot fail certifies nothing.** Each model is also run against a
deliberately corrupted in-memory batch that the official path must reject. A
harness that passes our data and cannot distinguish broken data is not evidence.

The result is called TRAIN_PATH_COMPATIBILITY, **never** TRAINING_COMPLETED. One
optimizer step on one batch proves the path is connected. It is not a training
run, produces no model, admits no data, and makes no claim about performance.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pickle
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

DEFAULT_TRAJ = Path.home() / "navfm-data" / "simulation_development" / "pilot_0002"
OUT = REPO / "gates" / "compatibility"
FORENSICS = REPO / "gates" / "forensics"

#: Declared before the first run, per the standing rule that a tolerance is
#: frozen in advance. This is the engineering tolerance already in use for R7.
REPEATABILITY_RTOL = 1e-5
REPEATABILITY_ATOL = 1e-6

#: PART D -- where each model's training path actually lives in the pinned tree.
#: Recorded so a reader can check the transcription rather than trust it.
UP = "third_party/visualnav-transformer/train/vint_train"
CROSSWALK: dict[str, dict[str, Any]] = {
    "_shared": {
        "dataset_class": f"{UP}/data/vint_dataset.py::ViNT_Dataset",
        "sample_index_builder": f"{UP}/data/vint_dataset.py::_build_index (L205-225)",
        "index_population_rule": f"{UP}/data/vint_dataset.py L219-221",
        "goal_sampler": f"{UP}/data/vint_dataset.py::_sample_goal (L227-)",
        "collate": "torch.utils.data.DataLoader default_collate (no custom collate upstream)",
        "batch_tuple": "(obs_image, goal_image, action_label, dist_label, goal_pos, "
                       "dataset_index, action_mask)",
    },
    "gnm": {
        "model_class": f"{UP}/models/gnm/gnm.py::GNM",
        "train_loop": f"{UP}/training/train_utils.py::train (L166-309)",
        "transform_and_forward": f"{UP}/training/train_utils.py L251-257",
        "loss_fn": f"{UP}/training/train_utils.py::_compute_losses (L36-96)",
        "loss_call": f"{UP}/training/train_utils.py L267-275",
        "total_loss": "alpha * 1e-2 * dist_loss + (1 - alpha) * action_loss",
        "alpha": 0.5,
        "alpha_source": "train/config/gnm.yaml:31",
        "backward_step": f"{UP}/training/train_utils.py L277-278",
        "optimizer": "AdamW (train.py); lr overridden to 1e-5 for this smoke path only",
    },
    "vint": {
        "model_class": f"{UP}/models/vint/vint.py::ViNT",
        "train_loop": f"{UP}/training/train_utils.py::train (L166-309)",
        "transform_and_forward": f"{UP}/training/train_utils.py L251-257",
        "loss_fn": f"{UP}/training/train_utils.py::_compute_losses (L36-96)",
        "loss_call": f"{UP}/training/train_utils.py L267-275",
        "total_loss": "alpha * 1e-2 * dist_loss + (1 - alpha) * action_loss",
        "alpha": 0.5,
        "alpha_source": "train/config/vint.yaml:39",
        "backward_step": f"{UP}/training/train_utils.py L277-278",
        "optimizer": "AdamW (train.py); lr overridden to 1e-5 for this smoke path only",
    },
    "nomad": {
        "model_class": f"{UP}/models/nomad/nomad.py::NoMaD "
                       f"(+ NoMaD_ViNT, DenseNetwork, ConditionalUnet1D)",
        "train_loop": f"{UP}/training/train_utils.py::train_nomad (L525-720)",
        "training_loss_is_inline": True,
        "loss_source_range": f"{UP}/training/train_utils.py L613-657",
        "note": "_compute_losses_nomad (L447-524) is the LOGGING/eval path -- it runs full "
                "diffusion sampling via model_output(). The training objective is the inline "
                "block, and that is what is transcribed here.",
        "action_preprocessing": f"{UP}/training/train_utils.py::get_delta (L945) then "
                                f"normalize_data (L933) against ACTION_STATS",
        "noise_scheduler": "diffusers DDPMScheduler(num_train_timesteps=num_diffusion_iters, "
                           "beta_schedule='squaredcos_cap_v2', clip_sample=True, "
                           "prediction_type='epsilon') -- train/train.py L214-219",
        "goal_masking": "goal_mask = (rand(B) < goal_mask_prob).long() -- L614",
        "total_loss": "alpha * dist_loss + (1 - alpha) * diffusion_loss",
        "alpha": 1e-4,
        "alpha_source": "train/config/nomad.yaml:47",
        "optimizer": "AdamW (train.py); lr overridden to 1e-5 for this smoke path only",
    },
}


def digest(obj: Any) -> str:
    import torch

    if isinstance(obj, torch.Tensor):
        return hashlib.sha256(obj.detach().cpu().contiguous().numpy().tobytes()).hexdigest()[:16]
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_trajectory(traj: Path, tag: str) -> tuple[Path, Path, Path]:
    """A private copy per build: the reference loader will not reopen an LMDB
    environment already open in this process. A harness constraint, not a
    property of the data."""
    tmp = Path(tempfile.mkdtemp(prefix=f"navfm-tp-{tag}-"))
    data = tmp / "data"
    (data / traj.name).mkdir(parents=True)
    for f in [*traj.glob("*.jpg"), traj / "traj_data.pkl"]:
        shutil.copy2(f, data / traj.name / f.name)
    split = tmp / "split"
    split.mkdir()
    (split / "traj_names.txt").write_text(traj.name + "\n")
    return tmp, data, split


def make_dataset(model: str, traj: Path, tag: str):
    from navfm import upstream

    cfg = upstream.model_config(model)
    opts = upstream.dataset_options(cfg, "go_stanford")
    tmp, data, split = stage_trajectory(traj, tag)
    ds = upstream.build_dataset(
        dataset_name="go_stanford", data_folder=str(data), split_folder=str(split),
        cfg=cfg, end_slack=opts["end_slack"], waypoint_spacing=opts["waypoint_spacing"],
        negative_mining=opts["negative_mining"], goals_per_obs=opts["goals_per_obs"],
    )
    return ds, cfg, opts, tmp


# ---------------------------------------------------------------- PART B / C --
def index_trace(traj: Path, models: list[str]) -> dict[str, Any]:
    """Enumerate every candidate index for every model, from the real dataset.

    The upstream population rule (``_build_index`` L219-221) has no rejection
    branch: every value in ``range(begin_time, end_time)`` is appended. So the
    honest thing to record is that ``rejected == 0`` and the count is fixed
    entirely by where the range starts and stops -- not to invent a filter that
    does not exist in the source.
    """
    traj_len = len(pickle.loads((traj / "traj_data.pkl").read_bytes())["yaw"])
    rows: list[dict[str, Any]] = []
    pops: dict[str, Any] = {}

    for model in models:
        ds, cfg, opts, tmp = make_dataset(model, traj, f"idx-{model}")
        try:
            ws, slack = opts["waypoint_spacing"], opts["end_slack"]
            cs, lp = cfg["context_size"], cfg["len_traj_pred"]
            begin, end = cs * ws, traj_len - slack - lp * ws
            accepted = {int(t) for _, t, _ in ds.index_to_data}
            # Every frame is a conceivable observation; the rule admits a window.
            for t in range(traj_len):
                valid = begin <= t < end
                if valid:
                    reason = ""
                elif t < begin:
                    reason = f"needs {cs} context frames behind; earliest is {begin}"
                else:
                    reason = f"needs {lp} horizon frames ahead; last is {end - 1}"
                ctx = list(range(t - cs * ws, t + 1, ws)) if valid else []
                act = list(range(t, t + lp * ws + 1, ws)) if valid else []
                max_goal = min(cfg.get("max_dist_cat", opts.get("max_dist_cat", 20)) * ws,
                               traj_len - t - 1) if valid else None
                rows.append({
                    "trajectory_id": traj.name, "candidate_index": t, "model": model,
                    "obs_indices": ",".join(map(str, ctx)),
                    "goal_index": f"sampled in (0,{max_goal}]" if valid else "",
                    "action_indices": ",".join(map(str, act)),
                    "distance_index": t if valid else "",
                    "goal_mask": "random per batch (NoMaD only)" if model == "nomad" else "n/a",
                    "valid": valid,
                    "rejection_reason": reason,
                    "source_file": f"{UP}/data/vint_dataset.py",
                    "source_line": "219-221",
                })
            in_range = {t for t in range(traj_len) if begin <= t < end}
            pops[model] = {
                "trajectory_frame_count": traj_len,
                "context_size": cs, "action_horizon": lp,
                "waypoint_spacing": ws, "end_slack": slack,
                "begin_time": begin, "end_time": end,
                "begin_rule": "context_size * waypoint_spacing",
                "end_rule": "traj_len - end_slack - len_traj_pred * waypoint_spacing",
                "candidate_population": traj_len,
                "accepted_population": len(accepted),
                "rejected_population": traj_len - len(accepted),
                "conservation_holds": traj_len == len(accepted) + (traj_len - len(accepted)),
                "predicted_effective": max(0, end - begin),
                "actual_effective": len(ds),
                "predicted_equals_actual": max(0, end - begin) == len(ds),
                "accepted_indices_match_rule": accepted == in_range,
                "first_accepted": min(accepted), "last_accepted": max(accepted),
                "no_rejection_branch_in_source": True,
                "source": f"{UP}/data/vint_dataset.py L219-221",
            }
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    OUT.mkdir(parents=True, exist_ok=True)
    FORENSICS.mkdir(parents=True, exist_ok=True)
    csv_path = FORENSICS / "nomad_sample_index_trace.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for m, p in pops.items():
        (OUT / f"{m}_sample_population.json").write_text(json.dumps(p, indent=2) + "\n")

    # Which candidates differ, and in which direction. This is the actual answer
    # to "which pair disappears" -- and it is not simply a loss.
    if {"vint", "nomad"} <= set(pops):
        v = set(range(pops["vint"]["begin_time"], pops["vint"]["end_time"]))
        n = set(range(pops["nomad"]["begin_time"], pops["nomad"]["end_time"]))
        pops["_difference"] = {
            "nomad_gains": sorted(n - v), "nomad_loses": sorted(v - n),
            "net": len(n) - len(v),
            "explanation": (
                f"NoMaD gains indices {sorted(n - v)} at the front because it needs only "
                f"{pops['nomad']['context_size']} context frames against "
                f"{pops['vint']['context_size']}, and loses {sorted(v - n)} at the back "
                f"because it predicts {pops['nomad']['action_horizon']} steps ahead against "
                f"{pops['vint']['action_horizon']}. Net {len(n) - len(v)}."
            ),
        }
    return {"populations": pops, "index_trace_csv": str(csv_path.relative_to(REPO))}


# ------------------------------------------------------------ PARTS E - O --
def _tensor_report(name: str, t: Any) -> dict[str, Any]:
    import torch

    if not isinstance(t, torch.Tensor):
        return {"name": name, "type": type(t).__name__}
    f = t.float()
    return {
        "name": name, "shape": list(t.shape), "dtype": str(t.dtype), "device": str(t.device),
        "min": float(f.min()) if t.numel() else None,
        "max": float(f.max()) if t.numel() else None,
        "finite": bool(torch.isfinite(f).all()), "digest": digest(t),
    }


def build_net(model: str, cfg: dict[str, Any]):
    from navfm import upstream

    if model == "nomad":
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_r6", REPO / "scripts" / "verify_r6_strict_load.py")
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod._build_nomad(cfg)
    return upstream.build_model(model)


def load_checkpoint(net: Any, ckpt: Path) -> int:
    import torch

    sd = torch.load(ckpt, map_location="cpu", weights_only=False)
    sd = sd.get("model", sd) if isinstance(sd, dict) else sd
    if hasattr(sd, "state_dict"):
        sd = sd.state_dict()
    sd = {k[len("module."):] if k.startswith("module.") else k: v for k, v in sd.items()}
    net.load_state_dict(sd, strict=True)
    return len(sd)


def official_loss(model: str, net: Any, batch: Any, cfg: dict[str, Any], *, seed: int):
    """Return (total, components, extra_state). Upstream implementation only.

    GNM/ViNT import ``_compute_losses`` directly. NoMaD transcribes the inline
    training block from ``train_nomad`` L613-657, because upstream provides no
    callable for it -- ``_compute_losses_nomad`` is the eval/logging path that
    runs full diffusion sampling, which is a different computation.
    """
    import torch
    import torch.nn.functional as F
    from vint_train.training.train_utils import _compute_losses

    from navfm import upstream

    transform = upstream.reference_transform()
    obs_image, goal_image, action_label, dist_label, _goal_pos, _ds_idx, action_mask = batch

    obs_split = torch.split(obs_image, 3, dim=1)
    obs = torch.cat([transform(o) for o in obs_split], dim=1)
    goal = transform(goal_image)
    extra: dict[str, Any] = {}

    if model in ("gnm", "vint"):
        dist_pred, action_pred = net(obs, goal)
        losses = _compute_losses(
            dist_label=dist_label, action_label=action_label,
            dist_pred=dist_pred, action_pred=action_pred,
            alpha=CROSSWALK[model]["alpha"], learn_angle=cfg["learn_angle"],
            action_mask=action_mask,
        )
        extra["outputs"] = [_tensor_report("dist_pred", dist_pred),
                            _tensor_report("action_pred", action_pred)]
        return losses["total_loss"], {k: v for k, v in losses.items()}, extra

    # -- NoMaD: transcribed from train_utils.py L613-657 -----------------------
    from diffusers.schedulers.scheduling_ddpm import DDPMScheduler
    from vint_train.training.train_utils import ACTION_STATS, get_delta, normalize_data

    torch.manual_seed(seed)
    scheduler = DDPMScheduler(
        num_train_timesteps=int(cfg["num_diffusion_iters"]),
        beta_schedule="squaredcos_cap_v2", clip_sample=True, prediction_type="epsilon",
    )
    B = action_label.shape[0]
    goal_mask_prob = float(cfg.get("goal_mask_prob", 0.5))
    goal_mask = (torch.rand((B,)) < goal_mask_prob).long()
    cond = net("vision_encoder", obs_img=obs, goal_img=goal, input_goal_mask=goal_mask)

    distance = dist_label.float()
    deltas = get_delta(action_label.numpy() if hasattr(action_label, "numpy") else action_label)
    naction = torch.from_numpy(normalize_data(deltas, ACTION_STATS)).float()
    assert naction.shape[-1] == 2, "action dim must be 2"

    dist_pred = net("dist_pred_net", obsgoal_cond=cond)
    dist_loss = F.mse_loss(dist_pred.squeeze(-1), distance)
    dist_loss = (dist_loss * (1 - goal_mask.float())).mean() / (
        1e-2 + (1 - goal_mask.float()).mean())

    noise = torch.randn(naction.shape)
    timesteps = torch.randint(0, scheduler.config.num_train_timesteps, (B,)).long()
    noisy_action = scheduler.add_noise(naction, noise, timesteps)
    noise_pred = net("noise_pred_net", sample=noisy_action, timestep=timesteps, global_cond=cond)

    def action_reduce(unreduced: torch.Tensor) -> torch.Tensor:
        while unreduced.dim() > 1:
            unreduced = unreduced.mean(dim=-1)
        assert unreduced.shape == action_mask.shape, f"{unreduced.shape} != {action_mask.shape}"
        return (unreduced * action_mask).mean() / (action_mask.mean() + 1e-2)

    diffusion_loss = action_reduce(F.mse_loss(noise_pred, noise, reduction="none"))
    alpha = CROSSWALK["nomad"]["alpha"]
    total = alpha * dist_loss + (1 - alpha) * diffusion_loss
    extra["diffusion_state"] = {
        "seed": seed, "timesteps": timesteps.tolist(),
        "noise_shape": list(noise.shape), "noise_digest": digest(noise),
        "noisy_action_digest": digest(noisy_action),
        "goal_mask": goal_mask.tolist(), "goal_mask_prob": goal_mask_prob,
        "scheduler": CROSSWALK["nomad"]["noise_scheduler"],
        "naction_digest": digest(naction),
    }
    extra["outputs"] = [_tensor_report("dist_pred", dist_pred),
                        _tensor_report("noise_pred", noise_pred)]
    return total, {"dist_loss": dist_loss, "diffusion_loss": diffusion_loss,
                   "total_loss": total}, extra


def one_batch(model: str, traj: Path, *, seed: int, run_label: str) -> dict[str, Any]:
    import numpy as np
    import torch
    from vint_train.data.vint_dataset import navfm_seed_sampling

    rec: dict[str, Any] = {"model": model, "run": run_label, "seed": seed}
    ckpt = REPO / "checkpoints" / f"{model}.pth"
    rec["checkpoint_sha256_before"] = file_sha256(ckpt)

    navfm_seed_sampling(seed)
    torch.manual_seed(seed)
    np.random.seed(seed)

    ds, cfg, opts, tmp = make_dataset(model, traj, f"{model}-{run_label}")
    try:
        rec["sample_count"] = len(ds)
        rec["sample_indices"] = [int(t) for _, t, _ in ds.index_to_data][:8]
        rec["resolved_config"] = {
            k: cfg.get(k) for k in (
                "image_size", "context_size", "context_type", "len_traj_pred", "learn_angle",
                "normalize", "goal_type", "obs_encoder", "obs_encoding_size", "vision_encoder",
                "encoding_size", "num_diffusion_iters", "goal_mask_prob", "down_dims",
                "cond_predict_scale", "mha_num_attention_heads", "mha_num_attention_layers",
            ) if k in cfg
        }
        rec["dataset_options"] = dict(opts)
        rec["metric_waypoint_spacing_m"] = __import__(
            "navfm.upstream", fromlist=["x"]).metric_waypoint_spacing("go_stanford")

        loader = torch.utils.data.DataLoader(ds, batch_size=4, shuffle=False, num_workers=0)
        batch = next(iter(loader))
        names = ["obs_image", "goal_image", "action_label", "dist_label",
                 "goal_pos", "dataset_index", "action_mask"]
        rec["batch"] = [_tensor_report(n, t) for n, t in zip(names, batch, strict=True)]
        rec["batch_all_finite"] = all(
            b.get("finite", True) for b in rec["batch"] if "finite" in b)

        net = build_net(model, cfg)
        rec["checkpoint_tensors"] = load_checkpoint(net, ckpt)
        net.train()
        rec["training_mode"] = net.training

        watched = [n for n, _ in net.named_parameters()][:6]
        before = {n: p.detach().clone() for n, p in net.named_parameters() if p.requires_grad}
        rec["watched_before"] = [
            {"name": n, "shape": list(before[n].shape),
             "norm": float(before[n].norm()), "digest": digest(before[n])} for n in watched
        ]

        opt = torch.optim.AdamW(net.parameters(), lr=1e-5)
        total, comps, extra = official_loss(model, net, batch, cfg, seed=seed)
        rec.update(extra)
        rec["losses"] = {k: float(v) for k, v in comps.items()}
        rec["losses_finite"] = {k: bool(np.isfinite(float(v))) for k, v in comps.items()}
        rec["all_losses_finite"] = all(rec["losses_finite"].values())
        rec["total_loss_is_scalar"] = total.dim() == 0

        opt.zero_grad()
        total.backward()

        trainable = [(n, p) for n, p in net.named_parameters() if p.requires_grad]
        with_grad = [(n, p) for n, p in trainable if p.grad is not None]
        nonzero = [n for n, p in with_grad if float(p.grad.abs().sum()) > 0]
        nan = [n for n, p in with_grad if bool(torch.isnan(p.grad).any())]
        inf = [n for n, p in with_grad if bool(torch.isinf(p.grad).any())]
        gnorm = float(torch.sqrt(sum((p.grad.detach() ** 2).sum() for _, p in with_grad))) \
            if with_grad else 0.0
        rec["gradients"] = {
            "parameters_total": len(list(net.named_parameters())),
            "parameters_trainable": len(trainable),
            "parameters_with_gradient": len(with_grad),
            "parameters_with_nonzero_gradient": len(nonzero),
            "parameters_with_nan_gradient": len(nan),
            "parameters_with_inf_gradient": len(inf),
            "gradient_global_norm": gnorm,
        }

        opt.step()

        unchanged = [n for n, p in net.named_parameters()
                     if p.requires_grad and torch.equal(before[n], p.detach())]
        changed = len(before) - len(unchanged)
        rec["parameters_changed_by_step"] = changed
        rec["parameters_total_trainable"] = len(before)
        # Which tensors the step did not move. An unused head is expected to be
        # still, but it must be named -- "most of them moved" is how a genuinely
        # disconnected branch survives review.
        sd_now = net.state_dict()
        dead = sum(int(sd_now[n].numel()) for n in unchanged if n in sd_now)
        tot = sum(int(v.numel()) for v in sd_now.values() if hasattr(v, "numel"))
        rec["parameters_unchanged"] = {
            "count": len(unchanged), "names": unchanged,
            "elements": dead, "checkpoint_elements": tot,
            "fraction_of_checkpoint": round(dead / tot, 6) if tot else 0.0,
            "megabytes_fp32": round(dead * 4 / 1e6, 2),
        }
        rec["watched_after"] = [
            {"name": n, "norm": float(dict(net.named_parameters())[n].norm()),
             "digest": digest(dict(net.named_parameters())[n].detach()),
             "changed": n not in unchanged} for n in watched
        ]

        rec["checkpoint_sha256_after"] = file_sha256(ckpt)
        rec["checkpoint_unchanged"] = (
            rec["checkpoint_sha256_before"] == rec["checkpoint_sha256_after"])

        rec["result"] = "PASS" if (
            rec["batch_all_finite"] and rec["all_losses_finite"] and rec["total_loss_is_scalar"]
            and rec["training_mode"] and not nan and not inf
            and rec["gradients"]["parameters_with_nonzero_gradient"] > 0
            and changed > 0 and rec["checkpoint_unchanged"]
        ) else "FAIL"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    rec["claim_boundary"] = (
        "TRAIN_PATH_COMPATIBILITY only. One optimizer step on one batch proves the official "
        "training path is connected for this data. NOT a training run, NOT fine-tuning, NOT "
        "dataset admission, NOT a performance claim."
    )
    rec["admission_status"] = "NOT_ADMITTED"
    rec["engineering_train_path_smoke_allowed"] = True
    return rec


# ------------------------------------------------------------------ PART P --
def invalid_fixture(model: str, traj: Path, *, seed: int) -> dict[str, Any]:
    """Prove the path rejects a batch it should reject.

    The corruption is a misshapen action label, in memory only -- never on a
    pilot file. Upstream asserts ``action_pred.shape == action_label.shape``
    (``_compute_losses`` L59) and, for NoMaD, ``naction.shape[-1] == 2`` and the
    action_mask shape agreement inside ``action_reduce``. A harness that accepts
    our data and cannot reject this is not a discriminating check.
    """
    import torch

    rec: dict[str, Any] = {"model": model, "corruption": "action_label truncated horizon"}
    ds, cfg, _opts, tmp = make_dataset(model, traj, f"{model}-invalid")
    try:
        loader = torch.utils.data.DataLoader(ds, batch_size=4, shuffle=False)
        batch = list(next(iter(loader)))
        rec["valid_action_shape"] = list(batch[2].shape)
        batch[2] = batch[2][:, :-1, :].contiguous()  # drop one horizon step
        rec["corrupted_action_shape"] = list(batch[2].shape)
        net = build_net(model, cfg)
        load_checkpoint(net, REPO / "checkpoints" / f"{model}.pth")
        net.train()
        try:
            official_loss(model, net, tuple(batch), cfg, seed=seed)
            rec["rejected"] = False
            rec["result"] = "FAIL"
            rec["detail"] = "the official path accepted a malformed batch"
        except (AssertionError, RuntimeError, ValueError, IndexError) as exc:
            rec["rejected"] = True
            rec["result"] = "PASS"
            rec["rejection"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rec


# ------------------------------------------------------------------ PART Q --
def repeatability(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    diffs = {}
    worst_abs = worst_rel = 0.0
    for k, va in a.get("losses", {}).items():
        vb = b.get("losses", {}).get(k)
        if vb is None:
            continue
        d = abs(va - vb)
        r = d / max(abs(va), 1e-12)
        diffs[k] = {"a": va, "b": vb, "abs": d, "rel": r}
        worst_abs, worst_rel = max(worst_abs, d), max(worst_rel, r)
    same_idx = a.get("sample_indices") == b.get("sample_indices")
    same_batch = [x.get("digest") for x in a.get("batch", [])] == \
                 [x.get("digest") for x in b.get("batch", [])]
    within = worst_abs <= REPEATABILITY_ATOL + REPEATABILITY_RTOL * max(
        abs(v["a"]) for v in diffs.values()) if diffs else False
    return {
        "sample_indices_identical": same_idx,
        "batch_digests_identical": same_batch,
        "loss_differences": diffs,
        "max_abs_difference": worst_abs, "max_rel_difference": worst_rel,
        "declared_tolerance": {"rtol": REPEATABILITY_RTOL, "atol": REPEATABILITY_ATOL,
                               "source": "existing engineering tolerance, R7; not newly invented"},
        "within_tolerance": bool(within),
        "result": "PASS" if (same_idx and same_batch and within) else "FAIL",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trajectory", default=str(DEFAULT_TRAJ))
    ap.add_argument("--model", action="append", choices=["gnm", "vint", "nomad"])
    ap.add_argument("--extra-syspath", action="append", default=[])
    ap.add_argument("--seed", type=int, default=20260813)
    args = ap.parse_args()

    for p in [*args.extra_syspath, str(REPO / "third_party" / "diffusion_policy")]:
        if p not in sys.path:
            sys.path.insert(0, p)

    traj = Path(args.trajectory)
    if not (traj / "traj_data.pkl").is_file():
        print(f"REFUSED: no trajectory at {traj}", file=sys.stderr)
        return 2

    import numpy
    import torch

    from navfm import upstream

    models = args.model or ["gnm", "vint", "nomad"]
    OUT.mkdir(parents=True, exist_ok=True)
    FORENSICS.mkdir(parents=True, exist_ok=True)

    traj_digest = hashlib.sha256()
    # The Option 1 payload only: numbered frames plus traj_data.pkl. Sibling
    # directories (raw capture, provenance) are not part of what the loaders read.
    for f in sorted([*traj.glob("*.jpg"), traj / "traj_data.pkl"]):
        traj_digest.update(f.name.encode())
        traj_digest.update(f.read_bytes())

    out: dict[str, Any] = {
        "check": "TRAIN_PATH_COMPATIBILITY",
        "not_a_claim_of": "TRAINING_COMPLETED",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "navfm_commit": __import__("subprocess").run(
                ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                text=True).stdout.strip(),
            "upstream_commit": upstream.upstream_commit(),
            "python": sys.version.split()[0], "torch": torch.__version__,
            "numpy": numpy.__version__, "device": "cpu",
        },
        "trajectory": {"path": str(traj), "name": traj.name,
                       "content_digest": traj_digest.hexdigest()[:32]},
        "stage": "SIMULATION_DEVELOPMENT", "admission_status": "NOT_ADMITTED",
        "training_allowed_formal": False, "engineering_train_path_smoke_allowed": True,
        "training_path_crosswalk": CROSSWALK,
    }

    print("TRAIN-PATH COMPATIBILITY — official path, forward + loss + backward + step")
    print("=" * 76)
    print(f"  trajectory {traj.name}  digest {out['trajectory']['content_digest'][:16]}")
    print("\n  PART B/C — sample index trace and population")
    out["index_trace"] = index_trace(traj, models)
    for m in models:
        p = out["index_trace"]["populations"][m]
        print(f"    {m:6} accepted {p['actual_effective']:>3}  "
              f"range [{p['begin_time']},{p['end_time']})  "
              f"predicted {p['predicted_effective']}  "
              f"rule-match {p['accepted_indices_match_rule']}  rejected {p['rejected_population']}")
    if "_difference" in out["index_trace"]["populations"]:
        d = out["index_trace"]["populations"]["_difference"]
        print(f"    NoMaD gains {d['nomad_gains']}, loses {d['nomad_loses']}, net {d['net']}")

    print("\n  PARTS G-O — one batch through the official path")
    out["models"] = {}
    for m in models:
        r1 = one_batch(m, traj, seed=args.seed, run_label="run1")
        r2 = one_batch(m, traj, seed=args.seed, run_label="run2")
        fx = invalid_fixture(m, traj, seed=args.seed)
        rep = repeatability(r1, r2)
        out["models"][m] = {"run1": r1, "run2": r2, "repeatability": rep,
                            "invalid_fixture": fx}
        (OUT / f"{m}_single_batch_forward.json").write_text(json.dumps(
            {k: r1[k] for k in ("model", "seed", "sample_count", "sample_indices", "batch",
                                "batch_all_finite", "outputs", "training_mode",
                                "resolved_config", "dataset_options", "diffusion_state")
             if k in r1}, indent=2) + "\n")
        (OUT / f"{m}_loss_smoke.json").write_text(json.dumps(
            {"model": m, "loss_source": CROSSWALK[m].get("loss_fn")
             or CROSSWALK[m].get("loss_source_range"),
             "alpha": CROSSWALK[m]["alpha"], "alpha_source": CROSSWALK[m]["alpha_source"],
             "total_loss_formula": CROSSWALK[m]["total_loss"],
             "components": r1["losses"], "finite": r1["losses_finite"],
             "all_finite": r1["all_losses_finite"],
             "total_is_scalar": r1["total_loss_is_scalar"]}, indent=2) + "\n")
        (OUT / f"{m}_backward_optimizer_smoke.json").write_text(json.dumps(
            {"model": m, "gradients": r1["gradients"],
             "watched_before": r1["watched_before"], "watched_after": r1["watched_after"],
             "parameters_changed_by_step": r1["parameters_changed_by_step"],
             "parameters_total_trainable": r1["parameters_total_trainable"],
             "parameters_unchanged": r1["parameters_unchanged"],
             "checkpoint_sha256_before": r1["checkpoint_sha256_before"],
             "checkpoint_sha256_after": r1["checkpoint_sha256_after"],
             "checkpoint_unchanged": r1["checkpoint_unchanged"]}, indent=2) + "\n")
        (OUT / f"{m}_training_contract.json").write_text(json.dumps(
            {"model": m, "crosswalk": CROSSWALK[m], "shared": CROSSWALK["_shared"],
             "resolved_config": r1["resolved_config"],
             "dataset_options": r1["dataset_options"],
             "metric_waypoint_spacing_m": r1["metric_waypoint_spacing_m"],
             "batch_contract": r1["batch"],
             "loss_components": list(r1["losses"].keys()),
             "diffusion_state": r1.get("diffusion_state"),
             "note": "model-specific differences are preserved, not standardised away"},
            indent=2) + "\n")

        g = r1["gradients"]
        print(f"    {m:6} {r1['result']:<4} loss {r1['losses'].get('total_loss', float('nan')):.6f}"
              f"  grads {g['parameters_with_nonzero_gradient']}/{g['parameters_trainable']} nonzero"
              f"  nan {g['parameters_with_nan_gradient']} inf {g['parameters_with_inf_gradient']}")
        print(f"           changed {r1['parameters_changed_by_step']}/"
              f"{r1['parameters_total_trainable']}  ckpt-unchanged "
              f"{r1['checkpoint_unchanged']}  repeat {rep['result']}"
              f" (max abs {rep['max_abs_difference']:.2e})  invalid-rejected {fx['result']}")

    (OUT / "train_path_compatibility.json").write_text(json.dumps(out, indent=2) + "\n")
    (FORENSICS / "training_path_crosswalk.json").write_text(json.dumps(CROSSWALK, indent=2) + "\n")

    failed = [m for m, r in out["models"].items()
              if r["run1"]["result"] != "PASS" or r["repeatability"]["result"] != "PASS"
              or r["invalid_fixture"]["result"] != "PASS"]
    print(f"\n  record -> {(OUT / 'train_path_compatibility.json').relative_to(REPO)}")
    print("  RESULT  : " + ("PASS" if not failed else f"FAIL ({', '.join(failed)})"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
