#!/usr/bin/env python3
"""Fail-closed read-only resource preflight and manual-run evidence verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = "navfm-resource-validation"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity(root: Path) -> dict:
    """Tracked bytes only; external outputs and untracked caches are not inputs."""
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"]):
        raise ValueError("tracked candidate tree is dirty")
    paths = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).decode().split("\0")
    records = [(relative, sha(root / relative)) for relative in sorted(filter(None, paths))]
    digest = hashlib.sha256(json.dumps(records, separators=(",", ":")).encode()).hexdigest()
    return {"head": head, "tracked_sha256": digest, "tracked_count": len(records)}


def validate_preflight_identity(before: dict, after: dict, capture: dict) -> None:
    if before != after or capture["repository"]["head"] != after["head"]:
        raise ValueError("tracked source or HEAD changed after preflight")


def validate_evidence(evidence: dict, expected_head: str, manifest_sha: str) -> None:
    if evidence.get("head") != expected_head or evidence.get("manifest_sha256") != manifest_sha:
        raise ValueError("resource evidence is for a different source/population")
    if evidence.get("source_identity") != source_identity(ROOT):
        raise ValueError("actual tracked source bytes differ from resource evidence")
    report = evidence["population"]
    executed = set(report["collected"]) - set(report["deselected"])
    if set(report["outcomes"]) != executed:
        raise ValueError("executed population lacks complete outcome evidence")
    if report["collection_errors"] or any(v != "passed" for v in report["outcomes"].values()):
        raise ValueError("resource validation contains failures/skips/collection errors")
    from check_population_sets import OWNER, check
    problems = check(report, json.loads((ROOT / "tests/population_manifest.json").read_text()),
                     OWNER, evidence["versions"], job_id="resource-validation")
    if problems:
        raise ValueError("; ".join(problems))


def validate_security_environment(environment: dict, approval_mode: str = "independent") -> None:
    reviews = [r for r in environment.get("protection_rules", []) if r.get("type") == "required_reviewers"]
    if approval_mode == "independent":
        if len(reviews) != 1 or not reviews[0].get("reviewers") or not reviews[0].get("prevent_self_review"):
            raise ValueError("workstation environment lacks required independent approval")
    elif approval_mode == "sole-maintainer":
        if reviews:
            raise ValueError("sole-maintainer mode must not represent a reviewer rule as independent approval")
    else:
        raise ValueError("unknown workstation approval mode")
    policy = environment.get("deployment_branch_policy")
    if not policy or not (policy.get("protected_branches") or policy.get("custom_branch_policies")):
        raise ValueError("workstation environment lacks branch restrictions")


def security_environment() -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    environment = json.loads(subprocess.check_output([
        "gh", "api", f"repos/{repository}/environments/navfm-resource-validation"]))
    approval_mode = os.environ.get("NAVFM_RESOURCE_APPROVAL_MODE") or "independent"
    validate_security_environment(environment, approval_mode)
    print(f"workstation approval mode: {approval_mode}")
    if approval_mode == "sole-maintainer":
        print("Reduced assurance: maintainer exact-SHA approval is not independent human review.")


def github_evidence(expected_head: str) -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    runs = json.loads(subprocess.check_output([
        "gh", "api", f"repos/{repository}/actions/workflows/resource-validation.yml/runs?event=workflow_dispatch&per_page=30"]))["workflow_runs"]
    eligible = [r for r in runs if r["head_sha"] == expected_head
                and r["event"] == "workflow_dispatch" and r["conclusion"] == "success"]
    if not eligible:
        raise ValueError("no successful manually approved resource-validation run for this exact HEAD")
    run = eligible[0]
    verify_run_artifact(run["id"], expected_head, run["run_attempt"])


def verify_run_artifact(run_id: int, expected_head: str, attempt: int | None = None) -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    artifact = f"{ARTIFACT}-{attempt or os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(["gh", "run", "download", str(run_id), "--repo", repository,
                        "--name", artifact, "--dir", directory], check=True)
        evidence = json.loads((Path(directory) / "resource-evidence.json").read_text())
        validate_evidence(evidence, expected_head, sha(ROOT / "tests/population_manifest.json"))
        capture_path = Path(directory) / "actual-environment-capture.json"
        inventory_path = Path(directory) / "archive-inventory.json"
        for key, path in (("isaac_host_capture_sha256", capture_path),
                          ("archive_inventory_sha256", inventory_path)):
            if sha(path) != evidence["versions"][key]:
                raise ValueError("resource artifact measurement digest mismatch")
        measured = json.loads(capture_path.read_text())
        validate_preflight_identity(evidence["source_identity"], source_identity(ROOT), measured)
        if measured["CAPTURE_VALIDATION"] != "PASS" or measured["nvidia_hold_state"]["HOLD_GUARD"] != "PASS":
            raise ValueError("owner has no passing actual capture/hold-stack measurement")
    print(f"validated resource owner run {run_id} for {expected_head}")


def current_owner_evidence(expected_head: str) -> None:
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = int(os.environ["GITHUB_RUN_ID"])
    jobs = json.loads(subprocess.check_output([
        "gh", "api", f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100"]))["jobs"]
    owner = [j for j in jobs if j["name"] == "resource-validation"]
    if len(owner) != 1 or owner[0]["status"] != "completed" or owner[0]["conclusion"] != "success":
        raise ValueError("current exact-HEAD resource owner did not complete successfully")
    verify_run_artifact(run_id, expected_head)


def preflight(output: Path) -> None:
    from navfm.arm_environment_guard import capture_arm_environment
    identity_before = source_identity(ROOT)
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    capture = capture_arm_environment("SELFTEST_A", repo_root=ROOT, frozen_head=head)
    output.mkdir(parents=True, exist_ok=True)
    capture_path = output / "actual-environment-capture.json"
    capture_path.write_text(json.dumps(capture, indent=2) + "\n")
    if capture["CAPTURE_VALIDATION"] != "PASS" or capture["nvidia_hold_state"]["HOLD_GUARD"] != "PASS":
        raise ValueError("actual environment capture/loaded GPU hold-stack validation failed")
    archive = Path(os.environ["NAVFM_ARCHIVE_ROOT"])
    attempt = archive / "runs/bo10/intervention/arm_a/pre_capture.json"
    expected = json.loads((ROOT / "gates/BO10/arm_a_attempt_001_20260917.json").read_text())["ATTEMPT_001_PRE_CAPTURE"]["sha256"]
    if sha(attempt) != expected:
        raise ValueError("Attempt001 archive does not match independently recorded hash")
    v1 = archive / "runs/bo10/intervention/execution_manifest.json"
    manifest = json.loads(v1.read_text())
    declared = manifest["repository"]["head"]
    gap = json.loads((ROOT / "gates/BO10/execution_readiness_gap_v1_20260912.json").read_text())
    if declared != gap["observed_at"]["manifest_bound_head"]:
        raise ValueError("recovered V1 manifest bound head is not independently corroborated")
    inventory = {"attempt001_sha256": sha(attempt), "v1_sha256": sha(v1),
                 "v1_bound_head": declared, "v1_byte_identity": "RECOVERY_OBSERVATION_NO_PRIOR_WHOLE_FILE_HASH"}
    inventory_path = output / "archive-inventory.json"
    inventory_path.write_text(json.dumps(inventory, indent=2) + "\n")
    alternate = Path(os.environ["NAVFM_ALTERNATE_PYTHON"])
    identity = subprocess.check_output([str(alternate), "-c", "import sys; print(sys.executable,sys.version)"], text=True).strip()
    import sys

    import numpy
    configured = Path(os.environ["NAVFM_RESOURCE_TEST_PYTHON"])
    if configured.resolve() != Path(sys.executable).resolve():
        raise ValueError("actual test interpreter differs from approved configured executable")
    if alternate.resolve() == configured.resolve():
        raise ValueError("alternate interpreter is not distinct")
    versions = {"test_python_configured": str(configured), "test_python_observed": sys.executable,
                "test_python_sha256": sha(configured.resolve()),
                "python": sys.version.split()[0], "numpy": numpy.__version__,
                "isaac_host_capture_sha256": sha(capture_path),
                "archive_inventory_sha256": sha(inventory_path), "alternate_python_identity": identity}
    (output / "source-identity.json").write_text(json.dumps(identity_before, indent=2) + "\n")
    validate_preflight_identity(identity_before, source_identity(ROOT), capture)
    (output / "versions.json").write_text(json.dumps(versions, indent=2) + "\n")


def bundle(output: Path) -> None:
    head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    before = json.loads((output / "source-identity.json").read_text())
    capture = json.loads((output / "actual-environment-capture.json").read_text())
    current = source_identity(ROOT)
    validate_preflight_identity(before, current, capture)
    evidence = {"source_identity": current, "head": head, "manifest_sha256": sha(ROOT / "tests/population_manifest.json"),
                "versions": json.loads((output / "versions.json").read_text()),
                "population": json.loads((output / "owner.json").read_text())}
    validate_evidence(evidence, head, evidence["manifest_sha256"])
    (output / "resource-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "bundle", "github", "security", "current"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--head")
    args = parser.parse_args()
    if args.mode == "security":
        security_environment()
    elif args.mode == "current":
        current_owner_evidence(args.head)
    elif args.mode == "github":
        github_evidence(args.head)
    elif args.mode == "preflight":
        preflight(args.output)
    else:
        bundle(args.output)
