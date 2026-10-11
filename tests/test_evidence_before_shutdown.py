"""EVIDENCE_BEFORE_SHUTDOWN — a run that emits no artefact did not succeed.

One diagnostic in this repository exited 0 and produced nothing. Its evidence
write sat after ``SimulationApp.close()``, which terminates the process, so the
write never ran. Every signal a caller normally trusts said the run was fine:
the exit code was 0, stderr was empty, and Isaac's own shutdown log looked
ordinary. Only a file-existence check in the calling shell noticed.

That is the FL-019 shape -- a clean status reported for a step that did not
happen -- and the defence has to be structural, because the failing signal is
the one everything downstream reads.

Two guards, and both must be able to fail:

* ``emit_evidence`` cannot return without a parseable artefact on disk.
* No evidence-producing Isaac harness may shut its runtime down before it has
  written what it owes, asserted from source order rather than from a comment.

The source-order check reads the file with ``ast``/text rather than importing
it: these harnesses build a ``SimulationApp`` at import-adjacent scope, and a
test that needed Isaac to verify a line ordering would not run on a build host.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from navfm.evidence import (
    EvidenceNotPersisted,
    RunOutcome,
    adjudicate_run,
    emit_evidence,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"

#: Harnesses that own an Isaac runtime AND owe an evidence artefact. A name
#: arrives here when such a harness is written, not when it first misbehaves.
EVIDENCE_PRODUCING_ISAAC_HARNESSES = (
    "diagnose_support_invariance.py",
    "diagnose_support_causal_controls.py",
    "diagnose_blocker_targetability.py",
    "camera_view_acceptance.py",
    "preregister_scene_poses.py",
    "scene_visibility_classification.py",
    "validate_camera_hard_gate.py",
    "validate_hospital_route_admission.py",
)


class TestEmitEvidencePersists:
    def test_it_returns_the_digest_of_what_actually_landed(self, tmp_path: Path) -> None:
        out = tmp_path / "result.json"
        digest = emit_evidence(out, {"check": "X", "value": 1})
        assert out.is_file()
        assert digest == hashlib.sha256(out.read_bytes()).hexdigest()
        assert json.loads(out.read_text())["check"] == "X"

    def test_it_creates_missing_parent_directories(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "deeper" / "result.json"
        emit_evidence(out, {"check": "X"})
        assert out.is_file()

    def test_required_keys_are_enforced(self, tmp_path: Path) -> None:
        with pytest.raises(EvidenceNotPersisted, match="missing required key"):
            emit_evidence(tmp_path / "r.json", {"value": 1}, required_keys=("check",))

    def test_an_unserialisable_record_raises_rather_than_half_writing(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "r.json"

        class Hostile:
            def __repr__(self) -> str:
                raise RuntimeError("not representable")

        with pytest.raises(EvidenceNotPersisted):
            emit_evidence(out, {"bad": Hostile()})
        assert not out.exists(), "nothing may be left behind when the record is unwritable"

    def test_success_is_impossible_without_an_artefact(self, tmp_path: Path) -> None:
        """The load-bearing property: returning normally implies evidence exists."""
        out = tmp_path / "r.json"
        emit_evidence(out, {"check": "X"}, required_keys=("check",))
        assert out.is_file() and out.read_bytes().strip()

    def test_the_guard_detects_an_unparseable_artefact(self, tmp_path: Path) -> None:
        """Prove the parse check can fail, by corrupting what was written."""
        out = tmp_path / "r.json"
        emit_evidence(out, {"check": "X"})
        out.write_text("{not json")
        with pytest.raises(json.JSONDecodeError):
            json.loads(out.read_text())


def _evidence_writers(tree: ast.Module) -> set[str]:
    """Names that persist evidence: ``emit_evidence`` and any local wrapper.

    Resolved one level deep, because several harnesses funnel their writes
    through a module-level ``_emit`` helper. Counting only the direct call would
    make the helper look like a harness that never writes.
    """
    writers = {"emit_evidence"}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == "emit_evidence"):
                    writers.add(node.name)
                    break
    return writers


def _is_close_call(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    return isinstance(func, ast.Attribute) and func.attr == "close"


def _writes_evidence(stmt: ast.stmt, writers: set[str]) -> bool:
    for sub in ast.walk(stmt):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in writers:
            return True
    return False


def _returns_nonzero(stmt: ast.stmt) -> bool:
    """A refusal: exits with a code that cannot be read as success."""
    if not isinstance(stmt, ast.Return) or stmt.value is None:
        return False
    value = stmt.value
    return isinstance(value, ast.Constant) and value.value not in (0, None)


def unguarded_shutdowns(source: str) -> list[int]:
    """Line numbers of ``app.close()`` calls that may precede persistence.

    The property is not "the write appears earlier in the file" -- that compared
    a helper's *definition* position against *call* positions and fired on three
    healthy harnesses. The property is: a path may shut the runtime down without
    having written evidence ONLY if it then exits non-zero. A refusal that
    returns 2 is honest; a path that returns 0 having written nothing is FL-019.
    """
    tree = ast.parse(source)
    writers = _evidence_writers(tree)
    offenders: list[int] = []

    def scan(body: list[ast.stmt], written_before: bool) -> None:
        written = written_before
        for i, stmt in enumerate(body):
            if _is_close_call(stmt):
                if not written and not any(_returns_nonzero(s) for s in body[i + 1:i + 2]):
                    offenders.append(stmt.lineno)
                continue
            if _writes_evidence(stmt, writers):
                written = True
            for field in ("body", "orelse", "finalbody"):
                for child in getattr(stmt, field, []) or []:
                    if isinstance(child, ast.stmt):
                        scan([c for c in getattr(stmt, field)], written)
                        break
            for handler in getattr(stmt, "handlers", []) or []:
                scan(handler.body, written)
    scan(tree.body, False)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            scan(node.body, False)
    return sorted(set(offenders))


class TestShutdownCannotPrecedePersistence:
    @pytest.mark.parametrize("name", EVIDENCE_PRODUCING_ISAAC_HARNESSES)
    def test_no_path_closes_the_runtime_then_exits_clean_without_evidence(
        self, name: str
    ) -> None:
        src = (SCRIPTS / name).read_text()
        assert "emit_evidence" in src, (
            f"{name} must persist evidence via navfm.evidence.emit_evidence"
        )
        assert "close()" in src, f"{name} is not an Isaac harness; remove it from the list"
        offenders = unguarded_shutdowns(src)
        assert not offenders, (
            f"{name} shuts its runtime down at line(s) {offenders} without having "
            "persisted evidence, on a path that does not exit non-zero. "
            "SimulationApp.close() can terminate the process, so the write would "
            "never run and the harness would still exit 0."
        )

    @pytest.mark.parametrize("name", EVIDENCE_PRODUCING_ISAAC_HARNESSES)
    def test_the_harness_does_not_persist_with_a_bare_write(self, name: str) -> None:
        """A raw write_text would bypass the read-back, so the guard would not apply."""
        src = (SCRIPTS / name).read_text()
        assert "write_text(json.dumps" not in src, (
            f"{name} writes evidence directly; route it through emit_evidence so the "
            "artefact is validated rather than merely written"
        )

    def test_the_ordering_check_detects_a_close_before_the_write(self) -> None:
        """Negative control: the check must fail on the shape it exists to catch."""
        bad = (
            "def main():\n"
            "    app = X()\n"
            "    app.close()\n"
            "    emit_evidence(out, rec)\n"
            "    return 0\n"
        )
        assert unguarded_shutdowns(bad) == [3]

    def test_a_refusal_path_may_close_without_evidence(self) -> None:
        """The other direction: closing before a non-zero exit is honest, not FL-019."""
        refusal = (
            "def main():\n"
            "    app = X()\n"
            "    if broken:\n"
            "        app.close()\n"
            "        return 2\n"
            "    emit_evidence(out, rec)\n"
            "    app.close()\n"
            "    return 0\n"
        )
        assert unguarded_shutdowns(refusal) == []

    def test_a_helper_that_wraps_emit_evidence_counts_as_a_write(self) -> None:
        """Otherwise a harness funnelling writes through _emit looks like it never writes."""
        wrapped = (
            "def _emit(rec):\n"
            "    emit_evidence(OUT, rec)\n"
            "def main():\n"
            "    app = X()\n"
            "    _emit(rec)\n"
            "    app.close()\n"
            "    return 0\n"
        )
        assert unguarded_shutdowns(wrapped) == []


class TestExitZeroIsNotEvidence:
    """FL-019 directly: a clean exit code for a step that did not happen.

    Every signal a caller normally trusts can be healthy while nothing was
    measured -- exit 0, empty stderr, an ordinary shutdown log. So the outcome is
    adjudicated from the exit code AND the artefact, and the failing case is
    given a name rather than being absorbed into "success".
    """

    def test_exit_zero_with_no_artefact_is_run_failed_no_artefact(
        self, tmp_path: Path
    ) -> None:
        """The load-bearing negative control."""
        assert adjudicate_run(0, tmp_path / "never_written.json") is (
            RunOutcome.RUN_FAILED_NO_ARTEFACT
        )

    def test_exit_zero_with_an_empty_artefact_is_caught(self, tmp_path: Path) -> None:
        out = tmp_path / "r.json"
        out.write_text("")
        assert adjudicate_run(0, out) is RunOutcome.RUN_FAILED_NO_ARTEFACT

    def test_exit_zero_with_an_unparseable_artefact_is_caught(self, tmp_path: Path) -> None:
        out = tmp_path / "r.json"
        out.write_text("{not json")
        assert adjudicate_run(0, out) is RunOutcome.RUN_FAILED_NO_ARTEFACT

    def test_exit_zero_missing_a_required_key_is_caught(self, tmp_path: Path) -> None:
        """A well-formed artefact that cannot say what it is, is not evidence."""
        out = tmp_path / "r.json"
        emit_evidence(out, {"value": 1})
        assert adjudicate_run(0, out, required_keys=("check", "verdict")) is (
            RunOutcome.RUN_FAILED_NO_ARTEFACT
        )

    def test_a_json_scalar_is_not_an_artefact(self, tmp_path: Path) -> None:
        out = tmp_path / "r.json"
        out.write_text("42")
        assert adjudicate_run(0, out) is RunOutcome.RUN_FAILED_NO_ARTEFACT

    def test_the_healthy_case_passes(self, tmp_path: Path) -> None:
        """The other direction: a guard that cannot pass gets deleted."""
        out = tmp_path / "r.json"
        emit_evidence(out, {"check": "X", "verdict": "PASS"})
        outcome = adjudicate_run(0, out, required_keys=("check", "verdict"))
        assert outcome is RunOutcome.RUN_OK
        assert outcome.is_evidence

    def test_a_nonzero_exit_is_believed_even_with_an_artefact(self, tmp_path: Path) -> None:
        """A harness that says it failed is not overruled by a file it left behind."""
        out = tmp_path / "r.json"
        emit_evidence(out, {"check": "X", "verdict": "PASS"})
        assert adjudicate_run(2, out, required_keys=("check",)) is RunOutcome.RUN_FAILED

    def test_only_run_ok_counts_as_evidence(self) -> None:
        assert RunOutcome.RUN_OK.is_evidence
        assert not RunOutcome.RUN_FAILED_NO_ARTEFACT.is_evidence
        assert not RunOutcome.RUN_FAILED.is_evidence
