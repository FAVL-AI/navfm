"""The original16-command qualification with one pre-physics solver factor."""

from pathlib import Path

from controller_telemetry_v1 import checked_array, derived_clipping, instrument, replace_once
from solver_position_candidate_v1 import install_solver_candidate, instrument_prefix

source = Path(__file__).with_name("qualify_imu_coverage_v2.py")
text = source.read_text()
text = replace_once(
    text,
    "return instrument_stage(setup_prefix(source))",
    "return instrument_stage(instrument_prefix(setup_prefix(source)))",
)
text = replace_once(
    text,
    "instrument_initialization(instrument_probe(source.read_text()))",
    "instrument_initialization(instrument_probe(instrument(source.read_text())))",
)
text = replace_once(
    text,
    '"ObservedBodyGyro": ObservedBodyGyro,',
    '"ObservedBodyGyro": ObservedBodyGyro, "checked_array": checked_array, "derived_clipping": derived_clipping, "install_solver_candidate": install_solver_candidate,',
)
exec(
    compile(text, str(source), "exec"),
    dict(
        __name__="__main__",
        __file__=str(source),
        instrument=instrument,
        checked_array=checked_array,
        derived_clipping=derived_clipping,
        instrument_prefix=instrument_prefix,
        install_solver_candidate=install_solver_candidate,
    ),
)
