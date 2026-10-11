# Initialization/history diagnostic v 2: explicit bootstrap eligibility

Status: FROZEN 2026-10-10 after bounded design/executable review. NOT RUN. Owner: Frank Asante Van Laarhoven <frankleroyvan@gmail.com>.

Version 1 freeze `f831a110e6854c919a21c8397eee950cf79b77fd`, its first failed
process, and result checkpoint `fc00ff9eff95bd65b452cb1d9e152079989ce45f` remain
immutable. Version 2 is a separate technical protocol, not a retry or repaired
version 1 result. The recovery pilot remains halted and INCONCLUSIVE.

## Evidence-based change

The installed synchronous orchestrator implementation documents an initialization
step on first use and explicitly disables automatic timeline advance for its
STARTING first frame to capture time 0. Version 1 applied ordinary-interval
physics guards to that bootstrap. Its observed first call had zero time advance,
zero feedback and sensor time 0 despite a positive requested delta. This source
behavior supports a bootstrap/measurement-contract mismatch, not an established
cause of the original paired image divergence or a simulator defect.

Installed primary source inspected read-only:
`omni.replicator.core-1.12.27+107.3.3.lx64.r.cp311/omni/replicator/core/scripts/orchestrator.py`,
`step()` lines 1502..1623, especially initialization and STARTING first-frame
branches. Its actual file digest is pinned in the executable configuration.
No new probe or image was used to choose this change.

## Fixed schedule and eligibility

After the original physics/robot/camera/controller setup, before goal/start
conditioning, perform exactly ONE explicitly labelled bootstrap orchestrator
call with delta_time=0, RT subframes=1, pause_timeline=true. Record public
orchestrator status, timeline/simulation/sensor times and feedback counters
before and after. Bootstrap must advance physics by zero and produce zero
feedback callbacks. Its not-yet-synchronized sensor time is recorded as an
UNQUALIFIED bootstrap observation; it is never used as current policy input or
credited as a valid capture/history match.

Then perform exactly THREE eligibility frames, each consisting of one 1/12 s
physics/render call and one unchanged-physics call. Every positive call must
advance simulation time by 1/12 s (1e-6 s tolerance) with exactly ten controller
updates; every zero call must advance zero with zero updates. After each pair,
retain live RGB, full root/world/local-camera/joints/targets/controller state,
actual timestep/settings readbacks, public orchestrator/timeline state, and
sensor/render timestamps. Sensor and simulation times must agree within 1e-8 s.
No adaptive extra render, best-frame selection, retry or warmup extension.

Do not alter the initial DLSS mode during this eligibility phase: record its
actual startup mode before bootstrap, require the same mode in all three
eligibility captures, and preserve the original fixed change to mode 2 after
eight goal-conditioning frames. Startup settings are not assumed from defaults.
Other required readbacks must exist; unsupported state fails closed. Eligibility
RGB is technical evidence only and is never model-scored. Every attempted eligibility
frame and failure is retained; the first mechanical guard failure halts the
process and all remaining declared processes.

Only if all fixed eligibility guards pass, continue within that SAME process to
the original goal conditioning, eight start-settling frames, 36-step fixed
script and method comparisons from version 1. No physics/controller/scene/robot
or renderer parameter is changed to achieve equivalence. This additional fixed
bootstrap/eligibility history is an explicit version 2 condition; it cannot
retroactively validate version 1 or the recovery pilot.

## Bound and unchanged contracts

Use exactly the same two already observed s_bend cases, two fixed repetitions,
one fresh reference and replay process per case/repetition: at most EIGHT
processes, sixteen method traces. Run in declared repetition/case/reference then
replay order. First process is also the technical eligibility gate. Any missing
capture, failed eligibility/ordinary interval, source/asset drift or unsupported
state halts all remaining processes. If each process is mechanically complete,
image/state comparison failures do not select or exclude runs, and repetition 2
proceeds. No retries; 600 s watchdog per process. No retrospective model rerun.

All version 1 comparison bounds, exact decision-36 buffers/relative ages,
original full snapshot, fixed continuous->root->full order, strict claim
eligibility and cross-repetition comparisons are unchanged. Ground truth only
initializes/restores/evaluates; script commands are fixed, and live yaw-rate PI
remains the only controller feedback. No recovery policy consumes a new image.

Success is a verified reproducible start only on these technical cases with ALL
observable-state/controller, six-buffer/age and cross-repetition guards passing.
Otherwise state the first observed divergence and bounded unresolved state.
A bootstrap eligibility pass alone validates stepping, not image equivalence or
reset history. No recovery, safety, illumination or held-out claim follows.

Design review, executable boundary tests and independent bounded review must
precede a new named freeze and every version 2 probe. Version 1 source/config/
plan/test files and the original recovery freeze remain byte-identical. New
collector/config/runner are separate. Runtime evidence stays external under a
new version 2 prefix; every launch/exit/failure is preserved.

Held-out geometry sealed, illumination paused, real robot unauthorised. Only the
engineering branch and draft pull request may be published after final checks.
