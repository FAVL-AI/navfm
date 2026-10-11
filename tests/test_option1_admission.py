import numpy as np
import pytest

from navfm.collection.dataset_admission import image_quality, motion_quality, split_routes
from navfm.collection.demonstrations import DemonstrationTeacher, route_specs


def test_unusable_uniform_images_and_stationary_paths_are_rejected():
    for value in (0, 127, 255):
        assert not image_quality(np.full((24, 32, 3), value, np.uint8))["usable"]
    image = np.zeros((24, 32, 3), dtype=np.uint8)
    image[:, ::2] = 160
    assert image_quality(image)["usable"]
    assert not motion_quality(np.zeros((20, 2)), np.zeros(20))["usable"]
    positions = np.column_stack([np.linspace(0, 1.2, 30), np.zeros(30)])
    assert motion_quality(positions, np.zeros(30))["usable"]
    positions[15, 0] += 2
    assert not motion_quality(positions, np.zeros(30))["usable"]


def test_frozen_scene_and_route_splits_do_not_leak():
    routes = route_specs()
    result = split_routes(routes)
    assert [len(result[k]) for k in ("train", "dev", "test")] == [6, 2, 2]
    routes[1]["split"] = "test"
    with pytest.raises(ValueError, match="scene crosses"):
        split_routes(routes)
    with pytest.raises(ValueError, match="route appears"):
        split_routes(route_specs() + route_specs()[:1])


@pytest.mark.parametrize("route", route_specs(), ids=lambda r: r["id"])
def test_scripted_teacher_reaches_each_polyline_in_ideal_dynamics(route):
    points = np.array(route["waypoints"])
    teacher = DemonstrationTeacher(points, route["speed"])
    xy, yaw = points[0].copy(), route["start_yaw"]
    done = False
    for _ in range(240):
        command, done = teacher.step(xy, yaw)
        if done:
            break
        xy += command[0] * np.array([np.cos(yaw), np.sin(yaw)]) / 12
        yaw += command[2] / 12
    assert done
    assert np.linalg.norm(xy - points[-1]) < 0.12
