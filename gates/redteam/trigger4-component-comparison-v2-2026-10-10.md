# Trigger 4: component comparison v2 protocol, 2026-10-10

Three independent read-only reviews before freeze (no v2 trial run before freeze).

## Round 1 (1da4e55): DO-NOT-FREEZE
- H1 B1 ignored --start-lost (spec without v2 keys). Fixed: topomap_components passes
  start_lost for every spec; test builds a lost B1 policy.
- H2 recorded initial node always 0 under resume. Fixed: effective node and lost state
  recorded per episode after set_chain; reset per route; analysis uses them; tested.
- H3 R2 changed threshold and scan together; mild kidnapped starts. Fixed: B1x control
  (v1 lost behaviour, R2's threshold); uninformative-view starts (yaw 180, 90);
  comparative gate.
- H4 V2 changed logic and steering together. Fixed: V2a (logic only) and V2b (+ steering).
- M1-M7 and LOW items: S1a at 0.5 m, stage 1 labelled in-sample; look-alike measure
  counts lost following, needs a full horizon, ends at task end; backward-step tally and
  decision 13/14 starts; premature-latch and false-global-match measures; completeness and
  exposure in gates; stage-3 criteria; v1 state-machine regression on recorded decisions.

## Round 2 (0468814): FREEZE-WITH-AMENDMENTS (H1-H4 verified fixed)
- N1/N9 stage-3 decisions implemented, NOT_TESTED for vacuous recovery comparisons.
- N2 trial and stage recorded and checked. N3 retry rule declared and enumerated.
- N4 role text names R2's whole bundle; R2 gate adds wrong stops and per-metre contacts.
- N5 V2b-minus-V2a contrast. N6 premature latch in metres. N7 stage-2 premature_*
  trials on the true s_bend chain; V2 gates need zero wrong stops there.
- N8 look-alike gate NOT_TESTED when A does not reproduce it or B1 has no evaluable
  encounter. N11-N14 integrity additions; N13 tests for checks, negative modes, gates.

## Round 3 (4030a37, narrow): FREEZE-WITH-AMENDMENTS
- H1 gates could pass on a subset of trials. Fixed: every declared trial of a question
  is required; tested.
- H2 stage 3 required comparators the protocol does not run (forced REVISE). Fixed:
  required set = passing components, A, counterparts (B1 also for R2); tested.
- M1 retry rule logged, not enforced; crashes invisible. Fixed: planned routes without an
  episode are CRASHED attempts; only the first two attempts can count; violations leave
  the route uncounted; tested.
- M2 stage-2 result trusted by mtime. Fixed: the record is committed under gates/v2/,
  read from that commit, checked (freeze commit, config hash, negative control, full
  stage-2 coverage) and its gates recomputed; stage-3 collections must postdate the commit;
  tested with a temporary repository.
- M3 missing data or integrity failure reported as REVISE. Fixed: INCOMPLETE; tested.
- M4/M5/L1 swap recovery exemption, R2 counterpart wording, vacuous comparisons recorded
  as NOT_TESTED. L2 collector refuses output names other than v2-<trial>-<variant>-<tag>;
  tested. L3 malformed manifests become integrity failures, not crashes.

Remaining stated limitations are listed in the config (known_limitations).

## Amendment v2.1 (before any counted trial)
An engineering smoke check (not counted) showed the at-rest matched state did not
reproduce the recorded camera view (11.3 grey levels, first-decision distances off
by 10.28, argmin 5 instead of the look-alike node 10). Matched states now replay the
recorded episode's commands from its start to the handover decision (cbbf3ea); a
replay smoke reproduced the recording exactly (0.0 m) and the decision-22 look-alike.

## Round 4 (cbbf3ea, narrow review of the amendment): FREEZE-WITH-AMENDMENTS
Nothing HIGH; replay mechanics, indexing and the amendment's numbers verified.
- Fidelity checked only x, y, yaw, which replay matches by construction. Fixed (ca03cde):
  image (<= 2.5 grey) and decision-K distance (<= 1.0, same window) bounds.
- Disclosure omitted the replay smoke and that two smokes ran counted cells. Fixed.
- Replay check read the collector's own record. Fixed: applied commands verified from
  trajectory transitions; source manifest hash recomputed.
- Replay-phase measures and fresh-counter consequence declared; pre-handover contact is
  an integrity failure; route following measured from handover; collector refuses a
  source episode that ended before handover; negative tests for each new check.
A fifth smoke confirmed the fidelity fields are recorded in Isaac (outcome not inspected).
Frozen as v2.1.

## Amendment 2 (v2.2): readback yaw wrap; recovery block re-collected (after stage 2 ran)

Trigger: stage 2 of v2.1 (83101fa) ended with 14 FAILED kidnap attempts, all with
"saved pose differs from captured pose". Diagnosis: the readback compared the
writer's unwrapped yaw with the raw wrapped capture yaw; exactly the 14 crossed
+/-pi. Fix commits 284045d, 1273db9. Record:
`configs/eval/component_comparison_v2_amendment_2.json`. The as-collected audit and
analysis (gates: B1 FAIL, V2a FAIL, V2b PASS, R2 INCOMPLETE) were produced before
the amendment and are kept unchanged.

### Round A1 (partial reruns of the 14): REFUTED
Survived: diagnosis (14/14 cross +/-pi, 0 passing attempts do; readback replay
rejects exactly the 14 with the frozen code, accepts all with the fix); the fix does
not weaken the check; no behaviour effect (readback after the loop); counts.
Findings and resolution:
- F1 HIGH: the 14 are not blind; transitions show all 8 failed R2 attempts ended
  0.13-0.31 m from the goal; the decision to amend was taken when the likely outcome
  was readable. -> Disclosed with a 48-row diagnostic table
  (v2-stage2-kidnap-first-attempts-inferred-20261010-01.json; inference 34/34 on
  passes); descriptive concordance rule; reporting conditions.
- F2 HIGH: partial reruns mix draws and source versions within a cell. -> Whole
  recovery block (12 cells, 48 attempts) re-collected; originals superseded.
- F3 HIGH: amendment record not pinned. -> sha256 pin, FROZEN status, base config,
  ancestry; widened-record test.
- F4 MEDIUM: launch-after-commit rests on file times. -> launch ledger (see A2/G3);
  limitation disclosed.
- F5 MEDIUM: not a retry under the frozen rule. -> declared a protocol change; skipped
  post-readback checks of the 14 listed.
- F6 LOW: readback repeats the writer's computation. -> 1273db9 checks the property
  (mod 2*pi, continuity) independently.
- F7 LOW: imprecise counts and non-repo claim. -> corrected.

### Round A2 (full re-collection): REFUTED (narrower)
Verified F1-F7 fixes, launcher arguments identical to stage 2, counts. Re-collection
judged defensible on three conditions (now `reporting_conditions` in the record).
- G1 HIGH: the block's rerun tag would be invisible to the analysis. -> block = tag
  plus rerun tag under the retry rule; superseded logged; other tags are violations;
  tests for -03 after non-PASS, after PASS, -04, and a block starting at -03.
- G2 MEDIUM: false claim that the robot USD is pinned. -> corrected; USD sha256 written
  to the ledger before and after every collection.
- G3 MEDIUM: launcher not committed or hardened; ledger unchecked. -> launcher committed,
  refuses dirty tree, non-descendant HEAD, changed record, foreign cell or route,
  existing output; cell order taken from the record; analysis checks ledger (clean tree,
  HEAD ancestry, frozen_routes.json digest), with tests.
- G4 MEDIUM: analysis script not pinned. -> script must equal its blob at the amendment
  commit; its sha256 stored in the gate record and required for stage-3 admission.
- G5 LOW/MEDIUM: concordance only prose. -> scripts/concordance_kidnap_v2.py committed
  before launch (reproduces the diagnostic table on all 48 superseded attempts);
  non-gating; no further amendment of the block whatever its result.
- G6 LOW: this section, FROZEN status and pin close in the freeze commit.

### Round A3 (G1-G6 fixes): REFUTED (one blocking finding)
Verified G1-G6 fixed; HEAD equal to the amendment commit passes ancestry; no circular
pin (the script pins the record; the record does not name the script's hash).
- H1 HIGH: the ledger requirement would fail every stage-3 attempt (no stage-3 ledger
  writer). -> launcher `stage3` mode (cells from the committed stage-2 gate record via
  required_stage3, tag s3-01) and stage-3 reruns (s3-02); test: a stage-3 attempt passes
  with a ledger entry, fails without.
- H2 MEDIUM: ledger read from any path; USD digests unchecked. -> ledger read from git
  (--ledger-commit/--ledger-path), blob sha256 stored in the output; USD digest must be
  equal before/after and across collections; tests.
- H3 LOW: rerun mode would rerun a PASS. -> refused unless the first attempt is not PASS.
- H4 LOW: file-time check remains; disclosed; no change.
Freeze commit: status FROZEN and the record's sha256 pinned in the analysis script, in
the same commit; the reviewer re-checks the pin against that commit before any launch.
