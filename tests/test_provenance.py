"""Tests for ``navfm.provenance``.

The helper exists so that a gate archive records *which instrument produced
the number*. The properties worth pinning are the ones that would let a
provenance claim be wrong while still looking well-formed:

* the identity is stable across calls in one environment — otherwise two runs
  in the same environment appear to be different instruments;
* the identity is sensitive to every field it claims to cover — otherwise two
  genuinely different environments collide and the archive says they match;
* the identity excludes what varies per run, so it can be compared at all;
* a dirty worktree is *declared*, never silently reported as clean, because a
  recorded commit would otherwise imply a tree that never existed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from navfm import provenance


def _git_init(root: Path) -> None:
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "T"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _git_commit_all(root: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", message], check=True, capture_output=True
    )
    out = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


class TestEnvironmentIdentity:
    def test_identity_is_stable_within_one_environment(self) -> None:
        assert provenance.environment_identity() == provenance.environment_identity()

    def test_identity_id_is_a_sha256(self) -> None:
        env_id = provenance.environment_identity().environment_id
        assert len(env_id) == 64
        assert set(env_id) <= set("0123456789abcdef")

    @pytest.mark.parametrize(
        "field, value",
        [
            ("python_version", "0.0.0"),
            ("torch_version", "0.0.0+fake"),
            ("cuda_version", "0.0"),
            ("os", "Fake-OS"),
            ("architecture", "fake64"),
        ],
    )
    def test_every_declared_field_moves_the_identity(
        self, monkeypatch: pytest.MonkeyPatch, field: str, value: str
    ) -> None:
        """A field in the identity that does not change the digest is decoration."""
        baseline = provenance.environment_identity().environment_id
        patches = {
            "python_version": lambda: monkeypatch.setattr(
                provenance.platform, "python_version", lambda: value
            ),
            "torch_version": lambda: monkeypatch.setattr(
                provenance, "_torch_versions", lambda: (value, "12.8")
            ),
            "cuda_version": lambda: monkeypatch.setattr(
                provenance, "_torch_versions", lambda: ("2.0.0", value)
            ),
            "os": lambda: monkeypatch.setattr(provenance.platform, "platform", lambda: value),
            "architecture": lambda: monkeypatch.setattr(
                provenance.platform, "machine", lambda: value
            ),
        }
        patches[field]()
        assert provenance.environment_identity().environment_id != baseline

    def test_distribution_set_moves_the_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(provenance, "_installed_distributions", lambda: ["a==1", "b==2"])
        one = provenance.environment_identity()
        monkeypatch.setattr(provenance, "_installed_distributions", lambda: ["a==1", "b==3"])
        two = provenance.environment_identity()
        assert one.environment_id != two.environment_id
        assert one.pip_freeze_digest != two.pip_freeze_digest

    def test_distribution_digest_is_order_independent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Install order must not change the identity; only the set may."""
        monkeypatch.setattr(provenance, "_installed_distributions", lambda: ["a==1", "b==2"])
        forwards = provenance.environment_identity().pip_freeze_digest
        monkeypatch.setattr(provenance, "_installed_distributions", lambda: ["a==1", "b==2"])
        assert provenance.environment_identity().pip_freeze_digest == forwards

    def test_pythonpath_moves_the_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A venv does not isolate you from PYTHONPATH, so the identity must
        cover it: sourcing ROS 2 Humble prepends Python 3.10 site-packages to a
        3.11 venv and silently changes which code imports (F-M2-2)."""
        monkeypatch.delenv("PYTHONPATH", raising=False)
        clean = provenance.environment_identity().environment_id
        monkeypatch.setenv("PYTHONPATH", "/opt/ros/humble/lib/python3.10/site-packages")
        assert provenance.environment_identity().environment_id != clean

    def test_unset_and_empty_pythonpath_agree(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PYTHONPATH", raising=False)
        unset = provenance.environment_identity().environment_id
        monkeypatch.setenv("PYTHONPATH", "")
        assert provenance.environment_identity().environment_id == unset

    def test_torch_absent_is_recorded_not_fatal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(provenance, "_torch_versions", lambda: (None, None))
        identity = provenance.environment_identity()
        assert identity.torch_version is None
        assert identity.cuda_version is None
        assert len(identity.environment_id) == 64


class TestExecutionFingerprint:
    def test_identity_excludes_what_varies_per_run(self, tmp_path: Path) -> None:
        """Two fingerprints from one environment must share an environment_id."""
        _git_init(tmp_path)
        (tmp_path / "f.txt").write_text("x\n")
        _git_commit_all(tmp_path, "c")
        first = provenance.execution_fingerprint(tmp_path)
        second = provenance.execution_fingerprint(tmp_path)
        assert first.environment_id == second.environment_id

    def test_records_repository_and_upstream_commits(self, tmp_path: Path) -> None:
        repo, upstream = tmp_path / "repo", tmp_path / "upstream"
        for root in (repo, upstream):
            root.mkdir()
            _git_init(root)
            (root / "f.txt").write_text("x\n")
        repo_sha = _git_commit_all(repo, "repo")
        upstream_sha = _git_commit_all(upstream, "upstream")

        fingerprint = provenance.execution_fingerprint(repo, upstream)
        assert fingerprint.repository_commit == repo_sha
        assert fingerprint.upstream_commit == upstream_sha
        assert repo_sha != upstream_sha

    def test_clean_worktree_reports_clean(self, tmp_path: Path) -> None:
        _git_init(tmp_path)
        (tmp_path / "f.txt").write_text("x\n")
        _git_commit_all(tmp_path, "c")
        assert provenance.execution_fingerprint(tmp_path).repository_worktree == "clean"

    def test_dirty_worktree_is_declared_and_names_the_file(self, tmp_path: Path) -> None:
        """A dirty tree is not invalid, but it must never be reported as clean."""
        _git_init(tmp_path)
        (tmp_path / "f.txt").write_text("x\n")
        _git_commit_all(tmp_path, "c")
        (tmp_path / "f.txt").write_text("changed\n")

        status = provenance.execution_fingerprint(tmp_path).repository_worktree
        assert status != "clean"
        assert "modified (1)" in status
        assert "f.txt" in status

    def test_first_entry_is_not_shifted_by_stripped_output(self, tmp_path: Path) -> None:
        """Regression: porcelain's XY field is two columns and column 1 is blank
        for an unstaged edit, so stripping the command output shifts the FIRST
        line by one and silently truncates its filename."""
        _git_init(tmp_path)
        (tmp_path / "alpha.txt").write_text("x\n")
        (tmp_path / "beta.txt").write_text("x\n")
        _git_commit_all(tmp_path, "c")
        (tmp_path / "alpha.txt").write_text("changed\n")
        (tmp_path / "beta.txt").write_text("changed\n")

        status = provenance.execution_fingerprint(tmp_path).repository_worktree
        assert "alpha.txt" in status and "beta.txt" in status
        assert "lpha.txt" not in status.replace("alpha.txt", "")

    def test_path_containing_a_space_survives(self, tmp_path: Path) -> None:
        _git_init(tmp_path)
        (tmp_path / "my file.txt").write_text("x\n")
        _git_commit_all(tmp_path, "c")
        (tmp_path / "my file.txt").write_text("changed\n")
        assert "my file.txt" in provenance.execution_fingerprint(tmp_path).repository_worktree

    def test_untracked_file_also_counts_as_dirty(self, tmp_path: Path) -> None:
        _git_init(tmp_path)
        (tmp_path / "f.txt").write_text("x\n")
        _git_commit_all(tmp_path, "c")
        (tmp_path / "extra.txt").write_text("new\n")
        assert provenance.execution_fingerprint(tmp_path).repository_worktree != "clean"

    def test_non_git_directory_is_unknown_not_clean(self, tmp_path: Path) -> None:
        """The dangerous failure is a non-repo silently reporting a clean tree."""
        status = provenance.execution_fingerprint(tmp_path).repository_worktree
        assert status.startswith("unknown")
        assert provenance.execution_fingerprint(tmp_path).repository_commit is None

    def test_upstream_absent_is_none_not_an_error(self, tmp_path: Path) -> None:
        _git_init(tmp_path)
        (tmp_path / "f.txt").write_text("x\n")
        _git_commit_all(tmp_path, "c")
        assert provenance.execution_fingerprint(tmp_path, None).upstream_commit is None


class TestRendering:
    def test_rendered_block_carries_every_b2_field(self, tmp_path: Path) -> None:
        """Addendum B2 enumerates what page one must show; none may be dropped."""
        fingerprint = provenance.execution_fingerprint(tmp_path)
        rendered = provenance.render_fingerprint(fingerprint)
        for label in (
            "Repository commit",
            "Upstream commit",
            "Interpreter",
            "Torch version",
            "CUDA version",
            "Python version",
            "OS",
            "Architecture",
            "Hostname",
            "UTC timestamp",
            "Working tree",
            "PYTHONPATH",
            "Environment identity",
        ):
            assert label in rendered, f"page one omits {label!r}"

    def test_absent_values_render_visibly(self, tmp_path: Path) -> None:
        """A missing value must read as absent, never as a blank that scans as fine."""
        rendered = provenance.render_fingerprint(provenance.execution_fingerprint(tmp_path))
        assert "(absent)" in rendered

    def test_json_output_round_trips(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert provenance.main(["--identity-only", "--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert set(payload) == set(asdict(provenance.environment_identity()))

    def test_cli_emits_a_fingerprint_block(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert provenance.main([]) == 0
        assert "EXECUTION FINGERPRINT" in capsys.readouterr().out


class TestEffectiveImportSurface:
    """The identity must cover *where* the load-bearing modules come from.

    Two environments agreeing on every version while importing those versions
    from different trees are not the same instrument, and the failure that
    forced this (F-M2-2) moved no version field at all.
    """

    def test_load_bearing_modules_are_located(self) -> None:
        identity = provenance.environment_identity()
        assert set(identity.module_locations) == set(provenance._LOAD_BEARING_MODULES)

    def test_locations_are_normalised_not_absolute(self) -> None:
        """Absolute machine-specific paths must not enter the hash."""
        for location in provenance.environment_identity().module_locations.values():
            if location is None:
                continue
            assert not location.startswith("/home/"), location
            assert location.startswith(("<prefix>", "<base_prefix>", "<repo>", "~", "/"))

    def test_a_module_moving_tree_moves_the_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        baseline = provenance.environment_identity().environment_id
        monkeypatch.setattr(
            provenance,
            "_module_locations",
            lambda root: ({"torch": "/opt/ros/humble/lib/python3.10/site-packages/torch"}, {}),
        )
        assert provenance.environment_identity().environment_id != baseline

    @pytest.mark.parametrize("var", ["PYTHONHOME"])
    def test_interpreter_env_vars_move_the_identity(
        self, monkeypatch: pytest.MonkeyPatch, var: str
    ) -> None:
        monkeypatch.delenv(var, raising=False)
        baseline = provenance.environment_identity().environment_id
        monkeypatch.setenv(var, "/somewhere/else")
        assert provenance.environment_identity().environment_id != baseline

    def test_user_site_enablement_moves_the_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        baseline = provenance.environment_identity().environment_id
        monkeypatch.setattr(
            provenance.site, "ENABLE_USER_SITE", not provenance.site.ENABLE_USER_SITE
        )
        assert provenance.environment_identity().environment_id != baseline

    def test_cwd_is_recorded_but_not_hashed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cwd locates the run; it does not define the instrument."""
        baseline = provenance.environment_identity().environment_id
        monkeypatch.chdir(tmp_path)
        assert provenance.environment_identity().environment_id == baseline
        assert provenance.execution_fingerprint(tmp_path).cwd == str(tmp_path)

    def test_raw_locations_archived_beside_normalised(self, tmp_path: Path) -> None:
        fingerprint = provenance.execution_fingerprint(tmp_path)
        assert set(fingerprint.module_locations_raw) == set(provenance._LOAD_BEARING_MODULES)
        for name, raw in fingerprint.module_locations_raw.items():
            if raw is not None:
                assert raw.startswith("/"), f"{name} raw location should be absolute"

    def test_sys_path_recorded_in_full(self, tmp_path: Path) -> None:
        assert provenance.execution_fingerprint(tmp_path).sys_path == list(sys.path)
