"""Can this intervention isolate its declared target -- decided before the query.

A probe reported eight Hospital walls as geometrically reachable and then hit a
different object five times. Reachability answered "can I aim at that region";
the question that mattered was "will *this* target be what answers". Identity
checking cannot repair that, because identity runs after an intervention that
never isolated anything.

So targetability is a property of the intervention, decided from geometry alone:

    intervention geometry -> CAUSAL_TARGETABILITY -> frozen -> query -> observation

never

    query -> did it hit the target? -> yes, so it was targetable

The second is circular, and it is easy to write by accident. The defence here is
structural rather than disciplinary: :class:`TargetabilityInput` has no field for
a hit, a collider or a distance, so a decision function taking one *cannot*
consult the observation. A leak would have to change the type signature, which a
regression asserts.

The state set is deliberately not boolean. ``TARGET_NOT_ISOLATABLE`` must be
reachable, because a gate that only ever finds a working direction is a search
procedure that terminates when the answer looks right -- an adequacy test has to
be able to say no. Candidate directions come from a fixed rule over the target's
own geometry, and the set is finite and frozen before any query runs.

Where conservative geometry cannot order the interactions, the answer is
``TARGET_AMBIGUOUS`` rather than isolatable. Pessimism costs a discarded probe;
optimism costs a false claim about a scene.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Targetability(str, Enum):
    """Why an intervention can or cannot isolate its declared target."""

    TARGET_ISOLATABLE = "TARGET_ISOLATABLE"
    TARGET_OCCLUDED = "TARGET_OCCLUDED"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    TARGET_NOT_ISOLATABLE = "TARGET_NOT_ISOLATABLE"
    INVALID_GEOMETRY = "INVALID_GEOMETRY"
    NO_EVIDENCE = "NO_EVIDENCE"

    @property
    def probative(self) -> bool:
        """Only an isolatable intervention may yield a target-level verdict."""
        return self is Targetability.TARGET_ISOLATABLE


@dataclass(frozen=True)
class Interval:
    """Where along a ray a body is expected to be met. Conservative bounds."""

    enter: float
    exit: float

    def precedes(self, other: Interval, margin: float) -> bool:
        return self.exit + margin <= other.enter

    def overlaps(self, other: Interval) -> bool:
        return not (self.exit <= other.enter or other.exit <= self.enter)


@dataclass(frozen=True)
class TargetabilityInput:
    """Everything the decision may see -- and nothing it may not.

    There is deliberately no ``actual_hit``, ``actual_collider``,
    ``identity_match`` or ``distance`` field. The decision cannot consult the
    observation it exists to qualify, because the type does not carry it. This is
    what makes the pre-query ordering an invariant rather than a convention.
    """

    declared_target: str
    origin: tuple[float, float, float]
    direction: tuple[float, float, float]
    max_range: float
    #: Where the declared target is expected along this ray, or None if the ray
    #: does not meet it at all.
    target_interval: Interval | None
    #: Structurally distinct bodies expected along the ray: (path, interval).
    competing: tuple[tuple[str, Interval], ...] = ()
    origin_inside: tuple[str, ...] = ()
    isolation_margin: float = 0.02

    def digest(self) -> str:
        return hashlib.sha256(json.dumps({
            "target": self.declared_target, "origin": list(self.origin),
            "direction": list(self.direction), "range": self.max_range,
            "target_interval": [self.target_interval.enter, self.target_interval.exit]
            if self.target_interval else None,
            "competing": [[p, [i.enter, i.exit]] for p, i in self.competing],
            "origin_inside": list(self.origin_inside),
        }, sort_keys=True).encode()).hexdigest()[:16]


def decide(inp: TargetabilityInput) -> tuple[Targetability, str]:
    """Classify one candidate intervention. Geometry only."""
    if inp.target_interval is None:
        return (Targetability.INVALID_GEOMETRY,
                "the ray does not meet the declared target's geometry at all")
    if inp.origin_inside:
        # Starting inside another body means the first responder is that body,
        # whatever the aim.
        return (Targetability.TARGET_OCCLUDED,
                f"intervention begins inside competing geometry: {inp.origin_inside[0]}")
    if inp.target_interval.enter > inp.max_range:
        return (Targetability.INVALID_GEOMETRY, "target lies beyond the declared range")

    nearer = [(p, iv) for p, iv in inp.competing
              if iv.precedes(inp.target_interval, inp.isolation_margin)]
    if nearer:
        return (Targetability.TARGET_OCCLUDED,
                f"{nearer[0][0]} is expected to respond before the declared target")
    straddling = [(p, iv) for p, iv in inp.competing if iv.overlaps(inp.target_interval)]
    if straddling:
        # Cannot order the two responses conservatively, so the query would not
        # be probative about either. Ambiguity is not isolation.
        return (Targetability.TARGET_AMBIGUOUS,
                f"{straddling[0][0]} overlaps the target interval; ordering unresolved")
    return (Targetability.TARGET_ISOLATABLE,
            "no structurally distinct body is expected to respond before the target")


@dataclass(frozen=True)
class TargetabilityDecision:
    """A frozen pre-query decision over a finite candidate set."""

    declared_target: str
    state: Targetability
    reason: str
    chosen: TargetabilityInput | None
    candidates: tuple[TargetabilityInput, ...]
    per_candidate: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def candidate_digest(self) -> str:
        """Freezes the candidate set, so directions cannot be added after a
        query disappoints."""
        return hashlib.sha256(
            "|".join(c.digest() for c in self.candidates).encode()).hexdigest()[:16]

    def to_json(self) -> dict[str, Any]:
        return {
            "declared_target": self.declared_target,
            "causal_targetability": self.state.value,
            "reason": self.reason,
            "probative": self.state.probative,
            "candidates_considered": len(self.candidates),
            "candidate_digest": self.candidate_digest,
            "per_candidate": [{"digest": d, "state": s} for d, s in self.per_candidate],
            "chosen_origin": list(self.chosen.origin) if self.chosen else None,
            "chosen_direction": list(self.chosen.direction) if self.chosen else None,
        }


def choose(candidates: list[TargetabilityInput]) -> TargetabilityDecision:
    """Decide over a finite, pre-generated candidate set.

    Termination is structural: the set is fixed before this runs and is never
    extended. If no candidate isolates the target the answer is
    ``TARGET_NOT_ISOLATABLE`` -- the gate says no rather than looking further.
    """
    if not candidates:
        return TargetabilityDecision("", Targetability.NO_EVIDENCE,
                                     "no candidate interventions were generated", None, ())
    target = candidates[0].declared_target
    results = [(c, *decide(c)) for c in candidates]
    per = tuple((c.digest(), st.value) for c, st, _ in results)
    for c, st, why in results:
        if st is Targetability.TARGET_ISOLATABLE:
            return TargetabilityDecision(target, st, why, c, tuple(candidates), per)
    # Report the least-bad reason, without ever promoting it to isolatable.
    for want in (Targetability.TARGET_AMBIGUOUS, Targetability.TARGET_OCCLUDED,
                 Targetability.INVALID_GEOMETRY):
        for _c, st, why in results:
            if st is want:
                return TargetabilityDecision(
                    target, Targetability.TARGET_NOT_ISOLATABLE,
                    f"no candidate isolates the target; nearest failure: {why}",
                    None, tuple(candidates), per)
    return TargetabilityDecision(target, Targetability.TARGET_NOT_ISOLATABLE,
                                 "no candidate isolates the target", None,
                                 tuple(candidates), per)
