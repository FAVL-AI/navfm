# Component comparison v2: stage-2 gate report (development, 2026-10-10)

**Scope.** These are development trials on development layouts, informed by previously
inspected v1 failures. Calibration overlaps the same routes. The six held-out groups
stay sealed and illumination work is paused.

A PASS here justifies fresh complete-episode evaluation (stage 3), and nothing more.
It does not establish:
- held-out generalisation;
- illumination robustness;
- sim-to-real transfer;
- novelty or a SOTA claim.

**Protocol and records**
- Protocol: v2.1, frozen at `83101fa` (config sha256 `44285743…a088a`), plus amendment 2
  frozen at `8959333` (record `configs/eval/component_comparison_v2_amendment_2.json`,
  pinned sha256 `6c3d7b2a…b64f`).
- Gate record: `gates/v2/stage2-gate-record-20261010.json`. This is the output of
  `scripts/analyse_component_comparison_v2.py` (script sha256 `9ea90041…`) with
  `--freeze-commit 83101fa --amendment-commit 8959333 --ledger-commit eb418e5`.
- Evidence root: `/home/favl/navfm-runtime-evidence` (not in git).

## 1. Gate decisions (frozen criteria, computed by the analysis)

| Component | Stage-2 gate | Stage 3 |
|---|---|---|
| V2b_confirm_steer (confirmation plus steering by the requested goal; steering alone is not tested) | **PASS, exactly at threshold** (3 of 4; ≥ 3 required) | runs, with A and C1 |
| R2_recover (the recovery bundle: in-place scan, scan budget, entry limit, non-arrival relocalisation; exit shared with B1x) | **PASS, exactly at threshold** (6 of 8 hard views; ≥ 6 required), amended after the data were seen (§4); 4 of the 6 successes sit on the ±1-node tolerance (§5) | runs, with A, B1x and B1 |
| V2a_confirm (confirmation, v1 steering) | FAIL (2 of 4 correct stops; ≥ 3 required) | does not run |
| B1_bounded (backward-step filter, look-alike question) | FAIL (did not correct every evaluable encounter; contacts 6 > A's 4) | does not run as a candidate (runs as R2's reported comparator) |

A failed gate is a result. Neither failed component is repaired within v2.

**Edges and previews.** Both passing gates sit exactly on their thresholds. Both also
include a cell whose outcome was previewed by a disclosed pre-freeze smoke run
(amendment v2.1):
- R2 on kidnapped_c `junction_run_0000`: in the smoke run it relocalised after 11 scan
  decisions and stopped. The counted attempt is an uninformative-view success, one of
  the edge cases.
- V2b on arrival_truncated `junction_run_0000`: in the smoke run it latched and
  stopped. The counted attempt is a correct stop.

No multiplicity correction is applied across the four gates.

## 2. Accounting

- **Collections and attempts**
  - 56 collections exist: 44 original (`-20261010-01`) and 12 re-collected under
    amendment 2 (`-20261010-02`).
  - 140 planned attempts in total: 92 original and 48 re-collected.
- **Counted attempts: 92.** Every counted attempt is PASS, and there are no integrity
  failures.
  - The 44 look-alike, premature-confirmation and arrival attempts come from `-01`.
  - The 48 recovery attempts come from `-02`.
- **Excluded or superseded: 48** original kidnap attempts. The analysis logs them per
  collection: 12 SUPERSEDED entries, one per `-01` kidnap collection, with no route.
  They are kept on disk and never scored.
  - 34 of them were PASS.
  - 14 were FAILED by the readback yaw-wrap defect (§4).
- **Reruns:** none were needed. All 48 re-collected attempts passed on their first
  attempt, so no `-20261010-03` collection exists.
- **Smoke runs:** 5 before the freeze (disclosed in amendment v2.1), not counted. Two
  of them previewed counted cells of the passing gates (§1).
- **Launch ledger:** `gates/v2/v2-amendment2-launch-ledger.jsonl`. It shows 12 launches
  from `daa3978` with a clean worktree, every exit 0, and one robot USD digest
  (`0ba6ca5d…`) before and after every collection.
- **Integrity checks:** all pass on all 92 counted attempts. They cover provenance at
  the freeze or amendment, the checkpoint, chain, config, qualification, budget,
  perturbation, resume and replay, the launch ledger and goal identity. Non-repository
  influencing files are identical across attempts.

**Negative controls.** Each control re-analyses the same evidence with one expected
value deliberately wrong. All five fail integrity, and every affected gate drops to
INCOMPLETE.

| Control | Failed attempts | Failing check |
|---|---|---|
| variant | 92 | component configuration |
| chain | 92 | chain_sha |
| start_lost | 92 | start_lost |
| trial | 92 | trial |
| resume | 28 (the resumed attempts) | see below |

The resume control fails closed through an exception, an `IndexError` in the
replay-applied comparison: a handover shifted by one decision reads one command past
the recorded list. It therefore shows that a shifted handover cannot pass. The
`resume` check's own conditions are exercised by unit tests, not by this control.

## 3. Matched-state starts: fidelity and state initialisation

28 attempts used replay-to-handover: 20 look-alike and 8 premature-confirmation.

| Measure | Result | Bound |
|---|---|---|
| Position error at handover | exactly 0.0 m (by construction: replay from the recorded start) | 0.02 m |
| Heading error at handover | exactly 0.0° (by construction) | 2° |
| Image mean absolute difference | 0.60–0.69 grey levels | 2.5 |
| Maximum distance-prediction difference | 0.03–0.24 | 1.0 |
| Search window | identical in 28 of 28 | identical |

No contact occurred before any handover, and every fidelity check passed. Only the image
and distance bounds test view fidelity.

**What was restored at the handover:**
- the simulator state and the 6-image observation history, rebuilt by replaying the
  recorded commands for decisions 0 to K−1 from the recorded start pose;
- the current node, set to the node the source episode recorded at decision K−1;
- the lost-at-start flag, where declared (kidnap trials only, which do not resume).

**What was reset to fresh values:** each variant's internal state.
- B1: pending proposal and lost counters.
- V2a and V2b: confirmation votes and approach phase.
- R2: recovery attempts.
- A holds no state beyond its node, so its handover is exact.
- B1 cannot accept a multi-node jump on the handover decision itself (known limitation).

## 4. Amendment 2: why the recovery block was re-collected

- **The defect.** The post-episode readback compared the writer's unwrapped yaw with
  the raw captured yaw. The 14 attempts whose heading crossed ±π were recorded as
  FAILED, after they had run.
  - Exactly those 14 crossed ±π; none of the 78 passing attempts did.
  - They were 8 of R2's 16 attempts (its in-place scans), 3 of B1's and 3 of B1x's.
- **Fixes:** `284045d` and `1273db9`, with tests.

**Gates as collected, before the amendment** (`v2-stage2-analysis-20261010-01.json`,
unchanged):

| Component | Gate |
|---|---|
| B1 | FAIL |
| V2a | FAIL |
| V2b | PASS |
| R2 | INCOMPLETE (14 attempts without a PASS) |

**R2 gate inputs as collected** (14 attempts unscored):

| Measure | R2 | B1x |
|---|---|---|
| Uninformative-view successes | 2 | 1 |
| All-trial successes | 8 | 8 |
| Wrong stops | 0 | 1 |

**Inferred outcomes of the 14 failed attempts.** These were read from their saved
transitions (`v2-stage2-kidnap-first-attempts-inferred-20261010-01.json`) and disclosed
before the re-collection:

| Attempts | Inferred outcome | Final distance from the goal |
|---|---|---|
| R2, all 8 (kidnap a and b `s_bend_run_0000`; kidnap c both s_bend; kidnap d all four) | ended on a stop or halt before the budget | 0.13–0.31 m |
| B1x, kidnap c `s_bend_run_0001` | ended (stopped) | about 0.51 m, just outside the radius |
| B1 kidnap c (3: `s_bend_run_0000`, `s_bend_run_0001`, `junction_run_0001`) and B1x kidnap c (`s_bend_run_0000`, `junction_run_0001`) | timed out | — |

Decisions and contacts of these 14 were never written.

The decision to amend was therefore taken when the likely recovery outcome was readable.
For that reason the whole block was re-collected, including attempts that had passed,
rather than only the failures.

**What the re-collection settles, and what it does not.** The pre-declared concordance
(`scripts/concordance_kidnap_v2.py`, `v2-stage2-kidnap-concordance-20261010-02.json`)
agrees on all 48 pairs:
- termination class: 48 of 48;
- ended within 0.5 m: 48 of 48.

So the re-collection agreed with the superseded attempts on both pre-declared descriptive
measures. By rule, the concordance excludes recovery success and contacts. The defect
itself is settled by the fix commits and their tests, not by the concordance. The
re-collection is not independent confirmation of R2: the R2 stage-2 PASS is labelled
**amended after the data were seen**, and confirmatory weight rests on stage 3.

Review: the amendment-2 section of `gates/redteam/trigger4-component-comparison-v2-2026-10-10.md`
(three rounds refuted, then the final check survived).

## 5. Five outcomes per component, with exposure

Counted stage-2 attempts. How these are scored:
- Distances are to the goal image's capture position (evaluation only).
- A correct stop is a stop within 0.5 m. An abstention is a declared non-arrival: it is
  never a wrong stop, and it is also counted as a timeout (no stop).
- Contacts are counted before the task end. Abstentions and scan halts reduce exposure,
  so contact comparisons are non-regression guards, not safety claims.

### Arrival recognition (`arrival_truncated`: the chain ends before the goal; 4 routes)

| Variant | Correct | Wrong | Abstain | Timeout | Contacts (per m) | Added stopping delay |
|---|---|---|---|---|---|---|
| A | 0 | 4 | 0 | 0 | 0 (0/4.2 m) | — |
| C1 | 0 | 0 | 0 | 4 | 3 (0.17/m) | — |
| V2a | 2 | 0 | 2 | 0 | 0 (0/10.5 m) | 29 and 20 decisions (14.5 s, 10.0 s) |
| V2b | 3 | 0 | 1 | 0 | 0 (0/9.4 m) | 17, 22 and 25 decisions (8.5–12.5 s) |

- **Mechanism.** V2 latched the approach at the truncated chain end, 0.64–1.24 m from
  the goal (the design; such latches are counted "premature" by distance). It then
  accumulated requested-goal votes until confirmation inside 0.5 m.
- **Abstentions.** V2b's one non-stop (`s_bend_run_0001`) was an abstention after 40
  approach decisions (`confirmation_budget`). The robot never came closer than 0.571 m,
  so the abstention avoided a wrong stop by halting short of the goal; it did not
  recognise arrival.
- **The cost.** Added stopping delay is 8.5–14.5 s after the first chain end.

### Premature confirmation (`premature_{true,rep}_d22`: matched starts where v1 stopped early; 2 attempts)

| Variant | Correct | Wrong | Abstain | Timeout | Contacts |
|---|---|---|---|---|---|
| A | 0 | 2 | 0 | 0 | 1 |
| C1 | 0 | 0 | 0 | 2 | 2 |
| V2a | 0 | 0 | 1 | 1 | 1 |
| V2b | 0 | 0 | 2 | 0 | 0 |

3 of the 4 V2 attempts latched 0.60–0.61 m from the goal. V2a on `premature_true_d22`
never latched, timed out and had a contact.

The robot never came within 0.5 m: the minimum was 0.593–0.594 m for V2b. V2 did not
confirm, and V2b abstained both times. V2b therefore halted at about the same place
where A declared its wrong stops (about 0.60 m). Its "0 wrong stops" holds because an
abstention is scored as a declared non-arrival; it is not evidence of better
localisation.

Not tested here: whether V2 recognises arrival from these starts. The robot never
reached the goal region.

### Look-alike (`ambiguity_{true,rep}_d{13,14,20,21,22}`: A against B1 from matched states before the bend; 10 pairs)

| Variant | Correct | Wrong | Timeout | Contacts (per m) |
|---|---|---|---|---|
| A | 0 | 6 | 4 | 4 (0.14/m) |
| B1 | 4 | 0 | 6 | 6 (0.17/m) |

**Node selection against route following.**

| Start | A | B1 | Look-alike status |
|---|---|---|---|
| d13, d14 (4 pairs) | Followed the look-alike every time: wrong stops at about 0.60 m, or timeouts | Never encountered it; stopped correctly (0.15–0.17 m) | NOT_TESTED (avoidance) |
| d20, d21, d22 (6 pairs) | Followed it | Corrected at the first encounter. About 20 decisions later it entered the v1 lost state (lost entries at decisions 22–25), never relocalised, left the route (lateral up to 1.74 m) and timed out with a contact | Correction then loss |

- **The corrections happen at handover.** All 6 corrections occur at decisions 0–2
  after the handover; 2 of them (d22, true and repeat) at decision 0.
  - With fresh counters (`max_jump` 2, `persistence` 2), B1 cannot accept a multi-node
    jump on the handover decision, so the decision-0 corrections are guaranteed by
    construction. This is the frozen limitation that a native B1 state on A's path is
    counterfactual.
  - The 4 corrections at decisions 1–2 are less constrained, but also early.
- **Backward proposals (descriptive).** On the A runs that timed out, 17 to 22 backward
  proposals were accepted. Most came after A's second followed encounter (decision 31
  or later), so they are a consequence of following the look-alike, not shown to be its
  cause. B1 had 0–1 backward proposals on the d20–d22 starts.
- **Conclusion.** B1 selects the right node at the look-alike only in a way partly fixed
  by the handover. It does not keep route following. Its correct stops come from
  avoidance.

### Recovery (`kidnapped_a`–`d`: start lost, off route; 16 attempts per variant; amended block)

| Variant | Correct | Wrong | Abstain or halt | Timeout | Contacts (per m) | Lost entries | Gate: first-entry successes over 16 trials | Successes over all lost entries (descriptive) | Gate: uninformative views (c, d), first-entry successes | False global matches while lost |
|---|---|---|---|---|---|---|---|---|---|---|
| B1 | 4 | 0 | 0 | 12 | 9 (0.17/m) | 16 | 4 | 4 | 1 of 8 | — |
| B1x | 8 | 2 | 0 | 6 | 4 (0.11/m) | 24 | 7 | 11 | 1 of 8 | 10 |
| R2 | 16 | 0 | 0 | 0 | 0 (0/24.7 m) | 18 | 13 | 15 | **6 of 8** (≥ 6 required) | 7 |

- **Which quantity the gate compares.** The gate's "all successes ≥ B1x" uses
  first-entry successes over all 16 trials: 13 against 7. False global matches are
  counted while lost, against the 5.881 exit, which was calibrated on local minima and
  is applied to global ones.
- **R2 is exactly at threshold, and on the node tolerance.** Its first-entry node
  errors on the 8 hard views are:

  | Trial | Node errors | Result |
  |---|---|---|
  | kidnapped_c | 0, 0, −1, −1 | 4 successes |
  | kidnapped_d | +1, +1 | 2 successes |
  | kidnapped_d | +2, +2 | 2 failures |

  - The tolerance is ±1 node. 4 of the 6 successes sit exactly on it, and the 2
    failures miss it by one node. With a tolerance of 0, R2 would score 2 of 8 and fail.
  - This is a property of the frozen definition, not a re-scoring.
- All 3 of R2's non-successful first entries relocalised to the wrong node (2 of them
  one node beyond the tolerance), so by the frozen definition they are not recovery
  successes:
  - **kidnap d, both junction routes:** relocalised 2 nodes ahead of the true node
    (5 vs 3, and 4 vs 2), yet both ended in correct stops;
  - **kidnap b, `s_bend_run_0000`:** relocalised at node 3 when the true node was 9;
    its second lost entry relocalised correctly.
- Wrong-node relocalisation is therefore R2's observed failure mode, even though its
  episodes ended well.
- R2 travelled less: 24.7 m, against 37.3 m (B1x) and 51.6 m (B1). It scans in place.
  Its zero contacts therefore partly reflect less exposure.

## 6. Limitations

- **Small numbers.** There are 1–4 attempts per cell and the trials are development
  trials.
  - Both passing gates sit exactly on their thresholds.
  - R2's hard-view successes depend on the ±1-node tolerance.
  - Two counted cells of the passing gates were previewed by smoke runs.
  - No multiplicity correction is applied across the four gates.
- **Narrow design.** One checkpoint, one seed, four routes and two scenes; the
  look-alike exists on one route only.
- **Not counterfactual replicas.** Runs are not bit-deterministic, so A/B1 "pairs" from
  matched starts are paired by start state, not replicas.
- **Attribution to bundles.**
  - R2's difference from B1x is attributable to the whole recovery bundle (scan, scan
    budget, entry limit, non-arrival relocalisation), not to the scan alone.
  - V2b's result is attributable to confirmation plus steering; steering without
    confirmation is not tested.
  - V2 and R2 together are not tested, although both advance.
- **Exit calibration.** The recovery exit (5.881) was calibrated on local window minima
  (about 15 tail points from one recording of forward-view minima; global and scan-view behaviour are measured, not calibrated) and is applied to global minima. While lost, R2
  recorded 7 false global matches (≤ exit at a node more than one away from the true
  node) and B1x 10.
- **Scan creep.** In-place scanning creeps at about 0.03 m/s; contacts during scans
  count.
- **Shared dependency.** The separate requested-goal check reuses the same distance
  head as localisation; it is not an independent verifier. Calibration used the same
  routes.
- **Two readback versions.** Original and re-collected cells ran different readback
  versions. Within each cell all counted attempts share one.
- **Unpinned robot USD.** It is pinned only by the amendment-2 ledger; earlier
  collections have no USD digest.
- **File times.** Launch-after-freeze and launch-after-amendment use file modification
  times, supplemented by the ledger.
- **Test failures.** Three known `test_environment_identity_v8` failures remain
  (BO-10 controls; they also fail without this work). This was not re-verified by the
  results review.

## 7. Next

Stage 3 (fresh complete episodes) runs for V2b and R2, with their comparators:
- **cells:** derived from the committed gate record's PASS statuses by the analysis's
  `required_stage3` rule (the record stores the statuses, not the set). The set is A,
  B1, B1x, C1, V2b and R2 on each stage-3 trial. That makes 18 cells and 54 attempts (4 + 4 + 1
  routes per variant);
- **trials:** `complete_true_chain`, `complete_truncated_chain`,
  `complete_wrong_chain_swap`;
- **launch:** `scripts/run_component_v2_block.sh stage3 8959333 <ledger> <this commit> gates/v2/stage2-gate-record-20261010.json`.

The stage-3 criteria are the frozen `stage_3_criteria`. The results review is recorded
in `gates/redteam/trigger6-component-results-v2-stage2-2026-10-10.md`.
