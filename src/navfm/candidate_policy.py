"""The intervention set, owned by the contract rather than by whichever script asks.

Five consumers independently generated probe candidates: a production audit
producing two lateral directions, a diagnostic producing four, a dense harness
producing one or two, a causality harness producing one at an adaptive standoff,
and an oracle probing the robot's own footprint. All of them recorded results
under one behavioural contract digest, so measurements of *different physical
experiments* were compared as though equivalent. That is not an implementation
slip; it is a gap in what the contract specified.

    A measurement contract defines the intervention as well as the
    interpretation.

A contract that says only how an observation is judged cannot make two
instruments comparable. Clean accounting cannot rescue an experiment that asks
the wrong physical question -- and a tidy ``0/8`` from a two-direction policy
would have been more dangerous than the ``-1`` that exposed the accounting bug,
because an impossible number announces itself while a plausible one does not.

So generation lives here, once, and every consumer calls it. The policy is
role-specific because a floor, a wall and the robot's own footprint are not
interrogated the same way, and it is finite because an intervention set that can
grow is a search that stops when the answer looks right.

Controls are first-class rather than script-local. A harness that needs a
deliberately wrong intervention -- a shared world origin, a non-production
standoff -- asks for it by name, so the wrongness is declared and digested
instead of reimplemented. A production consumer cannot reach one by default.

Nothing here can see a query outcome. Inputs are geometry, role and frozen
configuration; a candidate set is identical whatever the physics later returns,
which the observation-independence regressions assert structurally.

Expected semantics are frozen ahead of this implementation in
``gates/scenes/candidate_policy_expected_semantics.json``; the tests compare
against that record rather than recomputing from this module.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

POLICY_NAME = "navfm.candidate_policy"

#: Version 2 froze a support probe length of 1.00 m that matched the robot-pose
#: oracle's constant rather than the target-local probe every archived audit
#: actually fired at 1.50 m, and it could express neither the footprint role nor
#: the harness controls. Version 3 corrects the range against that evidence and
#: adds both. Digest 7136993d04151369 is retired and never reused.
POLICY_VERSION = 3

RETIRED_POLICY_DIGESTS = ("7136993d04151369",)


class PolicyError(ValueError):
    """A role, variant and subject that do not describe a real experiment."""


class Role(str, Enum):
    """What kind of thing is being interrogated. Roles are not interchangeable."""

    BLOCKER = "BLOCKER"
    SUPPORT = "SUPPORT"
    FOOTPRINT_SUPPORT = "FOOTPRINT_SUPPORT"


class Variant(str, Enum):
    """Which declared intervention is being run.

    ``DEFAULT`` is the only variant a production consumer may use. The controls
    exist so a harness can run a deliberately non-production intervention
    without inventing its own physics -- the variant is named in the policy and
    therefore in the digest, so a control can never be mistaken for a result.
    """

    DEFAULT = "DEFAULT"
    CAUSALITY_CONTROL = "CAUSALITY_CONTROL"
    SHARED_ORIGIN_CONTROL = "SHARED_ORIGIN_CONTROL"


@dataclass(frozen=True)
class Aabb:
    """Axis-aligned bounds of a declared target. The subject of a target role."""

    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    @property
    def centre(self) -> tuple[float, float, float]:
        return tuple((self.minimum[i] + self.maximum[i]) / 2 for i in range(3))  # type: ignore[return-value]

    def span(self, axis: int) -> float:
        return self.maximum[axis] - self.minimum[axis]


@dataclass(frozen=True)
class Pose:
    """A robot query pose. The subject of ``FOOTPRINT_SUPPORT``.

    Deliberately not an ``Aabb``: this role declares no target and adjudicates no
    collider identity, so giving it target bounds would imply a question it does
    not ask.
    """

    x: float
    y: float
    z_start: float


Subject = Aabb | Pose


@dataclass(frozen=True)
class BlockerPolicy:
    """Finite target-local lateral faces for a body that obstructs the robot.

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
    bears weight. Every parameter is read off the target-local support probe that
    actually executed: origin half a metre above the surface's own top face,
    straight down, 1.50 m of reach -- the value recorded in every SUPPORT row of
    the Office, Hospital and Warehouse audits.
    """

    faces: tuple[str, ...] = ("-Z",)
    start_height_m: float = 0.50
    probe_length_m: float = 1.50


@dataclass(frozen=True)
class FootprintPolicy:
    """Downward interrogation of the robot's own footprint at a pose.

    A different question from ``SUPPORT``: not "does this surface bear weight"
    but "is the robot supported where it stands". Half extents are the measured
    Yahboom collider footprint and carry no inflation -- a safety margin, if ever
    wanted, is declared as footprint plus planning margin and never by
    substituting a larger unexplained robot dimension.

    Whether the samples together constitute support -- all of them hitting,
    within a height tolerance -- is adjudication and stays downstream.
    """

    faces: tuple[str, ...] = ("-Z",)
    half_extents_m: tuple[float, float] = (0.1175, 0.0975)
    probe_length_m: float = 1.00


@dataclass(frozen=True)
class SharedOriginPolicy:
    """The retired construction, kept representable so it stays usable as a control.

    Every ray leaves one world origin along +X. It is what produced twelve probes
    striking the same wall at an identical distance while declaring twelve
    different targets, and it is preserved for exactly that reason: a negative
    control that no longer exists cannot demonstrate anything.
    """

    origin_x: float = 0.0
    direction: tuple[float, float, float] = (1.0, 0.0, 0.0)
    max_range_m: float = 40.0


@dataclass(frozen=True)
class Policy:
    """The complete intervention specification: everything, and only, the physics.

    It fixes what is asked -- role, origin, direction, standoff, range,
    population, identity, ordering. It fixes nothing about the answer: whether a
    query hits, which collider returns, whether that collider is correct, whether
    an experiment passes. Those belong downstream and are not representable here.
    """

    variant: Variant = Variant.DEFAULT
    blocker: BlockerPolicy = BlockerPolicy()
    support: SupportPolicy = SupportPolicy()
    footprint: FootprintPolicy = FootprintPolicy()
    shared_origin: SharedOriginPolicy = SharedOriginPolicy()

    def to_json(self) -> dict[str, Any]:
        return {
            "policy_name": POLICY_NAME,
            "policy_version": POLICY_VERSION,
            "variant": self.variant.value,
            "blocker": {"faces": list(self.blocker.faces),
                        "standoff_m": self.blocker.standoff_m,
                        "margin_m": self.blocker.margin_m},
            "support": {"faces": list(self.support.faces),
                        "start_height_m": self.support.start_height_m,
                        "probe_length_m": self.support.probe_length_m},
            "footprint": {"faces": list(self.footprint.faces),
                          "half_extents_m": list(self.footprint.half_extents_m),
                          "probe_length_m": self.footprint.probe_length_m},
            "shared_origin": {"origin_x": self.shared_origin.origin_x,
                              "direction": list(self.shared_origin.direction),
                              "max_range_m": self.shared_origin.max_range_m},
        }

    def digest(self) -> str:
        """Provenance for the policy itself.

        A result recording only a contract digest is incomplete: two runs can
        share a contract and differ in the physical question asked. Every
        intervention parameter above feeds this, so a policy change cannot hide
        under an unchanged contract label.
        """
        return hashlib.sha256(
            json.dumps(self.to_json(), sort_keys=True).encode()).hexdigest()[:16]


DEFAULT_POLICY = Policy()

#: Retained for callers that read the production parameters directly.
BLOCKER = DEFAULT_POLICY.blocker
SUPPORT = DEFAULT_POLICY.support
FOOTPRINT = DEFAULT_POLICY.footprint


def causality_control(standoff_m: float) -> Policy:
    """A blocker intervention at a declared non-production standoff.

    The four-face population is unchanged, so the standoff is the only thing that
    varies and the harness measures what it means to measure. 0.50 / 1.00 / 1.50 m
    are the values the contract's state-discrimination property was proved at.
    """
    if standoff_m <= 0.0:
        raise PolicyError(f"causality control needs a positive standoff, got {standoff_m!r}")
    return replace(
        DEFAULT_POLICY,
        variant=Variant.CAUSALITY_CONTROL,
        blocker=replace(DEFAULT_POLICY.blocker, standoff_m=standoff_m),
    )


def shared_origin_control(max_range_m: float) -> Policy:
    """The retired shared-origin intervention, requested explicitly or not at all."""
    if max_range_m <= 0.0:
        raise PolicyError(f"shared-origin control needs a positive range, got {max_range_m!r}")
    return replace(
        DEFAULT_POLICY,
        variant=Variant.SHARED_ORIGIN_CONTROL,
        shared_origin=replace(DEFAULT_POLICY.shared_origin, max_range_m=max_range_m),
    )


def policy_digest(policy: Policy = DEFAULT_POLICY) -> str:
    """The digest of a policy; by default, the production one."""
    return policy.digest()


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
    policy: Policy = DEFAULT_POLICY
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
            "variant": self.policy.variant.value,
            "candidate_policy_digest": self.policy.digest(),
            "candidate_count": len(self.candidates),
            "valid_candidate_count": len(self.valid_candidates),
            "candidate_set_digest": self.digest,
            "candidates": [c.to_json() for c in self.candidates],
        }


#: (face, axis, whether the origin sits on the max side of that axis)
_BLOCKER_FACES: tuple[tuple[str, int, bool], ...] = (
    ("+X", 0, False), ("-X", 0, True), ("+Y", 1, False), ("-Y", 1, True),
)

#: (label, dx sign, dy sign) -- centre first, then the four corners. Ordering is
#: semantically significant wherever a consumer takes the first usable candidate.
_FOOTPRINT_SAMPLES: tuple[tuple[str, float, float], ...] = (
    ("C", 0.0, 0.0), ("PP", 1.0, 1.0), ("PM", 1.0, -1.0), ("MP", -1.0, 1.0), ("MM", -1.0, -1.0),
)

_TARGET_ROLES = (Role.BLOCKER, Role.SUPPORT)
_VARIANT_ROLES: dict[Variant, tuple[Role, ...]] = {
    Variant.DEFAULT: (Role.BLOCKER, Role.SUPPORT, Role.FOOTPRINT_SUPPORT),
    Variant.CAUSALITY_CONTROL: (Role.BLOCKER,),
    Variant.SHARED_ORIGIN_CONTROL: (Role.BLOCKER,),
}


def _candidate_id(target_id: str, role: Role, label: str, policy: Policy) -> str:
    """Identity carries the policy, so two interventions cannot share evidence."""
    return f"{target_id}#{role.value}#{label}#{policy.digest()}"


def generate_candidates(target_id: str, role: Role, subject: Subject,
                        *, policy: Policy = DEFAULT_POLICY) -> CandidateSet:
    """The one generator. Audits, diagnostics, harnesses and oracles all call this.

    Deterministic in target id, role, subject geometry and policy, so identical
    inputs yield identical candidate IDs, origins, directions, ranges and
    ordering -- which is what makes two consumers' results comparable at all.
    """
    allowed = _VARIANT_ROLES[policy.variant]
    if role not in allowed:
        raise PolicyError(
            f"variant {policy.variant.value} does not define an intervention for role "
            f"{role.value}; it applies to {', '.join(r.value for r in allowed)}")
    if role in _TARGET_ROLES and not isinstance(subject, Aabb):
        raise PolicyError(f"role {role.value} interrogates a declared target and needs Aabb bounds")
    if role is Role.FOOTPRINT_SUPPORT and not isinstance(subject, Pose):
        raise PolicyError(f"role {role.value} interrogates a robot pose and needs a Pose")

    if isinstance(subject, Pose):
        return _footprint_set(target_id, subject, policy)
    if role is Role.SUPPORT:
        return _support_set(target_id, subject, policy)
    if policy.variant is Variant.SHARED_ORIGIN_CONTROL:
        return _shared_origin_set(target_id, subject, policy)
    return _blocker_set(target_id, subject, policy)


def _blocker_set(target_id: str, box: Aabb, policy: Policy) -> CandidateSet:
    cfg, centre = policy.blocker, box.centre
    out: list[Candidate] = []
    for face, axis, from_max in _BLOCKER_FACES:
        span = box.span(axis)
        origin_l = list(centre)
        origin_l[axis] = ((box.maximum[axis] + cfg.standoff_m) if from_max
                          else (box.minimum[axis] - cfg.standoff_m))
        direction = [0.0, 0.0, 0.0]
        direction[axis] = -1.0 if from_max else 1.0
        # A degenerate span cannot be interrogated across that axis; recorded as
        # an invalid candidate rather than dropped, so the finite set stays a
        # fixed size and its digest stays comparable across targets.
        valid = span > 1e-6
        out.append(Candidate(
            candidate_id=_candidate_id(target_id, Role.BLOCKER, face, policy),
            target_id=target_id, role=Role.BLOCKER, face=face,
            origin=(origin_l[0], origin_l[1], origin_l[2]),
            direction=(direction[0], direction[1], direction[2]),
            max_range=cfg.standoff_m + span + cfg.margin_m,
            valid=valid,
            invalid_reason="" if valid else f"degenerate extent on axis {axis}"))
    return CandidateSet(target_id, Role.BLOCKER, tuple(out), policy)


def _support_set(target_id: str, box: Aabb, policy: Policy) -> CandidateSet:
    cfg, centre = policy.support, box.centre
    return CandidateSet(target_id, Role.SUPPORT, (Candidate(
        candidate_id=_candidate_id(target_id, Role.SUPPORT, "-Z", policy),
        target_id=target_id, role=Role.SUPPORT, face="-Z",
        origin=(centre[0], centre[1], box.maximum[2] + cfg.start_height_m),
        direction=(0.0, 0.0, -1.0), max_range=cfg.probe_length_m),), policy)


def _footprint_set(target_id: str, pose: Pose, policy: Policy) -> CandidateSet:
    cfg = policy.footprint
    hx, hy = cfg.half_extents_m
    out = [Candidate(
        candidate_id=_candidate_id(target_id, Role.FOOTPRINT_SUPPORT, label, policy),
        target_id=target_id, role=Role.FOOTPRINT_SUPPORT, face="-Z",
        origin=(pose.x + sx * hx, pose.y + sy * hy, pose.z_start),
        direction=(0.0, 0.0, -1.0), max_range=cfg.probe_length_m)
        for label, sx, sy in _FOOTPRINT_SAMPLES]
    return CandidateSet(target_id, Role.FOOTPRINT_SUPPORT, tuple(out), policy)


def _shared_origin_set(target_id: str, box: Aabb, policy: Policy) -> CandidateSet:
    cfg, centre = policy.shared_origin, box.centre
    return CandidateSet(target_id, Role.BLOCKER, (Candidate(
        candidate_id=_candidate_id(target_id, Role.BLOCKER, "SHARED+X", policy),
        target_id=target_id, role=Role.BLOCKER, face="SHARED+X",
        origin=(cfg.origin_x, centre[1], centre[2]),
        direction=cfg.direction, max_range=cfg.max_range_m),), policy)


def provenance(effective_contract_digest: str, policy: Policy = DEFAULT_POLICY) -> dict[str, Any]:
    """What every behavioural artefact must record alongside its numbers."""
    return {
        "policy_name": POLICY_NAME,
        "policy_version": POLICY_VERSION,
        "candidate_policy_digest": policy.digest(),
        "variant": policy.variant.value,
        "effective_contract_digest": effective_contract_digest,
        "blocker_faces": list(policy.blocker.faces),
        "support_faces": list(policy.support.faces),
        "footprint_faces": list(policy.footprint.faces),
        "retired_policy_digests": list(RETIRED_POLICY_DIGESTS),
        "note": ("a result recording only a contract digest is incomplete provenance; "
                 "two runs can share a contract and ask different physical questions"),
    }
