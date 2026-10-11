"""Passive instrumentation of the preserved controller; never feeds readbacks back."""

from __future__ import annotations

import hashlib
import math


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("frozen instrumentation boundary changed")
    return source.replace(old, new)


def checked_array(value, size):
    value = value.tolist() if hasattr(value, "tolist") else value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
        value = value[0]
    if not isinstance(value, list) or len(value) != size:
        raise ValueError("joint readback schema mismatch")
    if not all(
        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value
    ):
        raise ValueError("nonfinite joint readback")
    return value


def derived_clipping(before, after, command, measured, gains, output):
    # These are derived formula evaluations; integral values themselves are observed.
    reset_base = 0.0 if command == 0 else before
    proposed = reset_base + (command - measured) / 120
    unclipped = gains.feedforward * command + gains.kp * (command - measured) + gains.ki * after
    return {
        "derived_proposed_integral": proposed,
        "derived_integral_clipped": abs(proposed) > gains.integral_limit,
        "derived_unclipped_output": unclipped,
        "derived_output_clipped": abs(unclipped) > gains.output_limit,
        "recorded_output": output,
    }


def instrument(source):
    source = replace_once(
        source,
        "            v, w = command(tick)",
        """            v, w = command(tick)
            integral_before = tracker.integral
            measured = None
            phase_mark("TELEMETRY_PRE_CONTROL", tick=tick, simulation_time=float(sim.current_time),
                       integral_before=float(integral_before), command=[v,w], dof_names=names,
                       wheel_indices=idx, evaluation_only_pose=preserve_nonfinite(robot.pose()[0].tolist()),
                       evaluation_only_orientation_wxyz=preserve_nonfinite(robot._articulation.get_world_poses()[1].tolist()),
                       evaluation_only_world_velocity=preserve_nonfinite(robot._articulation.get_velocities().tolist()))""",
    )
    source = replace_once(
        source,
        "            target = np.zeros((1, len(names)), dtype=np.float32)",
        """            phase_mark("TELEMETRY_POST_CONTROL", tick=tick, simulation_time=float(sim.current_time),
                       integral_after=float(tracker.integral), reused_native_rate=measured,
                       native_record=gyro.guard.records[-1] if measured is not None else None,
                       derived=derived_clipping(integral_before, tracker.integral,w,measured,tracker.gains,output)
                               if measured is not None and (v != 0 or w != 0) else {"reset": True, "recorded_output": output})
            target = np.zeros((1, len(names)), dtype=np.float32)""",
    )
    source = replace_once(
        source,
        "            robot._articulation.set_joint_velocity_targets(target)",
        """            phase_mark("TELEMETRY_REQUESTED_TARGET", tick=tick, simulation_time=float(sim.current_time),
                       requested=target.tolist(), dof_names=names, wheel_indices=idx)
            robot._articulation.set_joint_velocity_targets(target)
            accepted = robot._articulation.get_applied_actions().joint_velocities
            phase_mark("TELEMETRY_ACCEPTED_TARGET", tick=tick, simulation_time=float(sim.current_time),
                       accepted=preserve_nonfinite(accepted.tolist() if hasattr(accepted,"tolist") else accepted))
            checked_array(accepted, len(names))""",
    )
    source = replace_once(
        source,
        "            xy, yaw = robot.pose()",
        """            realized = robot._articulation.get_joint_velocities()
            phase_mark("TELEMETRY_POST_PHYSICS", tick=tick, simulation_time=float(sim.current_time),
                       realized=preserve_nonfinite(realized.tolist() if hasattr(realized,"tolist") else realized),
                       evaluation_only_orientation_wxyz=preserve_nonfinite(robot._articulation.get_world_poses()[1].tolist()),
                       evaluation_only_world_velocity=preserve_nonfinite(robot._articulation.get_velocities().tolist()))
            checked_array(realized, len(names))
            xy, yaw = robot.pose()""",
    )
    return source


def artifact_hashes(out):
    names = [
        "attempt/lifecycle.jsonl",
        "worker-entry.jsonl",
        "attempt/imu_qualification.json",
        "attempt/imu_readings.jsonl",
        "process.log",
    ]
    return {
        name: hashlib.sha256((out / name).read_bytes()).hexdigest()
        for name in names
        if (out / name).is_file()
    }
