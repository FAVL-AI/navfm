"""Option 1 admission helpers; offline labels never enter deployed policy."""

from __future__ import annotations

import numpy as np


def image_quality(rgb):
    gray = np.asarray(rgb, dtype=float).mean(axis=2)
    contrast = float(np.percentile(gray, 95) - np.percentile(gray, 5))
    gradient = float(
        (np.abs(np.diff(gray, axis=0)).mean() + np.abs(np.diff(gray, axis=1)).mean()) / 2
    )
    extreme = float(np.mean((gray < 3) | (gray > 252)))
    return {
        "contrast_p95_p05": contrast,
        "gradient_mean": gradient,
        "extreme_fraction": extreme,
        "usable": bool(contrast >= 15 and gradient >= 0.3 and extreme < 0.95),
    }


def motion_quality(positions, yaw):
    xy = np.asarray(positions, dtype=float)
    heading = np.unwrap(np.asarray(yaw, dtype=float))
    steps = np.linalg.norm(np.diff(xy, axis=0), axis=1)
    result = {
        "path_length_m": float(steps.sum()),
        "net_displacement_m": float(np.linalg.norm(xy[-1] - xy[0])),
        "max_step_m": float(steps.max()),
        "yaw_range_rad": float(np.ptp(heading)),
    }
    result["usable"] = bool(
        np.isfinite(xy).all()
        and np.isfinite(heading).all()
        and result["path_length_m"] >= 1.0
        and result["net_displacement_m"] >= 0.5
        and result["max_step_m"] <= 0.12
    )
    return result


def split_routes(routes):
    scenes = {}
    route_ids = set()
    result = {s: [] for s in ("train", "dev", "test")}
    for route in routes:
        if route["split"] not in result:
            # Held-out routes (split "heldout") never enter a training corpus.
            raise ValueError(f"route split {route['split']!r} cannot be admitted")
        if route["route_id"] in route_ids:
            raise ValueError("route appears more than once")
        route_ids.add(route["route_id"])
        previous = scenes.setdefault(route["scene"], route["split"])
        if previous != route["split"]:
            raise ValueError("scene crosses splits")
        result[route["split"]].append(route["id"])
    return result
