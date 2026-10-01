"""Engineering sidecar conformance and discriminating negative controls."""
import json
import pickle

import numpy as np
import pytest

from navfm.collection.recording import RecordingTrajectoryWriter, validate_records
from navfm.schema import TrajectorySpec
from navfm.validate import validate_trajectory


def record(i):
    return dict(frame_index=i, pre_image_index=i-1 if i else None,
                time_before=i/12, time_after=(i+1)/12,
                pose_before=[i*0.02, 0., 0.], pose_after=[(i+1)*0.02, 0., 0.],
                command_requested=[0.24, 0., 0.], command_accepted=[0.24, 0., 0.])


def test_sidecars_preserve_two_key_pickle_and_temporal_alignment(tmp_path):
    out = tmp_path / "trajectory"
    with RecordingTrajectoryWriter(out, metadata={"run_class": "ENGINEERING_ONLY"}) as w:
        for i in range(30):
            w.append(np.full((48,64,3), i, dtype=np.uint8),
                     [(i+1)*0.02, 0.], 0., transition=record(i))
    with (out / "traj_data.pkl").open("rb") as fh:
        data = pickle.load(fh)
    assert set(data) == {"position", "yaw"}
    sidecar = json.loads((out / "transitions.json").read_text())
    rows = sidecar["records"]
    assert len(rows) == 30
    np.testing.assert_allclose(np.array([v["pose_after"][:2] for v in rows]), data["position"])
    assert json.loads((out / "metadata.json").read_text())["run_class"] == "ENGINEERING_ONLY"
    for model in ("gnm", "vint", "nomad"):
        report = validate_trajectory(out, TrajectorySpec.for_model(model), check_images_decodable=True)
        assert report.ok, report.errors
        assert report.n_samples > 0
    with pytest.raises(FileExistsError):
        RecordingTrajectoryWriter(out).open()


@pytest.mark.parametrize("mutation", ["count", "time", "gap", "index", "nan", "shape"])
def test_negative_controls_refuse_invalid_records(mutation):
    rows = [record(0), record(1)]
    if mutation == "count":
        rows.pop()
    elif mutation == "time":
        rows[0]["time_after"] = 0.
    elif mutation == "gap":
        rows[1]["time_before"] += 0.01
    elif mutation == "index":
        rows[1]["pre_image_index"] = 99
    elif mutation == "nan":
        rows[0]["command_requested"][0] = float("nan")
    else:
        rows[0]["pose_after"].pop()
    with pytest.raises(ValueError):
        validate_records(rows, 2)


@pytest.mark.upstream
@pytest.mark.parametrize("model", ["gnm", "vint", "nomad"])
def test_sidecar_recording_is_consumed_by_pinned_official_loader(tmp_path, model):
    import torch

    from navfm import upstream
    from navfm.splits import write_splits

    out = tmp_path / "data" / "trajectory"
    with RecordingTrajectoryWriter(out) as w:
        for i in range(30):
            w.append(np.full((48, 64, 3), i, dtype=np.uint8),
                     [(i+1)*0.02, 0.], 0., transition=record(i))
    split, _ = write_splits(tmp_path / "splits", "recon", [out.name], [])
    ds = upstream.build_dataset(dataset_name="recon", data_folder=out.parent,
                                split_folder=split.parent, cfg=upstream.model_config(model))
    assert len(ds) > 0
    item = ds[0]
    assert len(item) == 7
    assert torch.isfinite(item[2]).all()
