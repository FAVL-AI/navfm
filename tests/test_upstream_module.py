"""Tests for :mod:`navfm.upstream`.

Split in two. The resolution logic is testable without the reference clone and
runs everywhere. The builders are only meaningful against the real thing, so
they carry ``pytest.mark.upstream`` and skip when it is absent -- the point of
this module is that we do *not* mock upstream.
"""

from __future__ import annotations

import pytest

from navfm import upstream

# ------------------------------------------------------------------ resolution


def test_upstream_root_honours_the_env_var(tmp_path, monkeypatch):
    clone = tmp_path / "vnt"
    (clone / "train" / "vint_train" / "data").mkdir(parents=True)
    (clone / "train" / "vint_train" / "data" / "vint_dataset.py").write_text("")
    monkeypatch.setenv("NAVFM_UPSTREAM", str(clone))
    upstream.upstream_root.cache_clear()
    try:
        assert upstream.upstream_root() == clone.resolve()
    finally:
        upstream.upstream_root.cache_clear()


def test_missing_upstream_raises_with_the_clone_command(tmp_path, monkeypatch):
    """The error has to be actionable: a missing clone is the single most common
    first failure, and 'ModuleNotFoundError: vint_train' does not tell anyone
    which repo to clone or which script to run afterwards."""
    monkeypatch.setenv("NAVFM_UPSTREAM", str(tmp_path / "nope"))
    monkeypatch.setattr(upstream, "_candidates", lambda: [tmp_path / "nope"])
    upstream.upstream_root.cache_clear()
    try:
        with pytest.raises(upstream.UpstreamNotFound, match="visualnav-transformer"):
            upstream.upstream_root()
    finally:
        upstream.upstream_root.cache_clear()


def test_build_model_rejects_unknown_types():
    with pytest.raises(ValueError, match="unknown model_type"):
        upstream.model_config("resnet")


# -------------------------------------------------------------------- builders

pytest.importorskip("yaml")
_HAVE_UPSTREAM = True
try:
    upstream.upstream_root()
except upstream.UpstreamNotFound:  # pragma: no cover - environment dependent
    _HAVE_UPSTREAM = False

needs_upstream = pytest.mark.skipif(_HAVE_UPSTREAM is False, reason="reference clone not found")


@pytest.mark.upstream
@needs_upstream
def test_model_config_layers_vint_over_defaults():
    cfg = upstream.model_config("vint")
    # From vint.yaml, overriding defaults.yaml's gnm-flavoured values.
    assert cfg["model_type"] == "vint"
    assert cfg["obs_encoding_size"] == 512
    # The config contradicts the ViNT class defaults (2/2). The released
    # checkpoint follows the config; building from class defaults would produce
    # a model whose state_dict silently half-matches vint.pth.
    assert cfg["mha_num_attention_heads"] == 4
    assert cfg["mha_num_attention_layers"] == 4
    # Inherited from defaults.yaml, absent from vint.yaml.
    assert cfg["eval_batch_size"] == 400
    assert cfg["image_size"] == [85, 64]
    # vint.yaml overrides defaults.yaml's action.min_dist_cat of 2.
    assert cfg["action"]["min_dist_cat"] == 0


@pytest.mark.upstream
@pytest.mark.torch
@needs_upstream
def test_build_vint_matches_the_published_shapes():
    torch = pytest.importorskip("torch")
    cfg = upstream.model_config("vint")
    model = upstream.build_model("vint", cfg)

    obs = torch.zeros(2, 3 * (cfg["context_size"] + 1), 64, 85)
    goal = torch.zeros(2, 3, 64, 85)
    with torch.no_grad():
        dist, action = model(obs, goal)
    assert tuple(dist.shape) == (2, 1)
    assert tuple(action.shape) == (2, cfg["len_traj_pred"], 4)

    # Paper Table 6 says 31 M; the built model is 29.7 M. Assert the order of
    # magnitude only -- the point is to catch a geometry mistake (2 vs 4 layers
    # is a ~3 M difference), not to relitigate the paper's rounding.
    n = sum(p.numel() for p in model.parameters())
    assert 28e6 < n < 32e6


@pytest.mark.upstream
@needs_upstream
def test_metric_waypoint_spacing_reads_the_reference_constants():
    assert upstream.metric_waypoint_spacing("recon") == pytest.approx(0.25)
    assert upstream.metric_waypoint_spacing("go_stanford") == pytest.approx(0.12)


@pytest.mark.upstream
@needs_upstream
def test_unregistered_dataset_is_an_error_not_a_default():
    """A missing spacing must never silently become 1.0: it multiplies every
    distance we report in metres."""
    with pytest.raises(KeyError, match="register_dataset"):
        upstream.metric_waypoint_spacing("isaac_m3pro_not_registered")


@pytest.mark.upstream
@pytest.mark.torch
@needs_upstream
def test_reference_transform_is_applied_per_frame():
    torch = pytest.importorskip("torch")
    transform = upstream.reference_transform()
    obs = torch.rand(2, 18, 8, 8)
    goal = torch.rand(2, 3, 8, 8)
    out_obs, out_goal = upstream.apply_reference_transform(obs, goal, transform, "cpu")
    assert out_obs.shape == obs.shape
    assert out_goal.shape == goal.shape
    # ImageNet normalisation of channel 0: (x - 0.485) / 0.229.
    torch.testing.assert_close(out_obs[:, 0], (obs[:, 0] - 0.485) / 0.229)
    # Channel 3 is the *first* channel of the second frame, so it gets the
    # red-channel constants again -- this is what "per frame" buys.
    torch.testing.assert_close(out_obs[:, 3], (obs[:, 3] - 0.485) / 0.229)
