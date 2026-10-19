from __future__ import annotations

import hashlib
import json
import signal
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import navfm.collection.static_arrival_camera_qualification as qualification

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from static_arrival_camera_qualification_worker_v1 import (  # noqa: E402
    _retain_failed_frame_diagnostics,
)

from navfm.collection.static_arrival_camera_qualification import (  # noqa: E402
    CAP_SECONDS,
    EPISODE_ID,
    FRAME_COUNT,
    QUERY_POSES,
    REFERENCE_POSES,
    build_qualification,
    build_worker_input,
    run_one_shot,
    run_supervised_worker,
    verify_capture,
    verify_completion_marker,
    verify_source_bindings,
)


def _worker_command(mode: str = "success") -> list[str]:
    return [
        sys.executable,
        str(ROOT / "tests/fixtures/static_arrival_camera_qualification_worker.py"),
        "--mode",
        mode,
    ]


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_freeze_binds_exposed_scene_fixture_and_exact_eight_frame_order():
    config = build_qualification(ROOT)
    worker_input = build_worker_input(config)
    assert config["status"] == "PREPARED_FOR_APPROVAL"
    assert config["fixture"]["identity"] == "legacy_corridor_scene_0"
    assert config["fixture"]["scene_index"] == 0
    assert config["population"] == {"frames": 8, "references": 3, "queries": 5}
    assert len(worker_input["frames"]) == FRAME_COUNT == 8
    assert [frame["role"] for frame in worker_input["frames"]] == [
        "reference",
        "reference",
        "reference",
        "query",
        "query",
        "query",
        "query",
        "query",
    ]
    assert len({frame["image_id"] for frame in worker_input["frames"]}) == 8
    assert all(frame["episode_id"] == EPISODE_ID for frame in worker_input["frames"])
    assert config["schedule"]["references"][0]["body_pose_xy_yaw_rad"] == list(REFERENCE_POSES[0])
    assert config["schedule"]["queries"][-1]["body_pose_xy_yaw_rad"] == list(QUERY_POSES[-1])
    assert config["budget"]["whole_process_cap_seconds"] == CAP_SECONDS == 120.0
    assert config["budget"]["status"] == "PROPOSED_FOR_APPROVAL_NOT_MEASURED"
    assert config["evidence"]["dataset_admission"] is False
    assert config["overlap_audit"] == {
        "planned_episode_identity_overlap": [],
        "exact_body_pose_overlap": [],
        "scene_specification_overlap": ["legacy_corridor_scene_0/F0"],
    }
    assert config["runtime"]["isaacsim_distribution_version"] == "5.1.0.0"


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_source_bindings_are_exact_and_reject_modified_source():
    config = build_qualification(ROOT)
    verify_source_bindings(config, ROOT)
    config["source_bindings"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source hash mismatch"):
        verify_source_bindings(config, ROOT)


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_harmless_subprocess_worker_passes_camera_evidence_contract(tmp_path: Path):
    config = build_qualification(ROOT)
    worker_input = build_worker_input(config)
    output = tmp_path / "qualification"
    record = run_supervised_worker(
        command=_worker_command(),
        output=output,
        worker_input=worker_input,
        freeze="fixture-freeze",
        cap_seconds=40,
    )
    assert record["status"] == "QUALIFICATION_PASS"
    assert record["frame_count"] == 8
    assert record["reference_count"] == 3
    assert record["query_count"] == 5
    assert record["child_exit_code"] == 0 and record["child_reaped"] is True
    assert record["timeout"] is False
    assert record["dataset_admission"] is False
    assert not record["finalization_complete"]
    assert not (output / "qualification_complete.json").exists()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        ("duplicate_time", "not strictly ordered"),
        ("label", "evaluator-only data"),
        ("metadata", "same-snapshot metadata"),
    ],
)
@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_qualification_admission_rejects_timing_label_and_snapshot_drift(
    tmp_path: Path, mutate: str, message: str
):
    config = build_qualification(ROOT)
    worker_input = build_worker_input(config)
    output = tmp_path / mutate
    run_supervised_worker(
        command=_worker_command(),
        output=output,
        worker_input=worker_input,
        freeze="fixture-freeze",
        cap_seconds=40,
    )
    report_path = output / "capture_report.json"
    report = json.loads(report_path.read_text())
    if mutate == "duplicate_time":
        report["frames"][1]["camera"]["rendering_time"] = report["frames"][0]["camera"][
            "rendering_time"
        ]
        report_path.write_text(json.dumps(report))
    elif mutate == "label":
        report["frames"][0]["geometric_proximity_label"] = True
        report_path.write_text(json.dumps(report))
    else:
        path = output / "capture_metadata" / f"{report['frames'][0]['image_id']}.json"
        metadata = json.loads(path.read_text())
        metadata["rendering_time"] += 0.1
        path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match=message):
        verify_capture(output, worker_input)


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_one_shot_registry_and_final_marker_bind_both_terminal_records(tmp_path: Path):
    config = build_qualification(ROOT)
    output = tmp_path / "evidence/one-shot"
    registry = tmp_path / "evidence/registry"
    record = run_one_shot(
        config=config,
        output=output,
        registry=registry,
        freeze="fixture-full-sha",
        worker_command=_worker_command(),
        root=ROOT,
    )
    assert record["status"] == "QUALIFICATION_PASS"
    marker = json.loads((output / "qualification_complete.json").read_text())
    registry_terminal = registry / "technical-scene0.reserved.terminal.json"
    terminal = output / "terminal_record.json"
    assert json.loads(terminal.read_text())["finalization_complete"] is True
    assert marker["terminal_sha256"] == hashlib.sha256(terminal.read_bytes()).hexdigest()
    assert (
        marker["registry_terminal_sha256"]
        == hashlib.sha256(registry_terminal.read_bytes()).hexdigest()
    )
    assert marker["freeze"] == "fixture-full-sha"
    assert json.loads(terminal.read_text())["dataset_admission"] is False
    assert json.loads(terminal.read_text())["child_exit_code"] == 0
    verify_completion_marker(output, registry_terminal, "fixture-full-sha")
    with pytest.raises(ValueError, match="already consumed"):
        run_one_shot(
            config=config,
            output=tmp_path / "evidence/retry",
            registry=registry,
            freeze="fixture-full-sha",
            worker_command=_worker_command(),
            root=ROOT,
        )


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_completion_marker_detects_capture_metadata_mutation(tmp_path: Path):
    config = build_qualification(ROOT)
    output = tmp_path / "evidence/one-shot"
    registry = tmp_path / "evidence/registry"
    run_one_shot(
        config=config,
        output=output,
        registry=registry,
        freeze="fixture-full-sha",
        worker_command=_worker_command(),
        root=ROOT,
    )
    row = json.loads((output / "capture_report.json").read_text())["frames"][0]
    metadata = output / "capture_metadata" / f"{row['image_id']}.json"
    metadata.write_text(metadata.read_text() + " ")
    with pytest.raises(ValueError, match="artifact changed after admission"):
        verify_completion_marker(
            output,
            registry / "technical-scene0.reserved.terminal.json",
            "fixture-full-sha",
        )


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_one_shot_refuses_preexisting_output_directory(tmp_path: Path):
    config = build_qualification(ROOT)
    output = tmp_path / "evidence/existing"
    output.mkdir(parents=True)
    (output / "preserve.txt").write_text("existing")
    with pytest.raises(ValueError, match="new and external"):
        run_one_shot(
            config=config,
            output=output,
            registry=tmp_path / "evidence/registry",
            freeze="fixture-full-sha",
            worker_command=_worker_command(),
            root=ROOT,
        )
    assert (output / "preserve.txt").read_text() == "existing"


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_worker_failure_is_preserved_with_exit_and_reap_status(tmp_path: Path):
    output = tmp_path / "failure"
    with pytest.raises(ValueError, match="worker failed"):
        run_supervised_worker(
            command=_worker_command("failure"),
            output=output,
            worker_input=build_worker_input(build_qualification(ROOT)),
            freeze="fixture-freeze",
            cap_seconds=40,
        )
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert terminal["status"] == "FAIL"
    assert terminal["child_exit_code"] == 7
    assert terminal["child_reaped"] is True
    assert not terminal["timeout"]
    assert (output / "partial.capture").is_file()


def test_failed_frame_diagnostics_preserve_requested_pose_readbacks_and_rgb(
    tmp_path: Path,
):
    class Camera:
        def get_world_pose(self, *, camera_axes: str):
            assert camera_axes == "world"
            return np.asarray([1.2, 0.0, 0.55]), np.asarray([1.0, 0.0, 0.0, 0.0])

        def get_current_frame(self, *, clone: bool):
            assert clone is True
            return {
                "rgb": np.arange(48, dtype=np.uint8).reshape(4, 4, 3),
                "rendering_time": 2.5,
                "rendering_frame": {
                    "referenceTimeNumerator": 5,
                    "referenceTimeDenominator": 2,
                },
            }

    output = tmp_path / "failed-attempt"
    output.mkdir()
    frame = {
        "image_id": "failed_query_00",
        "body_pose_xy_yaw_rad": [1.0, 0.0, 0.0],
    }
    report = {
        "camera_config": {"forward_offset_m": 0.2, "camera_height_m": 0.55},
        "frames": [{"image_id": frame["image_id"], "status": "STARTED"}],
    }
    _retain_failed_frame_diagnostics(
        Camera(), np, frame, output, report, RuntimeError("fixture only")
    )
    event = report["frames"][0]
    assert event["status"] == "FAIL"
    assert event["diagnostic_requested_camera_position"] == [1.2, 0.0, 0.55]
    assert event["diagnostic_actual_camera_position"] == [1.2, 0.0, 0.55]
    assert event["diagnostic_pose_readback_status"] == "READ"
    assert event["diagnostic_snapshot_status"] == "READ"
    saved = np.load(output / "failure_evidence/failed_query_00.npy", allow_pickle=False)
    assert saved.shape == (4, 4, 3)
    assert (
        event["diagnostic_rgb_sha256"]
        == hashlib.sha256(
            (output / "failure_evidence/failed_query_00.npy").read_bytes()
        ).hexdigest()
    )


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_timeout_veto_kills_and_reaps_harmless_worker(tmp_path: Path):
    output = tmp_path / "timeout"
    with pytest.raises(TimeoutError, match="single deadline"):
        run_supervised_worker(
            command=_worker_command("hang"),
            output=output,
            worker_input=build_worker_input(build_qualification(ROOT)),
            freeze="fixture-freeze",
            cap_seconds=32,
        )
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert terminal["status"] == "FAIL"
    assert terminal["timeout"] is True
    assert terminal["child_reaped"] is True
    assert not (output / "qualification_complete.json").exists()


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_supervisor_terminates_and_reaps_after_wait_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class InterruptedChild:
        pid = 12345
        returncode = None
        wait_calls = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise RuntimeError("synthetic wait interruption")
            self.returncode = -signal.SIGTERM
            return self.returncode

    child = InterruptedChild()
    monkeypatch.setattr(qualification.subprocess, "Popen", lambda *args, **kwargs: child)
    signalled = []
    monkeypatch.setattr(qualification.os, "killpg", lambda pid, sig: signalled.append((pid, sig)))
    output = tmp_path / "interrupted-wait"
    with pytest.raises(RuntimeError, match="synthetic wait interruption"):
        run_supervised_worker(
            command=_worker_command(),
            output=output,
            worker_input=build_worker_input(build_qualification(ROOT)),
            freeze="fixture-freeze",
            cap_seconds=40,
        )
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert signalled == [(child.pid, signal.SIGTERM)]
    assert terminal["child_exit_code"] == -signal.SIGTERM
    assert terminal["child_reaped"] is True
    assert terminal["status"] == "FAIL"


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_supervisor_falls_back_to_child_signal_when_process_group_signal_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    class SignalFailureChild:
        pid = 12346
        returncode = None
        wait_calls = 0

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = -signal.SIGTERM

        def wait(self, timeout=None):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise RuntimeError("synthetic wait interruption")
            return self.returncode

    child = SignalFailureChild()
    monkeypatch.setattr(qualification.subprocess, "Popen", lambda *args, **kwargs: child)

    def fail_group_signal(pid, sig):
        raise PermissionError("synthetic process-group signal denial")

    monkeypatch.setattr(qualification.os, "killpg", fail_group_signal)
    output = tmp_path / "signal-failure"
    with pytest.raises(RuntimeError, match="synthetic wait interruption"):
        run_supervised_worker(
            command=_worker_command(),
            output=output,
            worker_input=build_worker_input(build_qualification(ROOT)),
            freeze="fixture-freeze",
            cap_seconds=40,
        )
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert terminal["cleanup_term_group_error_type"] == "PermissionError"
    assert terminal["child_exit_code"] == -signal.SIGTERM
    assert terminal["child_reaped"] is True


@pytest.mark.isaac_host  # build_qualification() requires the bound Isaac worker interpreter
def test_finalization_marker_failure_revokes_qualification_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    output = tmp_path / "finalization-failure"
    original = qualification._atomic_json

    def fail_marker(path: Path, value: dict) -> None:
        if path.name == "qualification_complete.json":
            raise OSError("controlled qualification marker failure")
        original(path, value)

    monkeypatch.setattr(qualification, "_atomic_json", fail_marker)
    with pytest.raises(OSError, match="controlled qualification marker failure"):
        run_one_shot(
            config=build_qualification(ROOT),
            output=output,
            registry=tmp_path / "registry",
            freeze="fixture-freeze",
            worker_command=_worker_command(),
            root=ROOT,
        )
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert terminal["status"] == "FAIL"
    assert terminal["failure_type"] == "FinalizationFailure"
    assert not (output / "qualification_complete.json").exists()


def test_production_qualification_cli_requires_explicit_approval_and_exact_head(tmp_path: Path):
    script = ROOT / "scripts/static_arrival_camera_qualification_v1.py"
    result = subprocess.run(
        [sys.executable, str(script), "--freeze", "not-the-head", "--out", str(tmp_path / "out")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "--execute-approved" in result.stderr
    assert not (tmp_path / "out").exists()


def test_worker_constructs_isaac_app_before_omni_imports():
    worker_source = (ROOT / "scripts/static_arrival_camera_qualification_worker_v1.py").read_text()
    assert worker_source.index("with IsaacApp(") < worker_source.index("import omni.usd")
    assert worker_source.index("with IsaacApp(") < worker_source.index(
        "from isaacsim.sensors.camera import Camera"
    )
