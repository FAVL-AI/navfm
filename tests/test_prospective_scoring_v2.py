import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from offline_evaluation_contracts_v1 import atomic_snapshot, pairs_from_metadata, retained_attempt
from prospective_collection_budget_v2 import finalize_transaction
from prospective_data_contracts_v1 import content_sha, preserve_raw_draw
from prospective_scoring_contracts_v2 import COLLECTION_FREEZE, verify_bound_dataset


def synthetic_transaction(tmp_path):
    names = ["fixture0", "fixture1", "fixture2", "fixture3"]
    dataset = tmp_path / "data"
    dataset.mkdir()
    artifacts = {}
    for index in range(152):
        p = tmp_path / f"file{index}"
        p.write_bytes(b"fixture")
        artifacts[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    registry = tmp_path / "registry.json"
    admitted = dict(
        status="PASS",
        source_freeze=COLLECTION_FREEZE,
        splits={"train": [], "dev": names, "test": []},
        trajectories=[dict(id=n, processed_frames=36) for n in names],
    )
    finalize_transaction(
        tmp_path,
        registry,
        dict(status="PASS", freeze=COLLECTION_FREEZE, artifacts=artifacts),
        admitted,
        0,
        now=lambda: 10,
    )
    cfg = json.loads(
        (Path(__file__).parents[1] / "configs/eval/prospective_scoring_v2.json").read_text()
    )
    cfg.update(
        dataset=str(dataset),
        admission=str(tmp_path / "admission.json"),
        partitions={"train": [], "development": names},
        pairs={"development": pairs_from_metadata(names, dict.fromkeys(names, 36), [])},
    )
    cfg["collected_dataset_binding"] = dict(
        out=str(tmp_path),
        registry=str(registry),
        source_freeze=COLLECTION_FREEZE,
        identity={
            n: hashlib.sha256(
                (registry if n == "registry" else tmp_path / n).read_bytes()
            ).hexdigest()
            for n in ["registry", "ledger.json", "admission.json", "finalization_complete.json"]
        },
    )
    return cfg


def test_completed_dataset_bind_and_fixed_population(tmp_path):
    cfg = synthetic_transaction(tmp_path)
    assert verify_bound_dataset(cfg)["status"] == "PASS"
    assert len(cfg["pairs"]["development"]) == 32
    assert sum(not p["negative"] for p in cfg["pairs"]["development"]) == 16
    assert 4 * len(cfg["pairs"]["development"]) * cfg["evaluation"]["draws"]["gnm"] == 128
    assert 4 * len(cfg["pairs"]["development"]) * cfg["evaluation"]["draws"]["nomad"] == 512


@pytest.mark.parametrize("fault", ["wrong_source", "wrong_dataset", "marker", "artifact"])
def test_wrong_dataset_transaction_or_artifact_rejected(tmp_path, fault):
    cfg = synthetic_transaction(tmp_path)
    if fault == "wrong_source":
        cfg["collected_dataset_binding"]["source_freeze"] = "old-failed-freeze"
    if fault == "wrong_dataset":
        cfg["dataset"] = str(tmp_path / "other")
    if fault == "marker":
        (tmp_path / "finalization_complete.json").write_text("{}")
    if fault == "artifact":
        (tmp_path / "file0").write_bytes(b"changed")
    with pytest.raises(ValueError):
        verify_bound_dataset(cfg)


def test_invalid_raw_draw_survives_metric_exception_and_partial_snapshot(tmp_path):
    report = dict(rows=[])
    path = tmp_path / "report.json"

    def metric(*values):
        raise ValueError("controlled malformed output")

    wrapped = preserve_raw_draw(report, metric)

    def predict():
        return wrapped([[float("nan"), 1.0]], [])

    with pytest.raises(ValueError):
        retained_attempt(
            report, dict(pair_index=0, draw=0), predict, lambda: atomic_snapshot(path, report)
        )
    saved = json.loads(path.read_text())["rows"][0]
    assert saved["raw_prediction"]["actions"][0][0] == {"nonfinite": "nan"}
    assert saved["raw_prediction_sha256"] == content_sha(saved["raw_prediction"])
    assert saved["returned"] is False and saved["error_type"] == "ValueError"


def test_atomic_failure_preserves_prior_raw_draw(tmp_path, monkeypatch):
    import offline_evaluation_contracts_v1 as snapshots

    path = tmp_path / "report.json"
    prior = dict(rows=[dict(raw_prediction=dict(actions=[[1, 2]], distances=[3]))])
    atomic_snapshot(path, prior)

    def fail(*args):
        raise OSError("controlled replace failure")

    monkeypatch.setattr(snapshots.os, "replace", fail)
    with pytest.raises(OSError):
        atomic_snapshot(path, dict(rows=[]))
    assert json.loads(path.read_text()) == prior


def test_added_project_sources_are_attested_without_model_imports(tmp_path):
    from types import ModuleType

    from native_dependency_closure_v2 import verify_native_dependencies

    cfg = json.loads(
        (Path(__file__).parents[1] / "configs/eval/prospective_scoring_v2.json").read_text()
    )
    closure = json.loads(Path(cfg["native_dependency_manifest"]).read_text())
    modules = {}
    for index, path in enumerate(closure["continuation_source_addendum"]["added_project_paths"]):
        module = ModuleType(f"continuation{index}")
        module.__file__ = path
        modules[module.__name__] = module
    assert len(verify_native_dependencies(cfg, modules)) == 5
    foreign = tmp_path / "foreign.py"
    foreign.write_text("value=1\n")
    modules["continuation0"].__file__ = str(foreign)
    with pytest.raises(ImportError):
        verify_native_dependencies(cfg, modules)


def score_fixture(tmp_path):
    (tmp_path / "raw.txt").write_text("retained output")
    reservations = tmp_path.parent / (tmp_path.name + "-reservations.json")
    prior = [dict(model="gnm", freeze="test-freeze", status="STARTED", out=str(tmp_path))]
    atomic_snapshot(reservations, prior)
    ledger = dict(model="gnm", freeze="test-freeze", status="PASS")
    return reservations, prior, ledger


@pytest.mark.parametrize("fault", ["ledger", "artifact", "registry"])
def test_actual_scoring_finalization_failure_cannot_admit_next_stage(tmp_path, monkeypatch, fault):
    import prospective_scoring_contracts_v2 as contracts

    reservations, prior, ledger = score_fixture(tmp_path)
    original_sha = contracts.sha

    def digest(path):
        if fault == "artifact" and path.name == "raw.txt":
            raise OSError("controlled artifact failure")
        return original_sha(path)

    monkeypatch.setattr(contracts, "sha", digest)
    failed = [False]

    def writer(path, value):
        if not failed[0] and (
            (fault == "ledger" and path.name == "ledger.json")
            or (fault == "registry" and path == reservations)
        ):
            failed[0] = True
            raise OSError("controlled persistence failure")
        atomic_snapshot(path, value)

    with pytest.raises(OSError):
        contracts.finalize_score(tmp_path, reservations, prior, ledger, 0, writer, lambda: 10)
    assert ledger["status"] == "FAIL" and prior[-1]["status"] == "FAIL"
    assert not (tmp_path / "scoring_complete.json").exists()
    with pytest.raises(ValueError):
        contracts.verify_prior_scores(prior, "test-freeze")


def test_scoring_persistence_overrun_invalidates_completed_marker(tmp_path):
    from prospective_scoring_contracts_v2 import finalize_score, verify_prior_scores

    reservations, prior, ledger = score_fixture(tmp_path)
    clock = [1799.0]

    def writer(path, value):
        atomic_snapshot(path, value)
        if path == reservations:
            clock[0] = 1800.01

    with pytest.raises(TimeoutError):
        finalize_score(tmp_path, reservations, prior, ledger, 0, writer, lambda: clock[0])
    assert ledger["status"] == "FAIL" and not (tmp_path / "scoring_complete.json").exists()
    with pytest.raises(ValueError):
        verify_prior_scores(json.loads(reservations.read_text()), "test-freeze")


def test_completed_scoring_stage_requires_bound_output_and_artifacts(tmp_path):
    from prospective_scoring_contracts_v2 import finalize_score, verify_prior_scores

    reservations, prior, ledger = score_fixture(tmp_path)
    finalize_score(tmp_path, reservations, prior, ledger, 0, now=lambda: 10)
    verify_prior_scores(prior, "test-freeze")
    (tmp_path / "raw.txt").write_text("changed")
    with pytest.raises(ValueError, match="artifact"):
        verify_prior_scores(prior, "test-freeze")
