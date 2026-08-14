"""Measurements that cannot be confused with the absence of a measurement.

Three times in one session a null result was read as a clean result:

===========================  ==========================  =======================
Signal                       Read as                     Actually
===========================  ==========================  =======================
``pgrep`` matched            job running                 wrapper matched itself
``FULL_RENDER_CLOSURE``      dependencies complete       verifier reused the
                                                         traversal under test
``mdl_error_count == 0``     scene resolved cleanly      scene never loaded
===========================  ==========================  =======================

Each is the same error: a value reported by a process that never observed
anything. The fix is not more care. It is that a measurement carries its own
liveness, so ``0`` and "no measurement" cannot share a representation:

.. code-block:: text

    MEASUREMENT = LIVENESS + VALUE + PROVENANCE

never ``MEASUREMENT = VALUE``.

So :class:`MeasurementEnvelope` refuses to report a value until every declared
liveness precondition is true, and refuses to report ``MEASURED_ZERO`` over an
empty population -- a validator that examined nothing found no faults, and that
is not the same as finding none. ``0 collisions`` from a robot that never moved
is the case that motivates the population rule; a stationary robot collides with
nothing, perfectly.

The status is deliberately five-valued rather than boolean, because the four
ways of not having an answer are operationally different and a boolean collapses
them into the one that looks like success.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    """Why a measurement does or does not have a value.

    ``NOT_RUN``                 nothing was attempted.
    ``RUN_FAILED``              the process started and died before measuring.
    ``RUN_LIVE_NO_MEASUREMENT`` the process ran, the measurement did not execute
                                -- the case that produced ``mdl_error_count = 0``
                                from a scene that never loaded.
    ``MEASURED_ZERO``           a live measurement over a non-empty population
                                found nothing. This is the only clean zero.
    ``MEASURED_NONZERO``        a live measurement found something.
    """

    NOT_RUN = "NOT_RUN"
    RUN_FAILED = "RUN_FAILED"
    RUN_LIVE_NO_MEASUREMENT = "RUN_LIVE_NO_MEASUREMENT"
    MEASURED_ZERO = "MEASURED_ZERO"
    MEASURED_NONZERO = "MEASURED_NONZERO"

    @property
    def is_evidence(self) -> bool:
        """Only a completed measurement may back a claim."""
        return self in (Status.MEASURED_ZERO, Status.MEASURED_NONZERO)


class MeasurementError(ValueError):
    """A measurement asserted beyond what its liveness supports."""


@dataclass(frozen=True)
class Liveness:
    """Proof that the machinery capable of producing the value was running.

    Every field defaults to ``False``, so a caller who forgets to record a step
    gets ``NOT_RUN`` rather than a silent pass. Optimism is not the default.
    """

    process_started: bool = False
    runtime_started: bool = False
    subject_open_attempted: bool = False
    subject_open_succeeded: bool = False
    measurement_executed: bool = False
    artifact_written: bool = False

    #: Preconditions in the order they must hold. The first false one names the
    #: step that did not happen, which is what an operator actually needs.
    ORDER = ("process_started", "runtime_started", "subject_open_attempted",
             "subject_open_succeeded", "measurement_executed")

    def first_missing(self) -> str | None:
        for name in self.ORDER:
            if not getattr(self, name):
                return name
        return None

    @property
    def complete(self) -> bool:
        return self.first_missing() is None


@dataclass(frozen=True)
class MeasurementEnvelope:
    """One measurement, with the evidence that it was actually taken.

    ``value`` is not accepted on trust. It is admitted only when liveness is
    complete and the examined population is non-empty; otherwise the envelope
    reports why there is no answer and holds ``value = None``.
    """

    measurement: str
    liveness: Liveness
    value: Any = None
    items_examined: int | None = None
    expected_items: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def __post_init__(self) -> None:
        if not self.measurement:
            raise MeasurementError("a measurement must be named")
        if self.value is not None and not self.liveness.complete:
            raise MeasurementError(
                f"{self.measurement}: value {self.value!r} supplied while liveness is "
                f"incomplete (missing {self.liveness.first_missing()!r}). A value from a "
                f"process that did not run is the failure this type exists to prevent."
            )

    @property
    def status(self) -> Status:
        if not self.liveness.process_started:
            return Status.NOT_RUN
        if not self.liveness.subject_open_succeeded:
            # Started, then died or failed to open its subject. Distinguished
            # from NOT_RUN because the two need different operator responses.
            return Status.RUN_FAILED
        if not self.liveness.measurement_executed or self.value is None:
            return Status.RUN_LIVE_NO_MEASUREMENT
        if not self.items_examined:
            # A validator that examined nothing found no faults. That is not a
            # clean result; it is an empty one wearing a clean result's value.
            return Status.RUN_LIVE_NO_MEASUREMENT
        return Status.MEASURED_ZERO if _is_zero(self.value) else Status.MEASURED_NONZERO

    @property
    def is_evidence(self) -> bool:
        return self.status.is_evidence

    @property
    def population_complete(self) -> bool | None:
        """Whether every item expected was actually examined."""
        if self.expected_items is None or self.items_examined is None:
            return None
        return self.items_examined == self.expected_items

    def require_evidence(self) -> Any:
        """Return the value, or refuse. Use where a claim depends on it."""
        if not self.is_evidence:
            raise MeasurementError(
                f"{self.measurement}: status {self.status.value} — no value to report. "
                f"{'Missing step: ' + str(self.liveness.first_missing()) + '. ' if not self.liveness.complete else ''}"
                f"Report NO_EVIDENCE, never 0."
            )
        return self.value

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "measurement": self.measurement,
            "status": self.status.value,
            "liveness": {k: v for k, v in asdict(self.liveness).items()},
            "population": {"items_examined": self.items_examined,
                           "expected_items": self.expected_items,
                           "complete": self.population_complete},
            "value": self.value if self.is_evidence else None,
            "is_evidence": self.is_evidence,
            "evidence": self.evidence,
        }
        if self.note:
            d["note"] = self.note
        if not self.is_evidence:
            d["why_no_value"] = (
                f"liveness incomplete at {self.liveness.first_missing()!r}"
                if not self.liveness.complete
                else "measurement executed over an empty population"
            )
        return d

    def render(self) -> str:
        """One line for a human. Never prints a bare number without its status."""
        if self.is_evidence:
            pop = f" over {self.items_examined}" if self.items_examined is not None else ""
            return f"{self.measurement}: {self.value}{pop} [{self.status.value}]"
        return f"{self.measurement}: NO_EVIDENCE [{self.status.value}]"


def _is_zero(value: Any) -> bool:
    if isinstance(value, bool):
        return value is False
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, (list, tuple, set, dict, str)):
        return len(value) == 0
    return False


def not_run(measurement: str, note: str = "") -> MeasurementEnvelope:
    """The honest envelope for something that was never attempted."""
    return MeasurementEnvelope(measurement=measurement, liveness=Liveness(), note=note)


def write_envelopes(envelopes: list[MeasurementEnvelope], path: Any) -> Any:
    from pathlib import Path as _P

    p = _P(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([e.to_json() for e in envelopes], indent=2) + "\n")
    return p
