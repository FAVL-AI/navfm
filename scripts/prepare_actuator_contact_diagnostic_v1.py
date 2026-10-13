"""Fresh-arm diagnostic worker; direct targets and passive plant observation."""

import os
from pathlib import Path

from actuator_contact_diagnostic_v1 import command, passive_sample, prepare, setup_condition
from controller_telemetry_v1 import checked_array, derived_clipping

condition = os.environ["NAVFM_DIAGNOSTIC_CONDITION"]
if condition not in ("grounded", "airborne"):
    raise ValueError("unknown condition")
source = Path(__file__).with_name("qualify_imu_coverage_v2.py")
text = source.read_text()
changes = {
    "return instrument_stage(setup_prefix(source))": "return instrument_stage(setup_condition(setup_prefix(source), condition))",
    "instrument_initialization(instrument_probe(source.read_text()))": "instrument_initialization(instrument_probe(prepare(source.read_text(), condition)))",
    '"ObservedBodyGyro": ObservedBodyGyro,': '"ObservedBodyGyro": ObservedBodyGyro, "checked_array": checked_array, "derived_clipping": derived_clipping, "diagnostic_command": command, "passive_sample": passive_sample,',
}
for old, new in changes.items():
    if text.count(old) != 1:
        raise ValueError("frozen wrapper boundary drift")
    text = text.replace(old, new)
exec(
    compile(text, str(source), "exec"),
    {
        "__name__": "__main__",
        "__file__": str(source),
        "condition": condition,
        "setup_condition": setup_condition,
        "prepare": prepare,
        "command": command,
        "passive_sample": passive_sample,
        "checked_array": checked_array,
        "derived_clipping": derived_clipping,
    },
)
