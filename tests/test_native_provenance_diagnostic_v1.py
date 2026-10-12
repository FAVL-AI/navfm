import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from development_qualification_contracts_v1 import sha
from native_provenance_diagnostic_v1 import (
    run_observed,
    validate_rejection_path,
    verify_native_dependencies,
)


@pytest.mark.parametrize("listed", [False, True])
def test_first_rejection_category_and_atomic_evidence(tmp_path, listed):
    p = tmp_path / "actual.py"
    p.write_text("value=1\n")
    module = ModuleType("fixture")
    module.__file__ = str(p)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"files": [{"path": str(p), "sha256": "0" * 64}] if listed else []})
    )
    target = tmp_path / "reject.json"
    cfg = {"native_dependency_manifest": str(manifest), "diagnostic_rejection_path": str(target)}
    with pytest.raises(ImportError):
        verify_native_dependencies(cfg, {"fixture": module})
    d = json.loads(target.read_text())
    assert d["module"] == "fixture" and d["actual_sha256"] == sha(p)
    assert d["category"] == ("FILE_HASH_MISMATCH" if listed else "UNLISTED_ORIGIN")
    assert d["generator_export_identity"] == "UNKNOWN"

    def broken(*args):
        raise OSError("storage")

    target.unlink()
    with pytest.raises(OSError):
        verify_native_dependencies(cfg, {"fixture": module}, broken)


@pytest.mark.parametrize("timeout", [False, True])
def test_actual_child_exit_timeout_reap(tmp_path, timeout):
    class Child:
        pid = 123
        calls = 0

        def wait(self, timeout):
            self.calls += 1
            if self.calls == 1 and timeout != 5 and timed:
                raise subprocess.TimeoutExpired("child", timeout)
            return -9 if timed else 1

        def poll(self):
            return None if timed else 1

    timed = timeout
    child = Child()
    kills = []
    outcome = {}

    def launch(*args, **kwargs):
        return child

    if timed:
        with pytest.raises(subprocess.TimeoutExpired):
            run_observed([], {}, tmp_path, None, 145, outcome, launch, lambda *a: kills.append(a))
    else:
        assert run_observed([], {}, tmp_path, None, 145, outcome, launch) == 1
    assert outcome["timeout"] is timed and outcome["child_reaped"] is True
    assert outcome["child_exit_code"] == (-9 if timed else 1)
    assert bool(kills) is timed


def test_cleanup_signal_error_cannot_bypass_reaping(tmp_path):
    class Child:
        pid = 12
        calls = 0

        def wait(self, timeout):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("child", timeout)
            return 1

        def poll(self):
            return None

    child = Child()
    outcome = {}

    def kill(*args):
        raise OSError("signal")

    with pytest.raises(subprocess.TimeoutExpired):
        run_observed([], {}, tmp_path, None, 145, outcome, lambda *a, **k: child, kill)
    assert child.calls == 2 and outcome["child_reaped"] is True
    assert outcome["cleanup_signal_error_type"] == "OSError"


def test_first_rejection_survives_distinct_final_rejection(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": []}))
    target = tmp_path / "rejection.json"
    cfg = {"native_dependency_manifest": str(manifest), "diagnostic_rejection_path": str(target)}
    for name in ["first", "later"]:
        p = tmp_path / (name + ".py")
        p.write_text(name)
        module = ModuleType(name)
        module.__file__ = str(p)
        with pytest.raises(ImportError):
            verify_native_dependencies(cfg, {name: module})
    assert json.loads(target.read_text())["module"] == "first"


def test_rejection_path_mismatch_rejects_before_launch(tmp_path):
    cfg = {"diagnostic_rejection_path": str(tmp_path / "rejection.json")}
    validate_rejection_path(cfg, tmp_path)
    with pytest.raises(ValueError):
        validate_rejection_path(cfg, tmp_path / "other")
