# History stress test v5: measured results (attempt 01)

**Scope.** One approved execution of the frozen v5 history stress test
(`docs/HISTORY_STRESS_TEST_V5_PROPOSAL.md`, freeze record
`gates/history_stress_v5/FREEZE_RECORD.md`, commit `70ba823`). It is an offline replay
diagnostic of the requested-goal check's score. It does **not** measure stopping. H5 is an
out-of-distribution stress input, **not** a validated positive control.

> **Conclusion.** In this offline replay, the tested other-scene and uniform-grey history
> substitutions produced small score changes below the predeclared criterion. This extends the
> earlier history-substitution finding but does not identify the cause of the closed-loop
> failures or demonstrate improved stopping.

The v4 results (`docs/HISTORY_SENSITIVITY_OFFLINE_V4_RESULTS.md`, on branch
`research/history-sensitivity-offline-v4`) are unchanged and remain the record for arms H1–H3.

Raw evidence is external and read-only:
- `$NAVFM_EVIDENCE_ROOT/history-stress-test-v5-attempt-01/` holds the attempt records and
  per-call results;
- `$NAVFM_EVIDENCE_ROOT/history-stress-test-v5-attempt-01.{hashes,analysis}.json`;
- `$NAVFM_EVIDENCE_ROOT/history-stress-test-v5-execution-20261017/` holds the preflight checks,
  command, output, a results summary and digests.

Digests are listed at the end.

## Population
- **Routes: 2** (`junction_run_0000`, `junction_run_0001`).
- **Episodes: 4.** Each route was recorded under two variants, `C_verify` and `D_both`.
- **Queries: 72** recorded in-region decisions, the same 72 as v4: C j0 19, C j1 18, D j0 19,
  D j1 16.
- **Checkpoint: 1** (`option1-arrival-n31-e20-seed0-20261009-01/epoch_020.pth`). These episodes
  were already exposed in earlier diagnostics.
- **Donor history (H4):** `s_bend` scene 3, decisions 10–14. Eligible under the existing
  exposure exclusions (see the proposal and the trigger-4 record). Training scenes partially
  share appearance with both donor and query scenes (disclosed in the proposal, D2).
- **Distinct substitute histories.** H4 uses one fixed five-frame donor sequence per episode, so
  its 72 calls cover **4 distinct donor histories**. H5 uses **1** (uniform grey). The 72 deltas
  per arm are therefore not 72 independent history samples.

## Part A: execution and admission status

### Pre-execution checks (2026-10-17T06:21)
- **Commit.** Local HEAD = remote `research/history-positive-control-v5` =
  `70ba82348080d6ac7bc4e1c46055dd87f4da4688`, with a clean worktree.
- **Frozen hashes.** Runner `288b6cf7…`, builder `1a0194bf…` and manifest `294e726d…` match the
  freeze record. The external preparation `SHA256SUMS` (`49eed366…`) check passed.
- **Review closure.** Recorded in `gates/redteam/trigger4-history-positive-control-v5-2026-10-17.md`.
- **Attempt directory.** Unused.
- **Free disk.** 63.9 GB.
- **GPU.** 2051 MiB in use. Listed compute processes: a desktop daemon (251 MiB) and an
  Unreal editor (940 MiB) that was not launched by any command in this execution. The process-memory guard samples only the
  worker's PID, so neither affected the limits.

### Execution
- **Limits (unchanged from v4).** 600 s wall clock, 320 absolute forward ceiling, 4 GiB
  PyTorch-allocator cap, sampled process-memory guard, no retries.
- **Environment:**
  - torch 2.7.0+cu128, CUDA 12.8, cuDNN 9.7.1;
  - RTX 4080 SUPER, driver 580.178.04;
  - `cudnn.benchmark` False, `deterministic` False, matmul TF32 False, cuDNN TF32 True, matmul
    precision "highest".
- **Process status.** Supervisor `COMPLETE`, natural exit, worker exit code 0. No forced
  termination, no session survivors at cleanup, 0 retries.
- **Forwards.** 256 listed and 256 counted at the model hook; 0 during load.

  | Arm | Calls |
  |---|---|
  | H0, real history | 96 (72 queries + 24 repeat calls forming 12 triples) |
  | H4, other-scene history | 72 |
  | H5, uniform-grey synthetic history | 72 |
  | CTRL_goal_only | 12 |
  | CTRL_reversed_node_rows | 4 |
  | **Total** | **256** |

- **Time.** Execution ended at 18.0 s of the 600 s limit. Model load took 6.2 s; the worker
  took 17.0 s.
- **Memory.**
  - Allocator peaks: 289 MB reserved and 218 MB allocated, against the 4 GiB cap.
  - Process GPU memory, sampled: peak 576 MiB; the worker PID was present in 15 of
    18 samples, 0 failed.
  - Peak RSS: 1.42 GB (1.33 GiB).
- **Source origin.** All 16 `navfm` and `vint_train` modules were loaded from the staged,
  digest-matching snapshot.
- **Checkpoint.** Bound in the attempt preflight at `c7686983…5d7c`.
- **Immediate output hashes.** `hashes` ran right after `run`. Its record (`f1876c2b…`) covers
  59 attempt files, and all 59 still matched when this report was written.
- **Admission.** Frozen `admit` with the expected runner digest: **admitted, no reasons**.
- **Analysis.** Frozen `analyse`, unchanged.

### Inputs reached the model as specified
For every H4 and H5 call, compared with the paired H0 call:
- the goal tensor digest is identical (72 of 72 per arm);
- the observation tensor digest differs (72 of 72 per arm);
- the current (sixth) frame is identical, and the five history frames differ. In H5, all five
  history frames carry the synthetic frame's digest (`06d48196…6469`).

## Part B: scientific findings (replay regime; descriptive; 2 routes, 4 episodes, 1 checkpoint)

### Controls
- **Identical-input repeats:** bit-identical within the process (12 triples, N_repeat = 0).
  This does not bound noise across processes or kernel selections.
- **N_batch (goal-only batch minus H0):** |value| ≤ 0.0076, over 12 calls. This sets the
  response bound below.
- **N_order (reversed reference rows):** 0.0000, over 4 calls.

### Replay agreement with the logged deployed scores (72 queries)
- **Median |gap| 0.044** (p10/p90 of the signed gap −0.043 / +0.114; max |gap| 0.189). The
  prospective criterion (median |gap| ≤ 0.085) is met. As declared, this does not establish
  deployment equivalence.
- **Gate agreement at 7.745: 71 of 72.** The one disagreement is again
  `C_verify/junction_run_0000/k034`, the same query as in v4. Replay does not reproduce that
  logged gate decision.

### History substitution (Δ = arm − H0; the same query image, goal, reference rows and order)
Predeclared criterion: a response is detectable only if median |Δ| exceeds
max(0.0016, max |N_batch|) = 0.0076, overall **and** in at least 3 of 4 episodes.

| Arm | Calls | median \|Δ\| | max \|Δ\| | Episodes above bound | Criterion tier | Flips at 7.745 |
|---|---|---|---|---|---|---|
| H4, other-scene history | 72 | 0.0048 | 0.0059 | 0 of 4 | not detectable | 0 |
| H5, uniform-grey history | 72 | 0.00021 | 0.0013 | 0 of 4 | not detectable | 0 |

Predeclared ratios:

| Quantity | H4 | H5 |
|---|---|---|
| max \|Δ\| / logged margin | 0.049 | 0.00084 |
| max \|Δ\| / replay (H0) margin | 0.061 | 0.0040 |
| max \|Δ\| / episode reference scale | 0.015 (D j1) | 0.0034 |
| median \|Δ\| / pooled reference scale (1.18) | 0.0041 | 0.00018 |

Both arms are **below the predeclared response criterion**. No gate decision flipped in either
direction.

- **"Not detectable" is relative to the predeclared bound, not evidence of zero response.**
  The H4 shift is deterministic (repeats are bit-identical), same-sign in 72 of 72 calls and
  small. Its median |Δ| (0.0048) is about three times the largest v4 history effect (0.0016).
- **Sensitivity of the tier to the bound.** The bound is the largest of 12 |N_batch| values; the
  top three are 0.0036, 0.0049 and 0.0076. With the second-largest as the bound, H4 would still
  be below it. With the third-largest, H4 would be above it overall and in 3 of 4 episodes. The
  predeclared verdict is unchanged; this is disclosed because it rests on the top two control
  values. N_batch compares a batch of 1 with batches of 6–8; within an H0/H4 pair the batch
  shape and composition are the same.

**Per episode and per route:**

| Arm | Unit | n | median Δ | max \|Δ\| | Flips |
|---|---|---|---|---|---|
| H4 | C j0 | 19 | −0.0053 | 0.0059 | 0 |
| H4 | C j1 | 18 | −0.0034 | 0.0051 | 0 |
| H4 | D j0 | 19 | −0.0057 | 0.0059 | 0 |
| H4 | D j1 | 16 | −0.0045 | 0.0057 | 0 |
| H4 | route j0 | 38 | −0.0056 | 0.0059 | 0 |
| H4 | route j1 | 34 | −0.0037 | 0.0057 | 0 |
| H5 | C j0 | 19 | +0.00017 | 0.00034 | 0 |
| H5 | C j1 | 18 | +0.00011 | 0.00040 | 0 |
| H5 | D j0 | 19 | +0.00023 | 0.00048 | 0 |
| H5 | D j1 | 16 | +0.00039 | 0.0013 | 0 |
| H5 | route j0 | 38 | +0.00021 | 0.00048 | 0 |
| H5 | route j1 | 34 | +0.00020 | 0.0013 | 0 |

- **Sign.** All 72 H4 deltas are negative. 11 of 72 H5 deltas are negative. This is recorded as
  observed; no interpretation is attached to it here.
- **Scale.** H0 replay scores range from 4.81 to 16.22 across the 72 queries.

### What this establishes
In this offline replay, on these 72 recorded in-region queries, replacing the five preceding
history frames with frames from another scene, or with a uniform-grey synthetic frame, changed
the requested-goal score by at most 0.0059, below the predeclared criterion, and never moved a
decision across the 7.745 threshold. Together with v4, the score showed **low sensitivity to the
tested history substitutions**.

### What it does not establish
- **Architectural independence from history.** These interventions do not show that the model
  ignores history in general, nor which internal pathway carries or suppresses it.
- **Negligible impact on navigation.** Being below the score criterion does not establish that
  the effect on closed-loop behaviour is negligible.
- **That H5 validates the measurement.** H5 is out-of-distribution; it is not a positive
  control. No input in this run has been shown to move the score through the history channel.
- **Deployment behaviour.** The deployed inputs were live arrays rather than JPEGs, and replay
  does not reproduce one logged gate decision (k034).
- **The cause of the closed-loop failures, or improved stopping, calibration or remedies.** Nor
  any generalisation beyond two routes, four episodes, one checkpoint and these exposed
  episodes.
- **The separate contribution of the goal pathway.** The goal encoder's input (current frame
  and goal image) is identical across arms by design, so this run does not separate how much of
  the score that pathway carries.
- **Breadth of the substitutions.** Only 4 donor histories and 1 synthetic history were tested.
- **Out-of-distribution distance for H4.** Training scenes partially share appearance with the
  donor and query scenes, which limits how far H4 is from the training data.

## Review
Repository adversarial-review trigger 6 (a finding that depends on the absence of an effect)
applies. An independent read-only review recomputed every number and digest from the raw
evidence; the claim survives as a descriptive result. The record and the corrections applied are
in `gates/redteam/trigger6-history-stress-v5-results-2026-10-17.md`.

## Digests
| Item | sha256 |
|---|---|
| `…-attempt-01.hashes.json` (written immediately after the run) | `f1876c2b2f88d0d720d6d1600f4f83f7861c8cef203c2dc5da3575871cbdaff1` |
| `…-attempt-01.analysis.json` | `547c6faf6222d75420d1bc27b9f7cd4e53621bb9adcbf84be3f330758c2a6c80` |
| `results.jsonl` (worker terminal record) | `e37c8ece17f64f9f188635c2b273691aaeb9f2e4effa2841fc8cd152f0df1143` |
| Execution-evidence `SHA256SUMS` | `cefd2b78045314313baa6eb6154f52ed4379006357c2beb1d107935eac56f6b4` |
| v5 call manifest | `294e726d193b46d4ffa6dbb0bae6e479b4f76383ed735d7f1032173fc93418c7` |
| Runner | `288b6cf71814e6057cb9ce4a05d05960ffe38c241cd523e91ff5187346c20f74` |
| Checkpoint | `c7686983099080649dde0eaf79575149c26239321e23cf96788b3dd25b0d5d7c` |
