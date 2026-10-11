# Trigger 6: component comparison v2, stage-2 results (2026-10-10)

**Reviewed:** `gates/v2/stage2-report-20261010.md` and `gates/v2/stage2-gate-record-20261010.json`
(byte-identical to `v2-stage2-analysis-20261010-02.json`). An independent reviewer
was given only the artefacts and the evidence.

**Verdict:** ACCEPT WITH CHANGES.

**What held up.** Every table count recomputed exactly:
- correct, wrong, abstain, timeout, contacts, per-metre rates, path lengths;
- delays, latch distances, lost entries, successes;
- fidelity ranges and negative-control counts.

Also confirmed:
- collection and attempt accounting, the ledger, the hashes and the 48/48 concordance;
- all four gate statuses follow from `gates_to_stage_3`;
- the stage-3 set: 18 cells, 54 attempts.

**Findings, all applied to the report before commit:**

| ID | Severity | Finding | Change made |
|---|---|---|---|
| F1 | HIGH | 4 of R2's 6 hard-view successes sit exactly on the ±1-node tolerance; the 2 failures miss it by one node; a tolerance of 0 gives 2 of 8 | Added to §1, §5 and §6 |
| F2 | HIGH | The amendment's reporting condition was only partly met | Added the as-collected R2/B1x gate inputs and all 14 inferred outcomes (§4) |
| F3 | HIGH | Smoke runs previewed counted cells of both passing gates (R2 kidnapped_c `junction_run_0000`; V2b arrival_truncated `junction_run_0000`) | Disclosed (§1, §2, §6) |
| F4 | MEDIUM | V2b also passes exactly at threshold | Stated |
| F5 | MEDIUM | V2b's premature and arrival abstentions halted short of the goal, at about A's wrong-stop place; "0 wrong stops" holds on scoring semantics | Stated |
| F6 | MEDIUM | V2a on premature_true never latched | Corrected to "3 of 4 latched" |
| F7 | MEDIUM | B1's look-alike corrections occur at decisions 0–2 after handover; 2 at decision 0 are guaranteed by the fresh-counter reset | Qualified |
| F8 | MEDIUM | The "all successes" column was ambiguous against the gate quantity | Relabelled; the gate compares 13 against 7 |
| F9 | MEDIUM | Frozen known limitations were missing | Added: design scope, non-replica pairs, exit calibration and false global matches (R2 7, B1x 10), scan creep, untested V2+R2, bundle attribution |
| F10 | LOW–MEDIUM | The concordance claim overstated | Now "agreed on both pre-declared descriptive measures"; the defect is settled by the fixes and tests |
| F11 | LOW | Fidelity zeros are exact by construction | Stated |
| F12 | LOW | The backward-proposal sentence implied a cause | Made descriptive, with timing |
| F13 | LOW | Wording: required_stage3 derivation, per-collection superseded log, R2 abstentions column, goal-image scoring, multiplicity, verify status | Fixed |
