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
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def _declaration_copy(tmp_path: Path) -> Path:
    """A writable copy of the committed declaration, owned by the test.

    The source is only read, so the frozen artefact's content and mtime are
    both left alone.
    """
    source = REPO / "gates" / "G0" / "evaluation_declaration.json"
    target = tmp_path / "evaluation_declaration.json"
    target.write_text(source.read_text())
    return target


def _identity_check(declaration: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Run the freeze audit against ``declaration`` and return its identity check.

    The audit script is loaded as a module and its ``DECLARATION`` constant is
    redirected, rather than run as a subprocess against the real repository
    file. ``audit()`` writes nothing -- the only write in that script is
    ``main()``'s optional ``--json-out``, which is not reached here.
    """
    spec = importlib.util.spec_from_file_location(
        "protocol_freeze_audit", REPO / "scripts" / "protocol_freeze_audit.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DECLARATION", declaration)
    checks = module.audit("HEAD", REPO / "runs" / "__audit_negative_probe__", None)
    for check in checks:
        if check.name == "environment_identity_recorded":
            return check
    raise AssertionError("the audit emitted no environment_identity_recorded check")


class TestIdentityCheckCanFail:
    """Four perturbations, each forcing a non-zero exit."""

    def test_perturbed_pythonpath_fails(self) -> None:
        env = _base_env()
        env["PYTHONPATH"] = "/opt/ros/humble/lib/python3.10/site-packages"
        result = _run_audit(env)
        assert result.returncode != 0
        assert "FAIL" in _identity_line(result)
        assert "not the one the protocol froze" in result.stdout

    @pytest.mark.alternate_python
    def test_perturbed_executable_identity_fails(self) -> None:
        """A different interpreter is a different instrument, however similar.

        Not PYTHONHOME: a bad PYTHONHOME kills the interpreter before the audit
        runs, so it would test process death rather than the identity check.
        This runs the audit under the in-repo 3.13 environment instead, whose
        python version, prefix and distribution set all differ from the
        canonical 3.11 one.
        """
        other = Path(os.environ.get("NAVFM_ALTERNATE_PYTHON", str(REPO / ".venv-m1" / "bin" / "python")))
        if not other.is_file():
            pytest.fail("required alternate interpreter resource is absent")
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

    def test_perturbed_expected_identity_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Perturb the *declared* side: a declaration naming a different
        instrument must not be certified against this one.

        The perturbation happens in a test-owned copy. The committed
        ``gates/G0/evaluation_declaration.json`` is read but never written --
        mutate-then-restore leaves a modified mtime on frozen scientific
        evidence even when the bytes come back identical, so the audit's
        ``DECLARATION`` constant is redirected instead.
        """
        declaration = _declaration_copy(tmp_path)
        data = json.loads(declaration.read_text())
        data["environment"]["identity"] = "0" * 64
        declaration.write_text(json.dumps(data, indent=2) + "\n")
        check = _identity_check(declaration, monkeypatch)
        assert check.passed is False
        assert "expected 0000" in check.detail

    def test_absent_expected_identity_fails_rather_than_passing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The dangerous default: nothing to compare against must be a FAIL,
        not a silent pass. This is the exact shape of the original defect."""
        declaration = _declaration_copy(tmp_path)
        data = json.loads(declaration.read_text())
        del data["environment"]
        declaration.write_text(json.dumps(data, indent=2) + "\n")
        check = _identity_check(declaration, monkeypatch)
        assert check.passed is False
        assert "no preregistered identity" in check.detail

    def test_unperturbed_copy_trips_neither_detector(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive control for the two negatives above.

        Against an untouched copy neither detector may fire, so neither of the
        assertions above can be satisfied by an unrelated audit failure. This
        deliberately does not assert ``check.passed``: the frozen identity
        belongs to the environment the gate was frozen against, so an identity
        *mismatch* here is expected and is a different finding from a zeroed or
        missing identity.
        """
        declaration = _declaration_copy(tmp_path)
        check = _identity_check(declaration, monkeypatch)
        assert "no preregistered identity" not in check.detail
        assert "expected 0000" not in check.detail


class TestPatchIdentityCheckCanFail:
    """The check binds three things: the pin in the amendment commit's blob, the
    archived diff at that commit, and the LIVE clone's diff.

    Asserting that it passes at HEAD would tie this test to commit order rather
    than to behaviour: the pin lives in the amendment, so before that commit the
    correct result is FAIL-because-unbound. The earlier version of this test
    asserted the pass and therefore encoded the pre-amendment state as correct.
    """

    def _check(self, commit: str = "HEAD") -> audit.Check:
        by_name = {c.name: c for c in audit.audit(commit, Path("runs/__probe__"), None)}
        assert "upstream_patch_identity_verified" in by_name
        return by_name["upstream_patch_identity_verified"]

    def test_an_absent_pin_fails_rather_than_passing_vacuously(self) -> None:
        """No pin at the named commit must FAIL. If it passed, any patch set
        would satisfy the check -- the dangerous-default shape again.

        Pinned to `d4fc321`, the frozen-preregistration commit, which predates
        every patch amendment and therefore carries no digest. Asserting against
        HEAD would make this test's meaning flip the moment the amendment lands:
        it would pass for the right reason today and the wrong one tomorrow.
        """
        check = self._check("d4fc321")
        assert not check.passed, (
            "a commit with no pinned patch digest was certified; the check is "
            "vacuous and any patch set would satisfy it"
        )
        assert "unbound" in check.detail or "unarchived" in check.detail

    def test_the_live_clone_is_inspected_not_just_the_archived_diff(self) -> None:
        """Marker counts and the archived diff both survive an edit to the code
        beneath them. Only digesting the live clone detects a tampered body."""
        source = inspect.getsource(audit.audit)
        assert "_git_bytes_at(UPSTREAM" in source, "the live clone is never digested"
        assert "LIVE CLONE" in source

    def test_both_sides_are_read_from_the_commit_not_the_worktree(self) -> None:
        """Reading either side from the worktree makes this a self-consistency
        check that one coordinated edit satisfies."""
        source = inspect.getsource(audit.audit)
        assert 'f"{resolved}:PREREGISTRATION.md"' in source
        assert 'f"{resolved}:gates/G0/patch.diff"' in source

    def test_audit_reports_sixteen_checks(self) -> None:
        assert len(audit.audit("HEAD", Path("runs/__probe__"), None)) == 16


@pytest.mark.parametrize(
    "name", ["evaluation_pair_manifest_digest", "environment_identity_recorded"]
)
def test_new_checks_are_present(name: str) -> None:
    assert name in {c.name for c in audit.audit("HEAD", Path("runs/__probe__"), None)}
