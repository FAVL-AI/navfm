"""Tests for ``navfm.prereg`` — the commit-order control.

A pre-registration's entire force comes from having existed before the result.
`git log` inspected afterwards by the person who ran the experiment does not
establish that; it is the same person, the same afternoon, reporting on
themselves. These tests pin the five checks that do.

Task 2 requires unit tests for checks 1, 2 and 5 against a temporary git
repository. All five are covered here, because a check nobody tested is a check
nobody has seen fail.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from navfm import prereg


def _repo(root: Path) -> None:
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "T"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _commit(root: Path, text: str, message: str) -> str:
    (root / prereg.PROTOCOL_PATH).write_text(text)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qm", message], check=True, capture_output=True
    )
    out = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def _result(checks: list[prereg.PreregCheck]) -> dict[str, bool]:
    return {c.name: c.passed for c in checks}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root)
    return root


class TestCheck1CommitExists:
    def test_a_real_commit_resolves(self, repo: Path, tmp_path: Path) -> None:
        sha = _commit(repo, "protocol v1\n", "prereg")
        checks, _ = prereg.verify(sha, repo_root=repo, output_dir=tmp_path / "out")
        assert _result(checks)["commit_exists"] is True

    def test_a_fabricated_sha_is_refused(self, repo: Path, tmp_path: Path) -> None:
        _commit(repo, "protocol v1\n", "prereg")
        checks, _ = prereg.verify("0" * 40, repo_root=repo, output_dir=tmp_path / "out")
        assert _result(checks)["commit_exists"] is False
        with pytest.raises(prereg.GateExecutionInvalid, match="gate execution invalid"):
            prereg.enforce(checks)


class TestCheck2Ancestry:
    def test_a_commit_on_an_abandoned_branch_is_refused(self, repo: Path, tmp_path: Path) -> None:
        """A commit that is not in HEAD's history cannot have preceded anything
        in it — this is the rewritten-history case that b673fa5 already
        demonstrated in this repository."""
        _commit(repo, "protocol v1\n", "base")
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "-qb", "side"], check=True, capture_output=True
        )
        orphan = _commit(repo, "protocol side\n", "side work")
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "-q", "main"], check=True, capture_output=True
        )

        checks, _ = prereg.verify(orphan, repo_root=repo, output_dir=tmp_path / "out")
        result = _result(checks)
        assert result["commit_exists"] is True, "the commit does exist"
        assert result["commit_is_ancestor_of_head"] is False, "but it is not in HEAD's history"

    def test_an_ancestor_passes(self, repo: Path, tmp_path: Path) -> None:
        first = _commit(repo, "protocol v1\n", "prereg")
        _commit(repo, "protocol v1\nmore\n", "later work")
        checks, _ = prereg.verify(first, repo_root=repo, output_dir=tmp_path / "out")
        assert _result(checks)["commit_is_ancestor_of_head"] is True


class TestCheck3ProtocolHash:
    def test_absent_protocol_at_that_commit_is_refused(self, repo: Path, tmp_path: Path) -> None:
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm", "empty", "--allow-empty"],
            check=True,
            capture_output=True,
        )
        sha = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        checks, sha256 = prereg.verify(sha, repo_root=repo, output_dir=tmp_path / "out")
        assert _result(checks)["protocol_hash_matches"] is False
        assert sha256 is None

    def test_archived_copy_must_match_the_commit(self, repo: Path, tmp_path: Path) -> None:
        sha = _commit(repo, "protocol v1\n", "prereg")
        out = tmp_path / "out"
        out.mkdir()
        (out / prereg.PROTOCOL_PATH).write_text("protocol TAMPERED\n")
        checks, _ = prereg.verify(sha, repo_root=repo, output_dir=out)
        assert _result(checks)["protocol_hash_matches"] is False


class TestCheck4OutputOrdering:
    def test_output_predating_the_commit_is_refused(self, repo: Path, tmp_path: Path) -> None:
        """Output older than the protocol means the run began before the
        protocol was fixed, whatever the manifest later claims."""
        out = tmp_path / "out"
        out.mkdir()
        sha = _commit(repo, "protocol v1\n", "prereg")
        import os

        old = time.time() - 86_400
        os.utime(out, (old, old))
        checks, _ = prereg.verify(sha, repo_root=repo, output_dir=out)
        assert _result(checks)["output_postdates_commit"] is False

    def test_absent_output_directory_is_fine(self, repo: Path, tmp_path: Path) -> None:
        sha = _commit(repo, "protocol v1\n", "prereg")
        checks, _ = prereg.verify(sha, repo_root=repo, output_dir=tmp_path / "nope")
        assert _result(checks)["output_postdates_commit"] is True


class TestCheck5ProtocolStability:
    def test_reinitialising_under_a_different_protocol_is_refused(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """The headline case: a gate already run under one protocol, re-run
        under another. A protocol change after initialisation is a protocol
        change after execution."""
        first = _commit(repo, "protocol v1\n", "prereg v1")
        out = tmp_path / "out"
        out.mkdir()
        _, sha_v1 = prereg.verify(first, repo_root=repo, output_dir=out)
        (out / "preregistration.json").write_text(json.dumps({"protocol_sha256": sha_v1}))

        second = _commit(repo, "protocol v2 -- amended after seeing data\n", "prereg v2")
        checks, _ = prereg.verify(second, repo_root=repo, output_dir=out)
        assert _result(checks)["protocol_stable_across_runs"] is False
        with pytest.raises(prereg.GateExecutionInvalid):
            prereg.enforce(checks)

    def test_rerunning_under_the_same_protocol_is_allowed(self, repo: Path, tmp_path: Path) -> None:
        sha = _commit(repo, "protocol v1\n", "prereg")
        out = tmp_path / "out"
        out.mkdir()
        _, protocol_sha = prereg.verify(sha, repo_root=repo, output_dir=out)
        (out / "preregistration.json").write_text(json.dumps({"protocol_sha256": protocol_sha}))
        checks, _ = prereg.verify(sha, repo_root=repo, output_dir=out)
        assert _result(checks)["protocol_stable_across_runs"] is True

    def test_unreadable_marker_is_refused_not_ignored(self, repo: Path, tmp_path: Path) -> None:
        sha = _commit(repo, "protocol v1\n", "prereg")
        out = tmp_path / "out"
        out.mkdir()
        (out / "preregistration.json").write_text("{ not json")
        checks, _ = prereg.verify(sha, repo_root=repo, output_dir=out)
        assert _result(checks)["protocol_stable_across_runs"] is False


class TestEnforcement:
    def test_all_five_checks_are_always_reported(self, repo: Path, tmp_path: Path) -> None:
        """An operator fixing a gate should learn everything wrong in one pass,
        not one problem per run."""
        checks, _ = prereg.verify("0" * 40, repo_root=repo, output_dir=tmp_path / "out")
        assert {c.name for c in checks} == {
            "commit_exists",
            "commit_is_ancestor_of_head",
            "protocol_hash_matches",
            "output_postdates_commit",
            "protocol_stable_across_runs",
        }

    def test_a_clean_verification_enforces_silently(self, repo: Path, tmp_path: Path) -> None:
        sha = _commit(repo, "protocol v1\n", "prereg")
        checks, _ = prereg.verify(sha, repo_root=repo, output_dir=tmp_path / "out")
        prereg.enforce(checks)

    def test_the_refusal_says_it_is_not_a_finding(self, repo: Path, tmp_path: Path) -> None:
        """'Gate execution invalid' must never read as an adverse result."""
        checks, _ = prereg.verify("0" * 40, repo_root=repo, output_dir=tmp_path / "out")
        with pytest.raises(prereg.GateExecutionInvalid) as excinfo:
            prereg.enforce(checks)
        message = str(excinfo.value)
        assert "no evidential classification" in message
        assert "not a result" in message
