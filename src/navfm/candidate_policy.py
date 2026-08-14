"""The intervention set, owned by the contract rather than by whichever script asks.

Three consumers independently generated probe candidates: an audit producing two
directions, a diagnostic producing four, and a regression harness producing one
or two. All three recorded results under one behavioural contract digest, so
measurements of *different physical experiments* were compared as though
equivalent. That is not an implementation slip; it is a gap in what the contract
specified.

    A measurement contract defines the intervention as well as the
    interpretation.

A contract that says only how an observation is judged cannot make two
instruments comparable. Clean accounting cannot rescue an experiment that asks
the wrong physical question -- and a tidy ``0/8`` from a two-direction policy
would have been more dangerous than the ``-1`` that exposed the accounting bug,
because an impossible number announces itself while a plausible one does not.

So generation lives here, once, and every consumer calls it. The policy is
role-specific because a floor and a wall are not interrogated the same way, and
it is finite because an intervention set that can grow is a search that stops
when the answer looks right.

Nothing in this module can see a query outcome. Its inputs are geometry, role and
frozen configuration; a candidate set is therefore identical whatever the physics
later returns, which the parity and observation-independence regressions assert.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

POLICY_NAME = "navfm.candidate_policy"
POLICY_VERSION = 2


class Role(str, Enum):
    """What kind of thing is being interrogated. Roles are not interchangeable."""

    BLOCKER = "BLOCKER"
    SUPPORT = "SUPPORT"


@dataclass(frozen=True)
class BlockerPolicy:
    """Finite target-local faces for a body that obstructs the robot.

    Four faces, because the Hospital isolation diagnostic showed that a target
    unreachable across one axis is often cleanly reachable across the other, and
    a two-face policy silently reported those as untargetable. Vertical faces are
    excluded pending separate justification -- a ceiling approach is rarely a
    navigation-relevant question and would need its own evidence.
    """

    faces: tuple[str, ...] = ("+X", "-X", "+Y", "-Y")
    standoff_m: float = 0.30
    margin_m: float = 0.15


@dataclass(frozen=True)
class SupportPolicy:
    """Downward interrogation of a surface the robot would stand on.

    Deliberately not the blocker set. A support surface is met from above, and
    approaching a floor edge-on asks whether its rim obstructs, not whether it
    bears weight. Derived from the support probe already in use rather than
    invented here: probes drop onto the surface's own top face from a fixed
    height above it.
    """

    faces: tuple[str, ...] = ("-Z",)
    start_height_m: float = 0.50
    probe_length_m: float = 1.00


@dataclass(frozen=True)
class Candidate:
    """One planned intervention. Carries no observation and cannot acquire one."""

    candidate_id: str
    target_id: str
    role: Role
    face: str
    origin: tuple[float, float, float]
    direction: tuple[float, float, float]
    max_range: float
    valid: bool = True
    invalid_reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id, "target_id": self.target_id,
            "role": self.role.value, "face": self.face,
            "origin": list(self.origin), "direction": list(self.direction),
            "max_range": round(self.max_range, 6),
            "valid": self.valid, "invalid_reason": self.invalid_reason,
        }


@dataclass(frozen=True)
class CandidateSet:
    """A finite, frozen, digestible intervention set."""

    target_id: str
    role: Role
    candidates: tuple[Candidate, ...]
    policy_version: int = POLICY_VERSION

    @property
    def valid_candidates(self) -> tuple[Candidate, ...]:
        return tuple(c for c in self.candidates if c.valid)

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(
            [c.to_json() for c in self.candidates], sort_keys=True).encode()).hexdigest()[:16]

    def to_json(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id, "role": self.role.value,
            "policy_name": POLICY_NAME, "policy_version": self.policy_version,
            "candidate_count": len(self.candidates),
            "valid_candidate_count": len(self.valid_candidates),
            "candidate_set_digest": self.digest,
            "candidates": [c.to_json() for c in self.candidates],
        }


BLOCKER = BlockerPolicy()
SUPPORT = SupportPolicy()


def policy_digest() -> str:
    """Provenance for the policy itself.

    A result recording only a contract digest is incomplete: two runs can share a
    contract and differ in the physical question asked. Changing any parameter
    here changes this digest, so a policy change cannot hide under an unchanged
    contract label.
    """
    return hashlib.sha256(json.dumps({
        "name": POLICY_NAME, "version": POLICY_VERSION,
        "blocker": {"faces": list(BLOCKER.faces), "standoff_m": BLOCKER.standoff_m,
                    "margin_m": BLOCKER.margin_m},
        "support": {"faces": list(SUPPORT.faces), "start_height_m": SUPPORT.start_height_m,
                    "probe_length_m": SUPPORT.probe_length_m},
    }, sort_keys=True).encode()).hexdigest()[:16]


#: (face, axis, whether the origin sits on the max side of that axis)
_BLOCKER_FACES: tuple[tuple[str, int, bool], ...] = (
    ("+X", 0, False), ("-X", 0, True), ("+Y", 1, False), ("-Y", 1, True),
)


def generate_candidates(target_id: str, role: Role,
                        bounds_min: tuple[float, float, float],
                        bounds_max: tuple[float, float, float]) -> CandidateSet:
    """The one generator. Both diagnostics and audits call this.

    Deterministic in target geometry and role, so identical inputs yield
    identical candidate IDs, origins, directions, ranges and ordering -- which is
    what makes two consumers' results comparable at all.
    """
    mn, mx = bounds_min, bounds_max
    centre = tuple((mn[i] + mx[i]) / 2 for i in range(3))
    out: list[Candidate] = []

    if role is Role.SUPPORT:
        origin = (centre[0], centre[1], mx[2] + SUPPORT.start_height_m)
        out.append(Candidate(
            candidate_id=f"{target_id}#SUPPORT#-Z", target_id=target_id, role=role,
            face="-Z", origin=origin, direction=(0.0, 0.0, -1.0),
            max_range=SUPPORT.probe_length_m))
        return CandidateSet(target_id, role, tuple(out))

    for face, axis, from_max in _BLOCKER_FACES:
        span = mx[axis] - mn[axis]
        origin_l = list(centre)
        origin_l[axis] = ((mx[axis] + BLOCKER.standoff_m) if from_max
                          else (mn[axis] - BLOCKER.standoff_m))
        direction = [0.0, 0.0, 0.0]
        direction[axis] = -1.0 if from_max else 1.0
        # A degenerate span cannot be interrogated across that axis; recorded as
        # an invalid candidate rather than dropped, so the finite set stays a
        # fixed size and its digest stays comparable across targets.
        valid = span > 1e-6
        out.append(Candidate(
            candidate_id=f"{target_id}#BLOCKER#{face}", target_id=target_id, role=role,
            face=face, origin=(origin_l[0], origin_l[1], origin_l[2]),
            direction=(direction[0], direction[1], direction[2]),
            max_range=BLOCKER.standoff_m + span + BLOCKER.margin_m,
            valid=valid,
            invalid_reason="" if valid else f"degenerate extent on axis {axis}"))
    return CandidateSet(target_id, role, tuple(out))


def provenance(effective_contract_digest: str) -> dict[str, Any]:
    """What every behavioural artefact must record alongside its numbers."""
    return {
        "policy_name": POLICY_NAME,
        "policy_version": POLICY_VERSION,
        "candidate_policy_digest": policy_digest(),
        "effective_contract_digest": effective_contract_digest,
        "blocker_faces": list(BLOCKER.faces),
        "support_faces": list(SUPPORT.faces),
        "note": ("a result recording only a contract digest is incomplete provenance; "
                 "two runs can share a contract and ask different physical questions"),
    }
