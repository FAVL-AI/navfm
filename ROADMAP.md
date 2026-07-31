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
asks: *what would it take to prove that the reported result means what it
claims?* The audit of the reference implementation (paper draft §3, findings
F1–F11) is the demonstration that the question is not pedantic: the most-cited
open navigation models rest on an unspecified data format, silently corrupting
label pipelines, dead configuration keys, unexplained constants, and metrics
that move by 0.46 with batch size. Trustworthiness is not a module bolted onto
a policy; it is a property of the *evidence pipeline*, and that is what this
repository builds.

## Programme structure: papers, not modules

The programme is a sequence of mutually reinforcing papers sharing one
infrastructure — not a monolithic multi-module architecture. Each paper is
gated on evidence before the next is scoped. Anything without a green gate
behind it is labelled exactly that.

### Paper 1 — the current work (IN EXECUTION, Phases 0–6, gates G0–G6)

*Holonomic Execution of Nonholonomic Priors: A Forensically Validated
Simulation Pipeline for Adapting Visual Navigation Foundation Models.*

Contains, in the taxonomy of trustworthiness: the **admissibility layer**
(format specification + validator + compatibility proof — SHIPPED, tested),
the **provenance layer** (checkpoint hashes, pinned upstream, derived
constants, per-trajectory generative metadata — SHIPPED), the **evidence
ledger** (gates, tags, pre-registration — OPERATING), and the **transfer
benchmark** (E1–E6 — PRE-REGISTERED, PENDING). Plus one substantive scientific
question the audit makes askable: the demonstration/execution kinematics 2×2.

Status: scaffold complete and pushed (`FAVL-AI/navfm`, tag `scaffold-v0.1`);
first empirical gate (G0.c) is the immediate next milestone.

### Paper 2 — the audit as a standalone contribution (LOW MARGINAL COST)

The forensic audit (F1–F11) plus the format specification, published for the
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

## Objectives and measures (programme level)

| Objective | Measure | Horizon |
|---|---|---|
| Reproduce the ViNT baseline with documented fidelity | gate G0.c archived; offline metrics at stated batch size | ~3 months (WORKFLOW Phases 0–4) |
| Admissibility/provenance pipeline released, upstream-compatible | CI compatibility proof green on public infrastructure; validator + stats + splits released | DONE at scaffold; public at submission |
| Transfer validated sim → physical robot under one protocol | E6 table with CIs, ≥120 physical episodes, rosbags archived | Paper 1 completion |
| Stopping reliability characterised and improved | distance-head calibration curves; calibrated-stop vs baseline on E6 protocol | Paper 3 |
| External reproducibility | fraction of gates re-runnable from a fresh clone by a third party; adoption signals | continuous |

## Relationship to the field

GNM/ViNT/NoMaD (Berkeley), VLFM, NavGPT/NaviLLM and successors are *subjects
and beneficiaries* of this programme, not competitors: the admissibility
layer, the audit method, and the benchmark protocol apply to any of them. That
is the intended position — orthogonal to the policy-improvement axis the field
is crowded on, and compounding rather than depreciating as new models appear:
every new released model is new material for the same trustworthiness
pipeline.
