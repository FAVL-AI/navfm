import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from prospective_data_contracts_v1 import (
    content_sha,
    float32_position,
    frame_integrity,
    preserve_raw_draw,
    qualification_poses,
    safe_raw,
    specification,
    validate_seal,
)


def test_known_fixture_recipe_horizon_and_no_route_object_overlap():
    spec = specification([0, 1])
    assert len(spec["layouts"]) == 2
    assert sum(len(r["poses"]) for x in spec["layouts"] for r in x["routes"]) == 144
    for x in spec["layouts"]:
        for r in x["routes"]:
            assert len(r["poses"][5:14]) == 9
            assert all(abs(p[0]) <= 0.875 and abs(p[1]) == 0.35 for p in r["poses"])
        assert all(abs(o[0]) - o[3] / 2 > 1.3 for o in x["objects"][4:])


def test_seal_content_and_contamination_stop():
    spec = specification([0, 1])
    seal = dict(
        freeze="freeze",
        specification=spec,
        specification_sha256=content_sha(spec),
        prior_content_access="NONE_DECLARED",
    )
    assert validate_seal(seal, [], "freeze") == spec
    seal["prior_content_access"] = "INSPECTED"
    with pytest.raises(ValueError, match="contamination"):
        validate_seal(seal, [], "freeze")
    seal["prior_content_access"] = "NONE_DECLARED"
    seal["specification"]["layouts"][0]["objects"][0][0] = 1
    with pytest.raises(ValueError, match="drift"):
        validate_seal(seal, [], "freeze")


def test_clock_pose_shape_prevents_stale_reordered_capture():
    f = dict(
        rendering_time=1.0,
        rendering_frame={"referenceTimeNumerator": 12, "referenceTimeDenominator": 12},
    )
    frame_integrity(f, None, [0.0, 0.0, 0.55], [0.0, 0.0, 0.55], (240, 320, 4), 0.5, 1.0)
    with pytest.raises(ValueError, match="stale"):
        frame_integrity(f, f, [0.0, 0.0, 0.55], [0.0, 0.0, 0.55], (240, 320, 4), 0.5, 1.0)
    with pytest.raises(ValueError, match="pose"):
        frame_integrity(f, None, [0.1, 0.0, 0.55], [0.0, 0.0, 0.55], (240, 320, 4), 0.5, 1.0)


def test_raw_prediction_retained_without_changing_metric_inputs():
    report = {"rows": [{}]}
    seen = []

    def evaluate(a, d, *args):
        seen.append((a, d))
        return "original"

    hooked = preserve_raw_draw(report, evaluate)
    a = [[[1.0, math.nan]]]
    d = [[2.0]]
    assert hooked(a, d) == "original"
    assert seen[0][0] is a
    raw = report["rows"][0]["raw_prediction"]
    assert raw["actions"][0][0][1] == {"nonfinite": "nan"}
    assert report["rows"][0]["raw_prediction_sha256"] == content_sha(raw)
    json.dumps(raw, allow_nan=False)


def test_native_reference_time_and_held_interval():
    f = dict(
        rendering_time=1.0,
        rendering_frame={"referenceTimeNumerator": 12, "referenceTimeDenominator": 12},
    )
    assert (
        frame_integrity(f, None, [0.0, 0.0, 0.55], [0.0, 0.0, 0.55], (240, 320, 4), 0.5, 1.0)[
            "rendering_frame"
        ]
        == f["rendering_frame"]
    )
    for author, end in [(1.0, 1.5), (0.5, 0.9)]:
        with pytest.raises(ValueError, match="interval"):
            frame_integrity(f, None, [0.0, 0.0, 0.55], [0.0, 0.0, 0.55], (240, 320, 4), author, end)
    f["rendering_frame"]["referenceTimeDenominator"] = 0
    with pytest.raises(ValueError, match="rational"):
        frame_integrity(f, None, [0.0, 0.0, 0.55], [0.0, 0.0, 0.55], (240, 320, 4), 0.5, 1.0)


def test_float32_offset_and_reverse_qualification_coverage():
    position = [99.325, 0.35, 0.55]
    represented = float32_position(position)
    assert abs(represented[0] - position[0]) > 1e-6
    f = dict(
        rendering_time=1.0,
        rendering_frame={"referenceTimeNumerator": 12, "referenceTimeDenominator": 12},
    )
    frame_integrity(f, None, represented, position, (240, 320, 4), 0.5, 1.0)
    spec = specification([0, 1])
    counts = [
        len(qualification_poses(li, ri, r["poses"]))
        for li, x in enumerate(spec["layouts"])
        for ri, r in enumerate(x["routes"])
    ]
    assert counts == [16, 1, 1, 1]


def test_failed_camera_candidate_fields_are_jsonsafe_before_guard():
    import ast

    candidate = dict(
        camera={
            "rendering_time": math.nan,
            "rendering_frame": {"referenceTimeNumerator": 12, "referenceTimeDenominator": 12},
        },
        requested_camera_position=[99.325, 0.35, 0.55],
        actual_camera_position=[math.nan, 0.35, 0.55],
        requested_camera_quaternion=[1.0, 0.0, 0.0, 0.0],
        actual_camera_quaternion=[math.nan, 0.0, 0.0, 0.0],
    )
    safe = safe_raw(candidate)
    assert safe["camera"]["rendering_time"] == {"nonfinite": "nan"}
    json.dumps(safe, allow_nan=False)
    source = ast.parse(
        (Path(__file__).parents[1] / "scripts/prospective_capture_v1.py").read_text()
    )
    calls = [
        n for n in ast.walk(source) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    guard = next(n.lineno for n in calls if n.func.id == "frame_integrity")
    assert any(n.func.id == "write" and n.lineno < guard for n in calls)
