# Three-cell measurement: representation vs numpy version

**Label computation only. No checkpoint, no model, no G0.c metric.** Schema
reconnaissance under the acquisition ruling. `vint.pth` remains unloaded.

## Design

| Cell | numpy | path | isolates |
|---|---|---|---|
| A | 1.23.5 (era, throwaway) | object-dtype, as the reference ran it | — |
| B | 1.23.5 (era, throwaway) | float64-coerced (the proposed patch) | — |
| C | 2.4.4 (canonical) | float64-coerced | — |

`B − A` = **representation** effect at fixed numpy.
`C − B` = **numpy-version** effect at fixed representation.
`C − A` = the claim under test: *canonical-coerced equals era-reference*.

Scope: `_compute_actions` outputs — actions, `goal_pos`, distance label — over
the **full 760-trajectory holdout**, exhaustively over every valid timestep.
**44,038 samples**, 660,570 action elements. No sampling, no subset: the
downstream computation proved cheap enough to run whole, so no subset needed
declaring.

## Result

| Comparison | actions | goal_pos | dist |
|---|---|---|---|
| **B − A** (representation) | **bit-identical** | bit-identical | bit-identical |
| **C − B** (numpy version) | max abs **1.776e-15** | bit-identical | bit-identical |
| **C − A** (claim under test) | max abs **1.776e-15** | bit-identical | bit-identical |

**The representation effect is exactly zero.** Coercing object-dtype to float64
changes no computed value at all, at fixed numpy. Every difference between the
canonical-coerced path and the era-reference path is attributable to the numpy
version, not to the coercion.

### Scale of the residual difference

- max absolute difference: **1.776e-15**, against float64 eps 2.220e-16;
- 174,670 of 660,570 action elements differ (26.4 %), all at that scale;
- reported `max_rel` of 2.1e14 is an artefact: **every** large relative value
  occurs where the true value is exactly `0.0`, so the ratio divides ~2e-16 by
  zero. Among elements with `|true| > 1e-6`, max relative difference is
  **6.6e-11**;
- this is float64 non-associativity — reduction and dot ordering changed
  between numpy versions — and it is below the resolution of any metric this
  project reports, which are cosine similarities of order 1 and MSE on values
  normalised by `metric_waypoint_spacing = 0.12`.

### The warning finding, preserved independently

Cell A emitted **88,076 `VisibleDeprecationWarning`s** — exactly two per sample
across 44,038 samples. The reference implementation, running on its own corpus
under its own pinned dependency era, warned continuously that the behaviour it
depended on was deprecated. Cells B and C emit zero.

This is recorded as a finding in its own right, independent of the patch
decision and of whichever outcome row the comparison lands in.

## Where this lands in the declared mapping

The declared first row: *"C == A bit-identical (or differing only at the level
of float64 non-associativity with max-abs below any metric's resolution):
Route 1 is honestly 'restoration'."*

The measurement lands there on its face — the difference is float64
non-associativity at 1.78e-15, carried entirely by `C − B`, with the
representation effect exactly nil. **This document does not declare that
outcome adopted.** Under the standing rule the patch requires trigger-1 red-team
adjudication with this measurement attached as evidence, and it is not
self-cleared here.

## Contents

| File | What |
|---|---|
| `comparison.json` | full machine-readable comparison, all three pairs |
| `cell_hashes.txt` | SHA-256 of each cell's serialized output |
| `trajectories.txt` | the 760 holdout trajectories measured |
| `canonical_env.txt` | canonical environment identity |
| `../../scripts/measure_dtype_equivalence.py` | the comparison script |

Era environment: uv-managed CPython 3.11 with numpy 1.23.5, throwaway, clearly
labelled as non-canonical, discarded after the run.
