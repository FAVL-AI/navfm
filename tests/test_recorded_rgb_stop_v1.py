"""Hermetic mock-adaptation and frozen recorded-input selection guards; no encoder inference."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from recorded_rgb_stop_v1 import (
    CONFIG,
    MockStop,
    validate_admission_fields,
    validate_manifest,
    verify_file,
)


def test_mock_stop_latch_absence_cancel_and_reset_are_separate_from_native_publication():
    mock = MockStop()
    mock.reset("first")
    assert mock.request_motion((0.1, 0.2), "first") == "ACCEPTED_MOCK_ONLY"
    mock.request_motion((0.05, 0.1), "first")
    assert mock.current == (0.1, 0.2) and mock.pending
    assert mock.observe(False, "first")["new_mock_command"] is None
    assert mock.observe(True, "first")["new_mock_command"] == "MOCK_STOP_ONLY"
    assert mock.current is None and not mock.pending and mock.target == (0.0, 0.0)
    assert mock.request_motion((1, 1), "first") == "BLOCKED_MOCK_ONLY"
    assert mock.observe(None, "first") == {
        "status": "MOCK_ONLY",
        "new_mock_command": None,
        "latched": True,
    }
    assert mock.observe(True, "first")["new_mock_command"] is None
    mock.cancel("first")
    assert mock.observe(True, "first") == {
        "status": "CANCELED",
        "new_mock_command": None,
        "latched": True,
    }
    mock.reset("second")
    assert not mock.latched and not mock.canceled
    with pytest.raises(ValueError):
        mock.observe(True, "first")
    with pytest.raises(ValueError):
        mock.cancel("first")


@pytest.mark.parametrize("publication", [1, "true", []])
def test_mock_publication_does_not_accept_implicit_truthiness(publication):
    with pytest.raises(ValueError):
        MockStop().observe(publication, "unstarted")


def test_mock_episodes_are_independent():
    left, right = MockStop(), MockStop()
    left.observe(True, "unstarted")
    assert not right.latched
    with pytest.raises(ValueError):
        left.reset("")


def test_fixed_admitted_sequence_and_native_graph_gap():
    cfg = json.loads(CONFIG.read_text())
    validate_manifest(cfg)
    assert cfg["trajectory"] == "prospective_v1_layout0_route0"
    assert len(cfg["references"] + cfg["queries"]) == 16
    assert cfg["weights"]["placenav"]["provenance"] == "RETRIEVED_UNCERTIFIED_HASH"
    assert cfg["weights"]["ulvn"]["provenance"] == "VERIFIED_EXPECTED_LFS_HASH"


@pytest.mark.parametrize(
    "change", ["fitting", "navigation", "graph_claim", "reselection", "extra_forwards"]
)
def test_scope_or_selected_sequence_cannot_drift(change):
    cfg = copy.deepcopy(json.loads(CONFIG.read_text()))
    if change == "fitting":
        cfg["threshold_fitting"] = True
    if change == "navigation":
        cfg["navigation_authorized"] = True
    if change == "graph_claim":
        cfg["graph_status"] = "NATIVE_RAVEL_QUALIFIED"
    if change == "reselection":
        cfg["queries"][0]["frame"] = 2
    if change == "extra_forwards":
        cfg["max_encoder_forwards"] = 33
    with pytest.raises(ValueError):
        validate_manifest(cfg)


def test_immutable_record_or_weight_tampering_refused(tmp_path):
    file = tmp_path / "fixture"
    file.write_bytes(b"changed")
    with pytest.raises(ValueError):
        verify_file(file, "0" * 64)


def test_worker_python_network_refusal_is_enforced_in_isolated_process():
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys,socket; sys.path.insert(0,'scripts'); from recorded_rgb_stop_v1 import validate_admission_fields, reject_python_network; sys.addaudithook(reject_python_network); socket.socket().connect(('127.0.0.1',9))",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert result.returncode != 0 and "refuses Python network" in result.stderr


@pytest.mark.parametrize("mutation", ["DEV_selection", "image_binding", "finalization"])
def test_completed_admitted_DEV_metadata_guards_are_not_hash_only(mutation):
    cfg = json.loads(CONFIG.read_text())
    files = {
        f"{cfg['trajectory']}/{r['frame']}.jpg": r["sha256"]
        for r in cfg["references"] + cfg["queries"]
    }
    admitted = {
        "status": "PASS",
        "source_freeze": "fixture",
        "splits": {"train": [], "dev": [cfg["trajectory"]], "test": []},
        "dataset_file_sha256": files,
    }
    complete = {
        "status": "COMPLETE",
        "freeze": "fixture",
        "admission_sha256": cfg["admission"]["sha256"],
    }
    validate_admission_fields(cfg, admitted, complete)
    if mutation == "DEV_selection":
        admitted["splits"]["dev"] = ["a_different_layout"]
    if mutation == "image_binding":
        admitted["dataset_file_sha256"][next(iter(files))] = "0" * 64
    if mutation == "finalization":
        complete["status"] = "STARTED"
    with pytest.raises(ValueError):
        validate_admission_fields(cfg, admitted, complete)


def test_native_rgb_loader_rejects_missing_globals_before_source_access():
    from recorded_rgb_stop_v1 import ULVN_RGB_GLOBALS_V2, load_ulvn_rgb_definitions_v2

    namespace = dict.fromkeys(ULVN_RGB_GLOBALS_V2, object())
    for name in ULVN_RGB_GLOBALS_V2:
        reduced = dict(namespace)
        del reduced[name]
        with pytest.raises(ValueError, match="native RGB globals missing"):
            load_ulvn_rgb_definitions_v2({}, reduced)


def test_native_rgb_loader_rejects_globals_outside_frozen_allowlist():
    from recorded_rgb_stop_v1 import ULVN_RGB_GLOBALS_V2, load_ulvn_rgb_definitions_v2

    namespace = dict.fromkeys(ULVN_RGB_GLOBALS_V2, object())
    namespace["unapproved"] = object()
    with pytest.raises(ValueError, match="outside fixed allowlist"):
        load_ulvn_rgb_definitions_v2({}, namespace)
