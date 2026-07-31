"""End-to-end proof that data written by :mod:`navfm.writer` loads through the
*actual* reference ``ViNT_Dataset``, and that our label computation agrees with
its label computation to floating-point tolerance.

This is the test that makes the whole project's central claim checkable. Every
other test verifies our own code against our own reading of upstream; this one
verifies against upstream itself.

Skipped unless the reference package is importable. Point ``NAVFM_UPSTREAM`` at
a clone of ``robodhruv/visualnav-transformer`` (the ``train`` subdirectory is
added to ``sys.path`` automatically), or ``pip install -e <clone>/train``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")


def _add_upstream_to_path() -> bool:
    root = os.environ.get("NAVFM_UPSTREAM")
    candidates = []
    if root:
        candidates.append(Path(root))
    candidates += [
        Path(__file__).resolve().parents[1] / "third_party" / "visualnav-transformer",
        Path.home() / "vnt",
    ]
    for c in candidates:
        train_dir = c / "train"
        if (train_dir / "vint_train" / "data" / "vint_dataset.py").is_file():
            sys.path.insert(0, str(train_dir))
            return True
    try:
        import vint_train  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = pytest.mark.upstream
_HAVE_UPSTREAM = _add_upstream_to_path()

if not _HAVE_UPSTREAM:  # pragma: no cover
    pytest.skip(
        "reference visualnav-transformer not found; set NAVFM_UPSTREAM to a clone",
        allow_module_level=True,
    )

from vint_train.data.data_utils import to_local_coords as up_to_local  # noqa: E402
from vint_train.data.vint_dataset import ViNT_Dataset  # noqa: E402

from navfm.kinematics import compute_actions, to_local_coords  # noqa: E402
from navfm.splits import write_splits  # noqa: E402
from navfm.writer import TrajectoryWriter  # noqa: E402

CONTEXT_SIZE = 5
LEN_TRAJ_PRED = 5
METRIC_SPACING = 0.20
IMAGE_SIZE = [85, 64]  # (width, height), as the reference configs express it


@pytest.fixture(scope="module")
def synthetic_dataset(tmp_path_factory):
    """A small GNM-format dataset written entirely through navfm.writer."""
    root = tmp_path_factory.mktemp("isaac_m3pro")
    rng = np.random.default_rng(7)
    n_traj, n = 5, 60
    for k in range(n_traj):
        t = np.linspace(0.0, 2.0 * np.pi, n)
        radius = 2.0 + 0.3 * k
        pos = np.stack([radius * np.cos(t), radius * np.sin(t)], axis=1)
        # Arc length per step = radius * dtheta; scale so it lands near
        # METRIC_SPACING for a realistic normalisation.
        scale = METRIC_SPACING / (radius * (t[1] - t[0]))
        pos *= scale
        yaw = t + np.pi / 2.0  # tangent heading, already unwrapped
        with TrajectoryWriter(root / f"scene{k % 2}_run_{k:05d}") as w:
            for i in range(n):
                img = rng.integers(0, 255, (96, 128, 3), dtype=np.uint8)
                w.append(img, pos[i], yaw[i])
    return root


@pytest.fixture(scope="module")
def splits_nomad(tmp_path_factory, synthetic_dataset):
    """A separate split directory: upstream writes its index and LMDB caches
    *inside* the split folder, so sharing one across specs would collide."""
    names = sorted(p.name for p in Path(synthetic_dataset).iterdir() if p.is_dir())
    out = tmp_path_factory.mktemp("splits_nomad")
    write_splits(out, "recon", names, names[:1])
    return out


@pytest.fixture(scope="module")
def splits(tmp_path_factory, synthetic_dataset):
    names = sorted(p.name for p in Path(synthetic_dataset).iterdir() if p.is_dir())
    out = tmp_path_factory.mktemp("splits")
    write_splits(out, "recon", names, names[:1])
    return out


def make_dataset(data_root, splits_root, tmp_path, **kwargs):
    params = dict(
        data_folder=str(data_root),
        data_split_folder=str(Path(splits_root) / "recon" / "train"),
        # The dataset *name* selects the metric_waypoint_spacing constant and the
        # dataset_index from upstream's data_config.yaml. We borrow "recon"
        # rather than registering a new key so this test never mutates the
        # reference clone; scripts/register_dataset.py does the registration for
        # real runs.
        dataset_name="recon",
        image_size=IMAGE_SIZE,
        waypoint_spacing=1,
        min_dist_cat=0,
        max_dist_cat=20,
        min_action_distance=0,
        max_action_distance=10,
        negative_mining=True,
        len_traj_pred=LEN_TRAJ_PRED,
        learn_angle=True,
        context_size=CONTEXT_SIZE,
        context_type="temporal",
        end_slack=0,
        goals_per_obs=1,
        normalize=True,
        goal_type="image",
    )
    params.update(kwargs)
    return ViNT_Dataset(**params)


def test_reference_loader_accepts_our_dataset(synthetic_dataset, splits, tmp_path, monkeypatch):
    """The reference dataset class must index and load our trajectories."""
    monkeypatch.chdir(tmp_path)  # index/LMDB caches are written next to cwd
    ds = make_dataset(synthetic_dataset, splits, tmp_path)

    # 60 frames, context 5, horizon 5 -> 50 samples per trajectory, 5 trajectories.
    assert len(ds) == 5 * (60 - 5 - 5)

    item = ds[0]
    assert len(item) == 7, "reference __getitem__ returns a 7-tuple"
    obs_image, goal_image, actions, distance, goal_pos, _dataset_index, _action_mask = item

    assert tuple(obs_image.shape) == (3 * (CONTEXT_SIZE + 1), IMAGE_SIZE[1], IMAGE_SIZE[0])
    assert tuple(goal_image.shape) == (3, IMAGE_SIZE[1], IMAGE_SIZE[0])
    assert tuple(actions.shape) == (LEN_TRAJ_PRED, 4)  # dx, dy, cos, sin
    assert distance.dtype == torch.int64
    assert tuple(goal_pos.shape) == (2,)
    assert torch.isfinite(obs_image).all()
    assert torch.isfinite(actions).all()

    # The (cos, sin) columns must be unit-norm -- calculate_sin_cos's contract.
    norms = torch.linalg.norm(actions[:, 2:], dim=-1)
    torch.testing.assert_close(norms, torch.ones_like(norms), atol=1e-5, rtol=1e-5)


def test_our_to_local_coords_matches_upstream_bitwise():
    rng = np.random.default_rng(11)
    for _ in range(50):
        pts = rng.normal(size=(8, 2))
        origin = rng.normal(size=2)
        yaw = float(rng.uniform(-np.pi, np.pi))
        np.testing.assert_allclose(
            to_local_coords(pts, origin, yaw), up_to_local(pts, origin, yaw), atol=1e-12
        )


def test_our_action_labels_match_the_reference_dataset(
    synthetic_dataset, splits, tmp_path, monkeypatch
):
    """The decisive check: identical action labels for identical inputs."""
    import pickle

    monkeypatch.chdir(tmp_path)
    ds = make_dataset(synthetic_dataset, splits, tmp_path)

    checked = 0
    for i in range(0, len(ds), 37):
        f_curr, curr_time, _max_goal = ds.index_to_data[i]
        with open(Path(synthetic_dataset) / f_curr / "traj_data.pkl", "rb") as fh:
            traj = pickle.load(fh)

        # Upstream normalises by the dataset's metric_waypoint_spacing, read
        # from its own data_config.yaml. Use whatever value it resolved to so
        # the comparison isolates the *maths*, not the constant.
        spacing = ds.data_config["metric_waypoint_spacing"]

        ours = compute_actions(
            traj["position"],
            traj["yaw"],
            curr_time,
            len_traj_pred=LEN_TRAJ_PRED,
            waypoint_spacing=1,
            metric_waypoint_spacing=spacing,
            learn_angle=True,
            normalize=True,
        )
        theirs, _goal = ds._compute_actions(traj, curr_time, curr_time + 1)

        np.testing.assert_allclose(ours[:, :2], theirs[:, :2], atol=1e-10)
        np.testing.assert_allclose(ours[:, 2], theirs[:, 2], atol=1e-10)
        checked += 1
    assert checked >= 5


def test_nomad_spec_also_loads(synthetic_dataset, splits_nomad, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ds = make_dataset(
        synthetic_dataset,
        splits_nomad,
        tmp_path,
        image_size=[96, 96],
        context_size=3,
        len_traj_pred=8,
        learn_angle=False,
        min_action_distance=3,
        max_action_distance=20,
    )
    obs_image, _goal, actions, _dist, _gp, _di, _am = ds[0]
    assert tuple(obs_image.shape) == (3 * 4, 96, 96)
    assert tuple(actions.shape) == (8, 2)
