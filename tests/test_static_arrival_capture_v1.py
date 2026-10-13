from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from static_arrival_capture_launcher_v1 import (  # noqa: E402
    finalize_attempt,
    run_attempt,
)

from navfm.collection.static_arrival_capture import (  # noqa: E402
    FAMILY_ROLES,
    STRATA,
    build_schedule,
    capture_worker_input,
    evaluator_label_rows,
    validate_schedule,
    verify_source_manifest,
)


def _fixture_command(
    tmp_path: Path, family: str, mode: str = "success", label: str = "attempt"
) -> list[str]:
    worker = ROOT / "tests/fixtures/static_arrival_capture_worker.py"
    output = tmp_path / "external" / f"{family}-{label}"
    return [
        sys.executable,
        str(worker),
        "--config",
        str(ROOT / "configs/eval/arrival_measures_v1.json"),
        "--family-input",
        str(output / "attempt_inputs/family_input.json"),
        "--out",
        str(output),
        "--mode",
        mode,
    ]


def _attempt(
    tmp_path: Path, family: str = "F0", mode: str = "success", label: str = "attempt", **kwargs
):
    output = tmp_path / "external" / f"{family}-{label}"
    return run_attempt(
        config=build_schedule(),
        family=family,
        output=output,
        registry=tmp_path / "external" / "registry",
        freeze="synthetic-test-freeze",
        worker_command=_fixture_command(tmp_path, family, mode, label),
        wall_cap_s=kwargs.pop("wall_cap_s", 12.0),
        reap_reserve_s=kwargs.pop("reap_reserve_s", 1.0),
        finalize_reserve_s=kwargs.pop("finalize_reserve_s", 1.0),
        allow_fixture=True,
        **kwargs,
    )


def test_schedule_binds_population_roles_scenes_and_strata():
    config = build_schedule()
    counts = validate_schedule(config)
    assert counts == {"episodes": 20, "references": 160, "queries": 720, "decisions": 480}
    assert {episode["partition_role"] for episode in config["episodes"]} == set(
        FAMILY_ROLES.values()
    )
    assert len({episode["episode_id"] for episode in config["episodes"]}) == 20
    assert len({episode["goal_id"] for episode in config["episodes"]}) == 20
    assert len(config["scene_adapter"]["scenes"]) == 8
    assert config["camera"]["sim_hz"] == 16
    assert config["camera"]["held_sim_steps_per_capture"] == 4
    assert config["wall_budget"]["status"] == "PROPOSED_NOT_AUTHORIZED_NOT_MEASURED"
    assert config["wall_budget"]["whole_process_cap_seconds_per_family"] == 600
    assert config["wall_budget"]["pre_reap_attempt_allowance_seconds"] == 570
    assert config["wall_budget"]["child_reap_reserve_seconds"] == 10
    assert config["wall_budget"]["verification_and_finalization_reserve_seconds"] == 20


def test_checked_schedule_matches_current_bound_source():
    config_path = ROOT / "configs/eval/static_arrival_training_acquisition_v2.json"
    checked = json.loads(config_path.read_text())
    generated = build_schedule()
    assert checked == generated
    verify_source_manifest(checked, ROOT)


@pytest.mark.parametrize("mutation", ["duplicate_frame", "duplicate_episode", "exclude", "scene"])
def test_schedule_rejects_identity_exclusion_and_scene_drift(mutation: str):
    config = build_schedule()
    if mutation == "duplicate_frame":
        config["episodes"][1]["query_frames"][0]["image_id"] = config["episodes"][0][
            "query_frames"
        ][0]["image_id"]
    elif mutation == "duplicate_episode":
        config["episodes"][1]["episode_id"] = config["episodes"][0]["episode_id"]
    elif mutation == "exclude":
        config["exclusions"]["known_source_trajectory_ids_excluded"].append(
            config["episodes"][0]["episode_id"]
        )
    else:
        config["episodes"][0]["scene_index"] = 9
    with pytest.raises(ValueError):
        validate_schedule(config)


def test_worker_input_keeps_labels_out_and_binds_episode_identity():
    config = build_schedule()
    family = capture_worker_input(config, "F0")
    assert len(family["episodes"]) == 4
    assert len(family["frames"]) == 176
    assert len({frame["image_id"] for frame in family["frames"]}) == 176
    assert all(frame["episode_id"] for frame in family["frames"])
    assert all(
        not any(stratum in frame["image_id"] for stratum in STRATA) for frame in family["frames"]
    )
    assert all("geometric_proximity_label" not in frame for frame in family["frames"])
    assert all("distance_m" not in frame for frame in family["frames"])
    labels = evaluator_label_rows(config, "F0")
    assert len(labels) == 144
    assert all(row["access"] == "EVALUATOR_ONLY_NOT_DECISION_INPUT" for row in labels)


def test_source_manifest_requires_exact_bound_sources():
    config = build_schedule()
    verify_source_manifest(config, ROOT)
    config["source_bindings"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source hash"):
        verify_source_manifest(config, ROOT)


def test_runtime_flag_alone_cannot_bypass_camera_qualification():
    config = build_schedule()
    config["runtime_authorized"] = True
    with pytest.raises(ValueError, match="camera runtime qualification"):
        validate_schedule(config)


def test_actual_launcher_supervisor_success_is_fixture_only_and_one_shot(tmp_path: Path):
    record = _attempt(tmp_path)
    output = tmp_path / "external/F0-attempt"
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert record["status"] == "CONTRACT_TEST_ONLY_PASS"
    assert terminal["status"] == "CONTRACT_TEST_ONLY_PASS"
    assert terminal["child_exit_code"] == 0 and terminal["child_reaped"] is True
    assert terminal["frame_count"] == 176
    assert terminal["reference_count"] == 32
    assert terminal["query_count"] == 144
    assert terminal["scored_decisions"] == 96
    assert not (output / "finalization_complete.json").exists()
    with pytest.raises(ValueError, match="output must be new"):
        _attempt(tmp_path)
    with pytest.raises(ValueError, match="already consumed"):
        _attempt(tmp_path, label="retry")


def test_production_cli_refuses_preparation_schedule(tmp_path: Path):
    launcher = ROOT / "scripts/static_arrival_capture_launcher_v1.py"
    output = tmp_path / "external/production-refusal"
    result = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "--family",
            "F0",
            "--out",
            str(output),
            "--freeze",
            "test-only",
            "--execute-approved",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "preparation-only" in result.stderr
    assert not output.exists()


def test_worker_failure_retains_partial_output_and_terminal_status(tmp_path: Path):
    with pytest.raises(ValueError, match="worker failed"):
        _attempt(tmp_path, mode="failure")
    output = tmp_path / "external/F0-attempt"
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert terminal["status"] == "FAIL"
    assert terminal["child_exit_code"] == 7 and terminal["child_reaped"] is True
    assert (output / "partial.capture").is_file()


def test_timeout_is_a_veto_and_child_is_reaped(tmp_path: Path):
    with pytest.raises(TimeoutError, match="deadline"):
        _attempt(
            tmp_path,
            mode="hang",
            wall_cap_s=0.7,
            reap_reserve_s=0.2,
            finalize_reserve_s=0.2,
        )
    output = tmp_path / "external/F0-attempt"
    terminal = json.loads((output / "terminal_record.json").read_text())
    assert terminal["status"] == "FAIL"
    assert terminal["timeout"] is True and terminal["child_reaped"] is True
    assert not (output / "finalization_complete.json").exists()


def test_finalization_marker_failure_revokes_admission(tmp_path: Path):
    output = tmp_path / "external/finalization"
    reservation = tmp_path / "external/registry/F0.reserved.json"
    output.mkdir(parents=True)
    reservation.parent.mkdir(parents=True)
    (output / "attempt_start.json").write_text("{}")
    record = {"status": "PASS", "freeze": "fixture"}

    def marker_fails(path: Path, value: dict) -> None:
        if path.name == "finalization_complete.json":
            raise OSError("controlled marker failure")
        path.write_text(json.dumps(value))

    with pytest.raises(OSError, match="controlled marker"):
        finalize_attempt(output, reservation, record, marker_fails)
    terminal = json.loads((output / "terminal_record.json").read_text())
    registry_terminal = json.loads(reservation.with_suffix(".terminal.json").read_text())
    assert terminal["status"] == registry_terminal["status"] == "FAIL"
    assert terminal["finalization_complete"] is False
    assert not (output / "finalization_complete.json").exists()
