"""Run identity, and the lineage links that keep one experiment from becoming two.

A resume is supposed to continue *the same experiment*. Nothing in a checkpoint
file enforces that. `latest.pth` restores weights, optimizer moments and RNG
streams perfectly well into a run pointed at a different dataset, a different
batch size, a different checkpoint, or a different environment — and the result
is a single `runs/` directory, a single set of `metrics_epoch_*.json`, and one
row in a table, describing a population that was never one experiment.

This module makes the identity explicit, so that continuing a run and starting
a related one are different acts with different records.

**Identity** is the tuple that must match for a resume to be a continuation.
**Lineage** is what a run records when it is deliberately *not* a continuation:
the identity it descends from, and the intervention that made it distinct. The
second scheduler remedy — redefining the training horizon — is exactly that
case: it changes the optimisation protocol, so it mints a new identity and
records where it came from, rather than overwriting a lineage as though nothing
happened.

    >>> a = run_identity(batch_size=64, seed_set=[0])
    >>> b = run_identity(batch_size=128, seed_set=[0])
    >>> compare(a, b)
    ['batch_size: prior 64, requested 128']
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = [
    "IDENTITY_FIELDS",
    "IdentityMismatch",
    "compare",
    "identity_digest",
    "lineage_link",
    "run_identity",
]

#: Everything that must match for a resume to be a continuation rather than a
#: hybrid. Sourced from Task 1a and extended by the M2 review (M2-11) with the
#: metric set, environment identity and evidence class -- each of which can
#: change what a number means without changing anything else in the tuple.
IDENTITY_FIELDS: tuple[str, ...] = (
    "checkpoint_sha256",
    "dataset_split_digest",
    "evaluator_commit",
    "config_digest",
    "metric_set_version",
    "seed_set",
    "batch_size",
    "environment_id",
    "evidence_class",
    "architecture",
)


class IdentityMismatch(RuntimeError):
    """A resume was requested against an incompatible prior run."""


def run_identity(**fields: Any) -> dict[str, Any]:
    """Build an identity record. Unsupplied fields are ``None``, not absent.

    Explicit ``None`` rather than a missing key, so that "this run never
    recorded a dataset digest" and "this run recorded that it had none" are the
    same, comparable thing — and so a field added later reads as *unknown on
    both sides* rather than silently matching.
    """
    unknown = set(fields) - set(IDENTITY_FIELDS)
    if unknown:
        raise ValueError(f"not identity fields: {sorted(unknown)}")
    identity: dict[str, Any] = {name: fields.get(name) for name in IDENTITY_FIELDS}
    seeds = identity.get("seed_set")
    if isinstance(seeds, (list, tuple, set)):
        identity["seed_set"] = sorted(seeds)
    return identity


def identity_digest(identity: dict[str, Any]) -> str:
    canonical = json.dumps(
        {k: identity.get(k) for k in IDENTITY_FIELDS}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def compare(prior: dict[str, Any], requested: dict[str, Any]) -> list[str]:
    """Human-readable mismatches between two identities; empty means compatible.

    A field that is ``None`` on *both* sides is not a mismatch: neither run knew
    it. A field known on one side and not the other IS a mismatch, because a
    resume that silently drops a constraint the original run declared is exactly
    the hybrid this guards against.
    """
    mismatches: list[str] = []
    for name in IDENTITY_FIELDS:
        before, after = prior.get(name), requested.get(name)
        if before is None and after is None:
            continue
        if before != after:
            mismatches.append(f"{name}: prior {before!r}, requested {after!r}")
    return mismatches


def lineage_link(parent: dict[str, Any], *, intervention: str, note: str = "") -> dict[str, Any]:
    """Record that this run descends from another rather than continuing it.

    Used when the difference is deliberate. The parent's identity digest is
    recorded, not its directory name, because a directory can be renamed and a
    digest cannot.
    """
    if not intervention:
        raise ValueError("an intervention must be named; an unnamed fork is an untracked one")
    return {
        "derived_from_identity": identity_digest(parent),
        "intervention": intervention,
        "note": note,
        "is_continuation": False,
    }
