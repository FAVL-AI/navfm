"""The causal ledger: what went wrong, why nothing caught it, what we decided.

A list of fixed bugs is not a forensic record. It tells you the state ended up
correct without telling you why the error was possible, which checks were
satisfied while it was live, or what would have to change for it not to recur.
Those are the parts that transfer to anyone else's pipeline, and they are the
parts that are lost first.

So every entry here carries its causal chain, and the schema is enforced rather
than encouraged. An entry missing ``why_existing_checks_missed_it`` is refused at
construction, because that field is the one most easily left blank and the one
most worth having: a defect that no check could see is a statement about the
check suite, not about the defect.

Two fields exist to stop this document from drifting into advocacy:

``claim_boundary``
    what the evidence supports.
``non_claim``
    what a reader might reasonably infer from it that is **not** supported.

The second is not redundant. Overclaiming is rarely an assertion; it is usually
an omission that a reader fills in generously.

Scoring is deliberately blunt. ``severity = impact x detectability x
propagation`` on 1-5 scales, and *detectability is inverted* -- a defect that is
hard to notice scores higher, because the expensive failures are the quiet ones,
not the loud ones. Irreversibility is tracked as a separate flag and never
multiplied in: a cheap-but-permanent mistake and an expensive-but-recoverable one
are different kinds of problem, and averaging them into one number loses exactly
the distinction that should drive the decision.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

#: The causal chain. Order is the order an entry should be read in.
REQUIRED_FIELDS: tuple[str, ...] = (
    "issue_id",
    "title",
    "observation",
    "root_cause",
    "why_existing_checks_missed_it",
    "scientific_risk",
    "alternatives_considered",
    "decision",
    "decision_rule",
    "rejected_alternative",
    "correction",
    "validation",
    "regression_control",
    "evidence",
    "impact",
    "claim_boundary",
    "non_claim",
    "attribution",
    "propagation",
)

SCALE = range(1, 6)


class LedgerError(ValueError):
    """An entry that does not meet the schema. Raised at construction."""


@dataclass(frozen=True)
class ForensicEntry:
    """One defect, decision or finding, with the reasoning that produced it."""

    issue_id: str
    title: str
    observation: str
    root_cause: str
    why_existing_checks_missed_it: str
    scientific_risk: str
    alternatives_considered: list[str]
    decision: str
    decision_rule: str
    rejected_alternative: str
    correction: str
    validation: str
    regression_control: str
    evidence: list[str]
    impact: str
    propagation: str
    impact_score: int
    detectability_score: int
    propagation_score: int
    claim_boundary: str
    non_claim: str
    attribution: str = "Frank Asante Van Laarhoven"
    irreversible: bool = False
    status: str = "CLOSED"
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name in REQUIRED_FIELDS:
            value = getattr(self, name)
            if value in (None, "", [], {}):
                raise LedgerError(
                    f"{self.issue_id or '<no id>'}: field {name!r} is empty. Every entry "
                    f"must carry its full causal chain; a blank field is a claim that the "
                    f"question was asked and had no answer, which is rarely true."
                )
        for name in ("impact_score", "detectability_score", "propagation_score"):
            if getattr(self, name) not in SCALE:
                raise LedgerError(f"{self.issue_id}: {name} must be 1-5, got {getattr(self, name)}")
        if not self.issue_id.startswith("FL-"):
            raise LedgerError(f"issue_id must start with 'FL-', got {self.issue_id!r}")

    @property
    def severity(self) -> int:
        """impact x detectability x propagation, 1-125.

        Detectability is already stored inverted (5 = nearly invisible), so a
        quiet, wide-reaching, high-impact defect scores highest. That ordering is
        the point: the loud ones get fixed regardless of how they are scored.
        """
        return self.impact_score * self.detectability_score * self.propagation_score

    @property
    def severity_band(self) -> str:
        s = self.severity
        if s >= 60:
            return "CRITICAL"
        if s >= 30:
            return "HIGH"
        if s >= 12:
            return "MODERATE"
        return "LOW"

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity
        d["severity_band"] = self.severity_band
        return d


def write_jsonl(entries: Iterable[ForensicEntry], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e.to_json(), sort_keys=True) + "\n" for e in entries))
    return path


def _bullets(items: list[str]) -> str:
    return "\n".join(f"  - {i}" for i in items)


def render_markdown(entries: list[ForensicEntry], *, title: str, preamble: str) -> str:
    """Render the ledger, ranked by severity -- quietest and widest first."""
    ranked = sorted(entries, key=lambda e: (-e.severity, e.issue_id))
    out = [f"# {title}", "", preamble, "", "---", "", "## Ranked summary", ""]
    out += [
        "Severity is `impact x detectability x propagation`, each 1-5, with "
        "**detectability inverted** — 5 means almost nothing would have revealed it. "
        "Irreversibility is a separate flag and is deliberately not folded into the "
        "score; a cheap permanent mistake and an expensive recoverable one need "
        "different responses.",
        "",
        "| Rank | ID | Finding | Impact | Undetectability | Propagation | Severity | Band | Irreversible |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, e in enumerate(ranked, 1):
        out.append(
            f"| {i} | `{e.issue_id}` | {e.title} | {e.impact_score} | "
            f"{e.detectability_score} | {e.propagation_score} | **{e.severity}** | "
            f"{e.severity_band} | {'yes' if e.irreversible else 'no'} |"
        )
    out += ["", "---", ""]
    for e in ranked:
        out += [
            f"## `{e.issue_id}` — {e.title}",
            "",
            f"**Severity {e.severity} ({e.severity_band})** · impact {e.impact_score} · "
            f"undetectability {e.detectability_score} · propagation {e.propagation_score} · "
            f"irreversible: {'yes' if e.irreversible else 'no'} · status {e.status}",
            "",
            f"**What was observed.** {e.observation}",
            "",
            f"**Root cause.** {e.root_cause}",
            "",
            f"**Why existing checks missed it.** {e.why_existing_checks_missed_it}",
            "",
            f"**Scientific risk had it survived.** {e.scientific_risk}",
            "",
            "**Alternatives considered.**",
            _bullets(e.alternatives_considered),
            "",
            f"**Decision.** {e.decision}",
            "",
            f"**Decision rule.** {e.decision_rule}",
            "",
            f"**Rejected, and why.** {e.rejected_alternative}",
            "",
            f"**Correction.** {e.correction}",
            "",
            f"**Validation.** {e.validation}",
            "",
            f"**Regression control.** {e.regression_control}",
            "",
            "**Evidence.**",
            _bullets(e.evidence),
            "",
            f"**Impact on results.** {e.impact}",
            "",
            f"**Claim boundary.** {e.claim_boundary}",
            "",
            f"**Not claimed.** {e.non_claim}",
            "",
            f"**Propagation.** {e.propagation}",
            "",
            f"**Attribution.** {e.attribution}",
            "",
            "---",
            "",
        ]
    return "\n".join(out)
