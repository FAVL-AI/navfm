"""One diagnostic worker; no learned model or policy and no navigation admission."""

from pathlib import Path

from controller_plant_diagnostic_v1 import command, info, plant_readback, prepare, target_onset
from controller_telemetry_v1 import checked_array, derived_clipping

source = Path(__file__).with_name("qualify_imu_coverage_v2.py")
text = source.read_text()
needle = "instrument_initialization(instrument_probe(source.read_text()))"
if text.count(needle) != 1:
    raise ValueError("frozen wrapper boundary drift")
text = text.replace(
    needle, "instrument_initialization(instrument_probe(prepare(source.read_text())))"
)
needle = '"ObservedBodyGyro": ObservedBodyGyro,'
if text.count(needle) != 1:
    raise ValueError("frozen namespace boundary drift")
text = text.replace(
    needle,
    needle
    + ' "checked_array": checked_array, "derived_clipping": derived_clipping, "diagnostic_command": command, "diagnostic_info": info, "plant_readback": plant_readback, "target_onset": target_onset,',
)
exec(
    compile(text, str(source), "exec"),
    {
        "__name__": "__main__",
        "__file__": str(source),
        "prepare": prepare,
        "checked_array": checked_array,
        "derived_clipping": derived_clipping,
        "command": command,
        "info": info,
        "plant_readback": plant_readback,
        "target_onset": target_onset,
    },
)
