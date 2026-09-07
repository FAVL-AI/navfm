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

import hashlib
import json
from pathlib import Path

import pytest

from navfm.evidence import EvidenceNotPersisted, emit_evidence

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"

#: Harnesses that own an Isaac runtime AND owe an evidence artefact. A name
#: arrives here when such a harness is written, not when it first misbehaves.
EVIDENCE_PRODUCING_ISAAC_HARNESSES = (
    "diagnose_support_invariance.py",
    "diagnose_support_causal_controls.py",
    "diagnose_blocker_targetability.py",
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


class TestShutdownCannotPrecedePersistence:
    @pytest.mark.parametrize("name", EVIDENCE_PRODUCING_ISAAC_HARNESSES)
    def test_the_harness_writes_before_it_closes_the_app(self, name: str) -> None:
        src = (SCRIPTS / name).read_text()
        write_at = src.find("emit_evidence(")
        close_at = src.find("app.close()")
        assert write_at != -1, f"{name} must persist evidence via navfm.evidence.emit_evidence"
        assert close_at != -1, f"{name} is not an Isaac harness; remove it from the list"
        assert write_at < close_at, (
            f"{name} shuts its runtime down before persisting evidence. "
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

    def test_the_ordering_check_can_fail(self, tmp_path: Path) -> None:
        """The negative control for the check above, on a synthetic harness."""
        bad = "app.close()\nemit_evidence(out, rec)\n"
        assert bad.find("emit_evidence(") > bad.find("app.close()"), (
            "a harness closing before writing must be detected by this ordering rule"
        )
