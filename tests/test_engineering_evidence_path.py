"""Engineering evidence-path confinement, with discriminating controls.

`--engineering-step-cap` already forced `--out-dir` outside the repository, but
`--evidence` was only required to be new, so an engineering run could create its
evidence JSON and the `.milestones` file derived from it inside the working tree
-- contradicting both docs/ENGINEERING_RECORDING.md and the execution preflight.

The confinement check must reason about resolved filesystem ancestry rather than
string prefixes. `/repo-x` is not inside `/repo`, and `..` or a symlinked parent
that lands back inside the tree must still be refused. The
`test_sibling_directory_sharing_a_name_prefix_is_admitted` case below is the one
that fails if anyone reimplements this with `str.startswith`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "collect_bo10_trajectory.py"


def _collector():
    """Load the collector CLI as a module; nothing at import time runs a collection."""
    spec = importlib.util.spec_from_file_location("collect_bo10_trajectory", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# ancestry semantics
# --------------------------------------------------------------------------

def test_absolute_path_outside_the_repository_is_admitted(tmp_path: Path) -> None:
    mod = _collector()
    assert mod._outside_repo_violation("evidence", str(tmp_path / "e.json")) is None


def test_repository_root_itself_is_refused() -> None:
    mod = _collector()
    reason = mod._outside_repo_violation("evidence", str(REPO / "e.json"))
    assert reason is not None
    assert "outside the repository working tree" in reason
    assert str(REPO) in reason


def test_path_in_a_repository_subdirectory_is_refused() -> None:
    mod = _collector()
    assert mod._outside_repo_violation("evidence", str(REPO / "gates" / "e.json")) is not None


def test_dotdot_traversal_back_into_the_repository_is_refused() -> None:
    """A path that looks outside but normalises back inside must still be refused."""
    mod = _collector()
    sneaky = REPO / "gates" / ".." / "gates" / "e.json"
    assert ".." in str(sneaky)
    assert mod._outside_repo_violation("evidence", str(sneaky)) is not None


def test_symlinked_parent_resolving_into_the_repository_is_refused(tmp_path: Path) -> None:
    mod = _collector()
    link = tmp_path / "looks_outside"
    link.symlink_to(REPO / "gates", target_is_directory=True)
    assert mod._outside_repo_violation("evidence", str(link / "e.json")) is not None


def test_sibling_directory_sharing_a_name_prefix_is_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/repo-x` is NOT inside `/repo`. A string-prefix check would reject it."""
    mod = _collector()
    repo = tmp_path / "repo"
    repo.mkdir()
    sibling = tmp_path / "repo-x"
    sibling.mkdir()
    monkeypatch.setattr(mod, "REPO", repo)
    assert mod._outside_repo_violation("evidence", str(sibling / "e.json")) is None
    assert mod._outside_repo_violation("evidence", str(repo / "e.json")) is not None


def test_derived_milestone_path_is_covered_by_the_same_check() -> None:
    """The milestone label is validated too, not only the primary JSON.

    With the current derivation (`Path(evidence).with_suffix('.milestones')`) the
    milestone shares the evidence directory, so it cannot independently fall
    inside the tree while the evidence path is outside. The check is retained as
    defence against a future change to that derivation, and this asserts the
    helper refuses a milestone path inside the repository.
    """
    mod = _collector()
    inside = REPO / "gates" / "probe.milestones"
    reason = mod._outside_repo_violation("engineering milestone file", str(inside))
    assert reason is not None
    assert "engineering milestone file" in reason


# --------------------------------------------------------------------------
# CLI enforcement, before anything is written
# --------------------------------------------------------------------------

def _argv(evidence: Path, out_dir: Path, cap: int = 24) -> list[str]:
    return [
        "collect_bo10_trajectory.py",
        "--scene", "/nonexistent/scene.usd",
        "--scene-id", "probe",
        "--robot", "/nonexistent/robot.usd",
        "--admission-artefact", "/nonexistent/admission.json",
        "--out-dir", str(out_dir),
        "--evidence", str(evidence),
        "--engineering-step-cap", str(cap),
    ]


def test_rejected_run_creates_no_artefact_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rejection happens before mkdir, evidence write and milestone write."""
    mod = _collector()
    forbidden_dir = REPO / "gates" / "__evidence_path_probe__"
    evidence = forbidden_dir / "e.json"
    assert not forbidden_dir.exists(), "probe directory must not pre-exist"
    monkeypatch.setattr(sys, "argv", _argv(evidence, tmp_path / "out"))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert not forbidden_dir.exists()
    assert not evidence.exists()
    assert not evidence.with_suffix(".milestones").exists()
    assert not (tmp_path / "out").exists()


def test_admitted_run_passes_confinement_and_writes_its_first_milestone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control: an outside path is admitted and milestone writing begins.

    The collector then needs Isaac Sim, which is deliberately absent from this
    worktree's environment, so the run stops at that import. Reaching it proves
    confinement admitted the path rather than rejecting it.
    """
    mod = _collector()
    evidence = tmp_path / "nested" / "e.json"
    monkeypatch.setattr(sys, "argv", _argv(evidence, tmp_path / "out"))
    with pytest.raises(ModuleNotFoundError) as exc:
        mod.main()
    assert "isaacsim" in str(exc.value)
    milestones = evidence.with_suffix(".milestones")
    assert milestones.exists()
    assert "BEFORE_APP" in milestones.read_text()


def test_scientific_default_path_is_not_subject_to_confinement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --engineering-step-cap the confinement gate must not engage.

    The scientific collector legitimately writes its evidence into gates/, so the
    check is engineering-mode only. Asserted by reaching the Isaac import with an
    in-repo evidence path and no SystemExit.
    """
    mod = _collector()
    argv = [
        "collect_bo10_trajectory.py",
        "--scene", "/nonexistent/scene.usd",
        "--scene-id", "probe",
        "--robot", "/nonexistent/robot.usd",
        "--admission-artefact", "/nonexistent/admission.json",
        "--out-dir", str(tmp_path / "out"),
        "--evidence", str(REPO / "gates" / "__never_written__.json"),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(ModuleNotFoundError) as exc:
        mod.main()
    assert "isaacsim" in str(exc.value)
    assert not (REPO / "gates" / "__never_written__.json").exists()
    assert not (REPO / "gates" / "__never_written__.milestones").exists()
