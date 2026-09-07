"""Was a probe's observation caused by the target it declared?

The retired rule asked whether raw hit distances differed across targets. Under
target-relative construction that question is not answerable: the origin is
placed at the declared target's own surface plus a fixed offset, so the expected
distance is that offset for *every* target and the target's world position and
size cancel identically. Correct probes are therefore expected to be perfectly
invariant, and it is wrong, missing or occluded geometry that creates diversity.
The rule fired on the correct case and on the historical defect alike, so it
separated neither.

What replaces it is a conjunction, and the conjunction is the point:

* **residual** -- the hit came from where the declared target's geometry says it
  should. This alone says nothing about *what* was hit.
* **identity** -- the returned collider is that target, or a preregistered owner
  of it. This alone says nothing about *where* the answer came from.

Either on its own is satisfiable by a defect. A shared slab beneath three
declared targets answers all three at a consistent wrong distance: identity
fails, residual fails, and the retired rule fires exactly as it does on a
perfectly correct stratum.

Intervention response -- vary the offset, watch the distance follow -- is not
evaluated here. It is a calibration control on the instrument rather than a
per-probe verdict, and it lives in the harnesses that can actually vary an
intervention.

The tolerance is not a free parameter. It defaults to the height-agreement
tolerance already frozen for support measurements, and is passed explicitly by
callers that have their own frozen value.

    >>> adjudicate(hit=True, returned_collider="/W/T", declared_target="/W/T",
    ...            observed_distance_m=0.5, expected_distance_m=0.5).probative
    True
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "DEFAULT_TOLERANCE_M",
    "VERDICT_LABEL",
    "ProbeVerdict",
    "Reason",
    "adjudicate",
    "geometric_residual",
    "verdict_label",
]

#: Height-agreement tolerance, frozen as SUPPORT_TOL_M in the PhysX footprint
#: oracle. A support residual is a height agreement along -Z, so this is the
#: existing convention rather than a new number. Its exact value is not load
#: bearing: measured correct residuals sit ~6 orders of magnitude inside it and
#: the smallest measured defect residual is ~5.5x outside it.
DEFAULT_TOLERANCE_M = 0.05


class Reason(str, Enum):
    """Why a probe is not probative. Terminal and mutually exclusive."""

    PROBATIVE = "PROBATIVE"
    NO_HIT = "NO_HIT"
    WRONG_IDENTITY = "WRONG_IDENTITY"
    GEOMETRY_INCONSISTENT = "GEOMETRY_INCONSISTENT"


@dataclass(frozen=True)
class ProbeVerdict:
    """The adjudication, with the two conditions kept separately visible.

    They are reported apart rather than collapsed into one flag because a probe
    that hit the right object at the wrong distance and one that hit the wrong
    object at the right distance are different defects, and a single boolean
    would make them indistinguishable in the archive.
    """

    probative: bool
    reason: Reason
    identity_ok: bool
    geometry_ok: bool
    residual_m: float | None
    tolerance_m: float


def geometric_residual(
    observed_distance_m: float | None, expected_distance_m: float
) -> float | None:
    """Observed minus expected. ``None`` when nothing was hit.

    A miss has no residual. Returning 0.0 for it would let "nothing answered"
    read as "answered perfectly", which is the substitution this whole module
    exists to prevent.
    """
    if observed_distance_m is None:
        return None
    return observed_distance_m - expected_distance_m


def _same_or_related_path(hit: str, declared: str) -> bool:
    """Exact prim, or a true path-segment ancestor/descendant of it.

    Both directions are intended and both are in use: USD often reports the
    collider as a child mesh of the declared prim, and the PHYSICAL_OWNER_IDENTITY
    fixture declares a leaf owned by an ancestor Xform.

    The boundary is the whole point. A raw ``startswith`` made a lexical prefix
    look like a hierarchy: with a declared ``/World/Scene/Geo_M3_DoorWall``, a
    prim named ``/World/Scene/Geo_M3_DoorWallLamp`` was accepted as that wall,
    and the probe was recorded probative. Requiring the separator turns "the name
    begins the same way" back into "is inside that prim". ``/Wall`` no longer
    matches ``/WallLamp``, ``/Wall2`` or ``/Wallpaper``, and still matches
    ``/Wall`` and ``/Wall/Section0``.
    """
    return (hit == declared
            or hit.startswith(declared + "/")
            or declared.startswith(hit + "/"))


def _identity_matches(
    returned_collider: str | None,
    declared_target: str,
    preregistered_owners: tuple[str, ...],
) -> bool:
    """Identity, not category: "some wall" is not "this wall".

    A preregistered owner is accepted only when it was declared in advance, so a
    shared collider cannot acquire ownership retrospectively by being the thing
    that happened to answer. Owners are matched by the same path relation as the
    target, which is what the causality harness's frozen PHYSICAL_OWNER_IDENTITY
    fixture already asserts.
    """
    if not returned_collider:
        return False
    return any(_same_or_related_path(returned_collider, d)
               for d in (declared_target, *preregistered_owners))


def adjudicate(
    *,
    hit: bool,
    returned_collider: str | None,
    declared_target: str,
    observed_distance_m: float | None,
    expected_distance_m: float,
    tolerance_m: float = DEFAULT_TOLERANCE_M,
    preregistered_owners: tuple[str, ...] = (),
) -> ProbeVerdict:
    """Adjudicate one probe. Probative requires identity AND geometry.

    Raw distance equality across probes is deliberately not an input. Two probes
    returning the same number is the expected outcome of two correct
    target-relative interventions, and asking that they differ is asking the
    construction to do something it cannot.
    """
    if tolerance_m <= 0:
        raise ValueError("tolerance_m must be positive; a zero tolerance admits nothing")

    residual = geometric_residual(observed_distance_m, expected_distance_m)

    if not hit or observed_distance_m is None:
        return ProbeVerdict(False, Reason.NO_HIT, False, False, residual, tolerance_m)

    identity_ok = _identity_matches(returned_collider, declared_target, preregistered_owners)
    geometry_ok = residual is not None and abs(residual) <= tolerance_m

    if not identity_ok:
        # Reported ahead of geometry: a hit on the wrong object is the stronger
        # finding, and a wrong object at a plausible distance is precisely the
        # shared-collider case that read as success for twelve probes once.
        return ProbeVerdict(False, Reason.WRONG_IDENTITY, False, geometry_ok,
                            residual, tolerance_m)
    if not geometry_ok:
        return ProbeVerdict(False, Reason.GEOMETRY_INCONSISTENT, True, False,
                            residual, tolerance_m)
    return ProbeVerdict(True, Reason.PROBATIVE, True, True, residual, tolerance_m)


#: Reason -> the verdict string scene audits record. Kept here rather than in a
#: consumer so the label set cannot drift from the reasons that produce it, and
#: so a consumer's disposition table can be checked for exhaustiveness against
#: something other than itself.
VERDICT_LABEL: dict[Reason, str] = {
    Reason.PROBATIVE: "PASS_CORRECT_CAUSE",
    Reason.WRONG_IDENTITY: "FAIL_WRONG_CAUSE",
    Reason.GEOMETRY_INCONSISTENT: "FAIL_GEOMETRY_INCONSISTENT",
    Reason.NO_HIT: "FAIL_NO_HIT",
}


def verdict_label(verdict: ProbeVerdict) -> str:
    """The recorded verdict string for an adjudication.

    Every ``Reason`` maps, so a new reason cannot silently fall through to a
    default that reads as an ordinary failure.
    """
    try:
        return VERDICT_LABEL[verdict.reason]
    except KeyError as exc:  # pragma: no cover - guarded by an exhaustiveness test
        raise ValueError(f"no verdict label for {verdict.reason}") from exc
