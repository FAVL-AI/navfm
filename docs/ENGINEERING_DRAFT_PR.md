This branch adds the engineering recording and evidence pipeline, development arrival/recovery evaluation, and a reviewed initialization/history diagnostic. The latest diagnostic verifies a fresh-process command-replay start procedure on two short scripted development cases; it preserves the halted recovery pilot as inconclusive.

## Implemented pipeline

- Opt-in bounded engineering recording with observed transitions, source/asset provenance, external evidence paths, and fail-closed integrity checks.
- Development data admission, training/evaluation and topomap navigation tooling, qualified controller feedback, and frozen staged component-comparison protocols with matched conditions, independent reviews and traceable decision records.
- Prospective R2 pilot instrumentation and scoring with exact-node primary recovery, separate outcomes, contact/exposure accounting, immutable attempts and an integrity-gated launch ledger.
- Separate initialization/history collectors, deterministic reconstruction, runtime readbacks, fixed bootstrap/eligibility checks, and continuous/replay/direct-reset comparisons with frozen tolerances and cross-repetition controls.

## Verified results

- Stage 2 and stage 3 were reproduced from saved evidence (92 and 54 attempts respectively, zero integrity failures); final stage-3 tables reconcile. Stage 3 did not test qualifying recovery.
- The prospective pilot preserved eight recordings, with no retries. Two paired initial-image histories exceeded the frozen 2.5 grayscale bound despite closely matched positions/headings. The pilot is INCONCLUSIVE; the remaining 24 attempts were not run. No claim that R2 works or fails follows.
- Diagnostic v1 preserved its first-use stepping failure. Reconstruction of eight existing initial inputs repeats exactly on CPU and agrees on discrete outputs, but fails numerical equivalence with recorded CUDA outputs.
- Diagnostic v2 completed all eight declared technical processes with no retries/timeouts/drift. Fresh-process command replay passed all within-pair and cross-repetition state/history guards on two scripted cases. Direct root reset failed equivalence; full observable-state restoration passed physical/image bounds but failed history age/index guards. Independent analysis recomputation and all 376 capture hashes matched.

## Validation and known failures

With the documented admitted `NAVFM_UPSTREAM`, ruff and mypy pass; 45 focused prospective/diagnostic tests pass. Full `make verify` remains failed on exactly these three existing `tests/test_environment_identity_v8.py` cases:

- `test_v8_accepts_the_repaired_tree`: archived identity FAIL instead of expected PASS.
- `test_attempt_001_pre_capture_is_preserved_byte_for_byte`: missing archived `runs/bo10/intervention/arm_a/pre_capture.json`.
- `test_regeneration_on_an_unchanged_tree_is_idempotent`: REFUSED instead of expected FROZEN.

## Research limits and review scope

The original pilot image-mismatch cause remains unknown. The verified start procedure covers only the two short scripted technical cases and initialized proxy state; learned-policy handover/memory, recovery competence and broader generalization remain unverified. Shorter exposure does not establish improved safety. Held-out layouts remain sealed, illumination remains paused, and no real-robot actuation occurred. No additional recovery batch was run.

Runtime datasets, images, logs and weights remain outside Git. Reports contain evidence identities and hashes; the raw local evidence is not included in this PR. Original freezes and failed attempts are preserved. This is a draft for review, with no merge or history rewrite requested.

See `docs/PROJECT_HANDOFF.md`, `docs/PROSPECTIVE_R2_PILOT_RESULT.md`, and `docs/INITIALIZATION_DIAGNOSTIC_V2_RESULT.md` for the current state, detailed outcomes and exact evidence references.
