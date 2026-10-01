# Runtime attestation (R1-R8)

An opt-in engineering capability that records what the simulator **actually did**,
so a recorded setting can no longer become a claim that the running system used it.

That defect is not hypothetical. The BO-10 metadata-to-runtime audit found eight
recorded fields that nothing applied, because the collector bypassed
`IsaacApp.start()`: `rt_subframes`, `dlss_quality`, `renderer`, the launch
resolution, `warmup_frames`, and the camera's `horizontal_fov_deg`,
`focal_length_px` and `pitch_deg`. `focal_length_px` was not even a setting -- a
derived property whose only consumer was the metadata writer.

Requirements source: `prospective_attestation_requirements.md`, sha256
`a8c6bd34d64cb5559097e620cd36ac14f56e3c628890cc6d18fc627b8f1551eb`. Its
identifiers R1-R8 and their order are preserved.

## The split that makes the defect unwritable

    navfm.collection.attestation       readers   -- observe; never see intent
    navfm.collection.attestation_gate  gate      -- holds intent; applies the rules

`Observation` has no `requested` field, and `value` is `None` unless `status` is
`OBSERVED`. So `observed = read_runtime_value() or requested_value` cannot be
written by accident: the two values never live in the same object. A failed
getter, an unsupported API, an uninitialised object or a non-finite value each
produce their own status, and the gate treats every one of them as unresolved
rather than substituting intent.

## Rules, and where tolerances are allowed

Most requirements ask that a value be **recorded**, so their rule is `PRESENCE`:
satisfied when observed. Only three comparisons have a defensible mapping to
intent, and each states it:

| rule | mapping | tolerance |
|---|---|---|
| `R2.horizontal_fov` | requested degrees -> radians | `1e-6` rad, deg/rad round-off only |
| `R4.rt_subframes` | identity | none, exact integer equality |
| `R4.dlss_exec_mode` | `dlss_quality` true -> `execMode` 2 | none, exact equality |

Tolerances are declared in the source before any value is read, never widened
after seeing a result. `R6.spawn_world_z` deliberately has **no** agreement rule:
physics settling legitimately changes Z after spawn and no contract states an
allowance, so inventing one here would repeat the error this work exists to
prevent. `R7` carries no brightness threshold for the same reason.

## Provenance is declared, never inferred

`Provenance.LIVE_RUNTIME` vs `TEST_DOUBLE` is passed in by the caller. A decision
assembled from doubles reports `test_double_present: true`, so a unit-test pass
cannot be presented as a live Isaac read-back. Every observation also carries
`run_id`; the gate rejects one belonging to a different run.

Nothing here is a physical measurement. These are software read-backs of
simulator objects, and they are not hardware calibration.

## Admission

All eight requirements are mandatory, because the source document states what
must be recorded *before* the next collection. **Accounting for all eight is not
passing all eight**: every requirement appears in `per_requirement`, and any
mandatory one that is not `SATISFIED` sets
`SCIENTIFIC_COLLECTION_ELIGIBILITY = BLOCKED_BY_UNSATISFIED_ATTESTATION` and
writes a durable failure record outside the repository.

## Integration

`scripts/collect_bo10_trajectory.py` calls `attest_and_record()` after
`AFTER_CAMERA_ATTACH`, inside the `--engineering-step-cap` branch only; the
default scientific path is untouched. The readers receive the collector's **own**
camera, articulation and carb settings -- a validator that built its own second
camera would attest that camera, not the one that rendered.

A precondition-only pass resolves R1-R4, R6 and R8. R5 and R7 need per-step
wiring, so they stay unresolved and collection stays blocked, which is the
truthful outcome rather than a convenient one.

## What is not yet verified

Every result so far comes from test doubles. R2, R3, R4, R5 and R6 read real Isaac
objects and have had no live read-back, so their status is
`ENGINEERING_PATH_INTEGRATION_TESTED`, not `LIVE_RUNTIME_READBACK_VERIFIED`. The
smallest no-motion run that would settle them is one `--engineering-step-cap`
invocation that stops after `AFTER_ATTESTATION`; that needs separate
authorisation and is not performed by anything in this repository.
