"""Run frozen camera acquisition with one pre-shutdown durable completion insertion."""

from development_qualification_contracts_v1 import ROOT, sha
from prospective_collection_contracts_v1 import (
    ORIGINAL_CAPTURE_SHA,
    amended_capture,
    persist_measurement,
)

path = ROOT / "scripts/prospective_capture_v1.py"
if sha(path) != ORIGINAL_CAPTURE_SHA:
    raise ValueError("original capture source drift")
namespace = {
    "__name__": "__main__",
    "__file__": str(path),
    "persist_measurement": persist_measurement,
}
exec(compile(amended_capture(path.read_text()), str(path), "exec"), namespace)
