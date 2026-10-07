"""Scripted simulation teacher; privileged inputs are demonstration-only."""

from __future__ import annotations

import math

import numpy as np


def route_specs():
    shapes = [
        [[1.0, 0.0], [2.8, 0.0]],
        [[1.0, 0.0], [1.9, 0.0], [1.9, 0.9]],
        [[1.0, 0.0], [1.9, 0.0], [1.9, -0.9]],
        [[1.0, 0.0], [1.6, 0.35], [2.3, -0.35], [3.0, 0.0]],
        [[1.0, -0.4], [1.9, -0.4], [2.8, 0.4]],
    ]
    names = ["straight", "left", "right", "s_bend", "junction"]
    result = []
    for scene, (name, shape) in enumerate(zip(names, shapes, strict=True)):
        for variant in range(2):
            path = np.array(shape) + np.array([0, variant * 0.25])
            result.append(
                {
                    "id": f"{name}_run_{variant:04d}",
                    "scene": name,
                    "split": "train" if scene < 3 else "dev" if scene == 3 else "test",
                    "route_id": f"{name}_route_{variant}",
                    "scene_index": scene,
                    "seed": scene * 2 + variant,
                    "waypoints": path.tolist(),
                    "speed": 0.20 + variant * 0.02,
                    "start_yaw": float(math.atan2(*(path[1] - path[0])[::-1])),
                    "wall_half_width": 2.0 + scene * 0.1,
                }
            )
    return result


class DemonstrationTeacher:
    """Ground-truth waypoint teacher, never an RGB-only deployed method."""

    def __init__(self, points, speed):
        self.points = np.asarray(points)
        self.speed = speed
        self.index = 1

    def step(self, xy, yaw):
        error = self.points[self.index] - xy
        distance = float(np.linalg.norm(error))
        if distance < 0.12:
            if self.index == len(self.points) - 1:
                return [0.0, 0.0, 0.0], True
            self.index += 1
            error = self.points[self.index] - xy
            distance = float(np.linalg.norm(error))
        angle = math.atan2(error[1], error[0]) - yaw
        angle = math.atan2(math.sin(angle), math.cos(angle))
        return [
            min(self.speed, 0.8 * distance) * max(0.0, math.cos(angle)),
            0.0,
            float(np.clip(1.8 * angle, -0.7, 0.7)),
        ], False
