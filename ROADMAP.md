# ROADMAP — the thesis-level programme this repository anchors

This repository is not a navigation model. It is the first, load-bearing
component of a research programme whose subject is **navigation model
trustworthiness**: can the claims a navigation system's evaluation produces be
made checkable — data admissibility, label provenance, protocol
pre-registration, transfer validity — rather than assumed?

This document states the programme once, maps it onto what exists, and labels
every component with its honest maturity. It changes nothing about execution:
`docs/WORKFLOW.md` (phases, gates) remains the operative plan, and no work is
scheduled here that is not already gated there, except where explicitly marked
FUTURE.

## The framing

Most navigation papers ask: *did the robot reach the goal?* This programme
asks: *what would it take to make the reported result independently checkable —
to establish that it means what it claims?* The audit of the reference
implementation (paper draft §3, findings F1–F12) is the demonstration that the
question is not pedantic: widely used open navigation models rest on an
unspecified data format, silently corrupting label pipelines, dead
configuration keys, unexplained constants, and metrics that move by 0.46 with
batch size. Trustworthiness is not a module bolted onto a policy; it is a
property of the *evidence pipeline*, and that is what this repository builds.

## Research questions

- **RQ1 — Evaluation validity.** "Under what conditions can the performance
  claims of visual navigation systems be independently reconstructed and
  considered evidentially valid?" (Papers 1–2)
- **RQ2 — Transfer validity.** "How do mismatches between demonstration,
  execution, and evaluation conditions affect the validity of visual
  navigation transfer claims?" (Paper 1, extended through Paper 3)
- **RQ3 — Decision reliability.** "Can calibrated model evidence support more
  reliable stopping and safety decisions under domain shift than uncalibrated
  policy outputs?" (Papers 3–4)

These form a coherent escalation: can the result be reconstructed; does it
transfer validly; can the evidence support runtime decisions.

## Thesis-level claim

"Reliable visual navigation cannot be established solely through policy-level
performance metrics. It requires an evidence pipeline that controls data
admissibility, implementation provenance, protocol validity, transfer
conditions, and decision calibration; when these controls are applied,
previously hidden sources of variation and failure become measurable and
materially alter the interpretation of navigation performance."

## Terminology

**Admissibility.** "Data are admissible for a stated experiment when their
provenance, schema, semantics, generation conditions, integrity, and
compatibility satisfy pre-specified criteria sufficient for the experiment's
claimed inference." Admissibility is always relative to a claim under a
protocol — there is no context-free admissible dataset.

**Forensic.** Artefact-preserving, provenance-aware, independently
inspectable, hypothesis-neutral, and capable of reconstructing how a result
was produced.

**Compatibility proof.** Proof in the software-testing sense — a passing
executable check against the unmodified reference implementation — not
mathematical proof. This is the one place the word is retained, as the name of
an artefact. Empirical-validity language everywhere else uses "independently
checkable" or "evidential warrant", never "prove".

**Archived evidence.** A claim that cannot be demonstrated from the archived
evidence is equivalent to an unsupported claim. That is the operational
definition of why gates archive their outputs rather than assert their
properties, and why a documentation claim whose proof lived only in a
gitignored directory was not evidence (finding F-M1-2, `gates/failures/`).

## Programme structure: papers, not modules

The programme is a sequence of mutually reinforcing papers sharing one
infrastructure — not a monolithic multi-module architecture. Each paper is
gated on evidence before the next is scoped. Anything without a green gate
behind it is labelled exactly that.

Maturity labels used throughout this repository are exactly five: **SHIPPED**,
**OPERATING**, **IN EXECUTION**, **PRE-REGISTERED (PENDING)**, **FUTURE**.
They describe the maturity of a component. They are distinct from the honesty
markers PROVISIONAL and UNVERIFIED, which mark an unmeasured *value* and are
removable only by a measurement whose method is recorded in
`docs/HARDWARE.md`.

### Paper 1 — the current work (IN EXECUTION, Phases 0–6, gates G0–G6)

*Holonomic Execution of Nonholonomic Priors: A Forensically Validated
Simulation Pipeline for Adapting Visual Navigation Foundation Models.*

Contains, in the taxonomy of trustworthiness: the **admissibility layer**
(format specification + validator + compatibility proof — SHIPPED, tested),
the **provenance layer** (checkpoint hashes, pinned upstream, derived
constants, per-trajectory generative metadata — SHIPPED), the **evidence
ledger** (gates, tags, pre-registration — OPERATING), and the **transfer
benchmark** (E1–E6 — PRE-REGISTERED (PENDING)). Plus one substantive
scientific question the audit makes askable: the demonstration/execution
kinematics 2×2.

Status: infrastructure frozen at commit `c82e406`, annotated tag `m1-freeze`;
the first empirical gate (G0.c) is the immediate next milestone and no
scientific result exists before it.

**What milestone M1 contributed.** M1's contribution is the removal of three
independent threats to reproducible scientific evidence: a documented
reproduction command that failed on its own documented invocation, a
provenance claim whose proof existed only in a gitignored directory, and a
gate script that deleted paths it had not created (F-M1-1 to F-M1-3, recorded
in `gates/failures/`). It is explicitly **not** an improvement to the
navigation model. None of the three fixes changes what ViNT predicts; they
change whether any future claim about what ViNT predicts can be checked. The
distinction matters because the thesis is about evidence, not about policy
performance.

M1 validates the reproducibility infrastructure within a **declared**
execution environment. Extending that validation to the **canonical**
execution environment is M2's first work, and it happens before any scientific
claim is generated.

That ordering is itself evidence for the programme's central argument. The
pipeline produced F12, the scheduler-resume defect, and the three M1
verification defects *before* it produced a single navigation result. Once an
evidence pipeline is made executable and inspectable, hidden assumptions
become observable — which is what RQ1 asserts, demonstrated here on this
repository rather than claimed about someone else's.

### Paper 2 — the audit as a standalone contribution (FUTURE; low marginal cost)

The forensic audit (F1–F12) plus the format specification, published for the
community independently of the transfer study — a reproducibility/benchmark-
track paper. Nearly all content exists in `docs/METHODOLOGY.md` and paper
draft §3–4. Decision point: after G0.c, judge whether the reproduction number
plus the audit stands alone or is stronger folded into Paper 1. No new
infrastructure required either way.

### Paper 3 — stopping and distance-head reliability (FUTURE; scoped, not started)

For GNM-family models, "when to stop" is the temporal-distance head, and the
audit already shows its evidence is fragile: raw integer timestep labels
(F6), a distance loss trained on goal-masked samples in NoMaD (F7), and
batch-dependent evaluation. The paper: calibration analysis of the distance
head under distribution shift (sim → real, seen → unseen scenes), a proper
scoring-rule evaluation, and a calibrated stopping criterion evaluated on the
Paper 1 benchmark. Everything runs on this repository's eval harness; the new
work is the calibration methodology, not plumbing. Entry condition: Paper 1's
E6 data exists (it doubles as this paper's test bed).

### Paper 4 — safety arbitration on evidence (FUTURE; deliberately last)

A runtime layer that gates policy commands on the *reliability estimates*
Papers 1–3 produce (distance-head calibration, traversability confidence from
the occupancy ground truth the M3 PRO's dual LiDARs already log). This is only
honest work once the reliability estimates exist and are validated — which is
why it is last, and why it is not an architecture diagram today.

## What this programme is NOT committing to

Stated to keep future selves honest:

- **No six-module "NavFM architecture".** A stack of Goal-Validity /
  Traversability-Reasoner / Safety-Arbitration components, none built and each
  a paper-sized problem, is scope risk dressed as vision. Components enter this
  roadmap only when a paper with a gate structure exists for them.
- **No "foundation model" claims without training a foundation model.** The
  repository name is a namespace, not a capability claim; the paper draft says
  "we claim no new architecture" and that sentence survives every future
  edit.
- **No framework paper before an evidence paper.** The umbrella is credible
  because Paper 1 is airtight, not the other way round.

## Objectives and acceptance criteria (programme level)

Acceptance criteria, not target numbers. Numeric improvement targets are set
only after pilot variance is known, never before — a threshold chosen before
the variance is known is a threshold chosen to be met.

| Objective | Acceptance criterion | Horizon |
|---|---|---|
| Reproduce the ViNT baseline with documented fidelity | the pre-registered G0.c decision rule returns a classification under its own procedural-validity layer, **or** the reason equivalence cannot be established is documented as an audit finding | ~3 months (WORKFLOW Phases 0–4) |
| Admissibility/provenance pipeline released, upstream-compatible | zero schema violations on the declared corpus, and the unmodified upstream loader consumes generated data | SHIPPED at scaffold; public at submission |
| Transfer validated sim → physical robot under one protocol | ≥ 120 physical episodes, pre-registered exclusions, stratified scene design, effects reported with 95 % CIs | Paper 1 completion |
| Stopping reliability characterised and improved | a pre-defined calibration criterion and a pre-defined operational improvement, both on held-out domains | Paper 3 |
| External reproducibility | an independent fresh-clone re-run of the release gates, with archived environment identity and artefact identities | continuous |

## Key performance indicators

Exactly five, programme-wide:

1. **Gate reproducibility rate** — fraction of archived gates that re-run to
   the archived artefact hashes from a fresh clone.
2. **Artefact provenance completeness** — fraction of reported artefacts whose
   full identity chain (environment, commit, checkpoint, split, seed, config)
   is archived rather than asserted.
3. **Protocol deviation rate** — deviations per executed protocol, with every
   deviation classified and justified in `gates/failures/`.
4. **Transfer validity precision** — width and coverage of the interval
   estimates on which transfer claims rest.
5. **Claim correction yield** — the number and materiality of conclusions
   changed, narrowed, or rejected once admissibility and audit controls are
   applied. **This is the KPI that evidences the programme's central
   argument**: if applying the controls never changes a conclusion, the
   controls were not necessary, and the thesis is weaker for it. F12, the
   scheduler-resume defect, and F-M1-1 to F-M1-3 are its first entries.

## Relationship to the field

GNM/ViNT/NoMaD (Berkeley), VLFM, NavGPT/NaviLLM and successors are *subjects
and beneficiaries* of this programme, not competitors: the admissibility
layer, the audit method, and the benchmark protocol apply to any of them. That
is the intended position — orthogonal to the policy-improvement axis the field
is crowded on, and compounding rather than depreciating as new models appear:
every new released model is new material for the same trustworthiness
pipeline.
