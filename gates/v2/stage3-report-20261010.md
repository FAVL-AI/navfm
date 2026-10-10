# Component comparison v2: stage-3 report (development validation, 2026-10-10)

**Scope.** These are fresh complete episodes on the development layouts already
inspected in v1 and stage 2. **The truncated-chain trial is the same condition as stage
2's `arrival_truncated`** (same routes, chain, start and budget), so its A, C1 and V2b
cells are near-deterministic re-draws of stage-2 cells (start poses differ by about
2e-5 m). Matching outcomes there are expected and are not independent replication. The true-chain and swap episodes repeat v1 conditions. This is development validation, **not** held-out
generalisation. It establishes no illumination robustness, no sim-to-real transfer,
and no novelty or SOTA claim. The six held-out groups stay sealed and illumination
work is paused.

**Protocol and records**
- Protocol: v2.1, frozen at `83101fa`; the `stage_3_criteria` are unchanged since then.
- Amendment 2 is frozen at `8959333`. It changed which stage-2 data count, not any
  criterion.
- Admission came from the committed stage-2 gate record
  (`c2ef497:gates/v2/stage2-gate-record-20261010.json`).
- Decision record: `gates/v2/stage3-decision-record-20261010.json`. It was produced
  with `--freeze-commit 83101fa --amendment-commit 8959333 --ledger-commit 2879550
  --stage2-commit c2ef497`.

## 1. Accounting and provenance

| Item | Result |
|---|---|
| Collections | 18: tag `s3-01`, 6 variants × 3 trials |
| Attempts planned | 54 (true chain 4, truncated 4, swap 1 per variant) |
| Attempts recorded | 54, all PASS |
| Reruns | none (no `s3-02` collection) |
| Exclusions | none |
| Integrity failures | 0 |

**Ledger** (`gates/v2/v2-amendment2-launch-ledger.jsonl`, lines 25–60):
- 18 launches, from HEAD `c2ef497` with a clean worktree;
- every exit 0;
- robot USD digest `0ba6ca5d…` before and after every collection.

**Which commit is which.**
- `83101fa` is the frozen protocol (config and criteria).
- `8959333` is the frozen amendment record; the launcher requires HEAD to descend from
  it.
- `c2ef497` is the executed source: every manifest's influencing-file digests equal its
  blobs.
  - Among the files the collector loads, its only difference from `83101fa` is the
    amended readback (`scientific_preflight.py`).
  - Added after the freeze but outside the collector: the launcher
    `scripts/run_component_v2_block.sh` (runs at launch) and the analysis script
    (+175 lines; `stage3_decisions` unchanged).

**Stage-3 admission.** The stage-2 gates admitted V2b and R2, so stage 3 ran V2b and
R2 with their comparators:
- A, the baseline;
- C1 for V2b;
- B1x for R2 (decisive);
- B1 for R2 (reported only).

## 2. Decisions (frozen `stage_3_criteria`, computed by the analysis)

| Component | Decision | What the decision actually rests on |
|---|---|---|
| V2b_confirm_steer | **RETAIN** | **True and truncated chains only:** correct stops ≥ C1, wrong stops ≤ C1, zero wrong stops on true chains, and no contact regression against C1 or A. The swap-chain comparison with C1 is **NOT TESTED** (no stops in either arm; recorded, not counted) |
| R2_recover | **RETAIN** | **Wrong stops ≤ B1x and no contact regression only.** Recovery was NOT TESTED in stage 3: no lost entry on the true or truncated chains, and no pose-true node on the swap chain |

R2's recovery mechanism was therefore **not** tested prospectively here. The only
evidence for it is the stage-2 kidnap block, and that stage-2 PASS is **exploratory**
because the gate result changed after the data were seen (§5).

The amendment's premise was that confirmatory weight on recovery would rest on stage 3.
**That premise failed:** R2's recovery has no confirmatory evidence.

**What the contact guard can show.**
- "Contacts" counts episodes with any contact before the task end, not contact events.
- Every stage-3 contact occurred late in a 49.9 s timeout episode (frames 389–560, about
  32–47 s).
- V2b and R2 episodes ended earlier: V2b halted or stopped by 33.5 s on truncated chains
  and 37 s on the swap chain; R2 halted at 21 s on the swap chain. So they never entered
  the phase in which the comparators made contact.
- "No contact regression" is therefore largely an exposure effect, not evidence of safer
  driving. With 0 contacts in 4 episodes per condition, a true contact rate above 50% is
  still compatible.

## 3. Paired comparator outcomes (counts per variant × condition, all attempts)

**What the columns mean**
- C: correct stop (within 0.5 m of the goal image's capture position).
- W: wrong stop.
- Ab: abstention or halt, a declared non-arrival.
- TO: timeout with no declaration.
- Contacts are counted before the task end.

| Condition | Variant | C | W | Ab | TO | Contacts (path) | Added stopping delay |
|---|---|---|---|---|---|---|---|
| true chain (4) | A | 3 | 0 | 0 | 1 | 1 (10.8 m) | 0, 0, 0 |
| | C1 | 3 | 0 | 0 | 1 | 1 (11.0 m) | 1, 1, 1 decisions |
| | **V2b** | 3 | 0 | 1 | 0 | 0 (10.4 m) | 1, 1, 1 decisions (0.5 s) |
| | B1 | 4 | 0 | 0 | 0 | 0 (8.4 m) | 0 |
| | B1x | 4 | 0 | 0 | 0 | 0 (8.5 m) | 0 |
| | **R2** | 4 | 0 | 0 | 0 | 0 (8.5 m) | 0 |
| truncated chain (4) | A | 0 | 4 | 0 | 0 | 0 (4.1 m) | — |
| | C1 | 0 | 0 | 0 | 4 | 3 (18.1 m) | — |
| | **V2b** | 3 | 0 | 1 | 0 | 0 (9.2 m) | 15, 22, 25 decisions (**7.5–12.5 s**) |
| | B1 | 0 | 4 | 0 | 0 | 0 (3.9 m) | — |
| | B1x | 0 | 4 | 0 | 0 | 0 (3.9 m) | — |
| | **R2** | 0 | 4 | 0 | 0 | 0 (3.9 m) | — |
| swap chain (1) | A | 0 | 1 | 0 | 0 | 0 | — |
| | C1 | 0 | 0 | 0 | 1 | 1 | — |
| | **V2b** | 0 | 0 | 1 | 0 | 0 | — |
| | B1 | 0 | 0 | 0 | 1 | 1 | — |
| | B1x | 0 | 1 | 0 | 0 | 0 | — |
| | **R2** | 0 | 0 | 1 (recovery_failed halt) | 0 | 0 | — |

### V2b: the trade-off

| Measure | V2b | Comparator |
|---|---|---|
| Correct stops on truncated chains | 3 (the same routes as in stage 2; `s_bend_run_0001` abstained both times) | A and C1: 0 |
| Wrong stops overall | 0 | A: 5 |
| Contacts overall | 0 | A: 1; C1: 5 |
| Added stopping delay, truncated chains | 7.5–12.5 s after the first chain end | stage 2: 8.5–12.5 s |
| Added stopping delay, true chains | 0.5 s | — |

**The delay is a primary cost, not a footnote.** V2b latches at the chain end
(0.60–1.24 m from the goal on truncated chains) and keeps approaching until the
requested-goal votes confirm.

**V2b's two abstentions**
- **True `s_bend_run_0000`:** latched 0.60 m from the goal and never came closer than
  0.59 m.
  - A and C1 also failed (timeouts, minimum 0.60 and 0.59 m).
  - B1, B1x and R2 all stopped correctly here (0.16, 0.14 and 0.15 m), so bounded node
    selection reached this goal.
  - V2b inherits A's route following on this route (path 3.9 m, against B1's 2.4 m). It
    halted short and did not recognise arrival: this is a missed arrival.
- **Truncated `s_bend_run_0001`:** never came closer than 0.62 m. It halted short of
  the goal; there was no wrong stop.

### R2

- **Stopping.** On true chains R2 stops correctly 4 of 4, like B1 and B1x. On truncated
  chains R2 stops wrongly 4 of 4, like A, B1 and B1x: it has no arrival check, so the
  truncated-chain error is untouched.
- **Swap chain.** R2 entered the lost state, scanned for its 36-decision budget without
  relocalising, and halted (`recovery_failed`), whereas B1x stopped wrongly.
  - The halt was 1.75 m from the goal; the minimum distance was 1.69 m.
  - The lost state is from the manifest (`chain.event`); the decision record has no
    recovery field for swap attempts.
  - By the frozen rule this is recorded, not counted: there is no pose-true node on a
    swapped chain.
- **Contacts.** R2 has 0, as do B1x on the true and truncated chains. Exposure is
  similar on those conditions (8.4–8.5 m and 3.9 m).

## 4. Recovery: exact-node against ±1-node (stage-2 kidnap block; stage 3 had none to score)

This counts first lost entries per variant. The "easy" trials are kidnaps a and b
(yaw ±20°); the "hard" trials are kidnaps c and d (yaw 180° and 90°). The frozen
criterion counts ±1-node successes.

| Variant | Trials | First entries | Exact-node successes | ±1-node successes (frozen) | Relocalised to a wrong node (> ±1) | Re-entered lost within 10 | Never relocalised |
|---|---|---|---|---|---|---|---|
| R2 | easy (a, b) | 8 | 4 | 7 | 1 | 0 | 0 |
| R2 | hard (c, d) | 8 | **2** | **6** | 2 | 0 | 0 |
| B1x | easy | 8 | 4 | 6 | 0 | 1 | 1 |
| B1x | hard | 8 | 0 | 1 | 1 | 2 | 4 |
| B1 | easy | 8 | 1 | 3 | 0 | 0 | 5 |
| B1 | hard | 8 | 1 | 1 | 0 | 0 | 7 |

- With the exact-node criterion, R2's hard-view count is 2 of 8, below the 6 the gate
  requires.
- R2 never failed to relocalise. B1x and B1 often did: 5 and 12 of 16 respectively.
- R2's failures were all wrong-node relocalisations, 3 of 16. The two kidnapped_d
  junction runs relocalised to node 5 for a true node of 3, and to node 4 for a true
  node of 2.
- In stage 3, R2 had no lost entry on the true or truncated chains, and one
  unrelocalised entry on the swap chain, so there is nothing to score.

## 5. Post-data amendments and previews (kept explicit)

- **R2's stage-2 PASS is exploratory.** The re-collection of the kidnap block was
  decided after the superseded attempts' likely outcomes were readable (amendment 2).
  Stage 3's frozen criteria could have tested it prospectively, but complete episodes
  produced no scorable lost entry, so **R2's recovery remains prospectively untested**.
- **Smoke previews.** Two pre-freeze smoke runs previewed counted stage-2 cells of the
  passing components: R2 kidnapped_c `junction_run_0000` and V2b arrival_truncated
  `junction_run_0000`. Because the stage-3 truncated trial is the same condition, the
  V2b smoke run also previewed stage-3 V2b truncated `junction_run_0000` (a correct stop
  in both).
- **Thresholds.** Both stage-2 PASSes sit exactly at their thresholds. No criterion or
  threshold was changed after any data.

## 6. Why V2a failed stage 2 (and did not run here)

V2a is V2b without requested-goal steering: during the approach it keeps C1's chain
steering. On `arrival_truncated` it made 2 correct stops (junction routes) and 2
abstentions (s_bend routes), against a threshold of 3.

**How the figures below were computed**
- "In region" means within 0.5 m of the goal image's capture position.
- Heading error is |robot yaw − goal capture yaw|.
- Votes are the approach-phase decisions whose requested-goal distance was ≤ 7.745.

| Route | Variant | Frames in region | Heading error in region | Approach decisions | Votes | Lowest requested-goal distance in region | Outcome |
|---|---|---|---|---|---|---|---|
| truncated `s_bend_run_0000` | V2a | 117 (19 decisions) | 49.6–87.3° | 40 (the budget) | 0 | 11.9 | abstained (`confirmation_budget`) |
| | V2b | 107 | 5.7–87.3°; 5.7° at the stop | 18 | 2 | 4.16 | correct stop |
| truncated `junction_run_0000` | V2a | 112 | 15.6–33.1°; 25.7° at the stop | 30 | 3 | 5.37 | correct stop |
| | V2b | 66 | 5.3–6.5° | 23 | 2 | 6.62 | correct stop |
| truncated `junction_run_0001` | V2a | 45 | 17.7–27.2°; 26.7° at the stop | 21 | 2 | 7.17 | correct stop |
| | V2b | 75 | 3.1–8.0° | 26 | 2 | 5.52 | correct stop |
| truncated `s_bend_run_0001` | both | 0 (closest 0.56–0.57 m) | — | 40 | 0 | — | abstained |

**HYPOTHESIS** (association in 3 informative routes per arm, no intervention isolating
heading): confirmation needs the camera view roughly aligned with the goal image.

- V2a confirmed at heading errors of 16–33° and failed at 50–87°.
- V2b steered to within 3–8°, and its requested-goal distance fell below threshold only
  once its heading error was at most about 12°.
- So steering to the requested goal plausibly enables confirmation. The heading
  threshold is unknown.

On `s_bend_run_0000`, V2a turned a would-be wrong stop (A's) into a halt and did not
recognise arrival. On the junction routes it did recognise arrival.

## 7. Limitations

- **Small and narrow.** These are development layouts already inspected: 4 + 4 + 1
  routes, one checkpoint, one seed, two scenes. There are no significance claims (the
  frozen reporting rule).
- **Exposure.** Abstentions and halts reduce exposure; contact comparisons are
  non-regression guards.
- **Shared dependency.** The requested-goal check reuses the localisation distance
  head; it is not an independent verifier.
- **Untested combinations.** V2b and R2 together are untested, and so is V2b's steering
  without confirmation.
- **Not counterfactual replicas.** Runs are not bit-deterministic, so paired trials are
  not counterfactual replicas; same-start re-draws are near-deterministic.
- **Pause semantics.** The confirmation state's pause behaviour is unit-tested only;
  V2b has no lost state.
- **Scan creep.** In-place scanning creeps at about 0.03 m/s, and contacts during scans
  count. R2 scanned for 36 decisions on the swap chain, without contact.
- **Exit calibration.** The recovery exit is calibrated on local window minima and
  applied to global minima.
- **One look-alike route.** The look-alike exists on one route only.
- **Test failures.** Three known `test_environment_identity_v8` failures remain.
