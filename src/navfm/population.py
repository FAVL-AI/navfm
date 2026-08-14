"""Probe populations counted by identity, so an impossible count cannot arise.

A behavioural audit reported ``probative_population = -1``. The cause was
arithmetic: ``reachable - non_probative``, where ``reachable`` counted probes
whose reachability stage passed and ``non_probative`` counted every probe
rejected at *any* stage. Subtracting counts drawn from different universes can
produce a number no population can have, and that number then fed a
representativeness gate.

So nothing here is reconstructed by subtraction. Every stage holds a set of probe
identities, populations are ``len(...)`` of those sets, and a probe carries
exactly one terminal disposition. A negative population is not guarded against --
it is unrepresentable, because a set has no negative cardinality.

Two invariants make the rest checkable:

**Nesting.** Each stage's survivors are a subset of the previous stage's. A probe
cannot be targetable without having been reachable, and the type refuses to
record that it was.

**Partition.** Every selected probe ends in exactly one terminal disposition, the
dispositions are pairwise disjoint, and their union is the selected set. If those
fail the audit reports ``ACCOUNTING_INVALID`` and refuses to adjudicate rather
than passing a suspect denominator downstream.

Representativeness reports its numerator and denominator explicitly. ``1/8`` and
``8/8`` are different evidential situations and a single percentage hides which
one you have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Disposition(str, Enum):
    """Where a probe finally landed. Exactly one per selected probe."""

    PROBATIVE = "PROBATIVE"
    NONPROBATIVE_UNREACHABLE = "NONPROBATIVE_UNREACHABLE"
    NONPROBATIVE_NOT_TARGETABLE = "NONPROBATIVE_NOT_TARGETABLE"
    NONPROBATIVE_AMBIGUOUS = "NONPROBATIVE_AMBIGUOUS"
    NONPROBATIVE_QUERY = "NONPROBATIVE_QUERY"
    NONPROBATIVE_INVARIANCE = "NONPROBATIVE_INVARIANCE"
    NO_EVIDENCE = "NO_EVIDENCE"


class AccountingError(ValueError):
    """The populations do not form a valid partition of the selected set."""


@dataclass(frozen=True)
class ProbePopulation:
    """Stage-by-stage survivor sets, counted by identity.

    The stages nest: selected -> reachable -> targetable -> fired -> adjudicated
    -> probative. Each is validated as a subset of its predecessor at
    construction, so an inconsistent pipeline fails where it is built rather than
    where its numbers are consumed.
    """

    selected: frozenset[str]
    reachable: frozenset[str] = field(default_factory=frozenset)
    targetable: frozenset[str] = field(default_factory=frozenset)
    fired: frozenset[str] = field(default_factory=frozenset)
    adjudicated: frozenset[str] = field(default_factory=frozenset)
    probative: frozenset[str] = field(default_factory=frozenset)
    dispositions: dict[str, Disposition] = field(default_factory=dict)

    #: Stage order, used for both the nesting check and error messages.
    STAGES = ("selected", "reachable", "targetable", "fired", "adjudicated", "probative")

    def __post_init__(self) -> None:
        # Consecutive pairs: the tail is one shorter by construction, so this
        # zip is deliberately not strict.
        for outer, inner in zip(self.STAGES, self.STAGES[1:], strict=False):
            a, b = getattr(self, outer), getattr(self, inner)
            if not b <= a:
                raise AccountingError(
                    f"{inner} is not a subset of {outer}: {sorted(b - a)[:4]} survived a "
                    f"stage they never entered. Populations must nest, or a count means "
                    f"nothing.")
        if self.dispositions:
            self._validate_partition()

    def _validate_partition(self) -> None:
        covered = set(self.dispositions)
        if covered != set(self.selected):
            missing, extra = set(self.selected) - covered, covered - set(self.selected)
            raise AccountingError(
                f"dispositions do not partition the selected set; missing "
                f"{sorted(missing)[:4]}, unexpected {sorted(extra)[:4]}. Every selected "
                f"probe needs exactly one terminal disposition or a probe is counted twice "
                f"or not at all.")
        declared = {p for p, d in self.dispositions.items() if d is Disposition.PROBATIVE}
        if declared != set(self.probative):
            raise AccountingError(
                f"probative set disagrees with dispositions: "
                f"{sorted(declared ^ set(self.probative))[:4]}")

    # -- populations, always cardinalities of sets ---------------------------
    @property
    def probative_population(self) -> int:
        """Cannot be negative: it is the size of a set, not a difference."""
        return len(self.probative)

    @property
    def non_probative_by_reason(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.dispositions.values():
            if d is not Disposition.PROBATIVE:
                out[d.value] = out.get(d.value, 0) + 1
        return out

    @property
    def representativeness(self) -> tuple[int, int]:
        """Numerator and denominator, never collapsed to a percentage.

        1/8 and 8/8 are different evidential situations; a single ratio hides
        which one is in hand, and that is exactly what let a 1-of-8 sample
        support a scene-level failure claim.
        """
        return (len(self.probative), len(self.selected))

    def representative(self, minimum: float) -> bool:
        num, den = self.representativeness
        return den > 0 and (num / den) >= minimum

    def to_json(self) -> dict[str, Any]:
        num, den = self.representativeness
        return {
            "counts": {s: len(getattr(self, s)) for s in self.STAGES},
            "probative_population": self.probative_population,
            "non_probative_by_reason": self.non_probative_by_reason,
            "representativeness_numerator": num,
            "representativeness_denominator": den,
            "accounting_valid": True,
            "note": ("populations are set cardinalities; none is reconstructed by "
                     "subtracting counts drawn from different stages"),
        }


def build(selected: dict[str, Disposition], *, reachable: set[str], targetable: set[str],
          fired: set[str], adjudicated: set[str]) -> ProbePopulation:
    """Assemble a population from a disposition map and per-stage survivor sets."""
    probative = {p for p, d in selected.items() if d is Disposition.PROBATIVE}
    return ProbePopulation(
        selected=frozenset(selected), reachable=frozenset(reachable),
        targetable=frozenset(targetable), fired=frozenset(fired),
        adjudicated=frozenset(adjudicated), probative=frozenset(probative),
        dispositions=dict(selected))
