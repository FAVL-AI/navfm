"""Simulator identity: absent is ABSENT, and nothing is inferred.

Written before Isaac Lab is installed, so the cases that matter are the ones a
build host exercises: no Isaac Sim, no Isaac Lab, possibly no GPU driver. Each
must record what is true rather than a value that reads like a measurement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from navfm.simenv import (
    EXPECTED_ISAAC_SIM_VERSION,
    SimulatorIdentity,
    gpu_identity,
    isaac_lab_identity,
    package_version,
    simulator_identity,
)


class TestAbsentIsAbsent:
    def test_a_missing_distribution_is_none_not_empty(self) -> None:
        """None is unmistakable; '' could be read as a version."""
        assert package_version("navfm-nonexistent-distribution-xyz") is None

    def test_a_present_distribution_reports_its_version(self) -> None:
        """The other direction: the reader must be able to succeed."""
        assert package_version("pytest") is not None

    def test_isaac_lab_absent_records_installed_false(self) -> None:
        record = isaac_lab_identity()
        assert record["installed"] is (record["isaac_lab_version"] is not None)
        if not record["installed"]:
            assert record["isaac_lab_version"] is None

    def test_no_clone_declared_leaves_commit_none_rather_than_searching(self) -> None:
        """A recorder that went looking could find a checkout the run never used."""
        record = isaac_lab_identity(clone_path=None)
        assert record["clone_path"] is None
        assert record["isaac_lab_commit"] is None

    def test_a_declared_path_that_is_not_a_repo_is_reported_not_ignored(
        self, tmp_path: Path
    ) -> None:
        record = isaac_lab_identity(clone_path=tmp_path)
        assert "clone_error" in record
        assert record["isaac_lab_commit"] is None


class TestNothingIsInferred:
    def test_the_module_does_not_import_isaacsim(self) -> None:
        """Importing would be heavy, environment-specific, and self-discovering.

        Checked with ast rather than by grepping the text: the module's own
        docstring explains that it never imports isaacsim, and a text search
        matches that explanation. A guard that fires on the comment describing
        it is a guard that gets deleted.
        """
        import ast

        source = (Path(__file__).resolve().parents[1] / "src/navfm/simenv.py").read_text()
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "isaacsim" not in imported
        assert "isaaclab" not in imported

    def test_the_ast_import_check_can_fail(self) -> None:
        """Negative control: prove the check detects the import it forbids."""
        import ast

        bad = "import isaacsim.core.utils.stage as s\n"
        imported = {
            a.name.split(".")[0]
            for node in ast.walk(ast.parse(bad)) if isinstance(node, ast.Import)
            for a in node.names
        }
        assert "isaacsim" in imported

    def test_it_reports_the_interpreter_it_actually_runs_in(self) -> None:
        import sys

        assert simulator_identity().interpreter == sys.executable

    def test_a_build_host_without_isaac_sim_is_a_correct_answer_not_a_failure(self) -> None:
        identity = simulator_identity()
        assert isinstance(identity, SimulatorIdentity)
        assert identity.isaac_sim_present is (identity.isaac_sim_version is not None)


class TestExpectedVersionIsCheckedNotAssumed:
    def test_the_expected_version_is_the_frozen_one(self) -> None:
        assert EXPECTED_ISAAC_SIM_VERSION == "5.1.0"

    def test_a_mismatch_is_flagged_rather_than_tolerated(self) -> None:
        identity = simulator_identity()
        if identity.isaac_sim_version is None:
            assert identity.isaac_sim_matches_expected is False
        else:
            assert identity.isaac_sim_matches_expected == (
                identity.isaac_sim_version.startswith(EXPECTED_ISAAC_SIM_VERSION))

    def test_absent_never_counts_as_matching(self) -> None:
        """The load-bearing case: no simulator must not read as the right simulator."""
        identity = SimulatorIdentity(
            isaac_sim_version=None, isaac_sim_matches_expected=False,
            expected_isaac_sim_version="5.1.0", isaac_lab={}, python_version="3.11.0",
            torch_version=None, cuda_runtime=None, gpu={}, interpreter="/x", conda_env=None)
        assert identity.isaac_sim_matches_expected is False
        assert identity.isaac_sim_present is False


class TestGpuIdentity:
    def test_an_unreachable_driver_is_distinguished_from_no_gpu(self) -> None:
        record = gpu_identity()
        assert "driver_reachable" in record
        if not record["driver_reachable"]:
            assert "not evidence that no GPU exists" in record["note"]

    def test_a_reachable_driver_names_the_devices(self) -> None:
        record = gpu_identity()
        if record["driver_reachable"]:
            assert record["gpus"]
            assert {"name", "driver_version", "memory_total"} <= set(record["gpus"][0])


def test_the_record_serialises_and_carries_the_required_fields() -> None:
    import json

    d = simulator_identity().to_dict()
    json.dumps(d)
    for field in ("isaac_sim_version", "isaac_lab", "python_version", "torch_version",
                  "cuda_runtime", "gpu", "interpreter"):
        assert field in d


@pytest.mark.parametrize("field", ["isaac_lab_version", "isaac_lab_commit", "clone_worktree_dirty"])
def test_the_isaac_lab_block_always_carries_its_fields(field: str) -> None:
    """Present-but-null beats absent: a missing key reads as 'not recorded'."""
    assert field in isaac_lab_identity()
