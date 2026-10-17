# Trigger 6: history stress test v5 results (absence of an effect), 2026-10-17

The report under review is `docs/HISTORY_STRESS_TEST_V5_RESULTS.md` (attempt 01). The reviewer
was an independent read-only subagent. It recomputed every number from `results.jsonl` and the
frozen manifest rather than from the analysis output, recomputed every digest, and executed
nothing else.

The full review is in
`$NAVFM_EVIDENCE_ROOT/history-stress-test-v5-review-20261017/review_trigger6_results.md`
(sha256 `5cf3e0d88ce59a2b90765747b97faacda46252d432b66fb8b8e8ed9b79cf7a11`).

## Verdict: survives as a descriptive result, scoped to the tested substitutions
**HOLDS:**
- every number and per-episode/per-route row recomputes, including counts, controls, replay
  agreement and the k034 disagreement;
- every listed digest matches, and all 59 entries in the immediate hashes record still match;
- substituted histories reached the model: goal digest identical, observation digest
  different, current frame identical, all five history frames different, in 72 of 72 calls per
  arm; the H5 frame digest was recomputed from a 240×320×3 uint8 array of 128;
- no artefact explains the null: correct goal row, `eval()` under `inference_mode` after a
  strict load, no caching, history tokens reach the distance head, batch structure does not
  shrink Δ.

**NOT ESTABLISHED:** that the score cannot respond to history. H5 is not a positive control,
only 4 donor histories and 1 synthetic history were tested, and the goal encoder's input is
identical across arms by design.

## Corrections applied
- This record was written; it did not exist when the draft was reviewed.
- "Not detectable" is now stated to be relative to the predeclared bound. The H4 shift is
  reported as deterministic, same-sign (72 of 72) and small. The predeclared verdict is
  unchanged.
- The tier's dependence on the top two of 12 N_batch values is disclosed.
- H4's single fixed donor history per episode (4 distinct histories; H5: 1) is stated.
- The predeclared ratios to the replay margin, the episode reference scale and the pooled
  reference scale were added.
- The goal-pathway limitation was added.
- The sampled-memory sentence and the Unreal-editor sentence were reworded to what the evidence
  shows.
