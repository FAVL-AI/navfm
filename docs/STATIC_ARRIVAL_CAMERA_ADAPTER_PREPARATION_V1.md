# Static-arrival camera adapter preparation v1

**Status: PREPARATION ONLY.** The schedule and process path are implemented
and CPU-tested with a harmless worker. No Isaac process, camera render,
encoder/model inference, fitting, collection, scoring, or navigation ran.
Synthetic launcher success is recorded only as a contract-test outcome and
cannot produce a camera admission marker.

## Bound acquisition

The adapter calls the existing `legacy_boxes` training-scene builder and
binds its canonical geometry digest. It does not create a robot or use the
articulated collector. The frozen schedule contains 20 unique episode and
goal identities: four per family. F0 uses scenes 0 and 5; F1 uses 1 and 6;
F2 uses 2 and 7; F3 uses 8; F4 uses 9. Each episode specifies its scene,
coordinate frame, eight ordered reference poses, requested terminal node,
and 36 ordered query poses across four fixed strata. Reference and query
image IDs are distinct, deterministic opaque IDs; roles and strata are kept
in metadata rather than encoded in policy-image filenames. Roles remain
F0-F2 fit, F3 threshold selection, and F4 descriptive assessment.

The camera contract is 320×240 RGB, 68° horizontal FOV, 0.55 m height,
0.20 m forward offset, world axes and WXYZ orientation. Capture is scheduled
at 16 Hz simulation with four held steps per image (4 Hz target cadence),
plus eight warm-up steps. Native `rendering_time` and rational
`rendering_frame` values must be strictly ordered and are recorded as
observed; frame index is never used to invent time. Lighting is bound to the
training collector settings: one distant light at intensity 1500 and rotation
[-45°, 30°, 0°], plus dome intensity 800, with no per-episode variation.

The 0.5 m camera-center proximity label is derived only from the same-snapshot
captured camera poses, checked again by the parent, and written under
`evaluator_only`. RGB policy inputs contain images only. Query pose, label,
scene and stratum are not placed in the
policy-image directory or passed to a descriptor/decision implementation.
This is a geometric label, not successful arrival, safe STOP, or collision-free
completion. Repeated-structure locations are sampling candidates, not verified
visual lookalikes.

The exclusion record binds every known trajectory identity from the existing
prospective collection contract, the exposed development/retired-test IDs,
accessed-pilot status, and the sealed held-out IDs. The adapter does not load
those images, labels, outcomes, or layout geometry. F4 remains explicitly
descriptive because of documented appearance overlap.

## Launcher and process contract

The production CLI requires both an exact clean commit and an explicit
execution flag; the checked configuration has `runtime_authorized: false`
and separate known-fixture-at-16-Hz and training-scene camera gates marked
`NOT_RUN`.
One immutable registry reservation is consumed per family, with no retry.
The parent constructs the family-specific input from the frozen schedule,
binds schedule/source/input hashes, starts one camera-only worker, verifies
frame identity/order, episode/role mapping, image hashes, native timestamp
ordering and evaluator-label population, then writes terminal records. Only
complete runtime evidence can receive a finalization marker. Failure,
timeout, missing output, hash mismatch, or finalization error vetoes admission.

The proposed cap is **600 seconds for one complete appearance-family
process**, not one episode, not one batch, and not all 20 episodes as a single
process. Each process handles four episodes, 32 references and 144 queries
(176 images total). The five-family aggregate proposal is 3,000 seconds. The
first 570 seconds are the pre-reap attempt allowance. That time includes
launcher preflight, reservation/input persistence, worker startup, scene
construction, warm-up, all captures and incremental writes, and SDK close; it
is not 570 seconds of worker time after startup. The next 10 seconds reserve
TERM/KILL handling and child reaping; the final 20 seconds reserve output
verification plus terminal/finalization records. These allocations and the
total are unmeasured proposals, not approved execution budgets. The timed
attempt begins at launcher entry (after Python imports) and covers the full
sequence through finalization. Any overrun prevents PASS; child execution has
a deadline and bounded TERM/KILL/reap handling. Operating-system stalls during
parent-side filesystem calls cannot be preempted by this Python watchdog, so
admission also checks the elapsed whole-attempt budget.

The earlier 190-second limit applied to a separate two-room 144-frame pilot.
It does not apply to this 880-image proposal and does not establish its
feasibility. The current known-fixture qualification used a different camera
schedule; it does not qualify the training-scene builder or the proposed
16 Hz/four-step cadence. A fresh known-fixture qualification at this cadence,
followed by a separately authorized training-family runtime qualification,
is required before collection.

## Validation and boundary

Focused CPU tests exercise the schedule, source and geometry bindings,
population/role/stratum counts, exclusion and duplicate rejection, evaluator
label separation, and the launcher's real subprocess supervisor using a
harmless worker. They cover contract-only success, one-shot registry refusal,
worker failure with partial-evidence retention, timeout with reaping, and
finalization-marker failure. They do not validate rendering, camera timing,
pixel usability, Isaac compatibility, lighting, or acquisition throughput.

Validation on 2026-10-13: 45 focused tests passed (adapter, training-scene
builder, and existing frame-integrity contracts); Ruff check/format, mypy on
the schedule module, and Python compilation passed. Pytest plugin autoload was
disabled for this targeted run so unrelated system ROS pytest plugins would
not be imported. The production family CLI was separately verified to refuse
the checked-in preparation-only configuration without creating an output or
registry attempt.

The existing proposal's feature encoder/similarity definition and
deployment-matched reference builder remain separate prerequisites for
descriptor extraction and fitting. No scores or thresholds are changed by
this acquisition adapter. No physical stopping or navigation claim follows.
