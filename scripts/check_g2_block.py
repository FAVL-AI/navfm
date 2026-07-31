"""Block collection gate G2 while any deferred E2 analysis decision is unset.

    python scripts/check_g2_block.py          # exit 0 to proceed, 4 to refuse

`PREREGISTRATION.md` Amendment 1 defers four decisions by name — estimation
software and tolerance, the held-out scene count, the per-cell episode count,
and the estimator implementation — and states that all four must be fixed
before the first E2 episode is collected.

A deferral recorded only in prose is a deferral that gets forgotten at the
moment it becomes inconvenient: the collector is running, the GPU is warm, and
the person who wrote the clause is the person deciding whether it applies today.
**Deferral is only honest while it is mechanically impossible to proceed past
it.** This is that mechanism.

Two things are checked, not one:

1. every decision in ``gates/g2_decisions.json`` has status FIXED with a value
   and the amendment that fixed it;
2. ``PREREGISTRATION.md`` still carries the gate condition that imposed the
   block.

The second exists because the first can be satisfied by editing a JSON file.
Lifting the block by deleting the clause that imposed it is the obvious way
around a checker like this, so removing the clause fails the check rather than
passing it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DECISIONS = REPO / "gates" / "g2_decisions.json"
PROTOCOL = REPO / "PREREGISTRATION.md"


class G2Blocked(RuntimeError):
    """Collection may not begin. Not a failure of the collector."""


def load(decisions_path: Path = DECISIONS) -> dict[str, Any]:
    return json.loads(decisions_path.read_text())


def outstanding(record: dict[str, Any]) -> list[str]:
    """Decisions that are not yet fixed, with the reason each still blocks."""
    problems: list[str] = []
    for name, decision in sorted(record.get("decisions", {}).items()):
        status = str(decision.get("status", "DEFERRED")).upper()
        if status != "FIXED":
            problems.append(
                f"{name}: {status} -- {decision.get('why_deferred', 'no reason given')}"
            )
        elif decision.get("value") is None:
            problems.append(f"{name}: marked FIXED with no value, which fixes nothing")
        elif not decision.get("fixed_by_amendment"):
            problems.append(
                f"{name}: marked FIXED with no amendment naming where it was fixed. "
                f"A decision fixed outside the pre-registration is not pre-registered."
            )
    return problems


def gate_condition_intact(record: dict[str, Any], protocol_path: Path = PROTOCOL) -> bool:
    """Is the clause that imposed the block still in the pre-registration?"""
    marker = record.get("gate_condition_marker")
    if not marker:
        return False
    try:
        return marker in protocol_path.read_text()
    except OSError:
        return False


def check(
    decisions_path: Path = DECISIONS, protocol_path: Path = PROTOCOL
) -> tuple[bool, list[str]]:
    record = load(decisions_path)
    problems = outstanding(record)
    if not gate_condition_intact(record, protocol_path):
        problems.append(
            "the pre-registration no longer carries the gate condition that imposed this "
            "block (marker: "
            f"{record.get('gate_condition_marker')!r}). Removing the clause does not lift "
            "the block; it invalidates the record."
        )
    return (not problems), problems


def assert_unblocked(decisions_path: Path = DECISIONS, protocol_path: Path = PROTOCOL) -> None:
    """Raise :class:`G2Blocked` unless collection may proceed.

    Called from the collector's setup path so the refusal happens before a
    scene is opened, not after a session's worth of episodes exist.
    """
    ok, problems = check(decisions_path, protocol_path)
    if ok:
        return
    detail = "\n".join(f"    {p}" for p in problems)
    raise G2Blocked(
        "collection gate G2 is BLOCKED -- E2 collection may not begin.\n"
        f"{len(problems)} outstanding decision(s):\n{detail}\n\n"
        "These are deferred by name in PREREGISTRATION.md Amendment 1 and must be fixed\n"
        "in a further dated amendment, with the estimator's measured type-I error rate on\n"
        "simulated null data, BEFORE the first E2 episode is collected.\n"
        "This is not a collector fault. It is the pre-registration holding."
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--decisions", default=str(DECISIONS))
    p.add_argument("--protocol", default=str(PROTOCOL))
    args = p.parse_args(argv)

    ok, problems = check(Path(args.decisions), Path(args.protocol))
    if ok:
        print("G2 unblocked: all deferred E2 analysis decisions are fixed.")
        return 0
    print("G2 BLOCKED", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 4


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
