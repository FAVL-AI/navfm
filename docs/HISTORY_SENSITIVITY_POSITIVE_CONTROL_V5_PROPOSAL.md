# History positive control v5: proposal (PREPARED; NOT FROZEN; NOT APPROVED; NOT RUN)

Nothing in this document is a model output. No score from this extension exists.

## Question
On the same 72 fixed in-region queries as v4, does a much larger history substitution produce
a detectable response in the requested-goal score?

The substitution replaces the five history frames with frames from a **different scene
instance of the same corridor style** (scene 3, the s_bend route, instead of scene 4, the
junction route). Everything else stays fixed, identical to v4:
- the query image;
- the requested goal;
- the reference batch and its row order;
- the checkpoint and preprocessing.

Why this matters: v4 found at most 0.0016 change for substitutions of at most 0.28 m and about
25° within the goal region. v4 had no positive control, so it could not separate low history
sensitivity from substitutions too small to matter.

## Donor rule (fixed before any score)
- **Donor episode.** For a query from variant V on `junction_run_000r`, the donor is
  `cmp-V-trunc-20261009-01/s_bend_run_000r`.
- **Donor frames.** The images seen at that episode's decisions k = 10…14 (frames 59, 65, 71,
  77, 83). The same five frames serve every query of the episode, so the choice cannot depend on
  any query's score.
  - *Why k = 10…14.* These are the first five decisions with at least five real predecessors,
    plus a margin, so no frame comes from the initial repeated history.
  - No other window was examined. The only per-donor quantities computed were the descriptive
    pose and pixel figures below, and only for this window. No image was viewed.
- **Authenticated.** Every donor file's sha256 equals the donor episode's recorded `file_sha256`.
  The runner re-derives the donor frames from the episode record and refuses anything else. This
  includes a hash-correct frame from another decision, and any frame from an undeclared episode;
  both cases are tested.
- **Permitted, with the records cited:**
  - **Dev split.** Every donor's `runtime_manifest.json` has `route.split: dev`. They belong to
    the same, already-exposed component comparison (`cmp-*-trunc-20261009-01`) as the queries,
    whose split is `test`.
  - **Not training data.** The checkpoint's training list,
    `navfm-training-evidence/option1-arrival-n31-e20-seed0-20261009-01/training_subset/traj_names.txt`,
    has 31 trajectories, all from the expansion layouts. None is `s_bend` or `junction`.
  - **Not sealed.** Held-out groups are specified but not collected
    (`docs/ARRIVAL_RESEARCH_DECISION.md`).
  - **Accessed pilot: not fully established.** The closed accessed pilot is a two-layout,
    four-route kinematic pilot recorded under training evidence
    (`docs/PROSPECTIVE_SCORING_CONSOLIDATION_V2.md`). No record found here shows that it
    includes these runtime `cmp-*` episodes, but its layout identities were not checked
    route by route.
- **Excluded alternatives:**
  - The expansion layouts (`layout5`–`layout9`) are more visually distinct, but they are
    **the checkpoint's training data** (see the training list above). They are excluded for
    that reason, and because their relation to the accessed pilot was not established.
  - The hospital smoke runs recorded no images.

**Measured before any score:**

| Quantity | Value |
|---|---|
| World offset between donor frames and query | 19.6–20.0 m. This is the spacing between scene origins (y ≈ 60 vs 80), not visual distance: the camera cannot see across scenes, so this figure says nothing about how different the frames look |
| Mean-absolute pixel difference from the real H0 history slots | 10.0–26.2 (median 16.5) |
| Same measure, v4 arms (for comparison) | H3 median 9.7, H2 median 4.9 |

The pixel differences are measured on the stored 320×240 JPEGs, not at the model's input
resolution. The H4 median is about 1.7 times H3's.

**Limitation stated in advance.** Both scenes are the same legacy-corridor style, so the
visual difference is moderate. v4's H1 arm already used a quite different history (the query
image repeated, with no ego-motion) and produced at most 0.0016. A null result from H4 is
therefore the most likely single outcome, and it would be uninterpretable (see "Open decision").

## Population and calls (exact)
- **Manifest.** `history_call_manifest_v5_pc.json`, sha256
  `b58cf90a97f562e7cd4353112e0c47810310f8e57805194d98b9207ec0330d61`.
  - It was produced from the frozen v3 manifest (`391c2f02…`) by
    `scripts/history_sensitivity/build_positive_control_manifest_v5.py`.
  - It is kept external, in
    `$NAVFM_EVIDENCE_ROOT/history-positive-control-v5-prep-20261017/`.

| Arm or control | Calls |
|---|---|
| H0_real, repeat 0 (72), plus repeats 1–2 on the same 12 control queries as v4 | 96 |
| H4_unrelated_location_positive_control | 72 |
| CTRL_goal_only | 12 |
| CTRL_reversed_node_rows | 4 |
| **Total (exactly; acceptance requires all of them)** | **184** |

- The H0 and control calls are byte-identical to v4's. H0 is re-run so that every Δ is paired
  within the same process.
- No H1, H2 or H3 calls are made, and no other arm.
- There is no sweep over donors, distances or frames.

## Runner and resource contract
- **Same runner.** `scripts/history_sensitivity/history_runner.py`, extended by a production
  profile table. Production runs only the two pinned manifests:
  - v4: 306 calls;
  - v5: 184 calls.

  Admission requires the exact count of the manifest used.
- **Unchanged from v4:**
  - deployed-code staging and the origin checks;
  - restricted checkpoint loading;
  - forward accounting (cap equals the call count; ceiling 320);
  - the 600 s wall clock and its three layers;
  - the 4 GiB PyTorch-allocator cap and the sampled process-memory guard;
  - one attempt, no retries;
  - the immediate `hashes` step;
  - admission and analysis.
- **Proposed attempt directory:** `$NAVFM_EVIDENCE_ROOT/history-positive-control-v5-attempt-01`.
- **Additions from the review:**
  - each result records sha256 digests of the exact `obs` and `goals` tensors fed to the model;
  - query episodes must be declared query episodes;
  - the runner computes the detectable-response criterion itself.
- **Side effect on v4.** A v4 production rerun with this runner also needs the donor episode
  records under the evidence root. That makes v4 stricter, with no other change.

## Reporting (declared before execution)
- **Primary.** The paired Δ = score(H4) − score(H0 repeat 0) for all 72 queries. Report it per
  episode and per route as p10/p25/median/p75/p90 and max |Δ|, together with:
  - the ratio to each episode's reference scale;
  - the ratio to each query's margin, both replay and logged;
  - flips at 7.745.
- **Comparisons, measured in the same run where possible:**
  - N_repeat;
  - N_batch and N_order;
  - the v4 maxima, as a published reference: history max |Δ| 0.0016, N_batch max 0.0076.
- **Replay agreement** is re-measured on H0 exactly as in v4. That includes the per-query gaps
  and the gate agreement, keeping the v4 disagreement `C_verify/junction_run_0000/k034` visible.

**Detectable response (fixed now).** H4 counts as producing a detectable response if **both**
hold:
1. median |Δ_H4| exceeds the larger of:
   - the v4 history maximum (0.0016);
   - the largest |N_batch| measured in this run;
2. at least 3 of the 4 episodes have median |Δ_H4| above that same bound.

The bound is descriptive. No inferential test is made, because queries share frames and donors
are shared within an episode.

**Magnitude tier (fixed now).** A detectable response whose median |Δ_H4| is below 1% of the
pooled in-region reference scale (median 1.18) is reported as **detectable but negligible**.
The runner computes the bound, the episode medians, the 3-of-4 count, the ratio and the tier
(`positive_control_criterion`), and these are tested on synthetic met, not-met and negligible
cases.

## Interpretation rules (fixed now)
| Outcome | Interpretation | What it does not show |
|---|---|---|
| Detectable and non-negligible | The score is not invariant to history in this regime, and the v4 null is consistent with the size of the v4 perturbations | That history matters in deployment or for stopping, or how large the v4 effect would have been |
| Detectable but negligible | The score responds to history only at a negligible magnitude, even for this larger substitution | That history is unused |
| Detectable response with flips | Large history changes can move gate decisions on these queries | The same, plus no claim about deployed histories, which are never 20 m away |
| No detectable response | **Ambiguous** between low history sensitivity and an ineffective control (same corridor style; median pixel difference 16.5) | That history is unused by the model |

## Open decision (C1, for Frank)
The review rated a likely uninformative outcome as nearly blocking. It proposes adding one
extreme level known to change the input: five identical synthetic frames, such as uniform grey,
pinned by hash in the runner. That would be +72 calls, 256 in total, under the 320 ceiling, at
two levels rather than a sweep.

Synthetic frames are not "images from a different location", so they depart from the requested
specification. Not adopted without approval. The alternatives are:
1. add the synthetic level;
2. keep the single H4 level and accept now that a null outcome will not be cited as evidence for
   anything.

## Not in scope
- execution, until approved;
- any broader sweep;
- illumination or lighting work;
- Isaac, acquisition, fitting, navigation or threshold changes.

## Verification so far
- **Runner suite, extended with v5 tests,** with CUDA hidden: 51 tests, 51 passed, 0 failed,
  0 errors, 0 skipped (`test_run4_junit.xml` in the external preparation directory, against
  runner `dcd208d1…`).
- **v5 tests:**
  - full 184-call completion with a stand-in model, then admission and analysis;
  - the pinned production population;
  - a donor frame outside the rule, refused;
  - a donor from an undeclared episode, refused;
  - a hash-correct frame from the other variant's donor, refused;
  - a donor frame placed in an H0 slot (swapped consistently so pairing passes), refused by the
    own-episode binding;
  - a query relabelled to a donor route, refused;
  - tensor digests differ between H4 and H0 and are identical across repeats;
  - production preflight with CUDA hidden, which stops at `NO_CUDA` before any model is built.
- **Changed v4 expectation.** A production manifest with a call removed is now refused as "not
  pinned". It no longer matches any profile digest, so the refusal happens before the count rule
  is reached.
- **Independent review (trigger 4):** 0 blocking.
  - Confirmed: the manifest is exactly derived from v3; the donor rule has no score dependence;
    the profile pinning; the donor binding.
  - Fixed: R5 (criterion in code), T2 (two negative tests), D3 (framing and window
    rationale), P2 (magnitude tier, narrower claims), R3 (query episode check), P3 (tensor
    digests), D2 (records cited).
  - Noted: R4.
  - Open: C1 (above).
- **The fixes after the review have not been re-reviewed.**
