"""NoMaD native diffusion objective with explicit parameter-EMA API adaptation."""


def build(config):
    from verify_r6_strict_load import _build_nomad

    return _build_nomad(config)


def scheduler():
    from diffusers.schedulers.scheduling_ddpm import DDPMScheduler

    return DDPMScheduler(
        num_train_timesteps=10,
        beta_schedule="squaredcos_cap_v2",
        clip_sample=True,
        prediction_type="epsilon",
    )


def make_ema(model):
    from diffusers.training_utils import EMAModel

    return EMAModel(model.parameters(), power=0.75, use_ema_warmup=True)


def normalized_actions(actions):
    import numpy as np
    import torch
    from vint_train.training.train_utils import ACTION_STATS, get_action, get_delta, normalize_data

    normalized = normalize_data(get_delta(actions.detach().cpu().numpy()), ACTION_STATS)
    n = torch.as_tensor(normalized, dtype=actions.dtype, device=actions.device)
    reconstructed = get_action(n, ACTION_STATS)
    if not np.isfinite(normalized).all() or not torch.allclose(
        reconstructed, actions, rtol=0, atol=1e-5
    ):
        raise ValueError("NoMaD action normalization roundtrip failed")
    return n


def loss(model, batch, config, training=True):
    import torch
    from torch.nn import functional as F

    obs, goal, actions, distance, mask = batch
    B = obs.shape[0]
    gm = (
        (torch.rand(B, device=obs.device) < 0.5).long()
        if training
        else torch.zeros(B, dtype=torch.long, device=obs.device)
    )
    cond = model("vision_encoder", obs_img=obs, goal_img=goal, input_goal_mask=gm)
    dp = model("dist_pred_net", obsgoal_cond=cond)
    # Preserve native train_nomad's scalar distance reduction then goal-mask weighting.
    dl = F.mse_loss(dp.squeeze(-1), distance.float())
    dl = (dl * (1 - gm.float())).mean() / ((1 - gm.float()).mean() + 1e-2)
    action = normalized_actions(actions)
    ns = scheduler()
    noise = torch.randn_like(action)
    timesteps = torch.randint(0, 10, (B,), device=obs.device).long()
    npred = model(
        "noise_pred_net",
        sample=ns.add_noise(action, noise, timesteps),
        timestep=timesteps,
        global_cond=cond,
    )
    per = F.mse_loss(npred, noise, reduction="none").mean(dim=(1, 2))
    nl = (per * mask).mean() / (mask.mean() + 1e-2)
    total = 1e-4 * dl + (1 - 1e-4) * nl
    return (
        total,
        dp,
        None,
        {
            "dist_loss": float(dl.detach()),
            "diffusion_loss": float(nl.detach()),
            "goal_masks": gm.detach().cpu().tolist(),
            "diffusion_timesteps": timesteps.cpu().tolist(),
        },
    )


def predict(model, batch):
    import torch
    from vint_train.training.train_utils import ACTION_STATS, get_action

    obs, goal, *_ = batch
    cond = model(
        "vision_encoder",
        obs_img=obs,
        goal_img=goal,
        input_goal_mask=torch.zeros(obs.shape[0], dtype=torch.long, device=obs.device),
    )
    dp = model("dist_pred_net", obsgoal_cond=cond)
    x = torch.randn((obs.shape[0], 8, 2), device=obs.device)
    ns = scheduler()
    ns.set_timesteps(10)
    for t in ns.timesteps:
        noise = model("noise_pred_net", sample=x, timestep=t, global_cond=cond)
        x = ns.step(noise, t, x).prev_sample
    return dp, get_action(x, ACTION_STATS)
