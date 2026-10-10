# Trigger 6: component comparison v2, stage-3 results (2026-10-10)

**Reviewed:** `gates/v2/stage3-report-20261010.md` and
`gates/v2/stage3-decision-record-20261010.json` (byte-identical to
`v2-stage3-analysis-20261010-01.json`). An independent reviewer was given only the
artefacts and the evidence.

**Verdict:** ACCEPT WITH CHANGES. The RETAIN decisions follow from the frozen code and
criteria; the defects were in what the report said they establish.

**What held up:**
- §3 counts, contacts and paths;
- V2b's delays (15, 22 and 25 decisions) and latch range;
- the §4 exact-node table;
- provenance: config and script sha256, ledger lines 25–60, and `8959333` being an
  ancestor of `c2ef497`;
- the identity of the truncated trial with stage 2's `arrival_truncated`.

**Findings, all applied before commit:**

| ID | Severity | Finding | Change made |
|---|---|---|---|
| F1 | HIGH | V2b's swap comparison is NOT TESTED (no stops in either arm) | RETAIN restated as resting on the true and truncated chains |
| F2 | HIGH | Every comparator contact came late in a timeout; V2b and R2 episodes ended earlier | "No contact regression" reframed as largely an exposure effect, with the guard's detectable range stated (0 of 4 is compatible with a contact rate above 50%); "contacts" defined as episodes with any contact |
| F3 | HIGH | "Missed arrival by every variant that declares" was false: B1, B1x and R2 reached that goal | Corrected |
| F4 | HIGH | V2a/V2b figures in §6 were wrong | Corrected to 49.6–87.3°, 40 approach decisions, 2 V2b votes and 11.9 in region; computation stated |
| F5 | MEDIUM | The V2a account was causal on n = 1 | Relabelled HYPOTHESIS; junction headings added (V2a confirmed at 16–33°); "would-be wrong stops" limited to the s_bend route |
| F6 | MEDIUM | §4 omitted wrong-node relocalisations | Wrong-node and re-entered columns added. R2 had 3 wrong-node relocalisations; B1x had 1 wrong-node and 3 re-entries, not the reviewer's 4 wrong-node |
| F7 | MEDIUM | The truncated "check" is a near-deterministic re-draw; known limitations were missing | Reworded; limitations added |
| F8 | LOW | R2's swap-halt distance and its source | Halt at 1.75 m (minimum 1.69 m); the manifest is cited |
| F9 | LOW | Provenance and amendment wording | Launcher and analysis-script changes since the freeze noted; the failed stage-3 confirmatory premise for R2 stated |
