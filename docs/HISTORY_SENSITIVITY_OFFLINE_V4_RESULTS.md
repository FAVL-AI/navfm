# Offline history-sensitivity diagnostic v4: measured results (attempt 01)

**Scope.** One approved execution of the frozen v4 protocol
(`docs/HISTORY_SENSITIVITY_OFFLINE_PROTOCOL_V4.md`, freeze commit `eb54fb1`). It is a replay
diagnostic of the requested-goal check's score. It does **not** measure stopping, and it does
not by itself explain the closed-loop stopping failures.

> **Headline.** None of the tested history substitutions changed the replayed gate decision;
> the largest score change was 0.0016. **Replay did not reproduce one logged gate decision:**
> `C_verify/junction_run_0000/k034` was logged at 7.653 (accept) but replays at 7.819 (reject).
> This is despite the median replay gap of 0.044 meeting its prospective criterion. Replay
> agreement is therefore not complete at the gate, even though it is close at the median.

Raw evidence is external:
- `$NAVFM_EVIDENCE_ROOT/history-sensitivity-offline-v4-attempt-01/` holds the attempt records
  and per-call results;
- `$NAVFM_EVIDENCE_ROOT/history-sensitivity-offline-v4-attempt-01.{hashes,analysis}.json`;
- `$NAVFM_EVIDENCE_ROOT/history-sensitivity-offline-v4-execution-20261017/` holds the
  preflight checks, command, output and digests.

Digests are listed at the end.

## Part A: execution and admission status

### Pre-execution checks (2026-10-17T01:05)
- **Commit.** Local HEAD = remote `research/history-sensitivity-offline-v4` =
  `eb54fb1743a4357c7d542371a36f16aa45bef3c5`, with a clean worktree.
- **Frozen hashes.**
  - runner `add0bd46…`;
  - manifest `391c2f02…`;
  - builder `a4fdb50d…`;
  - the external freeze `SHA256SUMS` check passed.
- **Attempt directory.** Unused.
- **Free disk.** 29.2 GB. That is below the standing 50 GB pre-test reserve. Frank waived the
  reserve for this milestone; the declared output is about 1 MB.
- **GPU.** 1008 MiB in use, with one listed compute process (251 MiB, a desktop daemon).

### Focused tests and review (pre-execution)
- **Runner suite** on the frozen sources, with CUDA hidden: 42 tests, 42 passed, 0 failures, 0
  errors, 0 skipped. Source: `$NAVFM_EVIDENCE_ROOT/history-sensitivity-offline-v4-freeze-20261017/test_run5_junit.xml`.
  The JUnit file in the execution-evidence directory is the separate 6-test upstream check.
- **Review.** Three read-only runner reviews; no open blocking or should-fix finding
  (`gates/redteam/trigger4-history-sensitivity-runner-2026-10-17.md`).

### Repository-wide baseline failures
`make verify` has 30 failures, identical at the base `1de7994`. They group by cause as follows:

| Cause | Tests | Relevance to the runner |
|---|---|---|
| No upstream clone in a fresh worktree (`UpstreamNotFound`) | 6, including `test_vint_interface_v1::test_actual_native_preprocessing_context_and_normalization` and the official-loader tests | Coverage resolved: **all 6 pass** when `NAVFM_UPSTREAM` is set to the pinned clone `dca7981` (log in the execution evidence) |
| Untracked BO-10 run archive absent | 4 | Not used by the runner |
| `transformers` not installed | 4 (NoMaD EMA) | Not imported by the runner |
| Alternate interpreter resource absent | 1 | Not used |
| Camera-qualification harness worker not reaped | 15 | A separate harness; not imported or used by the runner's supervisor or admission |

The unrelated failures were not repaired.

### Execution
- **Command.** `run` with the frozen manifest and digest, `--attempt-dir` set to attempt 01 and
  `--evidence-root`. It ran with the Isaac env's interpreter, without starting Isaac.
- **Environment:**
  - torch 2.7.0+cu128, CUDA 12.8, cuDNN 9.7.1;
  - RTX 4080 SUPER, driver 580.178.04;
  - library defaults: `cudnn.benchmark` False, `deterministic` False, matmul TF32 False, cuDNN
    TF32 True, matmul precision "highest".
- **Process status:**
  - supervisor `COMPLETE`, natural exit, worker exit code 0;
  - no forced termination, no session survivors at cleanup, 0 retries.
- **Forwards.** 306 listed and 306 counted at the model hook; 0 during load.
- **Time.** Execution ended at 18.6 s of the 600 s limit. Model load finished at 5.9 s, and the
  worker took 17.7 s.
- **Memory.**
  - Allocator peaks: 290 MB reserved and 218 MB allocated, against the 4 GiB cap.
  - Process GPU memory, sampled: peak 576 MiB, seen in 17 of 19 samples, 0 failed.
  - Peak RSS: 1.41 GB (1.31 GiB).
- **Source origin.** All 16 `navfm` and `vint_train` modules were loaded from the staged,
  digest-matching snapshot, checked before load, after load and after the calls.
- **Immediate output hashes.** `hashes` ran right after `run`. Its record (`c0eb9f45…`) covers
  59 attempt files, and all 59 still matched at sealing.
- **Admission.** Frozen `admit` with the expected runner digest: **admitted, no reasons**.
- **Analysis.** Frozen `analyse`, unchanged.

## Part B: scientific findings (replay regime; descriptive; 2 routes, 1 checkpoint, exposed episodes)

### Replay agreement with the logged deployed scores (72 queries)
- **Gap (replay H0 minus logged score):**
  - median +0.028;
  - p10/p90 −0.043 / +0.114;
  - median |gap| 0.044;
  - max |gap| 0.189.
- **Per-episode median gaps:** C j0 +0.052, C j1 −0.004, D j0 +0.036, D j1 +0.006.
- **The prospective criterion (median |gap| ≤ 0.085) is met.** As declared, this does **not**
  establish deployment equivalence.
- **Gate agreement at 7.745: 71 of 72. One logged decision is not reproduced** (see the headline).
  - One disagreement: `C_verify/junction_run_0000/k034`, logged 7.653 (accept) vs replay 7.819
    (reject).

### Numerical references
- **Identical-input repeats:** bit-identical within the process (12 triples, N_repeat = 0).
  This does not bound noise across processes or kernel selections.
- **N_batch (goal-only batch minus H0):** |value| ≤ 0.0076, over 12 calls.
- **N_order (reversed reference rows):** 0.0000, over 4 calls.

### History substitution (Δ = arm − H0, the same query image, goal, reference rows and order)
| Arm | Calls | max \|Δ\| | median \|Δ\| | Flips at 7.745 | max \|Δ\| / logged margin |
|---|---|---|---|---|---|
| H1, query repeated ×6 | 72 | 0.0016 | 0.00022 | 0 | 0.0055 |
| H3, own history shifted by 5 (3 s splice) | 72 | 0.00066 | 0.00016 | 0 | 0.0016 |
| H2, pose-matched other variant | 50 (34 pairs, 16 mutual) | 0.00053 | 0.00014 | 0 | 0.00058 |

- **Per episode and per route:** every median Δ rounds to 0.000 and every max |Δ| is ≤ 0.002.
  There are no flips in any episode or route.
- **Scale.** For reference, the per-episode median change in the logged score between
  consecutive in-region decisions is 0.39–3.37. Across the 72 queries, the H0 replay scores
  range from 4.81 to 16.22 (population SD 3.10; sample SD 3.13).
- **Non-zero but negligible.** No Δ is exactly zero, and all exceed N_repeat = 0 only because
  the repeats were bit-identical. The largest history effect is about one fifth of the largest
  batch-composition effect (N_batch).

### Size of the substitutions (no positive control was run)
| Arm | How far the replaced history slots are from the real ones | Median mean-absolute pixel difference |
|---|---|---|
| H1 | 0.03–0.28 m from the query pose (median 0.14 m); \|Δyaw\| median 4.0°, max 24.9° | — |
| H3 | 0.17–0.28 m from the real slots (median 0.24 m) | 9.7 |
| H2 | 0.006–0.118 m (median 0.031 m); **a near-null perturbation by construction** | 4.9 |

- Every substitution keeps the robot inside the goal region, a few tenths of a metre from the real
  history.
- **No arm is a positive control for the history channel.** None uses, for example, frames from
  an unrelated location or blank frames. So this run does not show that the score *can* respond
  to history.
- What it does show:
  - The tested identical-input controls are repeatable: the 12 repeat triples are
    bit-identical.
  - H0 scores vary across queries from 4.81 to 16.22. Between queries, however, the current
    image, its pose, the history and the reference window all change together, so this spread
    does not isolate any single input.

### What this establishes
On these 72 recorded in-region queries, in the replay regime, replacing the five preceding
history frames changed the requested-goal score by at most 0.0016 units, and never moved a
decision across the 7.745 threshold. All three substitutions behave this way: repeated static,
temporally shifted by 3 s, and pose-matched from the other variant.

Within this population and replay regime, the check's score is **practically insensitive to
history substitutions of this size**: at most 0.28 m and about 25° of yaw, within the goal
region.

The model received the substituted frames, which the trigger-6 review checked:
- all five history slots differ from H0 by hash in every H1, H2 and H3 call;
- all six frames reach the encoder in chronological order;
- with the batch fixed, the identical-input repeat controls were bit-identical. Those controls
  show the computation is repeatable; they do not show that every non-zero Δ is free of numerical
  effects. Different inputs can follow different numerical paths, and a Δ of about 1e-4 is in
  the same range as the batch-composition effects (N_batch ≤ 0.0076).

### What it does not establish
- **That history is irrelevant to deployment.** The deployed inputs were live arrays rather than
  JPEGs, and the library environment is inferred.
- **Sensitivity to larger history perturbations.** No positive control was run.
- **The source of the large decision-to-decision changes in the logged score.** Between
  consecutive logged decisions, several inputs change together: the current image, its pose and
  heading, five of the six history frames, the reference window, and the variant's control
  state. This run held the current image fixed and varied only history, so it **does not
  isolate** the current image, the heading or any other input as the cause. Interactions between
  inputs, and the gap between replay and deployment, also remain possible.
- **Improved stopping, calibration or remedies.** Nor does it establish any generalisation
  beyond two routes, one checkpoint and these exposed episodes.

### Implication for H0/H1 (RECOMMENDATION, not a result)
This is a negative result that narrows the history explanation. For these inputs, history
substitution at these magnitudes is unlikely to explain the requested-goal check's rejection of
in-region frames. It does not establish that history is generally irrelevant. A bounded history
stress test (not a validated positive control) has been prepared but not executed (see
`docs/HISTORY_STRESS_TEST_V5_PROPOSAL.md`).

How the current view and heading drive the score is a separate question, which this run did not
isolate. The heading-capture study is still blocked by camera qualification.

## Trigger-6 review (finding of an absent effect)
- An independent read-only review recomputed every number from `results.jsonl`, the manifest
  and the episode records.
- It **refuted an artefact explanation**: no caching, no wrong row, no model-state or precision
  issue.
- The claim **survives as a descriptive result** for these perturbation sizes. It does not
  survive as a general statement about history sensitivity, because no positive control was run.
- This report applies the review's required wording changes:
  - the perturbation sizes and the missing positive control;
  - H2 described as near-null;
  - the INFERENCE wording;
  - the JUnit citation;
  - the GPU sentence;
  - the SD convention.

## Digests
| Item | sha256 |
|---|---|
| `…-attempt-01.hashes.json` (written immediately after the run) | `c0eb9f45c7871a9b35131a2a7563006a8b56651ad906c3e5b5d26bd1b20eb886` |
| `…-attempt-01.analysis.json` | `5586f98d2d7379a7faf06794f5f7566ce6513d19236da0932539c246b52d7c67` |
| `results.jsonl` (worker terminal record) | `667b5c3cc9f1afd5a738accf847fc477989707b3974c5c62f275d8c8180d175a` |
| execution-evidence `SHA256SUMS` (including the trigger-6 review) | `9e1311e02cf75ab0f5a21f3f847f3a9ca518009e659f22835aebd3503c7deea0` |
| runner / manifest / checkpoint | `add0bd46…` / `391c2f02…` / `c7686983…` |

These hashes establish integrity relative to digests recorded at the time. They do not by
themselves establish provenance. The provenance chain rests on the pushed freeze commit, the
pre-execution record and the immediate hash record, all kept outside the attempt directory.
