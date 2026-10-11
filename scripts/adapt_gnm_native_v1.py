"""GNM native distance/action objective and released initialization."""


def build(config):
    from navfm import upstream

    return upstream.build_model("gnm", config)


def loss(model, batch, config, training=True):
    from vint_train.training.train_utils import _compute_losses

    obs, goal, actions, distance, mask = batch
    dp, ap = model(obs, goal)
    values = _compute_losses(
        distance, actions, dp, ap, alpha=0.5, learn_angle=True, action_mask=mask
    )
    return (
        values["total_loss"],
        dp,
        ap,
        {
            "dist_loss": float(values["dist_loss"].detach()),
            "action_loss": float(values["action_loss"].detach()),
        },
    )
