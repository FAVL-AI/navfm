import pytest

from navfm.collection import fixture_identity as fi


def scene(partition=False, intensity=1500.0):
    sig = {
        "/World/Fixture/Scene3/Floor": {
            "type": "Cube",
            "api_schemas": ["PhysicsCollisionAPI"],
            "attributes": {"xformOp:translate": [2.0, 60.0, -0.05], "size": 1.0},
        },
        "/World/Fixture/Sun": {
            "type": "DistantLight",
            "api_schemas": [],
            "attributes": {"inputs:intensity": intensity},
        },
    }
    if partition:
        sig["/World/Fixture/Scene3/DoorPartition2"] = {
            "type": "Cube",
            "api_schemas": ["PhysicsCollisionAPI"],
            "attributes": {"xformOp:translate": [2.11, 61.45, 0.7]},
        }
    return sig


def test_identical_signatures_pass_and_digest_is_stable():
    assert fi.compare(scene(), scene()) == []
    assert fi.digest(scene()) == fi.digest(scene())
    fi.require_identical(scene(), scene(), what="fixture")


def test_extra_partition_is_rejected():
    # Negative control reproducing the invalid H0 run 01.
    differences = fi.compare(scene(), scene(partition=True))
    assert differences == ["absent from goal source: /World/Fixture/Scene3/DoorPartition2"]
    with pytest.raises(ValueError, match="DoorPartition2"):
        fi.require_identical(scene(), scene(partition=True), what="fixture")


def test_lighting_change_is_rejected():
    differences = fi.compare(scene(), scene(intensity=300.0))
    assert len(differences) == 1 and "inputs:intensity" in differences[0]
    assert fi.digest(scene()) != fi.digest(scene(intensity=300.0))


def test_rounding_tolerates_float_noise_only():
    a = scene()
    b = scene()
    b["/World/Fixture/Scene3/Floor"]["attributes"]["xformOp:translate"] = [
        2.0000000001,
        60.0,
        -0.05,
    ]
    assert fi.compare(a, b) == []
    b["/World/Fixture/Scene3/Floor"]["attributes"]["xformOp:translate"] = [2.001, 60.0, -0.05]
    assert fi.compare(a, b)


def test_camera_signature_detects_mount_change():
    manifest = {
        "requested": {
            "robot": {"camera": {"height": 0.55, "pitch_deg": 0.0}},
            "sim": {"resolution": [320, 240]},
        },
        "camera_local_pose": [[0.2, 0.0, 0.55], [1.0, 0.0, 0.0, 0.0]],
    }
    moved = {**manifest, "camera_local_pose": [[0.2, 0.0, 0.60], [1.0, 0.0, 0.0, 0.0]]}
    assert fi.compare(fi.camera_signature(manifest), fi.camera_signature(manifest)) == []
    assert fi.compare(fi.camera_signature(manifest), fi.camera_signature(moved))


def test_scene_roots_include_global_lights():
    assert fi.scene_roots(4) == (
        "/World/Fixture/Scene4",
        "/World/Fixture/Sun",
        "/World/Fixture/Dome",
    )
