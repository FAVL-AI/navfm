"""One launch amendment: explicit Hub mode, measured startup, unchanged physics probe."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from imu_lifecycle_v6 import (
    PhaseLog,
    author_stopped_initial_pose,
    capture_initialization_state,
    instrument_initialization,
    instrument_probe,
    instrument_stage,
    preserve_nonfinite,
)

# The parent creates the output root; the preserved worker owns the attempt mkdir.
_entry_out = Path(sys.argv[sys.argv.index("--out") + 1])
PhaseLog(_entry_out.parent / "worker-entry.jsonl").mark(
    "WORKER_ENTRY", OMNICLIENT_HUB_MODE=os.environ.get("OMNICLIENT_HUB_MODE")
)
from imu_controller_boundary_v1 import BodyGyro, GyroGuard  # noqa: E402
from qualify_imu_controller_v1 import setup_prefix  # noqa: E402


def main():
    out = Path(sys.argv[sys.argv.index("--out") + 1])
    phases = PhaseLog(out / "lifecycle.jsonl")

    def phase_mark(name, **fields):
        phases.mark(name, **fields)

    class ObservedBodyGyro(BodyGyro):
        def __init__(self, robot, sim):
            phase_mark("BEFORE_SENSOR_INIT", simulation_time=float(sim.current_time))
            super().__init__(robot, sim)
            self.first = True
            self.readiness_guard = GyroGuard(self.path)
            phase_mark(
                "AFTER_SENSOR_INIT", metadata=self.metadata, simulation_time=float(sim.current_time)
            )

        def observe_readiness(self, tick):
            value = self.interface.get_sensor_reading(
                self.path, use_latest_data=True, read_gravity=False
            )
            fields = dict(
                tick=tick,
                source=self.path,
                valid=bool(value.is_valid),
                sensor_time=float(value.time),
                simulation_time=float(self.sim.current_time),
                angular_velocity=[
                    float(value.ang_vel_x),
                    float(value.ang_vel_y),
                    float(value.ang_vel_z),
                ],
            )
            phase_mark("NATIVE_READINESS_OBSERVATION", **preserve_nonfinite(fields))
            if tick in (118, 119):
                self.readiness_guard.accept(value, float(self.sim.current_time), self.path)
                phase_mark("NATIVE_READINESS_ACCEPTED", tick=tick, sensor_time=float(value.time))

        def read(self):
            if self.first:
                phase_mark("BEFORE_FIRST_SAMPLE", simulation_time=float(self.sim.current_time))
            result = super().read()
            if self.first:
                phase_mark(
                    "AFTER_FIRST_SAMPLE",
                    sensor_time=self.guard.last_time,
                    simulation_time=float(self.sim.current_time),
                    rate=result,
                )
                self.first = False
            return result

    def observed_setup_prefix(source):
        return instrument_stage(setup_prefix(source))

    source = Path(__file__).with_name("imu_coverage_base_v2.py")
    exec(
        compile(
            instrument_initialization(instrument_probe(source.read_text())), str(source), "exec"
        ),
        {
            "__name__": "__main__",
            "__file__": str(source),
            "phase_mark": phase_mark,
            "preserve_nonfinite": preserve_nonfinite,
            "capture_initialization_state": capture_initialization_state,
            "author_stopped_initial_pose": author_stopped_initial_pose,
            "os": os,
            "ObservedBodyGyro": ObservedBodyGyro,
            "observed_setup_prefix": observed_setup_prefix,
        },
    )


if __name__ == "__main__":
    main()
