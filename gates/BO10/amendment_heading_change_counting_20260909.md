# Amendment — heading-change counting is grouped into turn episodes

**Dated 2026-09-09.** Amends the *measurement* of
`min_meaningful_heading_changes` in `COLLECTION_ROUTE_ADMISSION_V1`. It does not
amend any threshold.

## What is unchanged

- `min_meaningful_heading_changes = 3`
- `heading_change_definition_deg = 30.0`
- the 0.5 m decimation of the route before angles are measured
- every other frozen threshold
- Hospital's candidate-generation method, search budget and seed

## What changed

The rule for turning a sequence of heading deltas into a count.

**Before.** Deltas accumulated, and a turn was emitted the moment the running
total crossed 30°, resetting the accumulator.

**After.** A turn is a maximal run of same-signed deltas, uninterrupted by a
straight segment, and it counts once if its total exceeds 30°.

## Why

The old rule made the count depend on where the decimation grid happened to
fall. Decimating at 0.5 m replaces a corner that falls between samples with a
chord, so one 90° corner arrives as two 45° deltas and is emitted as two turns.
Measured on a single right-angle corner while sweeping the leg length:

| leg length (m) | 5.00 | 5.10 | 5.25 | 5.40 | 6.73 | 7.00 |
|---|---|---|---|---|---|---|
| old count | 1 | 2 | 2 | 1 | 2 | 1 |
| new count | 1 | 1 | 1 | 1 | 1 | 1 |

The same physical corner counted 1 or 2 according to an arbitrary alignment.
That is not a property of the route.

## How this was found, and why that matters

It was found from a **unit-test fixture**, while building the G10 boundary
tests — not from inspecting Hospital outcomes and not while looking for a way to
change a verdict. The distinction is the difference between fixing a protocol and
rescuing a hypothesis, and it is recorded here because a reader cannot otherwise
tell which happened.

## Direction of effect

Grouping can only **merge** counts. It can never create one. So for any route,
`new_count <= old_count`, and the gate is strictly harder to pass.

## Effect on the frozen Hospital result — none, and the argument is monotone

`gates/BO10/hospital_bo10_frozen_routeset_20260909.json` records
`NO_ADMISSIBLE_ROUTE`. That verdict survives this amendment without recomputation:

- **89 of 96** were rejected with counts of 0, 1 or 2. Since counts can only
  fall, all 89 remain below 3 and still fail G10.
- **7 of 96** reached G5 with counts of 3, 4 or 5, and all 7 failed G5. Several
  of their recorded turn lists are same-signed runs — route 006 `[35.5, 30.7,
  38.6]`, route 040 `[-30.6, -33.6, -32.4, -37.0]`, route 076 `[55.9, 37.1,
  38.9, 45.2, 45.0]` — which merge under the new rule wherever no straight
  segment separates them. Whether they merge cannot be determined from the
  artefact, because the candidate polylines were not stored. It does not need to
  be: those routes fail either way, and under the new rule some would fail G10 as
  well as G5.

No candidate was admitted on the strength of an over-count, because no candidate
was admitted at all.

## Effect on Office and later scenes

Office has not been measured. It is measured under the corrected counter from the
outset, so no Office result is produced under the defective rule and none needs
reconciling.

## Limitation of the amendment

`straight_deg = 1.0` — the delta below which a segment is treated as straight and
ends a turn episode — is a new parameter. It is set once, here, before Office is
measured, and it is not tuned against any outcome. A route whose corners are
separated by legs so short that no decimated segment is straight would still
merge them; at 0.5 m decimation that requires corners under roughly a metre
apart, which the 8 m minimum route length and the 5 m minimum start-goal
separation make an edge case rather than the common one. It is recorded as a
known boundary rather than claimed to be absent.
