# Prospective recovery baseline verification

Verified 2026-10-10 on branch `agent/engineering-recording`, starting at
`6a4701182640fdd78f8a12dcb4b30974d5e7a875` with a clean working tree.

The documented `make verify` ran with the admitted `NAVFM_UPSTREAM` and the local
virtual environment. Ruff passed and mypy reported no issues in 89 source files.
Pytest failed exactly the three documented environment-identity cases:

- `test_v8_accepts_the_repaired_tree`: expected PASS, observed FAIL; archived
  contract identity does not match this worktree.
- `test_attempt_001_pre_capture_is_preserved_byte_for_byte`: the expected
  `runs/bo10/intervention/arm_a/pre_capture.json` is absent.
- `test_regeneration_on_an_unchanged_tree_is_idempotent`: expected FROZEN,
  observed REFUSED.

These remain failures. No missing archival evidence was recreated or copied and
no contract or test was weakened. The verification log stays outside git at
`/tmp/navfm-prospective-verify-20261010.log`.

Both documented frozen analyses were reproduced to new external files under
`/home/favl/navfm-runtime-evidence/`:

- `prospective-r2-reproduced-stage2-20261010-01.json`: 92 attempts, no integrity
  failures; B1 FAIL, R2 PASS, V2a FAIL, V2b PASS.
- `prospective-r2-reproduced-stage 3-20261010-01.json`: 54 attempts, no integrity
  failures; R2 RETAIN and V2b RETAIN. The complete reproduced JSON equals the saved
  `v2-stage 3-analysis-20261010-01.json` object exactly.

All 18 variant/condition rows of the committed stage-3 comparator table were
reconciled against attempt aggregates: correct stops, wrong stops, abstentions,
timeouts, contact-bearing episodes, path lengths rounded to 0.1 m and stop delays
agree. V2b's truncated delays are 15, 22, 25 decisions: 7.5, 11, 12.5 seconds.

The decision remains narrow: stage 3 did not confirm recovery. True and truncated
conditions had no lost entry; the swapped chain had no pose-true node to score.
R2 still stopped wrongly on all four truncated chains. Shorter terminal exposure
cannot establish a safety improvement. The new experiment therefore tests
recovery directly with forced lost starts and exact-node primary scoring.

Only protocol/code/tests and concise evidence summaries may be committed. Runtime
outputs, logs, images and checkpoints remain external. Held-out layouts stay
sealed, illumination stays paused, and no push or real robot actuation is allowed.
