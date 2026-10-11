"""Freeze loaded source fingerprints while allowing newly imported dependencies."""

from __future__ import annotations


def verify_source_stability(expected: dict[str, str], observed: dict[str, str]) -> dict[str, str]:
    changed = sorted(name for name, digest in expected.items() if observed.get(name) != digest)
    if changed:
        raise ValueError(f"executing source changed or disappeared: {changed}")
    return {**expected, **observed}
