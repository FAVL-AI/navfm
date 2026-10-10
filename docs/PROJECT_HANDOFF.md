# Project handoff: arrival component comparison v2 (development)

Updated 2026-10-10 after the fixed offline CUDA numerical diagnostic.
Start from the current milestone below; prior stage 3 results
remain audited and preserved. Verify statements against files; files win.

## Current milestone: PR 2 integration CI repairs; merge BLOCKED

Normal PR 2 merge/main publication is authorised after meaningful checks. This milestone runs no experiment. All five original CI checks failed; genuine fixes fetch full history, repin all 2,791 nodes without losing any prior node/owner, and route the Torch-dependent constructor test to its existing owner. Full admitted-upstream verification retains three meaningful V8 failures. Clean no-Torch 3.11 reproduction confirms exact hermetic membership but ownership still rejects missing archived-manifest evidence; hosted CPU jobs also lack the frozen GPU/hold-stack resource. Python 3.10 UTC aliases are fixed in isolated integration candidate `680a631c2d5b5c97930d1362aa5969680fb00393`; all three supported Python typechecks pass, and candidate full verification still has the same three V8 failures. Candidate source identity changes are explicit; original engineering worktree `aa51007` and experiment freeze bytes/assets remain preserved. No experimental launch occurs on the changed candidate.

- Diagnosis/commands/counts/evidence: `docs/INTEGRATION_PR2_CI_REPORT.md`.
- Current durable PR text: `docs/ENGINEERING_DRAFT_PR.md`.
- Publication/remote check review must precede integration; no merge or main push with unvalidated meaningful checks, no bypass/force/history rewrite.
- Other worktrees and all prior experimental evidence are preserved. Held-out geometry sealed, illumination paused, robot actuation unauthorised.

## Preserved milestone: saved-input numerical mismatch reproduced offline

Freeze `32b83460839fbad96267ae9f3acbf81543903ad2` completed exactly two original-CUDA offline workers and 84 calls, without simulator launch, new image, retry or post-kidnap decision. Byte-identical preprocessed tensors with identical restored state/RNG produce bitwise identical outputs within/fresh processes. A separate CPU preprocessing-only audit performs zero inference and verifies all 168 reconstructed tensor hashes; observation max-absolute differences range 0.035014138–0.070028007 while goal/chain tensors match exactly. Differing preserved reference/replay observation tensors reproduce all seven original per-arm predictions exactly. All seven input pairs have matching discrete decisions but fail numerical agreement; yaw commands differ at steps 0/6, and later agreement is fixed scanning. Only stored state.history diverges; no additional sequence output amplification is observed.

- Result/deltas/settings/external hashes: `docs/OFFLINE_NUMERICAL_V1_RESULT.md`.
- Frozen protocol/manifest: `docs/OFFLINE_NUMERICAL_V1_PROTOCOL.md`, `configs/eval/offline_numerical_v1.json`.
- Single bounded interpretation review: `gates/redteam/offline-numerical-v1-interpretation-review-20261010.md`.
- External evidence: `/home/favl/navfm-runtime-evidence/offline-numerical-v1-20261010-01`.
- Checks: 89 focused PASS (13 new), ruff/mypy89 PASS, exact three preserved environment-identity failures.

Existing initialization/handover FAIL remains unchanged. The result identifies input-associated differences in this instrumented offline environment, not original rendering cause or universal CUDA determinism. Original global flags were incompletely recorded; evidence hooks synchronize. Next decision is preparation only of independently justified prospective behavioral-state/physical-command criteria for live-image variation, retaining same-input reproducibility and passive audit history. Use separate data near relevant margins; do not fit tolerances to observed maxima, reclassify attempts or launch automatically. No further process/efficacy is authorised by this result.

## Preserved milestone: observer passes; numerical learned handover FAILS

Freeze `9120decc6376db0f4f5bcece58e2866e488fdace` ran only the declared R2 A/s_bend0000 reference/replay pair. Both individual traces PASS; all 12 acquisition events are retained and all 84 image hashes checked. All 38 physical/history comparisons and all seven discrete learned outputs match, but all seven numerical invocation comparisons and full boundary policy state FAIL the unchanged 0.001 absolute / 0.00001 relative bound. Maximum window/predicted-distance difference is 0.068376541. Frozen decision is INITIALIZATION_HANDOVER_FAIL; execution STOPPED after two launches, with no post-kidnap policy invocation or efficacy run.

- Result, differing fields and external hashes: `docs/OBSERVER_WINDOW_V2_RESULT.md`.
- Frozen design/review: `docs/OBSERVER_WINDOW_V2_PROTOCOL.md` and `gates/redteam/observer-window-v2-executable-review-20261010.md`.
- External evidence: `/home/favl/navfm-runtime-evidence/replay-recovery-validation-v2-20261010-01`.
- Checks: 76 focused PASS; final ruff/mypy89 PASS, exactly three preserved environment-identity failures.

The observer repair does not validate actual learned handover or establish the numerical/image mismatch cause. All inherited freezes and failed attempts remain unchanged. Next decision: separately reviewed bounded input/numerical-equivalence investigation; no further launch, efficacy batch or threshold change follows automatically. Publication remains scoped to the engineering branch; root handles outgoing audit/publication.

## Preserved milestone: first learned-policy validation reference HALTED

First-pair executable freeze `d74927f7f2e88dd75e20f13646dc22f8e05c5671` is preserved. Only `A-s_bend_run_0000-R2_recover-r1-reference` ran: 114 render calls, 42 captures and seven scripted pre-kidnap CUDA learned-policy invocations. The frozen acquisition guard rejected an event with null active-call index alongside two boundary-call events. Saved RGB matches the last boundary event; stale pixels are not proved. Structured FAIL correctly halted despite process exit 0, without timeout/retry. Replay and all efficacy runs are NOT RUN; learned-policy handover remains unvalidated.

- Result/external hashes: `docs/REPLAY_RECOVERY_VALIDATION_V1_RESULT.md`.
- Frozen actual state/history/reset contract: `docs/PROSPECTIVE_R2_REPLAY_PROTOCOL_V1.md` and `configs/eval/replay_recovery_validation_v1.json`.
- One bounded executable review: `gates/redteam/replay-recovery-contracts-review-20261010.md`.
- External evidence: `/home/favl/navfm-runtime-evidence/replay-recovery-validation-v1-20261010-01`.
- Checks: 59 focused PASS; final full verify ruff/mypy89 PASS and exactly three preserved environment-identity failures.

No retry, repaired probe or further launch is authorised by this result. A future separately reviewed event-window contract/new freeze is the next decision; preserve this failed attempt and require initialization/actual learned-state gates before efficacy. The prior two-case proxy diagnostic below remains separate evidence.

## Preserved milestone: initialization/history diagnostic

Version 2 freeze `0393d46e814c80f2cc53ff9570af2c4015da2e7a` completed all eight fixed technical processes without retries, timeouts or provenance drift. **VERIFIED ON TWO SCRIPTED TECHNICAL CASES:** fresh-process command replay passes physical/controller, live six-buffer history and cross-repetition guards. Direct root reset fails; direct full observable-state restore passes physical/image bounds but fails temporal/index history equivalence. The recommendation requires fixed bootstrap, three eligible live frames, identical conditioning and 36-command replay with its own live history. No learned model or learned-policy handover was tested.

The original paired-image cause remains UNKNOWN and recovery pilot INCONCLUSIVE. Version 1 freeze `f831a110e6854c919a21c8397eee950cf79b77fd` and its failed first technical attempt remain preserved without retry. Its retrospective CPU reconstructions repeat exactly but fail the original CUDA/runtime numerical distance bound. Neither diagnostic reopens the remaining recovery starts.

- Current result/evidence hashes: `docs/INITIALIZATION_DIAGNOSTIC_V2_RESULT.md`.
- Frozen design: `docs/INITIALIZATION_DIAGNOSTIC_V2_PLAN.md`.
- Reviews: `gates/redteam/initialization-diagnostic-v2-protocol-review-20261010.md` and `gates/redteam/initialization-diagnostic-v2-results-review-20261010.md`.
- External evidence: `/home/favl/navfm-runtime-evidence/initialization-diagnostic-v2-20261010-01`.
- Preserved version 1: `docs/INITIALIZATION_DIAGNOSTIC_V1_RESULT.md`.
- Final `make verify`: ruff/mypy pass; exactly the three preserved `test_environment_identity_v8` failures. All 45 focused diagnostic/pilot tests pass.

Only scoped `agent/engineering-recording` publication to the existing FAVL-AI/navfm
remote and a draft pull request are authorised after outgoing-history checks.
No force push, history rewrite or merge. Held-out geometry stays sealed,
illumination paused, and real robot actuation unauthorised. Runtime artifacts
remain external.

## Next proposal and publication

Commit `7b7590061a338848fca9f3c1f54cca2cb831647a` was published on the engineering branch. Draft PR submission is handled separately; no merge is authorised. The durable authored description is `docs/ENGINEERING_DRAFT_PR.md`.

`docs/PROSPECTIVE_R2_REPLAY_PROTOCOL_V1.md` is a preparation-only draft for four new proposed recovery pairs. It requires metadata attestation of new experimental starts, intended-start initialization matching and actual learned-policy handover validation before efficacy. The timestamped post-kidnap boundary, actual arm-state/reset schema and finite first-pair launch contract were reviewed and frozen. The first version-1 reference failed integrity and halted. The separately frozen observer-window v2 pair passed acquisition/physical guards but failed numerical learned handover, as recorded above; efficacy did not run. Metadata-only comparison of 283 numeric tuple records establishes new experimental starts in that inventory, not research novelty. Full cross-repeat/cross-arm gates and efficacy remain blocked; do not resume the halted pilot automatically.

## Preserved milestone: prospective recovery pilot

The narrow R2 versus B1x prospective protocol was independently reviewed and
frozen at `54bfc239b3f8d4e5443212822582711b78925bbd`, then executed on four declared
development start pairs. Eight recordings are PASS, with no retries; two paired
initial-image differences fail the frozen 2.5 grayscale bound. Expansion was
HALTED: 12 further pairs/24 arm attempts are NOT RUN. Overall result:
**INCONCLUSIVE**, not recovery confirmation or a safety improvement.

- Result and all eight external attempt identities/hashes:
  `docs/PROSPECTIVE_R2_PILOT_RESULT.md`.
- Frozen protocol: `docs/PROSPECTIVE_R2_PROTOCOL_V1.md` and
  `configs/eval/prospective_r2_recovery_v1.json`.
- Independent review records:
  `gates/redteam/prospective-r2-protocol-review-20261010.md` and
  `gates/redteam/prospective-r2-pilot-review-20261010.md`.
- External analysis: `/home/favl/navfm-runtime-evidence/prospective-r2-v1-pilot-analysis-20261010-01.json`.
- External ledger: `/home/favl/navfm-runtime-evidence/prospective-r2-v1-launch-ledger.jsonl`.

Do not resume the remaining version 1 starts or loosen its matching bound. The
separately frozen initialization/state/history diagnostic and its bounded technical
outcome are recorded above. The earlier next-experiment proposal in section 7 is superseded
by this frozen pilot and its halted outcome. The complete stage 2/stage 3 evidence
below is preserved and was reverified: stage 3 analysis equals saved evidence,
all 18 report rows reconcile, and recovery remained NOT TESTED there.
Post-experiment full verification still has exactly the three documented
`test_environment_identity_v8` failures; ruff/mypy and 40 focused tests pass.
Only publication of `agent/engineering-recording` to the existing FAVL-AI/navfm
remote and a draft pull request is authorised after the reviewed initialization
diagnostic and outgoing-history checks. No force push, history rewrite or merge.
Held-out access, illumination experiment and real robot actuation remain unauthorised.

## 1. Repository state

| | |
|---|---|
| Worktree | `/home/favl/projects/navfm-engineering-recording` |
| Branch | `agent/engineering-recording`; scoped branch publication and draft pull request authorised after diagnostic/outgoing-history checks (see remote/PR for publication status) |
| HEAD | current diagnostic result/handoff commit (see `git log -1`); diagnostic freeze `f831a11`, prospective freeze `54bfc23`, prior baseline `6a47011` |
| Working tree | clean at handoff (`git status --porcelain` is empty) |
| Commits to preserve | `7d2e383`, `d6139c0` (v1 results) and everything after them |

Historical stage-3 handoff chain before the prospective freeze (preserved):

| Commit | What it does |
|---|---|
| `6a47011` | Stage-3 report and decision record; initial handoff (renamed from the earlier handoff note) |
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
