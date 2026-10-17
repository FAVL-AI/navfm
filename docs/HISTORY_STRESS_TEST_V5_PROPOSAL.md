# History stress test v5: proposal (PREPARED; NOT FROZEN; NOT APPROVED; NOT RUN)

Nothing in this document is a model output. No score from this extension exists.

**Naming.** This is a **history stress test**, not a validated positive control. No input
tested so far is known to produce a response, so neither arm can be assumed to work as a
control. (This document was first drafted as a "positive control" proposal; it was renamed and
extended with the synthetic arm. The git history keeps the earlier draft.)

## Question
On the same 72 fixed in-region queries as v4, do two specified history interventions, much
larger than v4's, produce a response in the requested-goal score above the criterion declared
here?

Everything else is fixed and identical to v4:
- the query image;
- the requested goal;
- the reference batch and its row order;
- the checkpoint and preprocessing.

Background: v4 found at most 0.0016 change for substitutions of at most 0.28 m and about 25°
within the goal region.

## The two interventions (both fixed before any inference)

### H4: real history from a different scene instance
- **What it is.** Real frames from a different scene instance of the same corridor style:
  scene 3, the s_bend route, instead of the queries' scene 4, the junction route.
- **Donor episode.** For a query from variant V on `junction_run_000r`, the donor is
  `cmp-V-trunc-20261009-01/s_bend_run_000r`.
- **Donor frames.** The images seen at decisions k = 10…14 (frames 59, 65, 71, 77, 83). The same
  five serve every query of the episode.
  - *Why this window.* These are the first five decisions with at least five real predecessors,
    plus a margin, so no frame comes from the initial repeated history.
  - No other window was examined, and no image was viewed.
- **Authentication.** Every donor file's sha256 equals the donor episode's recorded
  `file_sha256`. The runner re-derives the frames from the episode record and refuses any other
  frame, variant or episode.
- **Measured before any score:**
  - The median mean-absolute pixel difference from the real H0 history slots is 16.5 (range
    10.0–26.2), on the stored 320×240 JPEGs. That compares with 9.7 for v4's H3 and 4.9 for H2.
  - The scenes' origins are about 20 m apart, but the camera cannot see across scenes, so that
    is not a measure of visual difference.

### H5: synthetic, out-of-distribution uniform history
This is **not a physically possible approach** and **not a validated positive control**. It is
an extreme input intervention.

- **Frame.** One fixed frame: a C-contiguous `uint8` RGB array of shape (240, 320, 3), every
  value 128.
  - 128 is the 8-bit midpoint, chosen a priori.
  - The shape is the size of the stored query images.
  - There is no sweep, and no value was chosen using model scores.
- **Identity.** The token `synthetic:uniform_rgb128_h240_w320_uint8` with sha256
  `06d4819637d1c753371096aae289b573bbfcb238abd672521369dbc9dc376469` of its bytes. The runner
  builds the array itself and verifies this digest. Any other synthetic token is refused.
- **Construction.** The five history slots are this frame, followed by the unchanged query image.
- **Preprocessing.** The deployed path applies:
  - the 4:3 crop is a no-op on 320×240;
  - the image is resized to 85×64;
  - `ToTensor` gives 128/255 = 0.501961 per channel;
  - after ImageNet normalisation the values are (0.074065, 0.205182, 0.426492) for R, G, B.

## Eligibility of the H4 donors (checked against the accessed-pilot exclusion)
- **The accessed pilot.** It is the closed two-layout, four-route prospective pilot:
  - routes `prospective_v1_layout{0,1}_route{0,1}`;
  - data in `navfm-training-evidence/prospective-collection-v*`, with ledger status
    `prior_layout_exposure: ACCESSED_NOT_UNINSPECTED`;
  - its layouts are procedural object layouts generated from secret seeds
    (`scripts/prospective_data_contracts_v1.py:14-50`).
- **The donors are neither pilot data nor pilot layouts.** They are runtime comparison episodes,
  and their fixture records say `layout: legacy_corridor`, `scene_index: 3`.
- **How this was established.** From the code, the record names and status fields only. The
  pilot's sealed specification was not opened.
- **Other exclusions:**
  - the donors are `split: dev`. `configs/splits/arrival_split_v2.json` lists `s_bend_run_0000/0001`
    under development, which permits diagnosis but never held-out reporting. The junction query
    routes are retired from confirmatory use (diagnostic only), consistent with v4 and v5's
    diagnostic framing;
  - they are absent from the checkpoint's 31 training trajectories
    (`navfm-training-evidence/option1-arrival-n31-e20-seed0-20261009-01/training_subset/traj_names.txt`):
    25 expansion-layout trajectories (`layout5`–`layout9`) and 6 legacy routes (`straight`,
    `left` and `right` runs, two each). None is `s_bend` or `junction`. *(Correction: an
    earlier draft called all 31 expansion layouts.)*
  - **Partial appearance aliasing (disclosed).** `configs/splits/arrival_split_v2.json` and
    `docs/ARRIVAL_RESEARCH_DECISION.md` record that training scene 8 shares the `scene % 5`
    appearance parameters (floor colour, obstacle offset) with the donor scene 3, and that
    training scene 9 shares them with the query scene 4. The partition layouts differ, so the
    overlap is partial. Neither the H4 donor frames nor the queries are therefore
    appearance-disjoint from training. This does not affect eligibility, but it limits how
    out-of-distribution H4 is.
  - held-out groups are not collected.

  Absence from training is noted, but on its own it did not settle eligibility.
- **Excluded alternatives:**
  - the expansion layouts, because they are training data;
  - the hospital smoke runs, because they recorded no images.

## Population and calls (exact)
- **Manifest.** `history_call_manifest_v5_stress.json`, sha256
  `294e726d193b46d4ffa6dbb0bae6e479b4f76383ed735d7f1032173fc93418c7`.
  - It was produced from the frozen v3 manifest (`391c2f02…`) by
    `scripts/history_sensitivity/build_history_stress_manifest_v5.py`.
  - It is kept external, in `$NAVFM_EVIDENCE_ROOT/history-positive-control-v5-prep-20261017/`.
  - The superseded 184-call draft (`b58cf90a…`) is retained there.

| Arm or control | Calls |
|---|---|
| H0_real, repeat 0 (72), plus repeats 1–2 on the same 12 control queries as v4 | 96 |
| H4_other_scene_history | 72 |
| H5_uniform_synthetic_history | 72 |
| CTRL_goal_only | 12 |
| CTRL_reversed_node_rows | 4 |
| **Total (exactly; acceptance requires all of them; ceiling 320)** | **256** |

- The H0 and control calls are byte-identical to v4's. H0 is re-run so that every Δ is paired
  within the same process.
- There are no H1, H2 or H3 calls, and no other arm, donor, window or synthetic value.

## Runner and resource contract
- **Same runner,** `scripts/history_sensitivity/history_runner.py`. Production runs only the two
  pinned manifests, at their exact counts:
  - v4: 306 calls;
  - v5: 256 calls.
- **Unchanged from v4:**
  - deployed-code staging and the origin checks;
  - restricted checkpoint loading;
  - forward accounting;
  - the 600 s wall clock;
  - the 4 GiB PyTorch-allocator cap and the sampled process-memory guard;
  - one attempt, no retries;
  - the immediate `hashes` step;
  - admission.
- **Added:**
  - per-call digests of the exact `obs` and `goals` tensors fed to the model;
  - query episodes must be declared;
  - the declared criterion is computed per stress arm.
- **Side effect on v4.** A v4 rerun with this runner also needs the donor records under the
  evidence root.
- **Proposed attempt directory:** `$NAVFM_EVIDENCE_ROOT/history-stress-test-v5-attempt-01`.

## Reporting and response tiers (declared before execution; applied to H4 and H5 separately)
- **Primary.** The continuous paired Δ = score(arm) − score(H0 repeat 0) for all 72 queries,
  per episode and per route, as quantiles and max |Δ|, together with:
  - the ratio to the episode reference scale;
  - the ratio to the replay and logged margins.
- **Gate decisions.** Unchanged and flipped decisions at 7.745, in both directions.
- **Numerical controls:** N_repeat, N_batch and N_order, measured in the same run.
- **Replay agreement on H0,** as in v4, keeping the v4 k034 disagreement visible.
- **Tiers:**
  - *Detectable:* median |Δ| exceeds `bound = max(0.0016, this run's max |N_batch|)`, overall
    **and** in at least 3 of the 4 episodes.
  - *Detectable but negligible:* detectable, with median |Δ| below 1% of the pooled reference
    scale (1.18).
  - *Not detectable:* otherwise.

  The runner computes them (`stress_response_criterion`), and they are tested on synthetic met,
  not-met and negligible cases. The tiers are descriptive. No inferential test is made.

## Interpretation (fixed now)
| Outcome for an arm | What it supports | What it does not support |
|---|---|---|
| Detectable (non-negligible) | The score is sensitive to this history intervention on these queries; the v4 null is consistent with the size of v4's substitutions | Useful temporal reasoning; any cause of stopping failure; relevance to deployed histories (H5 is physically impossible; H4 is far from any real approach) |
| Detectable but negligible | The score responds to this intervention only negligibly | That history is unused |
| Not detectable | Only the bounded tested-input conclusion: these specified substitutions produced no response above the predefined criterion | That history is unused by the model |

"A null is the most likely outcome" was a reviewer's **hypothesis, not a measured
probability**, and no prediction is made here.

**Limitation stated in advance.** H5, like v4's H1, is a static history: five identical
frames, with no apparent motion. A response to H5 could therefore reflect the missing motion
rather than the missing content. H4, which contains real motion, partly separates the two.
Claims stay limited to "this intervention".

## Not in scope
- execution, until approved;
- any further control, sweep, value or donor;
- illumination or lighting work;
- Isaac, acquisition, fitting, navigation or threshold changes.

## Verification
- **Runner suite** with CUDA hidden: **57 tests, 57 passed, 0 failed, 0 errors, 0 skipped**
  (`test_stress_run2_junit.xml` in the external preparation directory, against the hashes below).
- **v5 tests:**
  - full 256-call completion with a stand-in model, then admission and per-arm criteria;
  - the pinned population;
  - H4 donor binding: wrong decision, wrong variant, undeclared episode, donor in an H0 slot, a
    donor frame with the expected H0 file name (refused by the own-episode binding), and a query
    relabelled to a donor route (refused with the declared-episode reason) are all refused;
  - H5 binding: an undeclared synthetic token, an H5 call with a real frame, and a synthetic
    frame in an H0 slot are all refused;
  - the synthetic array equals the declared specification;
  - admission refuses a stress arm whose tensor digest equals H0's, and requires H0 repeats to
    have identical tensors;
  - production preflight with CUDA hidden stops at `NO_CUDA` before any model is built.
- **Reviews (trigger 4):**
  - *Round 1,* of the 184-call draft: 0 blocking; fixes applied.
  - *Round 2,* covering H5 and the round-1 fixes: 0 blocking. It confirmed:
    - H5 is refused when wrong, cannot pass as a real frame, and reaches the deployed
      preprocessing exactly as a decoded image would;
    - the arithmetic;
    - the 256-call manifest;
    - D2, with no exclusion relaxed;
    - the framing.

    Fixed after round 2:
    - R3, the test now asserts the reason;
    - T2, the same-filename attack test and the comment;
    - P3, digest checks in admission;
    - F-1, stale wording;
    - V-1, the limitation above;
    - D2, the training-list citation.
  - The round-2 fixes have not been re-reviewed.

## Freeze candidate (not frozen; for execution approval)
| File | sha256 |
|---|---|
| `scripts/history_sensitivity/history_runner.py` | `288b6cf71814e6057cb9ce4a05d05960ffe38c241cd523e91ff5187346c20f74` |
| `scripts/history_sensitivity/test_history_runner.py` | `c9c54203b4c53062287c71c8a5312da40326aff2bfcc360d730bdd7d22d5e75d` |
| `scripts/history_sensitivity/history_substitutes.py` (test only) | `fa56cdd57aab5b47851670703ce19e412211a817f5265de51b5703f52d09aa21` |
| `scripts/history_sensitivity/build_history_stress_manifest_v5.py` (reproduces the manifest byte-identically) | `1a0194bfce07ce10e4dc4cdc9fcfcf714265ef1855a82768a6b7e15ed29da436` |
| `$NAVFM_EVIDENCE_ROOT/history-positive-control-v5-prep-20261017/history_call_manifest_v5_stress.json` | `294e726d193b46d4ffa6dbb0bae6e479b4f76383ed735d7f1032173fc93418c7` |
| H5 synthetic frame bytes | `06d4819637d1c753371096aae289b573bbfcb238abd672521369dbc9dc376469` |
| checkpoint (unchanged) | `c7686983099080649dde0eaf79575149c26239321e23cf96788b3dd25b0d5d7c` |

**Execution command (NOT approved).** The same sequence as v4: `run`, then `hashes`
immediately, then `admit` and `analyse` with `--expected-runner-sha256 288b6cf7…0f74`. Use
`--manifest` set to the v5 manifest, `--manifest-sha256 294e726d…18c7`, `--attempt-dir`
`$NAVFM_EVIDENCE_ROOT/history-stress-test-v5-attempt-01` and `--evidence-root`. Check free disk
space immediately before launch.
