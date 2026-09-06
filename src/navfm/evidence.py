"""Evidence classes: what a number is, declared by the run that produced it.

Every run in this repository emits a number. Almost none of those numbers are
scientific results, and the difference is not visible in the number. A loss of
1.2260 from a randomly initialised model on synthetic noise looks exactly like
a loss of 1.2260 from a released checkpoint on a real corpus — and `gates/M1/`
already contains a committed table headed "E2 … with interaction term" whose
rows are the former.

The repository's earlier defence was a single `random_init` boolean. That was
too coarse in one direction and too narrow in the other: it could not
distinguish a smoke test from a deliberate random-init control, and it asked
whether a checkpoint had been *named* rather than whether the run was evidence.

An evidence class is therefore declared per run, and it declares its own table
eligibility. The barrier in ``scripts/make_tables.py`` enforces that
declaration rather than re-deriving it, so a new class cannot silently acquire
table access by resembling an old one.

    >>> EvidenceClass.PIPELINE_SMOKE_TEST.scientific_result
    False
    >>> EvidenceClass.BASELINE_EVALUATION.table_eligible
    True
"""

from __future__ import annotations

import enum
import hashlib
import json
from pathlib import Path
from typing import Any

__all__ = [
    "EvidenceClass",
    "EvidenceNotPersisted",
    "emit_evidence",
    "evidence_block",
]


class EvidenceClass(enum.Enum):
    """What kind of evidence a run produced. Declared, never inferred."""

    #: Plumbing only. Synthetic data, random weights, or a truncated run whose
    #: purpose is to prove the code executes. Never a result.
    PIPELINE_SMOKE_TEST = "pipeline_smoke_test"

    #: A deliberately untrained model of the intended architecture, evaluated
    #: under the real protocol as the floor a trained model must beat. Real
    #: evidence about the instrument; not a claim about any model.
    RANDOM_INIT_CONTROL = "random_init_control"

    #: A structural check on a checkpoint -- does it load, do the tensor counts
    #: match, does it run. Produces numbers, answers no scientific question.
    CHECKPOINT_SANITY = "checkpoint_sanity"

    #: A released checkpoint evaluated on a declared split under a
    #: pre-registered protocol. Gate G0.c is this class.
    BASELINE_EVALUATION = "baseline_evaluation"

    #: A cell of the pre-registered experiment matrix.
    REGISTERED_EXPERIMENT = "registered_experiment"

    #: A real measurement that no pre-registration covers. Legitimate and
    #: useful, and barred from results tables precisely because it is
    #: unregistered -- this is the class that keeps exploratory work honest
    #: instead of driving it underground.
    DIAGNOSTIC_UNREGISTERED = "diagnostic_unregistered"

    @property
    def scientific_result(self) -> bool:
        """Does this class constitute a scientific result about a model?"""
        return self in {
            EvidenceClass.BASELINE_EVALUATION,
            EvidenceClass.REGISTERED_EXPERIMENT,
        }

    @property
    def table_eligible(self) -> bool:
        """May a run of this class appear in a results table?

        Identical to :attr:`scientific_result` today, and kept separate because
        they answer different questions and will diverge: a random-init control
        is not a result about a model, but a floor row in a results table is a
        defensible thing to want. When that day comes the change should be one
        property, reviewed, not a quiet reinterpretation of the other.
        """
        return self.scientific_result

    @property
    def requires_checkpoint_hash(self) -> bool:
        """Classes that make claims about a model must identify which bytes."""
        return self in {
            EvidenceClass.BASELINE_EVALUATION,
            EvidenceClass.REGISTERED_EXPERIMENT,
            EvidenceClass.CHECKPOINT_SANITY,
        }

    @classmethod
    def parse(cls, value: str) -> EvidenceClass:
        try:
            return cls(value)
        except ValueError:
            valid = ", ".join(c.value for c in cls)
            raise ValueError(f"unknown evidence class {value!r}; valid classes: {valid}") from None


def evidence_block(
    evidence_class: EvidenceClass,
    *,
    model_initialization: str,
    data_source: str,
) -> dict[str, Any]:
    """The four fields every ``metrics.json`` carries.

    ``scientific_result`` is derived from the class rather than passed in, so a
    run cannot declare a smoke-test class and a scientific-result flag at the
    same time. There is exactly one place that decision is made.
    """
    return {
        "evidence_class": evidence_class.value,
        "scientific_result": evidence_class.scientific_result,
        "model_initialization": model_initialization,
        "data_source": data_source,
    }


class EvidenceNotPersisted(RuntimeError):
    """A run finished without durably emitting the evidence it owed."""


def emit_evidence(
    path: str | Path,
    record: dict[str, Any],
    *,
    required_keys: tuple[str, ...] = (),
) -> str:
    """Write a run's evidence and prove it landed. Returns its SHA-256.

    Call this BEFORE shutting down any runtime the experiment used.
    ``SimulationApp.close()`` can terminate the process outright, so a write
    placed after it never executes -- and the process still exits 0. That
    produced exactly one failure here: a diagnostic reported success and left no
    artefact, caught by a caller's file-existence check rather than by any exit
    code (the F-M2/FL-019 genus, a clean status from a step that did not happen).

    Writing is not persisting. This re-reads and re-parses what it wrote, so the
    only way to return normally is for a valid artefact to exist on disk. A
    caller that reaches the next line has evidence; a caller that does not gets
    an exception rather than a zero.
    """
    target = Path(path)
    try:
        payload = json.dumps(record, indent=2, default=str) + "\n"
    except Exception as exc:  # any render failure means nothing was written
        raise EvidenceNotPersisted(
            f"record is not serialisable, so nothing was written to {target}: {exc}") from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload)

    # Read back rather than trust the write. A truncated or empty artefact is
    # indistinguishable from a healthy one until something tries to parse it.
    if not target.is_file():
        raise EvidenceNotPersisted(f"no artefact at {target} after writing it")
    raw = target.read_bytes()
    if not raw.strip():
        raise EvidenceNotPersisted(f"artefact at {target} is empty")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EvidenceNotPersisted(f"artefact at {target} does not parse: {exc}") from exc

    missing = [k for k in required_keys if k not in parsed]
    if missing:
        raise EvidenceNotPersisted(
            f"artefact at {target} is missing required key(s) {missing}; a result that "
            f"cannot say what it is may later be read as something it is not")

    return hashlib.sha256(raw).hexdigest()
