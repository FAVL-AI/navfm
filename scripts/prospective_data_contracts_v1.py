"""Prospective private specification, finite teacher schedule and contamination stops."""

import hashlib
import json
import math
import random
import struct
from fractions import Fraction
from numbers import Integral, Real

RECIPE = "two-static-rooms-v1"


def specification(seeds):
    if len(seeds) != 2 or any(type(s) is not int for s in seeds) or seeds[0] == seeds[1]:
        raise ValueError("two distinct prospective seed identities required")
    layouts = []
    for i, seed in enumerate(seeds):
        rng = random.Random(seed)
        # Pure procedural research fixtures; not authenticated robot geometry.
        objects = [
            [0, -1.5, 0.75, 6, 0.1, 1.5],
            [0, 1.5, 0.75, 6, 0.1, 1.5],
            [-2.5, 0, 0.75, 0.1, 3, 1.5],
            [2.5, 0, 0.75, 0.1, 3, 1.5],
        ]
        for sx in (-1, 1):
            for sy in (-1, 1):
                objects.append(
                    [
                        sx * rng.uniform(1.5, 2.1),
                        sy * rng.uniform(0.8, 1.15),
                        0.4,
                        rng.uniform(0.15, 0.35),
                        rng.uniform(0.15, 0.35),
                        0.8,
                    ]
                )
        routes = []
        for j in range(2):
            yaw = 0.0 if j == 0 else math.pi
            poses = [
                [(-0.875 + 0.05 * t) * (1 if j == 0 else -1), (-0.35 if j == 0 else 0.35), yaw]
                for t in range(36)
            ]
            routes.append(dict(id=f"prospective_v1_layout{i}_route{j}", poses=poses))
        layouts.append(
            dict(id=f"prospective_v1_layout{i}", seed=seed, objects=objects, routes=routes)
        )
    return dict(recipe=RECIPE, layouts=layouts)


def content_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_seal(seal, known_ids, expected_freeze):
    if seal["freeze"] != expected_freeze or seal["specification_sha256"] != content_sha(
        seal["specification"]
    ):
        raise ValueError("seal identity drift")
    if seal.get("prior_content_access") != "NONE_DECLARED":
        raise ValueError("contamination declaration; halt")
    spec = seal["specification"]
    if spec != specification([x["seed"] for x in spec["layouts"]]):
        raise ValueError("recipe/parameter drift")
    ids = [r["id"] for x in spec["layouts"] for r in x["routes"]]
    if set(ids) & set(known_ids) or len(set(ids)) != 4:
        raise ValueError("layout/trajectory reuse")
    return spec


def reference_time(frame):
    value = frame.get("rendering_frame")
    if not isinstance(value, dict):
        raise ValueError("native ReferenceTime dictionary required")
    numerator, denominator = (
        value.get("referenceTimeNumerator"),
        value.get("referenceTimeDenominator"),
    )
    if (
        isinstance(numerator, bool)
        or not isinstance(numerator, Integral)
        or numerator < 0
        or isinstance(denominator, bool)
        or not isinstance(denominator, Integral)
        or denominator <= 0
    ):
        raise ValueError("native ReferenceTime rational invalid")
    return Fraction(int(numerator), int(denominator))


def float32_position(values):
    return [struct.unpack("f", struct.pack("f", float(x)))[0] for x in values]


def qualification_poses(layout_index, route_index, poses):
    return poses[:16] if layout_index == route_index == 0 else poses[:1]


def frame_integrity(
    frame, previous, actual_position, expected_position, rgb_shape, author_time, hold_end
):
    current = frame.get("rendering_time")
    for value in (current, author_time, hold_end):
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ValueError("camera frame clock missing/nonfinite")
    reference = reference_time(frame)
    if previous and (
        reference <= reference_time(previous) or current <= previous["rendering_time"]
    ):
        raise ValueError("stale/reordered camera frame")
    # Both times are simulation seconds. No lag fitting; fixed 1e-6 clock precision allowance.
    if hold_end < author_time or current <= author_time or current > hold_end + 1e-6:
        raise ValueError("RGB timestamp outside authored held-pose interval")
    represented = float32_position(expected_position)
    if (
        rgb_shape != (240, 320, 4)
        or len(actual_position) != 3
        or any(not math.isfinite(float(x)) for x in actual_position)
        or any(
            abs(float(a) - float(b)) > 1e-6
            for a, b in zip(actual_position, represented, strict=True)
        )
    ):
        raise ValueError("camera shape/float32 represented held pose integrity")
    return {
        "rendering_time": float(current),
        "rendering_frame": {
            "referenceTimeNumerator": int(frame["rendering_frame"]["referenceTimeNumerator"]),
            "referenceTimeDenominator": int(frame["rendering_frame"]["referenceTimeDenominator"]),
        },
    }


def preserve_raw_draw(report, evaluator):
    """Attach exact returned lists before metrics; no model or control modification."""

    def metrics(predictions, distances, *args):
        row = report["rows"][-1]
        row["raw_prediction"] = safe_raw(dict(actions=predictions, distances=distances))
        row["raw_prediction_sha256"] = content_sha(row["raw_prediction"])
        return evaluator(predictions, distances, *args)

    return metrics


def safe_raw(value):
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        return float(value) if math.isfinite(value) else {"nonfinite": repr(float(value))}
    if isinstance(value, (list, tuple)):
        return [safe_raw(x) for x in value]
    if type(value).__module__.startswith("numpy") and hasattr(value, "tolist"):
        return safe_raw(value.tolist())
    if isinstance(value, dict):
        return {k: safe_raw(v) for k, v in value.items()}
    return value
