# Hospital RGB-only publication pilot — prospective protocol

EXPERIMENTAL RESULTS: NOT YET AVAILABLE. Performance improvement is an untested
hypothesis. A stationary instrumentation smoke is neither navigation admission
nor evidence of improvement. Historical effective intrinsics and rendering
settings remain unknown; the historical simulation cadence is supported at
12 Hz, image resolution is supported, and mounting offsets are nominal.
Separate loader compatibility is unaffected.

The 2026-10-07 prospective stationary smoke passed 12-frame instrumentation
validation with one subframe. Sensor times increased uniformly by
0.0833333358168602 seconds and agreed with capture simulation times. Effective
mode was `RaytracedLighting`, DLSS execution mode 2, resolution 640x480, and
read-back pinhole focal lengths approximately 512.107 px. These observations
do not recover historical settings. Visual inspection found a very dark
corridor with a bright robot foreground; semantic visibility is unresolved
and scientific navigation collection remains blocked. A mean image statistic
alone does not resolve this problem.

`scripts/prepare_hospital_pilot.py` prepares three matched route/seed pairs in
a new external manifest, counterbalancing arm order. It returns status 2 and
`BLOCKED_PENDING_FREEZE` while checkpoint, layer implementation, visual
qualification and the RGB-only input audit are unresolved. Three repetitions
are an engineering budget, not the publication sample size. No pilot arm has run.

Read back the trusted local smoke with
`scripts/verify_hospital_runtime_smoke.py --manifest <runtime_manifest.json>`;
it checks recording and executed-source hashes before deserializing poses.

## Runtime qualification

Run `scripts/hospital_runtime_smoke.py` with the installed 5.1 simulator Python,
the official Hospital scene and the reconciled physics robot asset. Supply a
fresh absolute output directory outside the repository. A PASS requires all
R1–R8 readbacks and agreement checks, increasing sensor timestamps matching
simulation capture time, 1/12-second stepping, finite poses, nonconstant uint8
RGB at observed resolution, and decoded saved images. The manifest separates
requested configuration from observations and pins source and saved files.
Nonconstant pixels establish only that capture is not uniform; they do not
establish semantic visibility or image quality. Inspect the captured view before
admitting navigation routes. Runtime readbacks describe this prospective run,
not the historical camera. Require this preflight on the actual collection
camera; passing a separate probe cannot attest another camera.

## Matched pilot freeze

Before either arm executes, freeze the baseline checkpoint SHA-256, preprocessing,
RGB history length, goal-image handling, waypoint units, controller, command
limits, timeout, termination rules and software/environment manifest. Freeze
the layer implementation and entry point separately. This checkout currently
has no HOCBF implementation; the second arm is blocked until the intended
implemented layer is identified and its RGB-only input boundary verified.

Use identical route IDs, starts, goal images, scene revision, seeds, camera
intrinsics/extrinsics, renderer and simulation rate for both arms. Select routes
before looking at outcomes, covering straight corridors, turns and visually
ambiguous areas. Reset the simulator between arms, counterbalance arm order,
and record both failures and successes. Instrument evaluation separately from
the method. Simulator pose, depth, collision geometry and occupancy must never
enter the deployed RGB-only method or its safety layer. They may define route
fixtures and score outcomes in an isolated evaluator. Audit this boundary with
a negative control that denies the policy access to ground-truth interfaces.

The pilot checks executability, leakage, controller units, image interpretability
and paired-record completeness. It does not select the strongest-looking seed
or establish the final paper's effect size. Preserve every attempted pair and
record invalid instrumentation runs distinctly from navigation failures.

## Publication evaluation freeze

The primary experimental unit is a matched route/seed pair. Freeze the population,
route splits, sample count, collision definition, goal tolerance and timeout
before evaluation. Determine sample count from a stated detectable effect and
pilot variance; do not invent a count or stop when significance appears.
Hold out test routes from layer tuning and checkpoint selection.

Primary endpoint: paired difference in collision-free goal completion within the
frozen timeout. Report completion and collision rates separately so stopping
cannot masquerade as safety improvement. Secondary endpoints: time to goal,
path efficiency against an evaluation-only reference, intervention frequency,
and wall-clock latency at the deployed method boundary. Report simulation time
and wall-clock time separately; collection at 12 Hz simulation time does not
prove real-time deployment throughput. Record censoring and timeout handling.

Use paired confidence intervals with resampling at the route level when seeds
share routes. Report counts, effect estimates and uncertainty, including null
or adverse outcomes. Prespecify ablations for the layer's actual components
once its implementation is identified. Challenge improvements with equal
command limits, equal preprocessing and latency, route-level breakdowns,
failure categories, leakage checks, and held-out performance. Claims remain
limited to simulated Hospital navigation until external validation exists.
