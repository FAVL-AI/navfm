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

## Round 2: the H5 synthetic arm and the round-1 fixes (v5 renamed "history stress test"; 256 calls)
The full table is in `…/history-positive-control-v5-prep-20261017/review_trigger4_v5_round2.md`.

**Confirmed:**
- the H5 binding: an undeclared token is refused; the array is rebuilt and hash-checked; no
  synthetic frame can pass as a real one, or the reverse;
- the deployed preprocessing path and its arithmetic;
- the 256-call manifest, derived exactly from v3;
- D2: accessed-pilot eligibility is sound and no exclusion was relaxed;
- the required framing.

**Fixed:**
- R3: the test now asserts the reason;
- T2: the same-filename attack test;
- P3: tensor-digest checks in admission;
- F-1: wording;
- V-1: the static-history limitation;
- D2: the training-list citation.

**Tests:** runner `288b6cf7…` and tests `c9c54203…`: 57 tests, 57 passed, 0 failures, 0 errors,
0 skipped (JUnit XML).

**Verdict:** READY FOR EXECUTION APPROVAL, per the reviewer, once R3 was fixed, which is done.
NOT FROZEN, NOT APPROVED. The round-2 fixes have not been re-reviewed.

## Closure check at 4b92919 (final hashes)
- **CLOSED:** R3 (the reason assertion discriminates), T2 (the same-filename attack is refused
  only by the own-episode binding), P3 logic (honest attempts are not refused), F-1, V-1.
- **Minor, non-blocking:** of P3's branches, only the stress-equals-H0 branch is tested.
- **D2 factual error, now corrected.** The training list is 25 expansion-layout trajectories plus
  6 legacy routes, not 31 expansion layouts. The partial appearance aliasing is now disclosed:
  training scene 8 with donor scene 3, and training scene 9 with query scene 4.
- **Donor eligibility:** ELIGIBLE under every exposure exclusion: the accessed pilot, sealed
  held-out groups, the training list, and the development split, which permits diagnosis.
- **Verdict:** ready for execution approval, with the D2 wording fixed. Not approved.
