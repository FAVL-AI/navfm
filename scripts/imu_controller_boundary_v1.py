"""Measured body-local gyro boundary; no root-state fallback or policy input."""

from __future__ import annotations

import ast
import json
import math


class GyroGuard:
    def __init__(self, source: str, period: float = 1 / 120):
        self.source = source
        self.period = period
        self.last_time = None
        self.records = []

    def accept(self, reading, now: float, source: str) -> float:
        record = {
            "source": source,
            "valid": bool(reading.is_valid),
            "time": float(reading.time),
            "controller_time": float(now),
            "angular_velocity": [
                float(reading.ang_vel_x),
                float(reading.ang_vel_y),
                float(reading.ang_vel_z),
            ],
        }
        self.records.append(record)
        if source != self.source or not record["valid"]:
            raise ValueError("invalid IMU source/reading")
        if not all(math.isfinite(v) for v in [record["time"], now, *record["angular_velocity"]]):
            raise ValueError("nonfinite IMU measurement")
        if not 0 <= now - record["time"] <= self.period + 1e-6:
            raise ValueError("IMU outside one-physics-tick clock window")
        if self.last_time is not None and record["time"] <= self.last_time:
            raise ValueError("stale IMU measurement")
        self.last_time = record["time"]
        return record["angular_velocity"][2]


class BodyGyro:
    def __init__(self, robot, sim):
        import numpy as np
        import omni.usd
        from isaacsim.sensors.physics import IMUSensor, _sensor
        from pxr import UsdPhysics

        self.sim = sim
        self.path = robot.prim_path + "/base_link/QualificationIMU"
        stage = omni.usd.get_context().get_stage()
        parent = stage.GetPrimAtPath(robot.prim_path + "/base_link")
        if not parent or not parent.HasAPI(UsdPhysics.RigidBodyAPI):
            raise ValueError("IMU parent must be the robot rigid body")
        if stage.GetPrimAtPath(self.path):
            raise ValueError("new IMU prim required")
        self.sensor = IMUSensor(
            self.path,
            dt=1 / 120,
            translation=np.zeros(3),
            orientation=np.array([1.0, 0.0, 0.0, 0.0]),
            angular_velocity_filter_size=1,
            linear_acceleration_filter_size=1,
            orientation_filter_size=1,
        )
        self.sensor.initialize()
        self.interface = _sensor.acquire_imu_sensor_interface()
        if abs(self.sensor.get_dt() - 1 / 120) > 1e-9:
            raise ValueError("IMU period readback mismatch")
        translation, orientation = self.sensor.get_local_pose()
        if not np.allclose(translation, np.zeros(3), atol=1e-9) or not np.allclose(
            orientation, np.array([1.0, 0.0, 0.0, 0.0]), atol=1e-9
        ):
            raise ValueError("IMU identity mount readback mismatch")
        self.metadata = {
            "source": self.path,
            "frame": "sensor/body-local",
            "period": self.sensor.get_dt(),
            "translation": translation.tolist(),
            "orientation_wxyz": orientation.tolist(),
            "schema_type": stage.GetPrimAtPath(self.path).GetTypeName(),
        }
        if self.metadata["schema_type"] != "IsaacImuSensor":
            raise ValueError("IMU schema readback mismatch")
        self.evidence_path = None
        self.failure = None
        self.guard = GyroGuard(self.path)

    def raise_if_failed(self):
        if self.failure is not None:
            raise RuntimeError("latched IMU controller failure") from self.failure

    def fail(self, error):
        self.failure = error
        if self.evidence_path is not None:
            try:
                with self.evidence_path.open("a") as stream:
                    stream.write(
                        json.dumps({"failure_type": type(error).__name__, "source": self.path})
                        + "\n"
                    )
            except OSError:
                pass  # Actuation must still be zeroed if evidence storage fails.

    def read(self):
        value = self.interface.get_sensor_reading(
            self.path, use_latest_data=True, read_gravity=False
        )
        try:
            return self.guard.accept(value, float(self.sim.current_time), self.path)
        finally:
            if self.evidence_path is not None and self.guard.records:
                with self.evidence_path.open("a") as stream:
                    stream.write(json.dumps(self.guard.records[-1]) + "\n")


def bind_collector_source(source: str) -> ast.Module:
    """Replace the one named controller measurement, preserving evaluation reads."""
    tree = ast.parse(source)
    replaced = attached = checked = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "on_physics_step":
            for item in node.body:
                if isinstance(item, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "measured" for t in item.targets
                ):
                    expected = "float(np.asarray(robot._articulation.get_velocities()).reshape(-1, 6)[0, 5])"
                    if ast.dump(item.value) != ast.dump(ast.parse(expected, mode="eval").body):
                        raise ValueError("collector measurement contract changed")
                    item.value = ast.parse("body_gyro.read()", mode="eval").body
                    replaced += 1
            node.body = [
                ast.Try(
                    body=[ast.parse("body_gyro.raise_if_failed()").body[0], *node.body],
                    handlers=[
                        ast.ExceptHandler(
                            type=ast.Name(id="BaseException", ctx=ast.Load()),
                            name="imu_error",
                            body=ast.parse(
                                "body_gyro.fail(imu_error)\nheld['command'] = (0., 0., 0.)\nwheel_targets(0., 0., 0.)"
                            ).body,
                        )
                    ],
                    orelse=[],
                    finalbody=[],
                )
            ]
        if isinstance(node, ast.FunctionDef) and node.name == "step":
            check = "if body_gyro is not None: body_gyro.raise_if_failed()"
            node.body.insert(0, ast.parse(check).body[0])
            node.body.append(ast.parse(check).body[0])
            checked += 1
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "tracker" for t in node.targets
        ):
            # Locate insertion in its containing block, not an arbitrary runtime hook.
            for parent in ast.walk(tree):
                for _field, value in ast.iter_fields(parent):
                    if isinstance(value, list) and node in value:
                        value.insert(
                            value.index(node) + 1,
                            ast.parse("body_gyro = BodyGyro(robot, sim) if tracker else None").body[
                                0
                            ],
                        )
                        attached += 1
                        break
                else:
                    continue
                break
    if (replaced, attached, checked) != (1, 1, 1):
        raise ValueError("exactly one controller boundary required")
    return ast.fix_missing_locations(tree)


def validate_evaluation(value):
    """Every sampled evaluation value must be numeric and finite, before scoring."""
    if isinstance(value, dict):
        for item in value.values():
            validate_evaluation(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            validate_evaluation(item)
    elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("nonfinite or nonnumeric evaluation sample")
