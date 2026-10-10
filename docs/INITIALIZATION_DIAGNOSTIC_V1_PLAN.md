# Initialization/history diagnostic v 1

Status: FROZEN 2026-10-10 after bounded design and executable review. Technical probes NOT RUN. No recovery trial is authorised by this
plan. Owner: Frank Asante Van Laarhoven <frankleroyvan@gmail.com>.

## Existing evidence and first divergence

The eight halted pilot recordings remain immutable. Their first differing
observation is already the lossless `start.png`, copied six times into initial
history before policy decision 0. On the four route pairs, initial grayscale MAD
is 0.292799,8.242943,1.129232,4.724297; the second and fourth fail 2.5. Pixel-exact
identity differs even in the passing pairs. Each arm's history matches its own
start image; cross-arm histories differ. Resume is absent, first inference frame
is 0, and its sensor time equals the predecision simulation time. Thus this first
mismatch precedes current-episode policy actions and replay indexing cannot
explain its onset. Earlier arm-dependent episode actions/durations in the reused
simulation may still affect subsequent starts.

Paired first model windows are identical: node ranges 0..14,0..13,0..11,0..10.
First argmin nodes agree 3,2,0,5; maximum first distance-vector differences are
0.048594,1.045055,0.487937,2.971416. First commands differ intentionally by arm:
R 2 scans at 0.4 rad/s; B 1x moves at 0.1 m/s and steers by its waypoint. These are
recorded descriptive observations, not a recovery comparison or causal proof.

Startup collection summaries record DLSS mode 0; source then sets mode 2 before
its goal render. Episode live readback observes 2. That readback is at the final
capture, not every initial image; the lifecycle label alone cannot establish an
initial-image setting. Startup histogram/auto-exposure enabled is false. There is
no initial full world-camera/root pose, joint-state or renderer-history readback.
Scene signatures/local camera/config/checkpoint match; matching XY/yaw alone does
not establish equality of hidden physical or rendering state.

Root teleport restores root XYZ/yaw and zeros root velocity; drive stop resets
PI/held command/wheel targets. It does not explicitly reset all joint positions,
joint velocities or renderer/sensor history. One simulation is reused across
routes. Initial simulation times differ by 0,14,1.5833,7.0833 s. Cause is UNKNOWN.
A descriptive affine brightness fit on the failing s_bend pair reduces gray MAD
from 8.242943 to 1.603979 (scale 0.969602,offset-3.648016); this suggests photometric
variation but does not isolate exposure, shading, geometry or rendering history.
The frozen pilot gate is unchanged and cannot be repaired by that regression.

## Bounded scope and units

Two already observed development cases only: `s_bend_run_0000` (passing pair)
and `s_bend_run_0001` (failing pair), with their existing declared start poses.
No remaining prospective starts, held-out geometry, illumination condition,
recovery threshold, learned-policy navigation or real robot actuation.

Part A: retrospective deterministic CPU reconstruction of each of the eight
existing first model invocations, from its exact lossless initial image, six-copy
history, fixed goal and original decoded chain. Compare reconstructed window,
distance vector, requested-goal distance and first output with recorded values;
repeat each reconstruction twice. This is an input/implementation audit of
existing views, not a new efficacy result. Absolute tolerance 1e-3 and relative 1e-5
for numerical outputs; exact window/history/config/checkpoint identity. Report
all mismatches, including CPU-versus-original-backend differences. No metric is
recalibrated from this audit. No new simulator image is model-scored.

Part B: two fixed repetitions of a matched technical simulator comparison on both
cases. Each case/repetition uses one fresh reference process and one fresh
command-replay process: eight processes total;16 method traces total. A separate
new collector imports existing robot/controller helpers and loads the recorded
development fixture. Existing frozen collection/scoring files remain untouched.
Each reference executes 36 frames (six decisions at 6-frame spacing) of fixed
scripted wheel commands: first 18 frames(0.04,0,0.15), next 18(0.04,0,-0.15), after
the existing goal-pose conditioning and 8-step initial settle. No learned policy
selects a command. The same script and nominal initialization apply to replay. Handover is after
exactly 36 physics/render steps: the would-be decision at frame36 consumes the
current capture at stored index35, and its six buffers are physical-step indices
6,12,18,24,30,36 (stored capture indices5,11,17,23,29,35), with relative ages
30,24,18,12,6,0 steps. No buffer from decision30 may substitute for the live
handover capture. The original full handover snapshot is saved before any reset.
Within each reference process the fixed order is continuous, direct root reset,
then direct full restore from that ORIGINAL pre-reset snapshot. The latter also
sees hidden renderer/solver state left by the root comparator; this order is
fixed and its carryover remains confounded, not an isolated reset effect.
Every attempted process, trace, failed assertion and output is preserved externally.
Per-process wallclock watchdog 600 s, no retries. Stop expansion on missing/invalid
capture, unexpected source/config/asset drift or unqualified actuation; never
stop/select based on image matching or recovery outcomes. Repetition 2 runs when
repetition 1 is mechanically complete even if comparisons fail.

## Compared start procedures and restored-state contract

| Method | Simulator/robot | Controller | Observation history | Policy state |
|---|---|---|---|---|
| continuous reference | uninterrupted fixed script from declared cold initialization; snapshot at frame 36 handover | uninterrupted PI/held command/targets, recorded | actual six sampled predecision RGB buffers and timestamps | declared initialized proxy only; no learned model or recovery updates |
| command replay handover | fresh process, same fixture/initialization and all 36 recorded commands; no pose injection during replay | same fresh PI then recorded command stream | reconstructed from its own live RGB at identical indices | same initialized proxy; reference proxy may be explicitly restored, never inferred from GT |
| direct root reset | same process after reference; restore reference handover root XYZ/quaternion, zero root velocities;8 settling steps; joints and renderer history NOT restored | reset PI and held command/targets to zero | six copies of its own newly observed image; reference history NOT restored | fresh initialized proxy, not handover-equivalent |
| direct full observable-state restore | same process after reference; restore saved root pose/velocity, joint positions/velocities and targets; unchanged-physics rerenders | restore saved PI/held command/targets | reference five previous RGB buffers plus its own current RGB; absolute simulator time and internal renderer state NOT restored | restore explicit proxy fields/counters; no claim about unobserved model memory |

These are different interventions, not automatically matched counterfactuals.
The direct-root procedure is an explicit incomplete-reset comparator. Full restore
is limited to observable API state: hidden solver/renderer history and clock may
remain different. No stale reference image may masquerade as the current capture.
Each ordinary conditioning/script frame uses exactly two orchestrator calls: one
1/12 s physics/render advance and one unchanged-physics render. Every call and
its before/after simulation and sensor times is recorded; no adaptive extra
rerender is allowed. Each direct comparison uses exactly six single unchanged-
physics orchestrator calls/captures. Six fixed rerenders per direct restore test convergence, with
full-state and timestamp readback each time; no adaptive warmup or chosen best
frame. Report all six images and compare the final predeclared one.

Ground truth initializes/reset poses and evaluates state agreement only. Replay
commands come from the fixed script, never pose error. Camera/history observations
are RGB only. The low-level PI uses live yaw-rate feedback as in its qualification.

## Frozen comparison rules

Compare each replay/direct trace with its same-case/same-repetition continuous
reference, at the predeclared handover boundary. Also compare each case
reference/reference across repetitions and each same method across repetitions,
using the identical frozen guards; do not infer repeatability from within-repeat
matching alone. Report first numeric divergence
and first bound violation, distinguishing reset, render, history assembly and
policy-input transformation. No broad first-difference search over other layouts.

- XY position<=0.02 m and yaw<=2 degrees, retaining pilot bounds.
- Root/world-camera Z difference<=0.002 m and full quaternion angular error<=0.2
  degrees; joint positions<=1e-3 rad, velocities<=1e-2 rad/s. These are conservative
  mechanism guards, not established sensor accuracy. All readbacks are retained.
- Root linear/angular velocity differences<=0.01 m/s and 0.01 rad/s.
- Controller integral<=1e-6 and held/target command differences<=1e-6.
- Six history buffers each grayscale MAD<=2.5, unchanged from the accepted
  observation bound; last/live image separately tested. No affine-normalized gate.
- Sensor time must equal the simulation/render time for the observed state within
  1e-8 s. Frame index and relative history ages must agree within 1e-6 s for replay.
  Direct resets disclose non-restored absolute time and replaced/copied history;
  they cannot pass a full-history-equivalence claim when ages differ.
- Actual per-observation settings readback: active renderer, DLSS mode 2, subframes 1,
  histogram enable/tau/clamp/EV/whiteScale, tonemap and exposure settings. Keep
  the existing light/scene signature fixed; this is not an illumination experiment.

Also record full root/world-camera/local-camera transforms, joints, velocities,
drive targets, controller state, scene/robot/qualification/source digests,
all command and capture timestamps, sequence indices and image hashes. Compare
recorded settings with actual live readback; intent fields do not satisfy guards.
Unsupported readbacks or setters are explicit UNKNOWN/UNRESTORED, not assumed
matches. No new dependencies, relaxed tolerances or fallback to different physics.

## Decisions and limitations

A full history-equivalent start procedure is VERIFIED REPRODUCIBLE only on
these two technical cases if both method/reference comparisons, reference/reference
and same-method cross-repetition comparisons meet ALL six image and relative-age
guards, full observable-state/controller guards and live-capture/readback integrity
checks. No age exemption permits that full claim. A method with replaced/copied
ages or non-restored observable state may earn only explicitly named partial-state
agreement, never overall reproducible-start verification. Specify all exclusions. Direct-root-only equivalence is not expected
or required; its measured failure is a useful negative comparator.
Otherwise report a bounded unresolved mismatch, first observable divergence and
unrestored states. A mechanism cause requires isolation, not mere correlation.
No recovery-rate, safety, illumination-robustness or held-out claim follows.

Independent bounded causal/protocol review, then executable review and a named
freeze commit must precede Part A model reconstruction and all new simulator
probes. Named-file lint/type/focused boundary checks precede freeze. Preserve
existing three environment-identity failures honestly. Results receive bounded
independent review before the diagnostic report/handoff commit.

Publication is separately scoped: only branch `agent/engineering-recording` to
the existing repository remote and a draft pull request, after outgoing-history,
authorship/artifact/privacy checks. No force push, history rewrite, merge, held-out
access, illumination experiment or real robot action. Runtime evidence never enters git.
