"""Known-fixture timing worker; no private specification or dataset admission."""

import sys
from pathlib import Path

from development_qualification_contracts_v1 import ROOT, sha
from prospective_collection_contracts_v1 import ORIGINAL_CAPTURE_SHA, persist_measurement
from prospective_timing_contracts_v1 import Events, TimedContext, timing_capture

out = Path(sys.argv[sys.argv.index("--out") + 1])
events = Events(out / "child_events.jsonl", "child_monotonic_v1")
events.emit("WORKER_ENTRY")
path = ROOT / "scripts/prospective_capture_v1.py"
if sha(path) != ORIGINAL_CAPTURE_SHA:
    raise ValueError("original capture source drift")
namespace = dict(
    __name__="__main__",
    __file__=str(path),
    events=events,
    TimedContext=TimedContext,
    persist_measurement=persist_measurement,
)
try:
    exec(compile(timing_capture(path.read_text()), str(path), "exec"), namespace)
finally:
    events.emit("WORKER_FINALLY", event_logging_ns=events.logging_ns)
