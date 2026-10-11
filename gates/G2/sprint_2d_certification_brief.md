# Sprint 2D — Cross-Consumer Intervention Certification

**Status: PREREGISTERED / BLOCKED**

**Purpose.** Certify that every target-directed collision consumer now
represents the same contract-owned physical intervention for equivalent target
geometry, role and policy configuration.

**This file defines the certification protocol. It does not record an executed
certification result.** Sprint 2D may begin only after the G2 Isaac Sim runtime
gate has executed and passed. See `runtime_gate_brief.md` in this directory.

| | |
|---|---|
| `SPRINT_2D_PROTOCOL` | **PREREGISTERED** |
| `SPRINT_2D_EXECUTION` | **NOT RUN** |
| `RUNTIME_GATE` | **NOT RUN** |
| `SPRINT_2D_CERTIFICATION` | **NOT RUN** |
| `SAFE_TO_REMEASURE_HOSPITAL` | **NO** |
| `CANONICAL_SCENE` | **NONE** |

---

## Why this is a separate sprint

Three statements are routinely collapsed into "the collision tests work". They
are not the same statement, and each is established by different evidence.

    Sprint 2C          "Do all tools call the same policy?"          PASS
          |
    G2 runtime gate    "Does the migrated policy still behave
                        correctly under executed PhysX?"             NOT RUN
          |
    Sprint 2D          "Do equivalent tools perform equivalent
                        physical experiments?"                       BLOCKED
          |
    Contract amendment
          |
    Hospital remeasurement

Sprint 2C proved wiring. Sprint 2D must prove equivalence of the experiment
itself, under executed evidence. A tool can call the right function and still
ask a different physical question if it feeds that function different inputs, or
interprets its output differently.

---

## Research question

> After migration to one contract-owned candidate policy, do all target-directed
> NavFM collision consumers construct and interpret equivalent physical
> interventions when given equivalent target geometry, role and policy
> configuration?

## Preregistered hypotheses

**H1.** For equivalent target geometry, target role and policy configuration,
every migrated target-directed consumer will generate an equivalent pre-query
candidate population. *Equivalent* means equality of every contract-relevant
intervention semantic: target identity, role, candidate count, candidate IDs,
candidate ordering, intervention labels/faces, origins, directions, standoff,
maximum range, validity state, and policy digest.

**H2.** Differences in downstream hit/miss, returned collider, occlusion,
ambiguity, identity adjudication and final verdict must arise from
physics, query and adjudication context, and must **not** mutate the pre-query
candidate population.

**H3.** Volumetric footprint overlap and sweep operations remain outside the
target-directed candidate-policy equivalence claim.

## Null / failure conditions

Certification **fails** if consumers that should be equivalent produce different
contract-relevant candidate semantics without a previously declared reason:

different candidate count · two faces versus four · different origin ·
different direction · different standoff · different range · different ordering
where order is semantically relevant · different validity handling · different
policy digest · adaptive candidate creation after observing a query result ·
candidate removal after failure · target identity influencing candidate
generation after query · support implemented with lateral blocker semantics ·
a local candidate generator still controlling execution.

**Equivalence must not be redefined after seeing results.** That is the whole
reason this file exists before the evidence does.

---

## Prerequisite gate — Sprint 2D is prohibited until this passes

Execution requires the committed G2 runtime evidence to show **all** of:

| Requirement | Current |
|---|---|
| `validate_collision_probe_causality` 9/9 actually executed | NOT RUN |
| `validate_dense_targetability` 5/5 actually executed | NOT RUN |
| `validate_physx_footprint_oracle` 9/9 actually executed | NOT RUN |
| total original frozen cases 23/23 | NOT RUN |
| no frozen case skipped | — |
| no expected answer rewritten | — |
| policy digest `c6534203825fa13d` | — |
| no negative population accounting | — |
| runtime provenance complete | — |
| runtime gate PASS | NOT RUN |
| `SAFE_TO_BEGIN_SPRINT_2D` YES | **NO** |

If any prerequisite is missing: `SPRINT_2D_STATUS = BLOCKED`.

**Static analysis and CI are not substitutes for this prerequisite.** Sprint 2C
was green on both while the physics remained unexecuted; that is precisely the
gap this gate closes.

---

## Certification subjects

Resolved from the repository at `e66fe93`, not assumed:

| # | Path | Imports the shared policy |
|---|---|---|
| 1 | `scripts/diagnose_hospital_isolation.py` | yes |
| 2 | `scripts/validate_dense_targetability.py` | yes |
| 3 | `scripts/validate_collision_probe_causality.py` | yes |
| 4 | `scripts/validate_physx_footprint_oracle.py` | **no — by design** |
| 5 | `scripts/audit_office_collision_coverage.py` | yes |

**Consumer 4 has no target-directed portion.** SD-001 established this by
survey: it declares no target in any operation, and its adjudication concerns
occupancy and traversability rather than collider identity. Its row in the
certification matrix is therefore `INTENTIONALLY_NOT_COMPARABLE`, and what must
be certified about it is the **boundary itself** — that it still routes nothing
through the candidate policy and still declares no target. If a target-directed
ray probe is ever added to it, that probe comes into scope.

## Out-of-scope boundary (SD-001)

Out of scope for intervention-policy equivalence: generic PhysX overlap ·
robot-footprint occupancy · robot-footprint sweep · traversability sweep ·
censored volumetric sweep · volumetric oracle operations without a declared
target. These remain under the footprint/oracle contract. **Do not force them
into candidate-policy certification.**

---

## The certification unit

The unit is **not** a script name, and **not** a final PASS/FAIL verdict. It is:

    TARGET + ROLE + POLICY CONFIGURATION + PRE-QUERY CANDIDATE POPULATION

Consumers are compared **before physics execution**, on an equivalent fixture.

### Canonical certification record

Per consumer and equivalent fixture, record: consumer · fixture ID · target ID ·
target role · target bounds/geometry digest · policy version · policy digest ·
policy variant · candidate count.

Per candidate: candidate ID · index/order · intervention label or face · origin ·
direction · standoff · range · valid/invalid · invalid reason.

Then, **separately**: query executed? · hit/miss · returned collider · identity
adjudication · targetability status · probative status · final fixture verdict.

**Do not combine the pre-query and post-query records into one ambiguous
state.** Their separation is the evidence for H2.

---

## BLOCKER certification

For equivalent blocker geometry under the default production policy, certify the
finite logical population `+X`, `-X`, `+Y`, `-Y`. All relevant consumers must
agree on: four logical slots · candidate IDs · ordering · origin rule · inward
directions · default standoff · range rule · validity semantics ·
degenerate-face handling.

No consumer may drop a face because another succeeded, add a face because
another failed, retry until hit, or construct candidates from an observed
collider identity.

## SUPPORT certification

Every support-capable consumer must use the same target-directed top-down
intervention, agreeing on: support role · candidate population · candidate ID ·
origin above the declared target · downward direction · standoff · range ·
validity semantics · target-specific identity requirement.

**Explicit negative regression.** The old lateral SUPPORT construction must
**fail** certification. Sprint 2D must make it impossible to certify "support"
implemented as a lateral blocker probe. That defect executed once, in the
superseded Hospital run, and produced eight support probes of which none fired.

## Control-variant certification

Certification includes the declared controls: `causality_control` at 0.50 m,
1.00 m and 1.50 m, and `shared_origin_control(40.0)`.

| Variant | Digest |
|---|---|
| production (v4) | `c6534203825fa13d` |
| `causality_control(0.50)` | `f262ab4c40adaf08` |
| `causality_control(1.00)` | `7670a01604dd7314` |
| `causality_control(1.50)` | `b303977ded31507c` |
| `shared_origin_control(40.0)` | `c0a05923595b72bb` |

These are explicit policy variants, never production defaults. For identical
variant configuration all consumers using it must receive identical intervention
semantics, and different variants must remain distinguishable by policy digest.

## Observation-independence certification

For a fixed target, role and policy configuration, generate the candidate
population under differing downstream outcomes — hit, miss, wrong collider,
occluded, non-isolatable, ambiguous. The canonical pre-query representation must
be unchanged.

Required: `candidate_generation(target, role, policy)` is independent of hit
result · collider identity · hit distance · hit point · hit normal · prior
candidate success · prior candidate failure · final scene verdict.

## Targetability certification

Targetability may **classify** a candidate — isolatable, occluded, ambiguous,
not-isolatable, invalid geometry, no evidence — but classification happens
against the preregistered population. It must not generate a new search
direction after observing a failure. A gate that looks further when it dislikes
the answer is a search, not a test.

## Identity / causality certification

Generic activity is not target-specific correctness. A target-directed probe is
not successful merely because something was hit. The chain must remain visible
end to end: candidate intervention → physics result → returned collider
identity → target-specific adjudication. Where a fixture requires
target-specific evidence, the intended target must be shown to have caused the
accepted observation.

## Accounting certification

Required nesting, by counted probe identity:

    selected ⊇ reachable ⊇ targetable ⊇ fired ⊇ adjudicated ⊇ probative

Terminal dispositions must be disjoint and their union must equal the selected
population.

**Regression requirement.** The historical state equivalent to `reachable = 7`
and `non_probative = 8` must never produce `probative_population = -1`. A
negative population is an instrument failure, not a number to interpret.

---

## Required negative controls

Target absent or disabled · wrong collider · occluded target · competing
geometry · non-isolatable target · degenerate geometry · invalid candidate ·
observation independence · SUPPORT lateral-probe rejection · candidate
population immutability.

**Do not add acceptance rules merely to make these pass.** A control that cannot
fail certifies nothing.

## Cross-consumer parity matrix

Rows are canonical fixture / target-role-policy combinations; columns are the
target-directed consumers able to represent that combination. Classify each
comparable pair as `IDENTICAL`, `INTENTIONALLY_NOT_COMPARABLE`, or `FAIL`.

Do not write "basically equivalent", "roughly the same" or "similar". Use exact
equality for numerical candidate semantics generated from the same
deterministic inputs. **If floating-point serialization requires a tolerance,
preregister the tolerance and its justification before execution.** A tolerance
chosen after seeing a discrepancy is a result fitted to its instrument.

`INTENTIONALLY_NOT_COMPARABLE` is valid only where certification inputs differ
by design — a different declared policy variant, a different target role, or a
volumetric operation outside SD-001 — and the exact reason must be recorded.
Serving a different downstream purpose does **not** license different candidate
physics for the same target, role and policy.

---

## Historical evidence boundary

Do not recompute the old Office or Warehouse behavioural rows to manufacture
before/after numbers. They were produced under superseded intervention
semantics and are retained as provenance under that status. A changed value
after an instrument correction is **not** a scene or model improvement, and
presenting it as one would be the most flattering error available here.

## Hospital claim boundary

Sprint 2D is **not** a Hospital remeasurement. Hospital remains
`NO_EVIDENCE / PENDING`; `wrong_1` remains `UNRESOLVED`. Do not run the
Hospital, Office or Warehouse production scene measurements. Do not select a
canonical scene. `gates/scenes/hospital_collision_coverage_audit.json` is known
stale and must not be edited, staged, cleaned, restored or reinterpreted.

---

## PASS criteria

`SPRINT_2D_CERTIFICATION = PASS` only if **all fourteen** hold:

1. runtime prerequisite gate PASS is verified;
2. all target-directed candidate generators are shared-policy controlled;
3. no duplicate local target-candidate generator controls execution;
4. equivalent BLOCKER inputs produce equivalent candidate populations;
5. equivalent SUPPORT inputs produce equivalent candidate populations;
6. explicit control variants produce their declared semantics;
7. observation outcome does not change candidate construction;
8. targetability does not mutate the candidate population;
9. target-specific identity adjudication remains separate from generic hit;
10. accounting invariants pass;
11. negative controls pass;
12. the volumetric footprint boundary remains preserved;
13. no frozen expectation was rewritten to obtain PASS;
14. provenance is complete.

Any item failing gives `FAIL` if executed, `BLOCKED` if not. **Do not average
failures away.** Fourteen criteria with one failure is a failure, not 13/14.

## What a PASS may claim

> The identified NavFM tools use equivalent contract-owned physical
> interventions for equivalent target geometry, role and policy configuration,
> and preserve a separate contract for volumetric footprint operations.

An instrumentation and certification claim. **It is not evidence that any Isaac
scene is suitable.**

## What a PASS may not claim

Not from Sprint 2D alone: Hospital is valid · Hospital passes · Office is valid ·
Warehouse is valid · a canonical scene is selected · a robot trajectory was
collected · GNM, ViNT or NoMaD performance · a safety improvement · a navigation
improvement · sim-to-real transfer.

**Sprint 2D certifies the measurement instrument, not the scene and not the
model.**

---

## The certification artefact, when it exists

When Sprint 2D executes, write a **new append-only result artefact** under this
directory, following the existing G2 evidence convention. **Do not put
observations into this preregistration file.**

The future result must bind: exact HEAD · runtime-gate evidence digest and path ·
candidate-policy digest · fixture digests · consumer set · parity results ·
negative-control results · accounting results · timestamp and environment ·
final certification status.

**Do not create that artefact now.**

## After a Sprint 2D pass

If and only if Sprint 2D passes, the next tranche prepares the append-only
behavioural-contract amendment binding the candidate-policy digest, the physical
intervention semantics, the parity certification evidence, the runtime harness
evidence, the accounting semantics and the expected-answer provenance.

**Only after that contract is frozen may Hospital be remeasured.** Do not begin
that tranche automatically from a Sprint 2D pass.
