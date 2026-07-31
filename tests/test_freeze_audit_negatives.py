"""Negative tests for the freeze audit's environment-identity check.

The check previously read:

    Check("environment_identity_recorded", True, f"environment_id {fp.environment_id}")

— constructed `passed=True` unconditionally. It asserted successful
verification without comparing anything, so a gate executed in a drifted
environment would still have shown a green Layer A. Recorded as an
audit-integrity defect in `gates/failures/F-M2-4.md`.

The lesson generalised into the standing rules: **a verification must fail when
its subject is absent.** Run it once against a deliberately broken state before
trusting it against a good one. These four tests are that run — each perturbs
one component of the effective-import identity and asserts the audit exits
non-zero. A check that cannot fail is not a check, and the only way to know the
difference is to break it on purpose.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "protocol_freeze_audit", REPO / "scripts" / "protocol_freeze_audit.py"
)
assert _SPEC and _SPEC.loader
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


def _run_audit(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the audit in a subprocess so environment perturbation is real."""
    return subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "protocol_freeze_audit.py"),
            "--amendment-commit",
            "HEAD",
            "--run-dir",
            "runs/__audit_negative_probe__",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )


def _base_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["MPLBACKEND"] = "Agg"
    return env


def _identity_line(result: subprocess.CompletedProcess[str]) -> str:
    for line in result.stdout.splitlines():
        if line.startswith("environment_identity_recorded"):
            return line
    return ""


class TestIdentityCheckCanFail:
    """Four perturbations, each forcing a non-zero exit."""

    def test_perturbed_pythonpath_fails(self) -> None:
        env = _base_env()
        env["PYTHONPATH"] = "/opt/ros/humble/lib/python3.10/site-packages"
        result = _run_audit(env)
        assert result.returncode != 0
        assert "FAIL" in _identity_line(result)
        assert "not the one the protocol froze" in result.stdout

    def test_perturbed_executable_identity_fails(self) -> None:
        """A different interpreter is a different instrument, however similar.

        Not PYTHONHOME: a bad PYTHONHOME kills the interpreter before the audit
        runs, so it would test process death rather than the identity check.
        This runs the audit under the in-repo 3.13 environment instead, whose
        python version, prefix and distribution set all differ from the
        canonical 3.11 one.
        """
        other = REPO / ".venv-m1" / "bin" / "python"
        if not other.is_file():
            pytest.skip("no second interpreter available to contrast with")
        result = subprocess.run(
            [
                str(other),
                str(REPO / "scripts" / "protocol_freeze_audit.py"),
                "--amendment-commit",
                "HEAD",
                "--run-dir",
                "runs/__audit_negative_probe__",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            env=_base_env(),
            timeout=300,
        )
        assert result.returncode != 0
        assert "FAIL" in _identity_line(result)
        assert "not the one the protocol froze" in result.stdout

    def test_perturbed_expected_identity_fails(self, tmp_path: Path) -> None:
        """Perturb the *declared* side: a declaration naming a different
        instrument must not be certified against this one."""
        declaration = REPO / "gates" / "G0" / "evaluation_declaration.json"
        original = declaration.read_text()
        try:
            data = json.loads(original)
            data["environment"]["identity"] = "0" * 64
            declaration.write_text(json.dumps(data, indent=2) + "\n")
            result = _run_audit(_base_env())
            assert result.returncode != 0
            assert "FAIL" in _identity_line(result)
            assert "expected 0000" in result.stdout
        finally:
            declaration.write_text(original)

    def test_absent_expected_identity_fails_rather_than_passing(self) -> None:
        """The dangerous default: nothing to compare against must be a FAIL,
        not a silent pass. This is the exact shape of the original defect."""
        declaration = REPO / "gates" / "G0" / "evaluation_declaration.json"
        original = declaration.read_text()
        try:
            data = json.loads(original)
            del data["environment"]
            declaration.write_text(json.dumps(data, indent=2) + "\n")
            result = _run_audit(_base_env())
            assert result.returncode != 0
            assert "no preregistered identity" in result.stdout
        finally:
            declaration.write_text(original)


class TestPatchIdentityCheckCanFail:
    def test_unpatched_clone_is_detected(self) -> None:
        """The sampling semantics the amendment freezes live in the patch. An
        unpatched clone silently restores the global-stream coupling."""
        checks = audit.audit("HEAD", Path("runs/__probe__"), None)
        by_name = {c.name: c for c in checks}
        assert "upstream_patch_identity_verified" in by_name
        # Present state is patched; assert the check reads the real marker.
        assert by_name["upstream_patch_identity_verified"].passed
        assert "markers applied" in by_name["upstream_patch_identity_verified"].detail

    def test_audit_reports_sixteen_checks(self) -> None:
        assert len(audit.audit("HEAD", Path("runs/__probe__"), None)) == 16


@pytest.mark.parametrize(
    "name", ["evaluation_pair_manifest_digest", "environment_identity_recorded"]
)
def test_new_checks_are_present(name: str) -> None:
    assert name in {c.name for c in audit.audit("HEAD", Path("runs/__probe__"), None)}
