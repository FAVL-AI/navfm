# F13 subfinding — Compatibility measurement population did not match the registered evaluator population

**Classification:** coverage overstatement — a measurement described as
exhaustive over a population it did not measure.

**Authorship acknowledged.** Introduced by the assistant, detected by trigger-1
adversarial adjudication, re-verified independently before correction.

## The two populations

| | samples |
|---|---|
| Upstream evaluator's valid-timestep range, `[context_size·ws, n − end_slack − len_traj_pred·ws)` | **41,872** |
| The compatibility measurement's range | **44,038** |

**Neither is a subset of the other.** The measurement excluded each
trajectory's final upstream-valid timestep, and included `t ∈ [0,4]`, which
upstream excludes via `begin_time = context_size · waypoint_spacing` at
`context_size: 5`. **210 of 760 trajectories contributed zero samples** to the
measured range (`n ≤ 6`).

## The claim that was wrong

`gates/G0/measurement/README.md` said the measurement ran *"over the full
760-trajectory holdout, exhaustively over every valid timestep… No sampling, no
subset"*, and `docs/reviews/DISPOSITIONS.md` recorded §4 as **conforming** on
that basis. The specification requires exclusions and their reasons to be
reported. None were reported, because none were noticed.

## Why it mattered

The measurement's purpose was to license a patch to the **registered G0.c
evaluation path**. A result over a population that is neither the registered
one nor a subset of it cannot, by itself, establish semantic preservation over
the registered one. The claim of exhaustive coverage removed the reader's cue
to ask which population had actually been measured — and the answer was
knowable from seven lines of the measurement script.

Two narrower overstatements travelled with it, both now recorded: `dist` is the
constant `5.0` in all three cells, because the script forces `goal_t = t + 5`,
so that row of the results table is true of a constant and would hold under any
patch whatsoever; and `goal_pos` duplicates `actions[:,4,:2]` and is discarded
by the evaluator (`offline.py:203` unpacks it as `_goal_pos`), so it is neither
independent corroboration nor load-bearing for G0.c.

## Why the coercion conclusion still stands, narrower

The `B − A` bit-identity result is a property of the **coercion operation**,
not of any particular population: coercing object-dtype cells that each hold
exactly one value to `float64` is a lossless widening, and the 44,038-sample
agreement is corroboration rather than the load-bearing argument. The yaw
column is bit-identical across all cells, so `calculate_sin_cos` is
bit-identical downstream. Masks and distance labels derive from integer indices
and cannot depend on dtype.

What the measurement does **not** establish is semantic preservation over the
exact registered evaluator population. That gap is closed not by re-measuring
but by the protocol itself: the evaluation-pair manifest is generated under the
amended registered loader, frozen before any checkpoint scoring, and every
scored pair is verified against it at runtime.

## Corrective action

* `gates/G0/measurement/README.md` — coverage claim retracted, both
  populations and the 210 zero-sample trajectories recorded, `dist` and
  `goal_pos` limitations stated (`8aadb33`).
* `docs/reviews/DISPOSITIONS.md` — §4 conformance row to be corrected from
  *conforms* to the true, narrower statement.
* The narrow amendment binds G0.c to the committed evaluation-pair manifest
  rather than to this measurement.

## Regression test

None is possible: this is a claim-accuracy defect, not a code defect. The
standing rule it falls under already exists — *a verification must fail when
its subject is absent* — but this is its inverse: **a measurement must state
the population it measured, and a coverage claim is a claim like any other,
requiring evidence rather than impression.**

Related: [F-M2-4](F-M2-4.md) (same author, same session, audit-integrity
family), [F-M1-2](F-M1-2.md) (claims whose evidence was never archived).
