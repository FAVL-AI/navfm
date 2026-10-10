import numpy as np
import pytest

from navfm.collection.scientific_preflight import require_scientific_preflight, validate_capture


def sample(**changes):
    args = dict(rgb=np.arange(36, dtype=np.uint8).reshape(3, 4, 3), pose=[0., 0., 0.],
                command_time=1., capture_time=1.+1/12, sensor_time=1.+1/12,
                previous_sensor_time=1., resolution=(4, 3), dt=1/12)
    args.update(changes)
    validate_capture(**args)


def test_valid_capture():
    sample()


@pytest.mark.parametrize("changes", [dict(sensor_time=1.), dict(capture_time=2.),
    dict(pose=[float("nan"), 0., 0.]), dict(previous_sensor_time=2.),
    dict(rgb=np.zeros((3, 4, 3), dtype=np.uint8)), dict(resolution=(3, 4))])
def test_rejects_invalid_capture(changes):
    with pytest.raises(ValueError):
        sample(**changes)


def test_doubles_cannot_admit_scientific_collection():
    class Decision:
        scientific_collection_permitted = True
        unsatisfied = ()

        def to_dict(self):
            return {"test_double_present": True}
    with pytest.raises(RuntimeError):
        require_scientific_preflight(Decision())


def test_saved_readback_detects_pose_corruption(tmp_path):
    from navfm.collection.recording import RecordingTrajectoryWriter
    from navfm.collection.scientific_preflight import verify_saved_recording

    path = tmp_path / "trajectory"
    capture = {"pose": [0., 0., 0.], "simulation_time": 1/12}
    with RecordingTrajectoryWriter(path) as writer:
        writer.append(np.arange(36, dtype=np.uint8).reshape(3, 4, 3), [0., 0.], 0.,
            transition=dict(frame_index=0, pre_image_index=None, time_before=0., time_after=1/12,
                pose_before=[0., 0., 0.], pose_after=[0., 0., 0.],
                command_requested=[0., 0., 0.], command_accepted=[0., 0., 0.]))
    verify_saved_recording(path, [capture], (4, 3))
    capture["pose"] = [1., 0., 0.]
    with pytest.raises(ValueError, match="saved pose"):
        verify_saved_recording(path, [capture], (4, 3))


def _write_turning(path, yaws):
    from navfm.collection.recording import RecordingTrajectoryWriter

    captures = []
    with RecordingTrajectoryWriter(path) as writer:
        for i, y in enumerate(yaws):
            t = (i + 1) / 12
            writer.append(np.arange(36, dtype=np.uint8).reshape(3, 4, 3), [0., 0.], y,
                transition=dict(frame_index=i, pre_image_index=None if i == 0 else i - 1,
                    time_before=i / 12, time_after=t,
                    pose_before=[0., 0., y], pose_after=[0., 0., y],
                    command_requested=[0., 0., 0.4], command_accepted=[0., 0., 0.4]))
            captures.append({"pose": [0., 0., y], "simulation_time": t})
    return captures


def test_saved_readback_accepts_heading_through_pi(tmp_path):
    """Regression: an in-place turn through +/-pi (stored unwrapped) is not corruption."""
    from navfm.collection.scientific_preflight import verify_saved_recording

    raw = np.angle(np.exp(1j * np.linspace(2.9, 3.6, 8)))  # wraps from +pi to -pi
    assert raw.min() < 0 < raw.max()
    path = tmp_path / "trajectory"
    captures = _write_turning(path, [float(y) for y in raw])
    verify_saved_recording(path, captures, (4, 3))


def test_saved_readback_still_detects_heading_corruption_after_wrap(tmp_path):
    """Negative control: a wrong heading or position is still refused after a wrap."""
    from navfm.collection.scientific_preflight import verify_saved_recording

    raw = [float(y) for y in np.angle(np.exp(1j * np.linspace(2.9, 3.6, 8)))]
    path = tmp_path / "trajectory"
    captures = _write_turning(path, raw)
    for k, bad in ((5, [0., 0., raw[5] + 0.01]), (2, [0.001, 0., raw[2]])):
        tampered = [dict(c) for c in captures]
        tampered[k] = {**tampered[k], "pose": bad}
        with pytest.raises(ValueError, match="saved pose"):
            verify_saved_recording(path, tampered, (4, 3))


def test_render_target_reader_handles_nonpickleable_runtime_path():
    import json

    from navfm.collection.attestation import Provenance, read_render_product

    class RuntimePath:
        def __deepcopy__(self, memo):
            raise RuntimeError("runtime paths cannot be pickled")

        def __str__(self):
            return "/World/Robot/base_link/Camera_front"

    class Camera:
        def get_render_product_path(self):
            return "/Render/Product"

    observations = read_render_product(Camera(), lambda path: RuntimePath(),
                                       lambda path: (640, 480), Provenance.TEST_DOUBLE)
    values = [o.to_dict() for o in observations]
    assert values[1]["value"] == "/World/Robot/base_link/Camera_front"
    json.dumps(values, allow_nan=False)


def test_legacy_renderer_key_cannot_substitute_for_effective_mode():
    from navfm.collection.attestation import Status, read_effective_settings

    class Settings:
        def get(self, key):
            return {"/renderer/active": "RaytracedLighting"}.get(key)

    renderer = next(o for o in read_effective_settings(Settings()) if o.name == "active_renderer")
    assert renderer.status is Status.UNRESOLVED_NO_SUPPORTED_ROUTE
    assert renderer.value is None


def test_saved_readback_checks_the_wrap_property_not_only_unwrap(tmp_path, monkeypatch):
    """A stored yaw off by 2*pi on one frame (a discontinuity) is refused even if
    unwrap_yaw itself were wrong in the same way."""
    import pickle

    import navfm.kinematics as kin
    from navfm.collection.scientific_preflight import verify_saved_recording

    raw = [float(y) for y in np.angle(np.exp(1j * np.linspace(2.9, 3.6, 8)))]
    path = tmp_path / "trajectory"
    captures = _write_turning(path, raw)
    with (path / "traj_data.pkl").open("rb") as f:
        poses = pickle.load(f)
    bad = np.asarray(poses["yaw"], float).copy()
    bad[4] += 2 * np.pi
    with (path / "traj_data.pkl").open("wb") as f:
        pickle.dump({"position": poses["position"], "yaw": bad}, f)
    monkeypatch.setattr(kin, "unwrap_yaw", lambda y: bad)  # a matching unwrap defect
    with pytest.raises(ValueError, match="not continuous"):
        verify_saved_recording(path, captures, (4, 3))
