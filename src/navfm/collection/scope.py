"""BO-10 / E2 scope separation, enforced at the admission boundary.

`gates/BO10/bo10_e2_scope_declaration_20260907.md` freezes one decision: the
BO-10 compatibility trajectory is collected outside the preregistered E2
population and may never enter it. This module is the mechanism that makes that
true, rather than the sentence that asserts it.

Three properties, each bought with a failure mode:

**Declared, never inferred.** A manifest says what it is. Nothing here derives
eligibility from a path, a scene name, an episode count or a date.

**Undeclared is refused, not admitted.** A manifest carrying no scope block
raises. The tempting default is the other one — admit unless told otherwise —
and it is the FL-019 shape exactly: a missing fact consumed as a benign value.
A future selection step that globs ``runs/`` would then pull a compatibility
trajectory into an estimator, and the number it produced would carry no record
that this had happened.

**Inconsistency is refused, not resolved.** ``purpose`` and ``e2_eligible`` must
agree. A manifest claiming ``BO10_FRAMEWORK_COMPATIBILITY`` with
``e2_eligible=True`` is not repaired to one reading or the other; it raises,
because the two fields disagreeing means the writer did not know what it was
recording.

    >>> assert_e2_admissible(bo10_scope().to_manifest_fields())
    Traceback (most recent call last):
    E2ScopeViolation: ...
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

__all__ = [
    "BO10_SCOPE_DECLARATION",
    "BO10_SCOPE_DECLARATION_SHA256",
    "CollectionPurpose",
    "CollectionScope",
    "E2Population",
    "E2ScopeViolation",
    "ScopeDeclarationError",
    "assert_e2_admissible",
    "authorise_g2_acknowledgement",
    "bo10_scope",
    "scope_of",
    "select_e2_population",
]

#: The frozen declaration this module enforces. Pinned by digest so that editing
#: the declaration without re-freezing it fails a test rather than silently
#: changing what the code permits.
BO10_SCOPE_DECLARATION = Path("gates/BO10/bo10_e2_scope_declaration_20260907.json")
BO10_SCOPE_DECLARATION_SHA256 = (
    "7bc18794bf6242b2652acc597f37ae680f126242bfeb5907d94592bc055e47ec"
)

BO10_EXCLUSION_REASON = (
    "compatibility trajectory collected outside the preregistered E2 population"
)


class CollectionPurpose(enum.Enum):
    """Why a trajectory was collected. Declared by the collector, never guessed."""

    #: The BO-10 compatibility trajectory: pipeline and loader proof only.
    BO10_FRAMEWORK_COMPATIBILITY = "BO10_FRAMEWORK_COMPATIBILITY"

    #: A cell of the preregistered E2 2x2 matrix. Not authorised yet -- the G2
    #: block still stands -- but the value exists so that E2 admission is a
    #: positive match rather than "not BO-10".
    E2_REGISTERED_CELL = "E2_REGISTERED_CELL"

    @property
    def e2_eligible(self) -> bool:
        """Does this purpose belong to the E2 statistical population?"""
        return self is CollectionPurpose.E2_REGISTERED_CELL

    @classmethod
    def parse(cls, value: str) -> CollectionPurpose:
        try:
            return cls(value)
        except ValueError:
            valid = ", ".join(p.value for p in cls)
            raise ScopeDeclarationError(
                f"unknown collection purpose {value!r}; valid purposes: {valid}"
            ) from None


class ScopeDeclarationError(RuntimeError):
    """A manifest's scope block is absent, malformed or self-contradictory."""


class E2ScopeViolation(RuntimeError):
    """A trajectory outside the E2 population was offered to an E2 consumer."""


@dataclasses.dataclass(frozen=True)
class CollectionScope:
    """The scope block a collection manifest carries."""

    purpose: CollectionPurpose
    e2_eligible: bool
    e2_exclusion_reason: str | None = None
    declaration_path: str | None = None
    declaration_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.e2_eligible != self.purpose.e2_eligible:
            raise ScopeDeclarationError(
                f"scope is self-contradictory: purpose {self.purpose.value} implies "
                f"e2_eligible={self.purpose.e2_eligible}, manifest says "
                f"e2_eligible={self.e2_eligible}. Refusing rather than choosing one "
                "reading: the disagreement means the writer did not know what it recorded."
            )
        if not self.e2_eligible and not self.e2_exclusion_reason:
            raise ScopeDeclarationError(
                "an excluded trajectory must record why it is excluded; a bare "
                "e2_eligible=false loses the reason a reader needs to check the exclusion"
            )

    def to_manifest_fields(self) -> dict[str, Any]:
        """The fields written into ``collection_manifest.json``."""
        block: dict[str, Any] = {
            "purpose": self.purpose.value,
            "e2_eligible": self.e2_eligible,
        }
        if self.e2_exclusion_reason:
            block["e2_exclusion_reason"] = self.e2_exclusion_reason
        if self.declaration_path:
            block["scope_declaration"] = self.declaration_path
        if self.declaration_sha256:
            block["scope_declaration_sha256"] = self.declaration_sha256
        return block


def bo10_scope(
    declaration_path: str | Path | None = None,
    declaration_sha256: str | None = None,
) -> CollectionScope:
    """The BO-10 compatibility scope: excluded from E2 by construction."""
    return CollectionScope(
        purpose=CollectionPurpose.BO10_FRAMEWORK_COMPATIBILITY,
        e2_eligible=False,
        e2_exclusion_reason=BO10_EXCLUSION_REASON,
        declaration_path=(str(declaration_path) if declaration_path else None),
        declaration_sha256=declaration_sha256,
    )


def scope_of(manifest: Mapping[str, Any]) -> CollectionScope:
    """Read a manifest's scope block, refusing anything short of a declaration.

    ``purpose`` and ``e2_eligible`` are both required. Deriving one from the
    other would mean a manifest could carry a scope it never stated.
    """
    if "purpose" not in manifest:
        raise ScopeDeclarationError(
            "manifest declares no collection purpose. An undeclared trajectory is "
            "refused rather than admitted: absence of a scope block is not evidence "
            "of E2 eligibility, and reading it as such is how a compatibility "
            "trajectory enters a statistical population."
        )
    if "e2_eligible" not in manifest:
        raise ScopeDeclarationError(
            "manifest declares a purpose but no e2_eligible field. Both are required; "
            "deriving one from the other would admit a scope the manifest never stated."
        )
    e2_eligible = manifest["e2_eligible"]
    if not isinstance(e2_eligible, bool):
        raise ScopeDeclarationError(
            f"e2_eligible must be a bool, got {type(e2_eligible).__name__} "
            f"({e2_eligible!r}); a truthy string would admit 'false'"
        )
    return CollectionScope(
        purpose=CollectionPurpose.parse(str(manifest["purpose"])),
        e2_eligible=e2_eligible,
        e2_exclusion_reason=manifest.get("e2_exclusion_reason"),
        declaration_path=manifest.get("scope_declaration"),
        declaration_sha256=manifest.get("scope_declaration_sha256"),
    )


def assert_e2_admissible(manifest: Mapping[str, Any], *, label: str = "trajectory") -> None:
    """Raise unless this trajectory belongs to the E2 statistical population.

    This is the mandatory negative control's subject: offering the BO-10
    manifest here must FAIL.
    """
    try:
        scope = scope_of(manifest)
    except ScopeDeclarationError as exc:
        raise E2ScopeViolation(f"{label} is not admissible to the E2 population: {exc}") from exc
    if not scope.e2_eligible:
        raise E2ScopeViolation(
            f"{label} is excluded from the E2 population by construction "
            f"(purpose={scope.purpose.value}, e2_eligible=false, reason: "
            f"{scope.e2_exclusion_reason}). It may not contribute to an E2 cell, "
            "estimator, tolerance decision, held-out evaluation, episode count, "
            "stopping decision, or effect-size claim."
        )


@dataclasses.dataclass(frozen=True)
class E2Population:
    """The result of filtering candidate trajectories for E2 admission."""

    admitted: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]

    @property
    def n_admitted(self) -> int:
        return len(self.admitted)

    @property
    def n_excluded(self) -> int:
        return len(self.excluded)

    def to_dict(self) -> dict[str, Any]:
        return {
            "admitted": list(self.admitted),
            "excluded": [{"id": i, "reason": r} for i, r in self.excluded],
            "n_admitted": self.n_admitted,
            "n_excluded": self.n_excluded,
        }


def select_e2_population(
    manifests: Iterable[tuple[str, Mapping[str, Any]]],
) -> E2Population:
    """Split candidate trajectories into the E2 population and its exclusions.

    Every exclusion is recorded with its reason. A filter that dropped rows
    silently would leave a population shaped by exclusions with no record of the
    shaping -- the case the standing red-team trigger 6 names.
    """
    admitted: list[str] = []
    excluded: list[tuple[str, str]] = []
    for traj_id, manifest in manifests:
        try:
            assert_e2_admissible(manifest, label=traj_id)
        except E2ScopeViolation as exc:
            excluded.append((traj_id, str(exc)))
        else:
            admitted.append(traj_id)
    return E2Population(admitted=tuple(admitted), excluded=tuple(excluded))


def authorise_g2_acknowledgement(
    declaration_path: str | Path,
    *,
    expected_sha256: str = BO10_SCOPE_DECLARATION_SHA256,
) -> CollectionScope:
    """Honour ``--acknowledge-g2-block`` only when bound to the frozen declaration.

    Returns the scope the acknowledgement was granted under, which the collector
    then stamps into the manifest. Raises otherwise -- an acknowledgement flag
    that can be passed on its own is a bypass with a comment attached.
    """
    path = Path(declaration_path)
    if not path.is_file():
        raise ScopeDeclarationError(
            f"--acknowledge-g2-block requires the frozen BO-10 scope declaration; "
            f"no file at {path}"
        )
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ScopeDeclarationError(
            f"scope declaration at {path} has digest {digest}, expected {expected_sha256}. "
            "The acknowledgement is bound to the declaration that authorised it; an "
            "edited declaration is a different authorisation and must be re-frozen."
        )
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScopeDeclarationError(f"scope declaration at {path} does not parse: {exc}") from exc

    purpose = CollectionPurpose.parse(str(record.get("purpose", {}).get("id", "")))
    if purpose is not CollectionPurpose.BO10_FRAMEWORK_COMPATIBILITY:
        raise ScopeDeclarationError(
            f"--acknowledge-g2-block is authorised for BO10_FRAMEWORK_COMPATIBILITY only; "
            f"this declaration authorises {purpose.value}"
        )
    if record.get("e2_status", {}).get("e2_eligible") is not False:
        raise ScopeDeclarationError(
            "the BO-10 scope declaration must state e2_eligible=false; refusing an "
            "acknowledgement whose declaration does not carry the exclusion it exists to impose"
        )
    return bo10_scope(declaration_path=str(path), declaration_sha256=digest)
