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

_CPS_SPEC = importlib.util.spec_from_file_location(
    "check_population_sets",
    Path(__file__).resolve().parents[1] / "scripts" / "check_population_sets.py",
)
assert _CPS_SPEC and _CPS_SPEC.loader
cps = importlib.util.module_from_spec(_CPS_SPEC)
_CPS_SPEC.loader.exec_module(cps)

_MANIFEST = json.loads(ctp.MANIFEST.read_text())
# Read from the manifest's population map, which is the primary record; the
# assertions below then prove the pin and the map agree with each other.
EXPECTED_UPSTREAM_NODE_IDS = frozenset(
    node for node, markers in _MANIFEST["population"].items() if "upstream" in markers
)
# Updated only through a reviewed re-pin, together with the manifest.
EXPECTED_UPSTREAM_DIGEST = "72ba6969c0d92a13142f4e3e0784edfb2fa03e9e50243a33fb1056afe713bb85"


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
        """The committed pin must describe this repo, or it pins nothing.

        Set equality, not a count. A count admits a substitution: drop one node
        and add another and 39 is still 39, while the population the pin claims
        to describe has changed. The digest is recomputed here rather than read,
        so a hand-edited manifest disagrees with itself.
        """
        manifest = json.loads(ctp.MANIFEST.read_text())
        assert manifest["required_marker"] == "upstream"

        # The upstream set is derivable from the manifest's own population map,
        # so the two representations must agree. Re-pinning is a reviewed act:
        # 26 pre-existing upstream-marked tests, + 7 RNG-domain tests that need
        # the patched clone, + 6 newly owned under Repair 3.
        derived = {
            node for node, markers in manifest["population"].items() if "upstream" in markers
        }
        pinned = set(manifest["required_node_ids"])
        assert pinned == derived, {"only_in_pin": pinned - derived, "only_in_population": derived - pinned}
        assert pinned == EXPECTED_UPSTREAM_NODE_IDS
        assert ctp.node_id_digest(sorted(pinned)) == EXPECTED_UPSTREAM_DIGEST
        assert manifest["required_node_ids_sha256"] == EXPECTED_UPSTREAM_DIGEST
        assert manifest["expected_required_count"] == len(EXPECTED_UPSTREAM_NODE_IDS) == 39

    def test_a_substituted_node_id_is_caught_though_the_count_is_right(self) -> None:
        """The failure a count-only assertion cannot see."""
        manifest = json.loads(ctp.MANIFEST.read_text())
        swapped = sorted((set(manifest["required_node_ids"]) - {min(EXPECTED_UPSTREAM_NODE_IDS)}) | {"tests/test_forged.py::t"})
        assert len(swapped) == 39
        assert set(swapped) != EXPECTED_UPSTREAM_NODE_IDS
        assert ctp.node_id_digest(swapped) != EXPECTED_UPSTREAM_DIGEST

    @pytest.mark.parametrize("drop", [True, False])
    def test_one_missing_or_one_extra_node_is_caught(self, drop: bool) -> None:
        nodes = set(EXPECTED_UPSTREAM_NODE_IDS)
        mutated = nodes - {min(nodes)} if drop else nodes | {"tests/test_extra.py::t"}
        assert ctp.node_id_digest(sorted(mutated)) != EXPECTED_UPSTREAM_DIGEST
        assert len(mutated) != 39

    def test_a_malformed_population_entry_is_refused(self) -> None:
        manifest = json.loads(ctp.MANIFEST.read_text())
        manifest["population"]["tests/test_forged.py::t"] = "upstream"  # str, not list
        with pytest.raises(cps.SchemaError):
            cps.validate_manifest(manifest)


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


# --------------------------------------------- scripts/check_population_sets.py


def _pop() -> dict[str, list[str]]:
    return {
        "tests/h.py::a": [],
        "tests/h.py::b": [],
        "tests/u.py::c": ["upstream"],
        "tests/t.py::d": ["torch"],
        "tests/p.py::e": ["plot"],
    }


def _sets_manifest(**overrides: Any) -> dict[str, Any]:
    population = overrides.pop("population", _pop())
    manifest: dict[str, Any] = {
        "population": population,
        "digests": {
            name: {"count": len(nodes), "sha256": cps.node_id_digest(nodes)}
            for name, nodes in cps.sets_from(population).items()
        },
        "upstream_commit": "dca79815b704e5aa9c6bdc3082351f9e3b2848c2",
        "upstream_path": "third_party/visualnav-transformer",
        "open_evidence_gaps": [],
        "job_ownership": {"upstream": "owner", "torch": "owner", "plot": "owner", "go_stanford": None},
    }
    manifest.update(overrides)
    return manifest


def _sets_report(executed: list[str], deselected: list[str], **overrides: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "exitstatus": 0,
        "collected": {node: [] for node in executed + deselected},
        "deselected": deselected,
        "collection_errors": [],
        "outcomes": dict.fromkeys(executed, "passed"),
        "skip_reasons": {},
    }
    report.update(overrides)
    return report


HERMETIC = ["tests/h.py::a", "tests/h.py::b"]
RESOURCE = ["tests/u.py::c", "tests/t.py::d", "tests/p.py::e"]
VERSIONS = {"python": "3.11.15", "numpy": "2.4.6", "torch": "2.13.0+cpu", "matplotlib": "3.11.1"}


class TestOwnershipModes:
    def test_a_valid_ordinary_report_passes(self) -> None:
        report = _sets_report(HERMETIC, RESOURCE)
        assert cps.check(report, _sets_manifest(), cps.ORDINARY, VERSIONS) == []

    def test_a_valid_owner_report_passes(self) -> None:
        report = _sets_report(HERMETIC + RESOURCE, [])
        assert cps.check(report, _sets_manifest(), cps.OWNER, VERSIONS, job_id="owner") == []

    def test_a_missing_owned_node_is_named(self) -> None:
        report = _sets_report(HERMETIC + RESOURCE[:-1], [])
        failures = "\n".join(cps.check(report, _sets_manifest(), cps.OWNER, job_id="owner"))
        assert "tests/p.py::e" in failures and "missing" in failures

    def test_an_extra_node_is_named(self) -> None:
        report = _sets_report([*HERMETIC, "tests/h.py::forged"], RESOURCE)
        failures = "\n".join(cps.check(report, _sets_manifest(), cps.ORDINARY))
        assert "tests/h.py::forged" in failures and "extra" in failures

    def test_a_substituted_node_is_caught_though_the_count_is_right(self) -> None:
        """The mutation a count comparison cannot see."""
        report = _sets_report(["tests/h.py::a", "tests/h.py::forged"], RESOURCE)
        failures = cps.check(report, _sets_manifest(), cps.ORDINARY)
        assert failures, "a same-size population with a different member was accepted"

    def test_an_unexpected_skip_fails(self) -> None:
        report = _sets_report(HERMETIC, RESOURCE)
        report["outcomes"]["tests/h.py::b"] = "skipped"
        assert any("unexpected skips" in f for f in cps.check(report, _sets_manifest(), cps.ORDINARY))

    def test_a_tracked_open_gap_is_not_an_unexpected_skip(self) -> None:
        report = _sets_report(HERMETIC, RESOURCE)
        report["outcomes"]["tests/h.py::b"] = "skipped"
        manifest = _sets_manifest(
            open_evidence_gaps=[{"node_id": "tests/h.py::b", "reason": "tracked", "status": "OPEN"}]
        )
        assert not any("unexpected skips" in f for f in cps.check(report, manifest, cps.ORDINARY))

    def test_an_owned_node_deselected_from_its_owner_fails(self) -> None:
        report = _sets_report(HERMETIC + RESOURCE[:-1], [RESOURCE[-1]])
        failures = "\n".join(cps.check(report, _sets_manifest(), cps.OWNER, job_id="owner"))
        assert "deselected from their owner job" in failures

    def test_deselecting_a_hermetic_node_from_an_ordinary_leg_fails(self) -> None:
        report = _sets_report(["tests/h.py::a"], [*RESOURCE, "tests/h.py::b"])
        failures = "\n".join(cps.check(report, _sets_manifest(), cps.ORDINARY))
        assert "deselected outside the pinned resource population" in failures

    def test_collection_errors_fail(self) -> None:
        report = _sets_report(HERMETIC, RESOURCE, collection_errors=["tests/broken.py"])
        assert any("collection errors" in f for f in cps.check(report, _sets_manifest(), cps.ORDINARY))

    def test_a_stale_stored_digest_is_refused(self) -> None:
        """Digests are recomputed; a stored digest may not certify itself."""
        manifest = _sets_manifest()
        manifest["digests"]["hermetic"]["sha256"] = "0" * 64
        report = _sets_report(HERMETIC, RESOURCE)
        assert any("stale" in f for f in cps.check(report, manifest, cps.ORDINARY))

    def test_missing_resource_version_provenance_fails(self) -> None:
        report = _sets_report(HERMETIC + RESOURCE, [])
        failures = cps.check(report, _sets_manifest(), cps.OWNER, {"python": "3.11.15"}, job_id="owner")
        assert any("resource-version provenance is missing" in f for f in failures)
        assert "torch" in "\n".join(failures)

    def test_an_incorrect_upstream_sha_fails(self, tmp_path: Path) -> None:
        import subprocess

        for args in (["init", "-q"], ["config", "user.email", "t@e.i"], ["config", "user.name", "T"]):
            subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
        (tmp_path / "f").write_text("x")
        subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "c"], check=True, capture_output=True)
        report = _sets_report(HERMETIC + RESOURCE, [])
        failures = cps.check(report, _sets_manifest(), cps.OWNER, VERSIONS, tmp_path, job_id="owner")
        assert any("manifest pins" in f for f in failures)

    def test_an_unreadable_upstream_checkout_fails(self, tmp_path: Path) -> None:
        report = _sets_report(HERMETIC + RESOURCE, [])
        failures = cps.check(report, _sets_manifest(), cps.OWNER, VERSIONS, tmp_path / "absent", job_id="owner")
        assert any("not readable" in f for f in failures)


class TestSchemaAndCli:
    def test_a_malformed_report_is_refused(self) -> None:
        with pytest.raises(cps.SchemaError):
            cps.check({"collected": {}}, _sets_manifest(), cps.ORDINARY)

    def test_a_malformed_manifest_is_refused(self) -> None:
        with pytest.raises(cps.SchemaError):
            cps.check(_sets_report(HERMETIC, RESOURCE), {"population": {}}, cps.ORDINARY)

    def test_an_unknown_mode_is_refused(self) -> None:
        with pytest.raises(cps.SchemaError):
            cps.check(_sets_report(HERMETIC, RESOURCE), _sets_manifest(), "guess")

    def test_a_missing_report_exits_non_zero(self, tmp_path: Path) -> None:
        manifest = tmp_path / "m.json"
        manifest.write_text(json.dumps(_sets_manifest()))
        assert cps.main([str(tmp_path / "absent.json"), "--mode", cps.ORDINARY,
                         "--manifest", str(manifest)]) == 1

    def test_a_missing_manifest_exits_non_zero(self, tmp_path: Path) -> None:
        report = tmp_path / "r.json"
        report.write_text(json.dumps(_sets_report(HERMETIC, RESOURCE)))
        assert cps.main([str(report), "--mode", cps.ORDINARY,
                         "--manifest", str(tmp_path / "absent.json")]) == 1

    def test_invalid_json_exits_non_zero(self, tmp_path: Path) -> None:
        report = tmp_path / "r.json"
        report.write_text("{not json")
        manifest = tmp_path / "m.json"
        manifest.write_text(json.dumps(_sets_manifest()))
        assert cps.main([str(report), "--mode", cps.ORDINARY, "--manifest", str(manifest)]) == 1

    def test_cli_exit_codes(self, tmp_path: Path) -> None:
        report, manifest = tmp_path / "r.json", tmp_path / "m.json"
        manifest.write_text(json.dumps(_sets_manifest()))
        report.write_text(json.dumps(_sets_report(HERMETIC, RESOURCE)))
        assert cps.main([str(report), "--mode", cps.ORDINARY, "--manifest", str(manifest)]) == 0

        report.write_text(json.dumps(_sets_report(["tests/h.py::a"], RESOURCE)))
        assert cps.main([str(report), "--mode", cps.ORDINARY, "--manifest", str(manifest)]) == 1


# ------------------------------------------- go_stanford corpus ownership (Repair 6)

CORPUS_NODE = "tests/c.py::TestReleasedGoStanfordCorpus::test_released_records_convert"


def _corpus_pop() -> dict[str, list[str]]:
    return {**_pop(), CORPUS_NODE: ["go_stanford"]}


def _corpus_manifest(owner: str | None = None, **overrides: Any) -> dict[str, Any]:
    manifest = _sets_manifest(population=_corpus_pop(), **overrides)
    manifest["job_ownership"] = {
        "upstream": "owner",
        "torch": "owner",
        "plot": "owner",
        "go_stanford": owner,
    }
    return manifest


CORPUS_SHA = "1fe1411945abd9cd0f335e845fe40d3477aac641aeb5669c961ec9debc4fb8a4"
# An owner records provenance for what it owns, so a corpus owner's versions
# file carries the corpus digest alongside python and numpy.
OWNER_VERSIONS = {**VERSIONS, "go_stanford_sha256": CORPUS_SHA}

OWNED_BY_OWNER = HERMETIC + RESOURCE
# A corpus-owner job runs the hermetic population plus the one node it owns; the
# upstream/torch/plot nodes belong to a different job and are deselected there.
CORPUS_JOB_RUNS = [*HERMETIC, CORPUS_NODE]


class TestCorpusOwnership:
    def test_the_corpus_node_is_in_the_resource_union_not_the_hermetic_set(self) -> None:
        sets = cps.sets_from(_corpus_pop())
        assert CORPUS_NODE in sets["go_stanford"] == {CORPUS_NODE}
        assert CORPUS_NODE in sets["resource_union"]
        assert CORPUS_NODE not in sets["hermetic"]

    def test_an_ordinary_leg_may_deselect_the_corpus_node(self) -> None:
        report = _sets_report(HERMETIC, [*RESOURCE, CORPUS_NODE])
        assert cps.check(report, _corpus_manifest(), cps.ORDINARY, VERSIONS) == []

    def test_a_non_owner_job_may_deselect_the_corpus_node(self) -> None:
        """upstream-compat owns upstream/torch/plot, not the corpus."""
        report = _sets_report(OWNED_BY_OWNER, [CORPUS_NODE])
        assert cps.check(report, _corpus_manifest(), cps.OWNER, VERSIONS, job_id="owner") == []

    def test_a_marker_with_no_owner_fails_completeness_and_names_the_node(self) -> None:
        report = _sets_report(OWNED_BY_OWNER, [CORPUS_NODE])
        failures = "\n".join(cps.check(report, _corpus_manifest(), cps.COMPLETENESS))
        assert "go_stanford" in failures and CORPUS_NODE in failures
        assert "no owner job" in failures

    def test_open_evidence_gaps_cannot_baseline_the_missing_owner(self) -> None:
        """Recording that a node executes nowhere is not the same as evidence."""
        manifest = _corpus_manifest(
            open_evidence_gaps=[{"node_id": CORPUS_NODE, "reason": "attempt", "status": "permitted"}]
        )
        report = _sets_report(OWNED_BY_OWNER, [CORPUS_NODE])
        failures = "\n".join(cps.check(report, manifest, cps.COMPLETENESS))
        assert CORPUS_NODE in failures, "an open-gap entry suppressed a missing-owner failure"

    def test_completeness_passes_once_an_owner_executes_the_node(self) -> None:
        report = _sets_report(CORPUS_JOB_RUNS, RESOURCE)
        assert cps.check(report, _corpus_manifest(owner="corpus-job"), cps.COMPLETENESS) == []

    def test_a_declared_owner_that_does_not_execute_the_node_fails(self) -> None:
        report = _sets_report(HERMETIC, RESOURCE)
        failures = "\n".join(
            cps.check(report, _corpus_manifest(owner="corpus-job"), cps.OWNER, VERSIONS, job_id="corpus-job")
        )
        assert CORPUS_NODE in failures and "missing" in failures

    def test_a_declared_owner_that_executes_the_node_passes(self) -> None:
        report = _sets_report(CORPUS_JOB_RUNS, RESOURCE)
        assert (
            cps.check(
                report, _corpus_manifest(owner="corpus-job"), cps.OWNER, OWNER_VERSIONS, job_id="corpus-job"
            )
            == []
        )

    def test_a_declared_owner_that_skips_the_node_fails(self) -> None:
        report = _sets_report(CORPUS_JOB_RUNS, RESOURCE)
        report["outcomes"][CORPUS_NODE] = "skipped"
        failures = "\n".join(
            cps.check(report, _corpus_manifest(owner="corpus-job"), cps.OWNER, VERSIONS, job_id="corpus-job")
        )
        assert CORPUS_NODE in failures and "unexpected skips" in failures

    def test_a_declared_owner_that_deselects_the_node_fails(self) -> None:
        report = _sets_report(HERMETIC, [*RESOURCE, CORPUS_NODE])
        failures = "\n".join(
            cps.check(report, _corpus_manifest(owner="corpus-job"), cps.OWNER, VERSIONS, job_id="corpus-job")
        )
        assert CORPUS_NODE in failures and "deselected from their owner job" in failures

    def test_removing_the_corpus_marker_puts_the_node_in_the_hermetic_set(self) -> None:
        """The mutation that would smuggle a corpus test into the ordinary legs."""
        unmarked = {**_corpus_pop(), CORPUS_NODE: []}
        report = _sets_report(HERMETIC, [*RESOURCE, CORPUS_NODE])
        manifest = _sets_manifest(population=unmarked)
        manifest["job_ownership"] = {
            "upstream": "owner",
            "torch": "owner",
            "plot": "owner",
            "go_stanford": None,
        }
        failures = "\n".join(cps.check(report, manifest, cps.ORDINARY, VERSIONS))
        assert CORPUS_NODE in failures

    def test_a_missing_report_still_exits_non_zero_in_completeness_mode(self, tmp_path: Path) -> None:
        manifest = tmp_path / "m.json"
        manifest.write_text(json.dumps(_corpus_manifest()))
        assert cps.main([str(tmp_path / "absent.json"), "--mode", cps.COMPLETENESS,
                         "--manifest", str(manifest)]) == 1


# ---------------------------------------- provenance follows ownership (Repair 6)

CORPUS_VERSIONS = {"python": "3.11.15", "numpy": "2.4.6", "go_stanford_sha256": CORPUS_SHA}


class TestProvenanceFollowsOwnership:
    """What a job must record is decided by what it owns, in both directions.

    A blanket requirement is wrong twice over: it lets a corpus job pass while
    saying nothing about which corpus it read, and it fails that same job for
    lacking a torch version it never used. Provenance describes the measurement
    or it is decoration.
    """

    def test_a_corpus_owner_must_record_which_corpus_it_read(self) -> None:
        report = _sets_report(CORPUS_JOB_RUNS, RESOURCE)
        versions = {"python": "3.11.15", "numpy": "2.4.6"}
        failures = "\n".join(
            cps.check(
                report, _corpus_manifest(owner="corpus-job"), cps.OWNER, versions, job_id="corpus-job"
            )
        )
        assert "go_stanford_sha256" in failures

    def test_a_corpus_owner_that_records_the_digest_passes(self) -> None:
        report = _sets_report(CORPUS_JOB_RUNS, RESOURCE)
        assert (
            cps.check(
                report,
                _corpus_manifest(owner="corpus-job"),
                cps.OWNER,
                CORPUS_VERSIONS,
                job_id="corpus-job",
            )
            == []
        )

    def test_a_corpus_owner_is_never_asked_for_a_torch_it_does_not_use(self) -> None:
        report = _sets_report(CORPUS_JOB_RUNS, RESOURCE)
        failures = "\n".join(
            cps.check(
                report,
                _corpus_manifest(owner="corpus-job"),
                cps.OWNER,
                CORPUS_VERSIONS,
                job_id="corpus-job",
            )
        )
        assert "torch" not in failures and "matplotlib" not in failures

    def test_a_torch_owner_must_still_record_torch_and_matplotlib(self) -> None:
        report = _sets_report(OWNED_BY_OWNER, [CORPUS_NODE])
        versions = {"python": "3.11.15", "numpy": "2.4.6"}
        failures = "\n".join(
            cps.check(report, _corpus_manifest(owner="corpus-job"), cps.OWNER, versions, job_id="owner")
        )
        assert "torch" in failures and "matplotlib" in failures

    def test_the_corpus_digest_is_not_demanded_of_a_hermetic_leg(self) -> None:
        report = _sets_report(HERMETIC, [*RESOURCE, CORPUS_NODE])
        versions = {"python": "3.11.15", "numpy": "2.4.6"}
        assert cps.check(report, _corpus_manifest(owner="corpus-job"), cps.ORDINARY, versions) == []

    def test_required_versions_is_derived_not_declared(self) -> None:
        assert cps.required_versions(cps.ORDINARY, {"go_stanford"}) == ("python", "numpy")
        assert cps.required_versions(cps.COMPLETENESS, {"torch"}) == ()
        assert cps.required_versions(cps.OWNER, set()) == ("python", "numpy")
        assert cps.required_versions(cps.OWNER, {"go_stanford"}) == (
            "python",
            "numpy",
            "go_stanford_sha256",
        )
        assert cps.required_versions(cps.OWNER, {"upstream", "torch", "plot"}) == (
            "python",
            "numpy",
            "matplotlib",
            "torch",
        )


class TestAJobMustNameItself:
    """F-M1-1: a gate that infers execution state cannot certify it.

    The concrete hazard is arithmetic, not stylistic. ``job == job_id`` with an
    absent ``--job-id`` compares None to None, so an unnamed run would claim
    ownership of exactly the markers that nobody owns -- and then pass, because
    it deselected them.
    """

    def test_owner_mode_without_a_job_id_refuses_rather_than_guessing(self) -> None:
        report = _sets_report(OWNED_BY_OWNER, [CORPUS_NODE])
        failures = "\n".join(cps.check(report, _corpus_manifest(), cps.OWNER, VERSIONS))
        assert "requires --job-id" in failures

    def test_an_unnamed_run_does_not_inherit_the_unowned_marker(self) -> None:
        report = _sets_report(OWNED_BY_OWNER, [CORPUS_NODE])
        failures = "\n".join(cps.check(report, _corpus_manifest(), cps.OWNER, VERSIONS))
        assert "go_stanford_sha256" not in failures, "an unnamed run claimed the unowned marker"

    def test_naming_the_job_is_enough_to_be_checked(self) -> None:
        report = _sets_report(OWNED_BY_OWNER, [CORPUS_NODE])
        assert cps.check(report, _corpus_manifest(), cps.OWNER, VERSIONS, job_id="owner") == []


class TestJobOwnershipSchema:
    """The ownership map is validated, not trusted: a typo must not read as null."""

    def test_a_missing_ownership_map_is_a_schema_error(self) -> None:
        manifest = _sets_manifest()
        del manifest["job_ownership"]
        with pytest.raises(cps.SchemaError, match="job_ownership"):
            cps.check(_sets_report(HERMETIC, RESOURCE), manifest, cps.ORDINARY, VERSIONS)

    def test_an_unknown_marker_is_refused(self) -> None:
        manifest = _sets_manifest()
        manifest["job_ownership"]["go_stanfrod"] = "typo-job"
        with pytest.raises(cps.SchemaError, match="unknown resource marker"):
            cps.check(_sets_report(HERMETIC, RESOURCE), manifest, cps.ORDINARY, VERSIONS)

    def test_an_unmentioned_marker_is_refused(self) -> None:
        manifest = _sets_manifest()
        del manifest["job_ownership"]["go_stanford"]
        with pytest.raises(cps.SchemaError, match="does not mention"):
            cps.check(_sets_report(HERMETIC, RESOURCE), manifest, cps.ORDINARY, VERSIONS)

    def test_an_empty_owner_name_is_not_a_quiet_null(self) -> None:
        manifest = _sets_manifest()
        manifest["job_ownership"]["go_stanford"] = "   "
        with pytest.raises(cps.SchemaError, match="job name or null"):
            cps.check(_sets_report(HERMETIC, RESOURCE), manifest, cps.ORDINARY, VERSIONS)
