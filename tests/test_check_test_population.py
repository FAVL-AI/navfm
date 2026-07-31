"""Tests for ``scripts/check_test_population.py``.

The invariant exists because of F-M2-1: a suite can exit 0, print a green
count, and have silently lost two thirds of the specification. The only test
that matters here is whether the checker refuses the exact report shape that
failure produced — a contracted population with a healthy-looking exit status.

Everything else in this file guards the ways a checker like this quietly stops
checking: passing when the pin is stale, ignoring collection errors, or
treating "never ran" as "fine".
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_test_population",
    Path(__file__).resolve().parents[1] / "scripts" / "check_test_population.py",
)
assert _SPEC and _SPEC.loader
ctp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ctp)

REQUIRED = [f"tests/test_upstream_compat.py::test_{i}" for i in range(26)]


def _healthy_report() -> dict[str, Any]:
    return {
        "exitstatus": 0,
        "collected": {n: ["upstream"] for n in REQUIRED} | {"tests/test_other.py::t": []},
        "deselected": [],
        "collection_errors": [],
        "outcomes": {n: "passed" for n in REQUIRED} | {"tests/test_other.py::t": "passed"},
        "skip_reasons": {},
    }


def _manifest(upstream_path: str = "/nonexistent") -> dict[str, Any]:
    return {
        "required_marker": "upstream",
        "expected_required_count": len(REQUIRED),
        "required_node_ids_sha256": ctp.node_id_digest(REQUIRED),
        "upstream_path": upstream_path,
        "upstream_commit": "dca79815b704e5aa9c6bdc3082351f9e3b2848c2",
    }


class TestTheFailureThisExistsFor:
    def test_the_f_m2_1_shape_is_refused(self) -> None:
        """9 passed, 6 skipped, 11 never collected — and exit status 0.

        This is the real report shape from the environment missing matplotlib
        and cv2. A checker that passes this is not a checker.
        """
        report = _healthy_report()
        collected, outcomes = {}, {}
        for i, node in enumerate(REQUIRED):
            if i < 9:
                collected[node] = ["upstream"]
                outcomes[node] = "passed"
            elif i < 15:
                collected[node] = ["upstream"]
                outcomes[node] = "skipped"
            # the remaining 11 are simply absent -- never collected
        report["collected"] = collected
        report["outcomes"] = outcomes
        report["skip_reasons"] = dict.fromkeys(
            list(collected)[9:15], "train_utils needs wandb/prettytable/matplotlib/cv2/diffusers"
        )

        failures = ctp.check(report, _manifest())
        assert failures, "the checker accepted the exact failure it was built to catch"
        joined = "\n".join(failures)
        assert "CONDITION 1" in joined  # population contracted
        assert "CONDITION 2" in joined  # required tests skipped
        assert "matplotlib" in joined, "the skip reason must survive into the failure output"

    def test_exit_status_zero_does_not_rescue_a_contracted_population(self) -> None:
        report = _healthy_report()
        report["exitstatus"] = 0
        del report["collected"][REQUIRED[0]]
        del report["outcomes"][REQUIRED[0]]
        assert ctp.check(report, _manifest())


class TestConditions:
    def test_healthy_report_passes(self) -> None:
        assert ctp.check(_healthy_report(), _manifest()) == []

    def test_a_deselected_required_test_fails(self) -> None:
        report = _healthy_report()
        report["deselected"] = [REQUIRED[3]]
        assert any("CONDITION 2" in f for f in ctp.check(report, _manifest()))

    def test_a_collection_error_fails_even_if_everything_else_passed(self) -> None:
        """A run with a collection error has an unknown population."""
        report = _healthy_report()
        report["collection_errors"] = ["tests/test_broken.py"]
        assert any("collection error" in f.lower() for f in ctp.check(report, _manifest()))

    def test_collected_but_never_run_is_not_fine(self) -> None:
        report = _healthy_report()
        del report["outcomes"][REQUIRED[5]]
        assert any("never run" in f for f in ctp.check(report, _manifest()))

    def test_a_failing_required_test_fails(self) -> None:
        report = _healthy_report()
        report["outcomes"][REQUIRED[2]] = "failed"
        assert any("CONDITION 3" in f for f in ctp.check(report, _manifest()))

    def test_swapped_node_ids_fail_even_at_the_right_count(self) -> None:
        """Count alone is not identity: 26 different tests is not 26 tests."""
        report = _healthy_report()
        report["collected"].pop(REQUIRED[0])
        report["outcomes"].pop(REQUIRED[0])
        report["collected"]["tests/test_new.py::t"] = ["upstream"]
        report["outcomes"]["tests/test_new.py::t"] = "passed"
        failures = ctp.check(report, _manifest())
        assert any("node-id set" in f for f in failures)


class TestPin:
    def test_upstream_drift_is_a_violation(self, tmp_path: Path) -> None:
        """The required-test expectation is only meaningful against the pin."""
        import subprocess

        for args in (
            ["init", "-q"],
            ["config", "user.email", "t@e.i"],
            ["config", "user.name", "T"],
        ):
            subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
        (tmp_path / "f").write_text("x")
        subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-qm", "c"], check=True, capture_output=True
        )

        manifest = _manifest(upstream_path=str(tmp_path))
        assert any("upstream commit" in f for f in ctp.check(_healthy_report(), manifest))

    def test_manifest_round_trips(self, tmp_path: Path) -> None:
        built = ctp.build_manifest(_healthy_report(), "upstream", "/nonexistent")
        assert built["expected_required_count"] == len(REQUIRED)
        path = tmp_path / "m.json"
        path.write_text(json.dumps(built))
        assert ctp.check(_healthy_report(), json.loads(path.read_text())) == []

    def test_the_repository_manifest_matches_the_repository(self) -> None:
        """The committed pin must describe this repo, or it pins nothing."""
        manifest = json.loads(ctp.MANIFEST.read_text())
        assert manifest["required_marker"] == "upstream"
        assert manifest["expected_required_count"] == 26
        assert len(manifest["required_node_ids"]) == 26
        assert (
            ctp.node_id_digest(manifest["required_node_ids"])
            == manifest["required_node_ids_sha256"]
        )


class TestCli:
    def test_exit_codes(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        report_path, manifest_path = tmp_path / "r.json", tmp_path / "m.json"
        report_path.write_text(json.dumps(_healthy_report()))
        manifest_path.write_text(json.dumps(_manifest()))
        assert ctp.main([str(report_path), "--manifest", str(manifest_path)]) == 0

        broken = _healthy_report()
        broken["outcomes"][REQUIRED[1]] = "skipped"
        report_path.write_text(json.dumps(broken))
        assert ctp.main([str(report_path), "--manifest", str(manifest_path)]) == 1
        assert "INVARIANT VIOLATED" in capsys.readouterr().err
