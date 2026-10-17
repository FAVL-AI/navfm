# Trigger 6: history-sensitivity v4 results (absence of an effect), 2026-10-17

The report under review is `docs/HISTORY_SENSITIVITY_OFFLINE_V4_RESULTS.md` (attempt 01). The
reviewer was an independent read-only subagent. It recomputed every number from the external
results, manifest and episode records, and executed nothing else.

The full table is in
`$NAVFM_EVIDENCE_ROOT/history-sensitivity-offline-v4-execution-20261017/review_trigger6_results.md`.

## Verdict: survives as a descriptive result, scoped to these perturbation sizes
**HOLDS:**
- substituted histories reached the model (hashes and the tensor path, in chronological order);
- no artefact: no caching, no wrong row, no model-state or precision issue;
- every number recomputes;
- the Part A execution facts and digests.

**NOT ESTABLISHED:** sensitivity to larger history perturbations. No positive control was run,
and the substitutions were all at most 0.28 m and about 25°, with H2 near-null.

## Corrections applied
- Perturbation sizes and the missing positive control are now stated.
- H2 is described as near-null.
- The claim is scoped to "substitutions of this size".
- "Must come mainly from the current image" became "most plausibly attributable (INFERENCE; not
  tested)".
- The JUnit citation is corrected.
- The GPU memory sentence is corrected.
- The SD convention is stated.
- The free space below the 50 GB reserve is disclosed.
