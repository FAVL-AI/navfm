"""Pure boundary controls; no model or simulator invocation."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from development_qualification_contracts_v1 import ORDER, compare_initial, next_launch


def boundary():
    return {
        "counters": {"stop_count": 0, "stopped": False},
        "history_length": 6,
        "pose": [1.0, 0.0, 0.0],
        "camera": {"product": "fixed"},
    }


def test_first_declared_launch():
    next_launch([], ORDER[0])


@pytest.mark.parametrize("launch", [ORDER[1], "unknown"])
def test_wrong_first_launch(launch):
    with pytest.raises(ValueError):
        next_launch([], launch)


@pytest.mark.parametrize("status", ["FAIL", "TIMEOUT"])
def test_failed_previous_halts(status):
    with pytest.raises(ValueError):
        next_launch(
            [
                {"event": "start", "id": ORDER[0]},
                {"event": "end", "id": ORDER[0], "status": status},
            ],
            ORDER[1],
        )


def test_incomplete_previous_halts():
    with pytest.raises(ValueError):
        next_launch([{"event": "start", "id": ORDER[0]}], ORDER[1])


def test_duplicate_launch_rejected():
    with pytest.raises(ValueError):
        next_launch(
            [
                {"event": "start", "id": ORDER[0]},
                {"event": "end", "id": ORDER[0], "status": "PASS"},
            ],
            ORDER[0],
        )


def test_valid_initial_pair():
    assert compare_initial(boundary(), boundary(), 0)["status"] == "PASS"


@pytest.mark.parametrize(
    "field,value",
    [
        ("pose", [1.021, 0.0, 0.0]),
        ("pose", [1.0, 0.0, 0.036]),
        ("history_length", 5),
        ("counters", {"stop_count": 1, "stopped": False}),
    ],
)
def test_initial_guard_detects_drift(field, value):
    a = boundary()
    b = copy.deepcopy(a)
    b[field] = value
    assert compare_initial(a, b, 0)["status"] == "FAIL"


@pytest.mark.parametrize("mad", [2.5001, float("nan")])
def test_rgb_mismatch_halts(mad):
    assert compare_initial(boundary(), boundary(), mad)["status"] == "FAIL"


@pytest.mark.parametrize("pose", [[float("nan"), 0, 0], [1, 0, float("inf")]])
def test_nonfinite_pose_rejected(pose):
    a = boundary()
    b = boundary()
    b["pose"] = pose
    assert compare_initial(a, b, 0)["status"] == "FAIL"


def test_unknown_ledger_record_rejected():
    with pytest.raises(ValueError):
        next_launch([{"event": "unknown", "id": ORDER[0]}], ORDER[0])


@pytest.mark.parametrize(
    "change", [{"role": "gnm-release"}, {"checkpoint_sha256": "wrong"}, {"device_type": "cpu"}]
)
def test_prior_report_crossbinding(tmp_path, change):
    import json

    from development_qualification_contracts_v1 import sha, validate_prior

    path = tmp_path / "compat-vint-release.json"
    report = {
        "role": "vint-release",
        "checkpoint_sha256": "pin",
        "status": "PASS",
        "device_type": "cuda",
        **change,
    }
    path.write_text(json.dumps(report))
    records = [{"event": "end", "id": ORDER[0], "freeze": "f", "report_sha256": sha(path)}]
    with pytest.raises(ValueError):
        validate_prior(records, "f", {"models": {"vint-release": {"sha256": "pin"}}}, tmp_path)


def test_prior_freeze_mismatch(tmp_path):
    from development_qualification_contracts_v1 import validate_prior

    with pytest.raises(ValueError):
        validate_prior([{"freeze": "old"}], "new", {}, tmp_path)


def test_changed_chain_bytes_refused(tmp_path, monkeypatch):
    import development_qualification_contracts_v1 as c

    chain = tmp_path / "chain.json"
    chain.write_text('{"nodes":[1,2]}')
    digest = c.sha(chain)
    chain.write_text('{"nodes":[2,1]}')
    monkeypatch.setattr(
        c.subprocess, "check_output", lambda cmd, **kw: "f\n" if "rev-parse" in cmd else b""
    )
    with pytest.raises(ValueError):
        c.frozen("f", {"inputs": [{"path": str(chain), "sha256": digest}], "upstream_files": []})


def test_cuda_absence_refused_before_collector(monkeypatch):
    import types

    import collect_development_vint_v1 as worker

    monkeypatch.setitem(
        sys.modules,
        "torch",
        types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False)),
    )
    with pytest.raises(ValueError, match="before policy or simulator"):
        worker.main()


@pytest.mark.parametrize(
    "sensor,sim", [(float("nan"), 1.0), (1.0, float("inf")), ("1", 1.0), (True, 1.0), (1.03, 1.0)]
)
def test_invalid_clocks_rejected(sensor, sim):
    from development_qualification_contracts_v1 import validate_clocks

    with pytest.raises(ValueError):
        validate_clocks(sensor, sim)


@pytest.mark.parametrize(
    "failure",
    [KeyboardInterrupt(), InterruptedError(), __import__("subprocess").TimeoutExpired("child", 1)],
)
def test_cancel_or_timeout_kills_child_group(monkeypatch, failure):
    import os
    import subprocess

    from development_qualification_contracts_v1 import run_bounded

    class Child:
        pid = 12345
        waits = 0

        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1:
                raise failure
            return 0

        def poll(self):
            return None

    child = Child()
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: child)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: calls.append(pid))
    with pytest.raises(type(failure)):
        run_bounded(["fixed"], {}, ".", None, 1)
    assert calls == [12345] and child.waits == 2


def test_unadmitted_controller_blocks_pair_before_output(tmp_path, monkeypatch):
    import json

    import run_development_qualification_v1 as launcher

    config = tmp_path / "configs/eval/development_qualification_v1.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {"development_pair_authorized": False, "development_blocker": "unadmitted GT feedback"}
        )
    )
    output = tmp_path.parent / (tmp_path.name + "-evidence")
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "frozen", lambda *args: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["runner", "--freeze", "fixed", "--stage", "development-pair", "--out", str(output)],
    )
    with pytest.raises(ValueError, match="unadmitted GT feedback"):
        launcher.main()
    assert not output.exists()
