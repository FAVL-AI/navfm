"""One launch amendment: explicit Hub mode, measured startup, unchanged physics probe."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from imu_lifecycle_v2 import PhaseLog, instrument_probe, instrument_stage

# The parent creates the output root; the preserved worker owns the attempt mkdir.
_entry_out = Path(sys.argv[sys.argv.index("--out") + 1])
PhaseLog(_entry_out.parent / "worker-entry.jsonl").mark(
    "WORKER_ENTRY", OMNICLIENT_HUB_MODE=os.environ.get("OMNICLIENT_HUB_MODE")
)
from imu_controller_boundary_v1 import BodyGyro  # noqa: E402
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
            phase_mark(
                "AFTER_SENSOR_INIT", metadata=self.metadata, simulation_time=float(sim.current_time)
            )

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

    source = Path(__file__).with_name("qualify_imu_controller_v1.py")
    exec(
        compile(instrument_probe(source.read_text()), str(source), "exec"),
        {
            "__name__": "__main__",
            "__file__": str(source),
            "phase_mark": phase_mark,
            "os": os,
            "ObservedBodyGyro": ObservedBodyGyro,
            "observed_setup_prefix": observed_setup_prefix,
        },
    )


if __name__ == "__main__":
    main()
