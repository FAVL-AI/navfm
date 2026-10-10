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
