# Handoff: arrival component comparison v2.1 (development)

Written 2026-10-10, while stage 2 of the frozen v2.1 protocol was still
collecting. Verify every statement below against the repository and the
evidence directory before acting on it; where they disagree, the files win.

## 1. Where things stand

| | |
|---|---|
| Worktree | `/home/favl/projects/navfm-engineering-recording` |
| Branch | `agent/engineering-recording` (not pushed; do not push) |
| Frozen protocol | `configs/eval/component_comparison_v2.json`, v2.1, frozen at `83101fa`, sha256 `44285743347e20e89ea03be74d001f9647d7f54dd2bff8903cbae9b41b2a088a` |
| Commits to preserve | `7d2e383`, `d6139c0` (v1 results) and everything after them |
| Evidence root | `/home/favl/navfm-runtime-evidence` (outside git; never commit it) |
| Stage 1 | Done, logic replay: `v2-stage1-replay-20261010-01.json`; S1a, S1b and S1c pass (in-sample consistency check only) |
| Stage 2 | **Collecting** (44 collections, 92 attempts, names `v2-<trial>-<variant>-20261010-01`); not yet audited or analysed |
| Stage 3 | Not started; allowed only for components whose committed stage-2 gate is PASS |

Recent history, newest first:

- `83101fa` freeze v2.1 after the amendment review
- `ca03cde` image-level replay fidelity and replay checks
- `cbbf3ea` v2.1 amendment: matched-state starts replay the recorded episode to the handover
- `f663882` freeze v2 after three red-team rounds
- `4030a37`, `0468814` v2 revisions after the red-team rounds
- `1da4e55` v2 components (confirmation, recovery, matched-state trials), marked PROPOSED
- `d6139c0` v1 results: 44 of 44 verified attempts, with traces and per-component decisions
- `7d2e383` mypy annotation fixes (re-scoring the v1 episodes gave identical results)

## 2. What v2 tests

The paper's question is verified arrival under illumination shift. **Illumination
work is paused** until the baseline is repaired. v2 is that repair, on
development layouts only.

- **V2a_confirm and V2b_confirm_steer** (`src/navfm/collection/arrival_confirmation.py`):
  a requested-goal confirmation state that does not need the chain-arrival flag
  on the same decision. The approach phase latches at the first chain end. A
  decision votes when its requested-goal distance is at most 7.745; two votes in
  the last four decisions confirm. A pause clears the votes. 40 approach
  decisions without confirmation is a terminal ABSTAINED. V2b steers to the
  requested goal during the approach; V2a keeps C1's steering. The check reuses
  the same distance head as localisation (a shared dependency); it is not an
  independent verifier.
- **R2_recover** (`RecoveringTopomapState` in `src/navfm/collection/topomap.py`):
  lost entry is unchanged. While lost, the robot scans in place at 0.4 rad/s.
  Relocalisation needs a global argmin at most 5.881 (calibration:
  `recovery-calibration-v2-20261010-01.json`) on two consecutive decisions
  within one node. A relocalisation decision is never an arrival. Each scan has
  a budget of 36 decisions and an episode allows at most 2 lost entries;
  running out ends in `recovery_failed`, a non-arrival halt.
- **B1_bounded and B1x_exit**: the v1 backward-step filter, and B1 with the R2
  exit threshold but no scan (the control for R2).
- **A_baseline and C1_verify**: the v1 comparators, rerun unchanged.

Stage-2 trials:

- `ambiguity_{true,rep}_d{13,14,20,21,22}`: A against B1, starting at matched
  states before the bend.
- `premature_{true,rep}_d22` and `arrival_truncated`: A, C1, V2a and V2b.
- `kidnapped_a` to `kidnapped_d`: B1, B1x and R2. Kidnaps c and d have
  uninformative starting views.

Matched-state starts (v2.1) replay the recorded commands for decisions 0 to
K-1 from the recorded start pose. They hand over at decision K, starting from
the node the source episode recorded at K-1. Fidelity bounds: 0.02 m,
2 degrees, 2.5 grey levels, distance difference 1.0, and the same search
window. A fidelity failure is an integrity failure, not a component result.

What is restored at the handover:

- the simulator state and image history, by replay;
- the starting node;
- the lost-at-start flag, where the trial declares it.

What is reset: each variant's internal state (pending proposals, the lost
counters, confirmation votes and recovery attempts). See `known_limitations`
in the config.

## 3. Exactly how stage 2 was launched

The launchers sat in a session scratchpad, so they are reproduced here
verbatim in content. Per trial and variant:

```bash
export OMNICLIENT_HUB_MODE=disabled \
  NAVFM_UPSTREAM=/home/favl/navfm-runtime-evidence/option1-admitted-20261007-02/upstream
# ARGS from the frozen config's trial: --route-id per route, --topomap-root of its
# condition, --max-steps budget, --resume-from/--resume-decision, --start-lost, perturbation
timeout 5400 ~/miniforge3/envs/isaac/bin/python scripts/collect_option1.py \
  --out $E/v2-$TRIAL-$VARIANT-20261010-01 --policy-period-frames 6 $ARGS \
  --robot /home/favl/projects/navfm/assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd \
  --actuation wheel \
  --checkpoint /home/favl/navfm-training-evidence/option1-arrival-n31-e20-seed0-20261009-01/epoch_020.pth \
  --checkpoint-sha256 c7686983099080649dde0eaf79575149c26239321e23cf96788b3dd25b0d5d7c \
  --qualification /home/favl/navfm-runtime-evidence/articulated-control-20261009-10/qualification.json \
  --yaw-feedback \
  --goal-root /home/favl/navfm-runtime-evidence/arrival-goal-traversal-final-frame-20261009-01 \
  --comparison-config configs/eval/component_comparison_v2.json --variant $VARIANT --trial $TRIAL
```

Order: look-alike, then premature confirmation, then arrival recognition,
then recovery.

**Retry rule:** one rerun only after a non-PASS or crashed attempt, never after
a PASS, and only a route's first two attempts can count. A rerun takes a new
suffix (`-20261010-02`).

## 3a. Amendment 2 (v2.2), made after stage 2 ran

Stage 2 finished as follows:

- 44 collections, 92 attempts: 78 PASS and 14 FAILED.
- All 14 failures were kidnap attempts whose heading crossed ±π. The cause was
  a defect in the saved-recording readback (fixed in `284045d`, `1273db9`).
- Gates as collected:
  - `B1_bounded`: FAIL
  - `V2a_confirm`: FAIL
  - `V2b_confirm_steer`: PASS
  - `R2_recover`: INCOMPLETE
- Evidence:
  - `v2-stage2-audit-20261010-01.json`
  - `v2-stage2-analysis-20261010-01.json`
  - `v2-stage2-kidnap-first-attempts-inferred-20261010-01.json` (diagnostic)

Record: `configs/eval/component_comparison_v2_amendment_2.json` (FROZEN; pinned in
the analysis script). Review: the amendment-2 section of
`gates/redteam/trigger4-component-comparison-v2-2026-10-10.md`. The amendment does
three things:

- **Re-collect** the whole recovery block (12 kidnap cells, 48 attempts) under the tag
  `20261010-02`; the original `-01` collections are superseded.
- **Launch** every amendment-era collection with `scripts/run_component_v2_block.sh`
  (modes `block`, `stage3`, `rerun`). It writes a launch ledger.
- **Analyse** with `--amendment-commit <freeze commit> --ledger-commit <c> --ledger-path gates/v2/<ledger>`.

`scripts/concordance_kidnap_v2.py` is descriptive only. The R2 stage-2 gate must be
reported as amended after the data were seen. Confirmatory weight rests on stage 3.

## 4. Next steps, in order

1. Confirm all 44 collections finished and list every non-PASS attempt.
   Apply the retry rule; do not change code first.
2. Audit:
   `scripts/audit_closed_loop_episodes.py --collection <each> --goal-root /home/favl/navfm-runtime-evidence/arrival-goal-traversal-final-frame-20261009-01 --out <new file>`,
   with `NAVFM_UPSTREAM` set.
3. Analyse:
   `scripts/analyse_component_comparison_v2.py --config configs/eval/component_comparison_v2.json --freeze-commit 83101fa --audit <audit> --trial <each stage-2 trial> --out <new file>`.
   Then repeat it with each `--negative-control` (`variant`, `chain`,
   `resume`, `start_lost`, `trial`); each control must fail integrity.
4. Report:
   - accounting: collections, attempts, failures, retries, exclusions;
   - per-attempt fidelity;
   - state initialisation;
   - mechanism outcomes: ambiguity corrected, followed or avoided (no
     encounter means NOT_TESTED); recovery successes and failure reasons;
     approach-latch distance;
   - the five outcomes: correct stops, wrong stops, contacts (raw and per
     metre), recovery success, added stopping delay;
   - the gate statuses exactly as the frozen analysis computes them.
5. Commit the stage-2 gate record under `gates/v2/`, naming files explicitly.
6. Stage 3 runs only for PASS components, plus A and their counterparts (and
   B1 for R2). Launch it after that commit, passing `--stage2-commit` and
   `--stage2-path`.
7. Red-team the results (trigger 6, since the samples are shaped by
   exclusions and resumed runs). Archive the review under `gates/redteam/`.

A failed gate is a result. Do not repair it within v2, and do not change
thresholds or the protocol silently. Any amendment is a new dated section,
red-teamed before collection.

## 5. Rules that bind any agent here

- **Authorship:** Frank Asante Van Laarhoven <frankleroyvan@gmail.com> only.
  No co-author trailers, no tool or AI attribution. In commit messages, call
  the repository-root instructions file "the standing-instructions file".
  Never use `--no-verify`.
- **Do not push. Do not actuate the real robot.**
- **Keep the six held-out groups sealed. Keep illumination work paused.**
- **Never commit** artefacts, logs, weights, images or `runs/`. Run formatters
  and `git add` on named files only, never on a directory, then read
  `git diff --cached --stat`. (A directory-wide `ruff format` plus `git add`
  once swept 83 unrelated scripts into a freeze commit.)
- **Never edit source while a collection is running.**
- **Kill only PIDs you started.** Never `pkill -f`.
- **One agent per worktree.** Do not run a second writing agent here while
  another is active.
- **Verify before committing:** `make verify` (ruff, mypy, pytest), plus
  `NAVFM_UPSTREAM=third_party/visualnav-transformer python -m pytest -q`
  where format modules are touched.
  - **Known failures:** 3 `test_environment_identity_v8` failures, which also
    fail without this work (see `docs/ARRIVAL_RESEARCH_DECISION.md`). Report
    them as failures, never as passes.
- **Claim limits:** these are development trials informed by previously
  inspected failures. A PASS justifies fresh complete-episode evaluation, not
  held-out generalisation, illumination robustness, sim-to-real transfer,
  novelty or a SOTA claim.

## 6. Key documents

- `docs/ARRIVAL_RESEARCH_DECISION.md`: v1 results and component decisions.
- `gates/redteam/trigger4-component-comparison-v2-2026-10-10.md`: the v2
  protocol reviews (rounds 1 to 4 and the v2.1 amendment).
- `gates/redteam/trigger6-component-results-2026-10-10.md`: the v1 results
  review.
- `configs/eval/component_comparison_v2.json`: definitions, gates, stage-3
  criteria, retry rule, fidelity bounds, known limitations.
