"""Explicit telemetry worker, prepared only; reuses unchanged coverage schedule."""

from pathlib import Path

from controller_telemetry_v1 import checked_array, derived_clipping, instrument

source = Path(__file__).with_name("qualify_imu_coverage_v2.py")
text = source.read_text()
needle = "instrument_initialization(instrument_probe(source.read_text()))"
if text.count(needle) != 1:
    raise ValueError("frozen wrapper boundary changed")
text = text.replace(
    needle, "instrument_initialization(instrument_probe(instrument(source.read_text())))"
)
# The transformed base executes in an explicit namespace; inject passive helpers there.
text = text.replace(
    '"ObservedBodyGyro": ObservedBodyGyro,',
    '"ObservedBodyGyro": ObservedBodyGyro, "checked_array": checked_array, "derived_clipping": derived_clipping,',
)
exec(
    compile(text, str(source), "exec"),
    {
        "__name__": "__main__",
        "__file__": str(source),
        "instrument": instrument,
        "checked_array": checked_array,
        "derived_clipping": derived_clipping,
    },
)
