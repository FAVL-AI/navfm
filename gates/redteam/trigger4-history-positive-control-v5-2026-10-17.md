# Trigger 4: history positive control v5 design, 2026-10-17

One independent read-only review of the prepared, unexecuted v5 extension: builder, manifest,
runner diff, tests and proposal. The full table is in
`$NAVFM_EVIDENCE_ROOT/history-positive-control-v5-prep-20261017/review_trigger4_v5_round1.md`.

## Round 1: 0 blocking
**Confirmed:**
- the manifest is derived exactly from v3: 184 calls, kept calls byte-identical, donor rule
  followed, hashes match;
- no score dependence;
- production pinned to two manifest digests at every point;
- donor binding: wrong frames and episodes are refused; H0/H1/H3 stay bound to the query
  episode.

**Fixed:**
- R5: detectable-response criterion and magnitude tier computed in code.
- T2: wrong-variant donor and donor-in-H0-slot tests.
- D3: framing (scene instance, not a 20 m distance) and the rationale for the window.
- P2: negligible tier and narrower interpretation.
- R3: query episode must be declared.
- P3: per-call tensor digests.
- D2: records cited; accessed-pilot exclusion stated as not fully established.

**Noted:** R4, a v4 rerun now needs the donor records.

**Open:** C1, the likely uninformative null. Frank to decide between adding a synthetic extreme
level (which departs from the image-based specification) and accepting that a null will not be
cited.

## Tests
Runner `dcd208d1…` and tests `ec1734f6…`: 51 tests, 51 passed, 0 failures, 0 errors, 0 skipped
(JUnit XML). The fixes made after the review have not been re-reviewed.

## Verdict
**NOT FROZEN. NOT APPROVED.** Blocked on the C1 decision.
