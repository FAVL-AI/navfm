# Trigger-3 adjudication — Amendment 4 (0.17398 attribution: source evidence and measurement)

Date: 2026-08-07
Trigger: 3 (amendment to PREREGISTRATION.md)
Artefact: PREREGISTRATION.md `## Amendment 4` to EOF
Method: independent reviewer, artefacts and git history only, instructed to
refute and to default to "refuted" when uncertain.

## Verdicts

| Round | Verdict | Blocking |
|---|---|---|
| 1 | Cannot determine | The amendment's stated purpose corresponded to no extant defect: it presented itself as correcting a misattribution that had already been corrected at `8cb0e18`, in the paragraph immediately below the blockquote, under `docs/reviews/2026-07-31-remediation-order.md` §1 and verified closed in `gates/redteam/trigger3-g0c-amendment-v3-2026-07-31.md` — committed in that same commit. As drafted it would have led a reader to conclude a falsehood stood uncorrected in the preregistration for a week. It did not. |
| 2 | **Fixing — commit permitted** | One wrong duration (below), corrected before commit. |

## Erratum, and its provenance

The revision stated that `d6cef79` is "about 9.5 hours" after the protocol
freeze at `d4fc321`. Recomputed: `d4fc321` = 1785459869, `d6cef79` = 1785490366,
elapsed **8 h 28 m 17 s**. The 9.5 h figure belongs to a different pair —
`92e3004 → d6cef79` = 9 h 33 m 41 s — which is the "verified life" cell in the
table below it. The two spans were conflated.

The wrong figure entered via the round-1 review, which wrote "~9.5 h after the
freeze"; the drafting adopted it without recomputing. The reviewer recomputed
rather than re-reading its own text and self-reported the origin. Recorded here
because it is the failure the `gates/failures/` convention exists to capture: a
figure supplied by a check, adopted downstream on the check's authority, and
wrong. **A number from a reviewer is evidence, not an oracle**; the recomputation
is the oracle. Corrected to the exact `8 h 28 m` rather than a rounded value,
because the paragraph's declared job is to replace an imprecise inherited phrase.

## Why Fixing, not Rescuing

- Nothing operative changes. `PREREGISTRATION.md` lines 1–716 byte-identical to
  HEAD; Condition 7's band `0.1 ≤ L/0.17398 ≤ 10` untouched; outcome mapping
  untouched. No G0.c datum exists to rescue.
- Append-only: 0 deletions; Amendments 1–3 byte-unchanged; frozen section
  byte-identical to `d4fc321`.

## What the amendment contributes over committed Amendment 2

Four of five contributions verified genuinely new:

1. **The `pre-freeze` imprecision disclaimer** — the phrase "spans the
   repository's entire pre-freeze history" originates in externally-mandated
   text and is reproduced unqualified in Amendment 2. No committed document
   flags it as imprecise; this is the first to. The criterion's life straddles
   the freeze rather than being bounded by it.
2. A drop-in replacement sentence for the mandated blockquote's false first
   sentence — Amendment 2 corrected in prose but supplied no substitute.
3. Verbatim source quotations behind the three commit claims, both verified
   byte-exact against their blobs.
4. The quantification (38/21 commits; 9 h 34 m / 2 h 14 m), replacing Amendment
   2's qualitative "had shortened that life".
5. The outcome-mapping section remains redundant with this directory's v3
   record, but now says so and names `gates/redteam/` as the venue.

## Findings recorded, not resolved

- **Metric selection was checked for self-flattery and cleared.** Four metrics
  exist: files touched 1.27×, commits 1.81×, insertions 2.08×, wall-clock
  4.27×. The amendment reports commits and wall-clock — including the least
  flattering — and omits the most flattering. Reviewer: "The framing does not
  favour the author."
- **The drop-in replacement is unsanctioned on the record.** The blockquote is
  verbatim-mandated by `docs/reviews/2026-07-31-g0c-amendment-specification.md`.
  Amendment 4 substitutes its first sentence by supersession, not by mandate. No
  post-`8cb0e18` review document addresses whether the mandating channel accepts
  this. Non-operative and factually correct, but unratified.
- The false sentence also survives at
  `docs/reviews/2026-07-31-g0c-amendment-specification.md:18`, correctly, as a
  verbatim archive. At every commit where it has existed anywhere in this
  repository, an in-repo flag or correction has existed in the same commit
  (`f2dead0` carried the v2 review that flags it).

## Disposition

**Committed in narrowed form.** The amendment as reviewed was substantially
wider than what survived. Withdrawal was considered and evaluated against the
standing instruction — *withdraw if the reviewer concludes Amendment 4 adds no
necessary correction because the misattribution was already corrected and
independently verified at `8cb0e18`*. **That condition was not met.** The
reviewer agreed the misattribution was fully closed at `8cb0e18` and kept the
amendment on a different ground: the phrase "spans the repository's entire
pre-freeze history" stands unqualified in committed `PREREGISTRATION.md:237`,
the criterion's life straddles the freeze, and no committed file flags this.
Verified independently before acting: `git grep` finds the phrase asserted in
three committed files and contradicted in none.

The amendment was then narrowed to that single still-open imprecision. Removed
before commit, as outside its scope or as unnecessary framing:

* the drop-in replacement sentence for the mandated blockquote — the blockquote's
  attribution is already corrected adjacent to it, and substituting text inside
  an externally-mandated quotation by supersession was unratified on the record
  (a limitation this review itself raised and could not resolve);
* the understatement-factor table (1.81× / 4.27×) and the "consequence of the
  misattribution" framing — a measured chronology carries the same facts without
  characterising them;
* the outcome-mapping section — redundant with Blocking 5 in this directory's v3
  record, and `gates/redteam/` is the venue for red-team adjudications;
* all language implying motive. The committed amendment contains no instance of
  "flattered", "not neutral", "understate" or equivalent, verified by grep.

What remains is the lifetime clarification, the three-row chronology table, an
explicit statement that this amendment does **not** perform the `8cb0e18`
correction, and the interval erratum below. 47 insertions, 0 deletions.

### Erratum carried into the amendment

The 9.5-hour figure this review supplied for the `d4fc321 → d6cef79` gap was
wrong; the correct value is 8 h 28 m, and 9.5 h is the `92e3004 → d6cef79` span.
It was carried into a draft of the amendment without recomputation. The
timestamps were subsequently recomputed independently against
`git show -s --format=%ct` before commit. Recorded in the amendment itself,
because the rule it illustrates is load-bearing here: **a reviewer's statement is
evidence to verify, not a fact to copy without recomputation.**

Recorded for the avoidance of doubt: withdrawing an uncommitted proposed
amendment would not have violated the append-only property of the committed
preregistration history. That property constrains committed text; a proposal
never committed is not part of that history.
