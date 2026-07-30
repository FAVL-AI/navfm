"""Format-contract tests. These are the tests that prevent a wasted GPU week."""

from __future__ import annotations

import pickle

import numpy as np
import pytest
from PIL import Image

from navfm.schema import (
    TrajectorySpec,
    check_image_names,
    check_traj_data,
    min_length_for,
)
from navfm.validate import validate_dataset, validate_trajectory
from navfm.writer import TrajectoryWriter, center_crop_to_aspect


def make_frames(n: int, size=(64, 48)):
    rng = np.random.default_rng(0)
    return [rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8) for _ in range(n)]


def make_pose(n: int, radius: float = 2.0):
    t = np.linspace(0.0, 1.6 * np.pi, n)
    pos = np.stack([radius * np.cos(t), radius * np.sin(t)], axis=1)
    yaw = t + np.pi / 2.0
    return pos, yaw


# --------------------------------------------------------------- spec maths


def test_min_length_matches_reference_index_arithmetic():
    # ViNT: context 5, horizon 5 -> begin=5, end=T-5; need end > begin => T > 10.
    assert min_length_for("vint") == 11
    assert min_length_for("nomad") == 12  # context 3, horizon 8
    spec = TrajectorySpec.for_model("vint")
    assert spec.num_samples(10) == 0
    assert spec.num_samples(11) == 1
    assert spec.num_samples(20) == 10


def test_waypoint_spacing_and_end_slack_scale_the_requirement():
    spec = TrajectorySpec(context_size=5, len_traj_pred=5, waypoint_spacing=3, end_slack=3)
    assert spec.min_length == 5 * 3 + 5 * 3 + 3 + 1
    assert spec.num_samples(spec.min_length) == 1
    assert spec.num_samples(spec.min_length - 1) == 0


# ------------------------------------------------------------ traj_data checks


def test_check_traj_data_accepts_valid():
    pos, yaw = make_pose(20)
    assert check_traj_data({"position": pos, "yaw": yaw}, n_images=20) == []


def test_check_traj_data_tolerates_column_yaw_like_the_loader():
    pos, yaw = make_pose(20)
    assert check_traj_data({"position": pos, "yaw": yaw[:, None]}, n_images=20) == []


def test_check_traj_data_flags_image_count_mismatch():
    pos, yaw = make_pose(20)
    problems = check_traj_data({"position": pos, "yaw": yaw}, n_images=19)
    assert any("image count" in p for p in problems)


def test_check_traj_data_flags_wrapped_yaw():
    pos, _ = make_pose(20)
    yaw = np.linspace(-np.pi + 0.05, np.pi - 0.05, 20)
    yaw[10:] -= 2 * np.pi  # simulate a branch cut
    problems = check_traj_data({"position": pos, "yaw": yaw}, n_images=20)
    assert any("not unwrapped" in p for p in problems)


def test_check_traj_data_flags_missing_keys_and_bad_shapes():
    assert any("missing" in p for p in check_traj_data({"yaw": np.zeros(3)}))
    problems = check_traj_data({"position": np.zeros((3, 3)), "yaw": np.zeros(3)})
    assert any("(T, 2)" in p for p in problems)


def test_check_traj_data_flags_non_finite():
    pos, yaw = make_pose(10)
    pos[3, 0] = np.nan
    assert any("non-finite" in p for p in check_traj_data({"position": pos, "yaw": yaw}))


# ------------------------------------------------------------- image naming


def test_image_names_must_be_unpadded_and_contiguous():
    assert check_image_names(["0.jpg", "1.jpg", "2.jpg"]) == []
    assert any("invalid image filename" in p for p in check_image_names(["000.jpg", "1.jpg"]))
    assert any("invalid image filename" in p for p in check_image_names(["0.png"]))
    assert any("not contiguous" in p for p in check_image_names(["0.jpg", "2.jpg"]))


# ------------------------------------------------------------------- writer


def test_writer_roundtrip_produces_loader_compatible_output(tmp_path):
    n = 30
    frames = make_frames(n)
    pos, yaw = make_pose(n)
    out = tmp_path / "office_a_run_00001"

    with TrajectoryWriter(out, metadata={"scene": "office_a"}) as w:
        for i in range(n):
            w.append(frames[i], pos[i], yaw[i])

    assert out.is_dir()
    jpgs = sorted(p.name for p in out.glob("*.jpg"))
    assert len(jpgs) == n
    assert set(jpgs) == {f"{i}.jpg" for i in range(n)}

    with open(out / "traj_data.pkl", "rb") as fh:
        data = pickle.load(fh)
    assert set(data) >= {"position", "yaw"}
    assert data["position"].shape == (n, 2)
    assert data["yaw"].shape == (n,)
    np.testing.assert_allclose(data["position"], pos, atol=1e-9)
    assert data["metadata"]["scene"] == "office_a"

    report = validate_trajectory(out, TrajectorySpec.for_model("vint"), check_images_decodable=True)
    assert report.ok, report.errors
    assert report.n_samples == 30 - 10


def test_writer_is_atomic_on_exception(tmp_path):
    out = tmp_path / "traj"
    with pytest.raises(RuntimeError), TrajectoryWriter(out) as w:
        w.append(make_frames(1)[0], [0.0, 0.0], 0.0)
        raise RuntimeError("simulated crash mid-episode")
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_writer_unwraps_yaw(tmp_path):
    n = 12
    frames = make_frames(n)
    pos = np.zeros((n, 2))
    pos[:, 0] = np.arange(n) * 0.1
    yaw = np.linspace(np.pi - 0.3, np.pi + 0.3, n)
    yaw = np.arctan2(np.sin(yaw), np.cos(yaw))  # wrap it, as a sensor would
    with TrajectoryWriter(tmp_path / "t") as w:
        for i in range(n):
            w.append(frames[i], pos[i], yaw[i])
    with open(tmp_path / "t" / "traj_data.pkl", "rb") as fh:
        stored = pickle.load(fh)["yaw"]
    assert np.abs(np.diff(stored)).max() < 0.2
    assert check_traj_data({"position": pos, "yaw": stored}, n_images=n) == []


def test_writer_rejects_bad_pose(tmp_path):
    from navfm.schema import TrajectorySchemaError

    with TrajectoryWriter(tmp_path / "t") as w:
        with pytest.raises(TrajectorySchemaError):
            w.append(make_frames(1)[0], [0.0, np.nan], 0.0)
        w.abort()


def test_center_crop_to_aspect_is_idempotent_and_correct():
    wide = Image.new("RGB", (1920, 1080))
    cropped = center_crop_to_aspect(wide)
    assert cropped.size == (1440, 1080)
    assert center_crop_to_aspect(cropped).size == (1440, 1080)
    tall = Image.new("RGB", (480, 640))
    assert center_crop_to_aspect(tall).size == (480, 360)
    already = Image.new("RGB", (640, 480))
    assert center_crop_to_aspect(already).size == (640, 480)


# ---------------------------------------------------------------- validator


def test_validator_detects_partial_directories(tmp_path):
    (tmp_path / ".partial-abc").mkdir()
    n = 15
    with TrajectoryWriter(tmp_path / "scene_run_00000") as w:
        pos, yaw = make_pose(n)
        for i, f in enumerate(make_frames(n)):
            w.append(f, pos[i], yaw[i])
    report = validate_dataset(tmp_path, model="vint")
    assert not report.ok
    assert any("staging directories" in e for e in report.dataset_errors)


def test_validator_flags_desynced_images(tmp_path):
    n = 15
    out = tmp_path / "scene_run_00000"
    with TrajectoryWriter(out) as w:
        pos, yaw = make_pose(n)
        for i, f in enumerate(make_frames(n)):
            w.append(f, pos[i], yaw[i])
    (out / f"{n - 1}.jpg").unlink()  # simulate a lost frame
    report = validate_trajectory(out, TrajectorySpec.for_model("vint"))
    assert not report.ok
    assert any("not contiguous" in e or "image count" in e for e in report.errors)


def test_validator_warns_on_short_trajectory(tmp_path):
    n = 8  # below ViNT's minimum of 11
    with TrajectoryWriter(tmp_path / "scene_run_00000") as w:
        pos, yaw = make_pose(n)
        for i, f in enumerate(make_frames(n)):
            w.append(f, pos[i], yaw[i])
    report = validate_trajectory(tmp_path / "scene_run_00000", TrajectorySpec.for_model("vint"))
    assert report.ok  # valid format...
    assert report.n_samples == 0  # ...but useless
    assert any("0 training samples" in w for w in report.warnings)
