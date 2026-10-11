"""Negative controls for resource evidence: absent readiness never becomes success."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location("resource_ci", Path(__file__).parents[1] / "scripts/resource_ci.py")
assert _SPEC and _SPEC.loader
resource = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(resource)


@pytest.fixture(autouse=True)
def stable_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resource, "source_identity", lambda root: {"head": "a" * 40, "tracked_sha256": "c" * 64})


def evidence() -> dict:
    return {"source_identity": {"head": "a" * 40, "tracked_sha256": "c" * 64}, "head": "a" * 40, "manifest_sha256": "b" * 64,
            "population": {"collected": {"test.py::case": []}, "deselected": [],
                           "collection_errors": [], "outcomes": {}, "skip_reasons": {}},
            "versions": {}}


@pytest.mark.parametrize("field", ["head", "manifest_sha256"])
def test_different_source_or_population_is_refused(field: str) -> None:
    item = evidence()
    item[field] = "wrong"
    with pytest.raises(ValueError, match="different source/population"):
        resource.validate_evidence(item, "a" * 40, "b" * 64)


def test_collected_but_unexecuted_node_is_refused() -> None:
    with pytest.raises(ValueError, match="complete outcome"):
        resource.validate_evidence(evidence(), "a" * 40, "b" * 64)


@pytest.mark.parametrize("outcome", ["failed", "skipped", "error"])
def test_every_nonpassing_outcome_blocks_attestation(outcome: str) -> None:
    item = evidence()
    item["population"]["outcomes"] = {"test.py::case": outcome}
    with pytest.raises(ValueError, match="failures/skips"):
        resource.validate_evidence(item, "a" * 40, "b" * 64)


def test_missing_manual_owner_run_is_failure_not_pending_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "FAVL-AI/navfm")
    monkeypatch.setattr(resource.subprocess, "check_output", lambda *a, **kw: b'{"workflow_runs": []}')
    with pytest.raises(ValueError, match="no successful manually approved"):
        resource.github_evidence("a" * 40)


def test_missing_environment_protection_is_refused() -> None:
    with pytest.raises(ValueError, match="independent approval"):
        resource.validate_security_environment({})


@pytest.mark.parametrize("mutation", ["reviewers", "prevent_self_review", "deployment_branch_policy"])
def test_each_workstation_security_requirement_is_mandatory(mutation: str) -> None:
    env = {"protection_rules": [{"type": "required_reviewers", "reviewers": [{"id": 1}],
                                "prevent_self_review": True}],
           "deployment_branch_policy": {"custom_branch_policies": True}}
    resource.validate_security_environment(env)
    if mutation == "deployment_branch_policy":
        env[mutation] = None
    else:
        env["protection_rules"][0][mutation] = False
    with pytest.raises(ValueError):
        resource.validate_security_environment(env)


@pytest.mark.parametrize("jobs", [[], [{"name": "resource-validation", "status": "in_progress", "conclusion": None}],
                                   [{"name": "resource-validation", "status": "completed", "conclusion": "failure"}]])
def test_current_run_missing_or_failed_owner_is_refused(jobs: list, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    monkeypatch.setenv("GITHUB_REPOSITORY", "FAVL-AI/navfm")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setattr(resource.subprocess, "check_output", lambda *a, **kw: json.dumps({"jobs": jobs}).encode())
    with pytest.raises(ValueError, match="did not complete successfully"):
        resource.current_owner_evidence("a" * 40)


def test_current_successful_owner_verifies_artifact_without_overall_run_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "FAVL-AI/navfm")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setattr(resource.subprocess, "check_output", lambda *a, **kw:
                        b'{"jobs":[{"name":"resource-validation","status":"completed","conclusion":"success"}]}')
    seen = []
    monkeypatch.setattr(resource, "verify_run_artifact", lambda run, head: seen.append((run, head)))
    resource.current_owner_evidence("a" * 40)
    assert seen == [(123, "a" * 40)]


@pytest.mark.parametrize("changed", ["head", "tracked_sha256"])
def test_source_or_head_change_after_preflight_is_refused(changed: str) -> None:
    before = {"head": "a" * 40, "tracked_sha256": "c" * 64}
    after = {**before, changed: "changed"}
    with pytest.raises(ValueError, match="changed after preflight"):
        resource.validate_preflight_identity(before, after, {"repository": {"head": after["head"]}})


def test_matching_head_with_different_tracked_bytes_is_refused() -> None:
    item = evidence()
    item["source_identity"]["tracked_sha256"] = "different"
    with pytest.raises(ValueError, match="actual tracked source bytes"):
        resource.validate_evidence(item, "a" * 40, "b" * 64)


def test_sole_maintainer_requires_explicit_mode_and_retains_branch_guard() -> None:
    environment = {"protection_rules": [], "deployment_branch_policy": {"custom_branch_policies": True}}
    with pytest.raises(ValueError, match="independent approval"):
        resource.validate_security_environment(environment)
    resource.validate_security_environment(environment, "sole-maintainer")
    environment["deployment_branch_policy"] = None
    with pytest.raises(ValueError, match="branch restrictions"):
        resource.validate_security_environment(environment, "sole-maintainer")


def test_approval_mode_rejects_unknown_and_misrepresented_review() -> None:
    environment = {"protection_rules": [], "deployment_branch_policy": {"custom_branch_policies": True}}
    for mode in ("", "self-review", "SOLE-MAINTAINER"):
        with pytest.raises(ValueError, match="unknown"):
            resource.validate_security_environment(environment, mode)
    environment["protection_rules"] = [{"type": "required_reviewers", "reviewers": [], "prevent_self_review": False}]
    with pytest.raises(ValueError, match="must not represent"):
        resource.validate_security_environment(environment, "sole-maintainer")


def test_security_environment_reads_explicit_mode_and_reports_reduced_assurance(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    import json
    monkeypatch.setenv("GITHUB_REPOSITORY", "FAVL-AI/navfm")
    monkeypatch.setenv("NAVFM_RESOURCE_APPROVAL_MODE", "sole-maintainer")
    environment = {"protection_rules": [], "deployment_branch_policy": {"custom_branch_policies": True}}
    monkeypatch.setattr(resource.subprocess, "check_output", lambda *a, **kw: json.dumps(environment).encode())
    resource.security_environment()
    assert "not independent human review" in capsys.readouterr().out
    monkeypatch.delenv("NAVFM_RESOURCE_APPROVAL_MODE")
    with pytest.raises(ValueError, match="independent approval"):
        resource.security_environment()
