# Project handoff: arrival component comparison v2 (development)

Updated 2026-10-10 after stage 3 finished, been audited and committed. Start from
this audited result; do not restart the investigation. Verify every statement
against the files; where they disagree, the files win.

## 1. Repository state

| | |
|---|---|
| Worktree | `/home/favl/projects/navfm-engineering-recording` |
| Branch | `agent/engineering-recording`; **not pushed** (no push is authorised) |
| HEAD | the commit that adds this file (see `git log -1`); its parent chain is listed below |
| Working tree | clean at handoff (`git status --porcelain` is empty) |
| Commits to preserve | `7d2e383`, `d6139c0` (v1 results) and everything after them |

Commits since v1, newest first:

| Commit | What it does |
|---|---|
| this commit | Stage-3 report and decision record; this handoff (renamed from the earlier handoff note) |
| `2879550` | Stage-3 lines appended to the launch ledger |
| `c2ef497` | Stage-2 gate record, report and results review. This is also the **executed source of stage 3** |
| `eb418e5` | Launch ledger, stage-2 block |
| `daa3978` | Final amendment review: survives |
| `8959333` | **Amendment 2, frozen** (record, pinned analysis, launcher, concordance) |
| `1273db9`, `284045d` | Readback yaw fix and its property check |
| `306e77a` | First handoff note |
| `83101fa` | **v2.1 frozen protocol** |
| `ca03cde`, `cbbf3ea`, `f663882`, `4030a37`, `0468814`, `1da4e55` | v2 development and freezes |

## 2. Frozen configurations

| What | Where | Identity |
|---|---|---|
| Protocol v2.1 | `configs/eval/component_comparison_v2.json` | commit `83101fa`, sha256 `44285743347e20e89ea03be74d001f9647d7f54dd2bff8903cbae9b41b2a088a` |
| Amendment 2 | `configs/eval/component_comparison_v2_amendment_2.json` | commit `8959333`, sha256 `6c3d7b2ad1e1d3649e95560fdea3b0c4ce9d250fde11a950d52f2a1200a4b64f` (pinned in the analysis script) |
| Analysis | `scripts/analyse_component_comparison_v2.py` | must equal its blob at `8959333` (sha256 `9ea90041…`) |
| Launcher | `scripts/run_component_v2_block.sh` | modes `block`, `stage3`, `rerun`; refuses a dirty tree or a non-descendant HEAD |
| Checkpoint | `/home/favl/navfm-training-evidence/option1-arrival-n31-e20-seed0-20261009-01/epoch_020.pth` | sha256 `c7686983…5d7c` |

## 3. Results (committed)

### Stage 2

The gate record is `gates/v2/stage2-gate-record-20261010.json` and the report
`gates/v2/stage2-report-20261010.md`.

| Component | Gate | Notes |
|---|---|---|
| V2b_confirm_steer | **PASS**, at threshold | 3 of 4 correct stops on truncated chains; 0 wrong stops; 0 contacts |
| R2_recover | **PASS**, at threshold; **exploratory** | Changed after the data were seen (amendment 2). 4 of its 6 hard-view successes sit on the ±1-node tolerance; with exact-node scoring it has 2 of 8 |
| V2a_confirm | FAIL | 2 of 4 correct stops (see below) |
| B1_bounded | FAIL | Look-alike correction partly fixed by the handover reset; then loses track; contacts 6 against A's 4 |

### Stage 3

The decision record is `gates/v2/stage3-decision-record-20261010.json` and the report
`gates/v2/stage3-report-20261010.md`.

| Component | Decision | What it rests on |
|---|---|---|
| V2b | **RETAIN** (true and truncated chains; swap NOT TESTED) | 3 correct stops on truncated chains where A and C1 have 0; 0 wrong stops; 0 contacts. The cost is **7.5–12.5 s added stopping delay**. Its contact result is largely an exposure effect: comparator contacts all occurred late in timeouts |
| R2 | **RETAIN** | **Wrong stops and contacts only.** Recovery was not tested: no scorable lost entry in complete episodes. R2 still stops wrongly on all 4 truncated chains |

- The stage-3 truncated trial is the same condition as stage 2's `arrival_truncated`,
  so it is a reproducibility check.
- Smoke previews and the post-data amendment are disclosed in both reports.

### Why V2a failed

V2a keeps C1's chain steering during the approach.

- On truncated `s_bend_run_0000` the robot was within 0.5 m of the goal for 117 frames,
  but faced 49.6–87.3° away from the goal image's heading.
- Its requested-goal distance in that region never fell below 7.745 (minimum 11.9), so
  it collected 0 votes in 40 approach decisions (the budget) and abstained.
- V2b, which steers to the requested goal, reached 5.7° and confirmed with 2 votes.
- V2a did confirm on the junction routes, at 16–33° heading error.
- HYPOTHESIS (association only, no intervention isolating heading): confirmation needs
  the view roughly aligned with the goal image.

### Reviews

- `gates/redteam/trigger4-component-comparison-v2-2026-10-10.md`: the protocol and
  amendment-2 rounds.
- `gates/redteam/trigger6-component-results-v2-stage2-2026-10-10.md`: the stage-2
  results review.
- `gates/redteam/trigger6-component-results-v2-stage3-2026-10-10.md`: the stage-3
  results review.

## 4. Evidence paths (outside git; never commit them)

The evidence root is `/home/favl/navfm-runtime-evidence`. It contains:

- **Stage-2 collections:**
  - `v2-<trial>-<variant>-20261010-01` (44; the 12 kidnap ones are SUPERSEDED);
  - `v2-kidnapped_*-*-20261010-02` (12, the re-collected block).
- **Stage-3 collections:** `v2-complete_*-*-s3-01` (18).
- **Audits:**
  - `v2-stage2-audit-20261010-01.json` (as collected);
  - `v2-stage2-audit-20261010-02.json`;
  - `v2-stage3-audit-20261010-01.json`.
- **Analyses:**
  - `v2-stage2-analysis-20261010-01.json` (as collected, before the amendment);
  - `v2-stage2-analysis-20261010-02.json`;
  - `v2-stage3-analysis-20261010-01.json`.
- **Negative controls:** `v2-stage2-negctl-{variant,chain,resume,start_lost,trial}-20261010-02.json`.
  All five fail integrity, as they must.
- **Amendment diagnostics:**
  - `v2-stage2-kidnap-first-attempts-inferred-20261010-01.json`;
  - `v2-stage2-kidnap-concordance-20261010-02.json`.
- **Launch ledger:** `v2-amendment2-launch-ledger.jsonl` (the committed copy is under
  `gates/v2/`).
- **Earlier work:**
  - v1: `component-comparison-*`;
  - stage-1 replay: `v2-stage1-replay-20261010-01.json`;
  - recovery calibration: `recovery-calibration-v2-20261010-01.json`;
  - smokes: `smoke-v2-20261010/`.

## 5. Exact verification commands

```bash
cd /home/favl/projects/navfm-engineering-recording
E=/home/favl/navfm-runtime-evidence
# software
NAVFM_UPSTREAM=$E/option1-admitted-20261007-02/upstream PATH=$PWD/.venv/bin:$PATH make verify
#   expected: ruff and mypy clean; pytest fails ONLY the 3 known
#   tests/test_environment_identity_v8.py tests (BO-10 controls that also fail without
#   this work). Report them as failures, never as passes. Without NAVFM_UPSTREAM, 5 more
#   tests fail because third_party/ is absent from this worktree.
# stage-2 gates, reproduced from evidence (output path must be new)
export NAVFM_UPSTREAM=$E/option1-admitted-20261007-02/upstream
T2=$(.venv/bin/python -c "import json;c=json.load(open('configs/eval/component_comparison_v2.json'));print(' '.join('--trial '+n for n,t in c['trials'].items() if t['stage']==2))")
.venv/bin/python scripts/analyse_component_comparison_v2.py --config configs/eval/component_comparison_v2.json \
  --freeze-commit 83101fa --audit $E/v2-stage2-audit-20261010-02.json $T2 \
  --amendment-commit 8959333 --ledger-commit eb418e5 --ledger-path gates/v2/v2-amendment2-launch-ledger.jsonl \
  --out /tmp/stage2-check.json
# stage-3 decisions
.venv/bin/python scripts/analyse_component_comparison_v2.py --config configs/eval/component_comparison_v2.json \
  --freeze-commit 83101fa --audit $E/v2-stage3-audit-20261010-01.json \
  --trial complete_true_chain --trial complete_truncated_chain --trial complete_wrong_chain_swap \
  --amendment-commit 8959333 --ledger-commit 2879550 --ledger-path gates/v2/v2-amendment2-launch-ledger.jsonl \
  --stage2-commit c2ef497 --stage2-path gates/v2/stage2-gate-record-20261010.json --out /tmp/stage3-check.json
# negative controls: add --negative-control {variant,chain,resume,start_lost,trial} to the stage-2 command
```

Expected:
- **Stage 2:** 92 attempts, no integrity failures. B1 FAIL, R2 PASS, V2a FAIL, V2b PASS.
- **Stage 3:** 54 attempts, no integrity failures. R2 RETAIN, V2b RETAIN.

## 6. Unresolved issues

1. **R2's recovery is prospectively untested.** The amendment's premise, that stage 3
   would carry the confirmatory weight, failed.
   - Its stage-2 PASS is exploratory: changed after the data were seen, exactly at
     threshold, and dependent on the ±1-node tolerance (exact-node 2 of 8).
   - Stage 3 produced no scorable lost entry.
2. **V2b's added stopping delay** (7.5–12.5 s on truncated chains) is a primary
   trade-off.
   - Its abstentions halt short of the goal, at about the place A stops wrongly; they do
     not recognise arrival.
   - Its steering and its confirmation are untested separately; V2b and R2 together are
     untested.
3. **The B1 look-alike question is unresolved.** The matched-start design resets B1's
   counters at the handover, which partly fixes its corrections.
4. **The resume negative control** fails closed through an `IndexError`, not through
   the `resume` check; that check's conditions are covered only by unit tests.
5. **Launch-after-commit** relies on file times plus the ledger. Collections before
   amendment 2 have no robot USD digest.
6. **Three `test_environment_identity_v8` failures** remain (pre-existing, documented in
   `docs/ARRIVAL_RESEARCH_DECISION.md`).
7. **This file's earlier name** named a vendor tool; it was renamed at the owner's request.

## 7. Next justified experiment (proposal; not authorised, not frozen, not run)

**A prospective recovery test for R2 against B1x, on development layouts.**

- **Design:**
  - new kidnap start poses that no one has inspected (new arc fractions and headings,
    including uninformative views), declared and frozen before any run;
  - **exact-node and ±1-node recovery both pre-declared**, with exact-node as the
    primary measure;
  - the same frozen thresholds (exit 5.881, scan budget 36, two entries);
  - a pre-declared sample size;
  - an independent red-team before the freeze.
- **Add:** V2b+R2 combined, and V2b's steering without confirmation, to separate the two
  mechanisms.
- **Report V2b's added delay** as a primary outcome next to correct stops and contacts.

Held-out layouts stay sealed, and illumination work stays paused until the baseline
repair is accepted.

## 8. Standing rules (bind any agent here)

- **Authorship.** Frank Asante Van Laarhoven <frankleroyvan@gmail.com> only. No
  co-author, tool or AI attribution. In commit messages, call the root instructions file
  "the standing-instructions file". Never `--no-verify`.
- **No push. No real-robot actuation. No held-out access. No illumination experiments.**
- **Commits.** Never commit artefacts, logs, weights, images or `runs/`. Run formatters
  and `git add` on named files only, then read `git diff --cached --stat`.
- **Running collections.** Never edit source while a collection runs. Kill only PIDs
  you started.
- **One agent per worktree.**
- **Claims.** These are development results. No claim of held-out generalisation,
  illumination robustness, sim-to-real transfer, novelty or SOTA.
