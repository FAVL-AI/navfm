# Articulated simulation and deployment integration methods

This milestone continues the admitted Option 1 corpus at `a3a6974`. Hospital is
paused. Evidence separates dataset validity, offline prediction, articulated
closed-loop simulation, and real transfer. Only the first three have executed;
closed-loop model episodes currently establish integration and failures, not
successful navigation. No real robot was actuated and real test data remain untouched.

## Physical control qualification

`scripts/qualify_articulated_control.py` uses Isaac Sim 5.1, 120 Hz physics,
wheel-joint velocity targets and articulation pose/velocity/joint readbacks.
Initial spawns set the pose; there are no subsequent kinematic pose updates,
body-velocity overrides, or ground-truth feedback commands. Commands are held
for three seconds followed by two seconds of commanded zero. Steady tracking
uses samples after the first second. Residual motion uses the final 0.5 seconds.
Stopping distance sums actual XY motion after the first zero command.

Before executing, the following absolute engineering gates were declared:
linear error <=0.05 m/s, yaw-rate error <=0.15 rad/s, wheel-rate RMSE <=0.5 rad/s,
stop travel <=0.05 m, residual linear speed <=0.01 m/s and yaw rate <=0.03 rad/s.
The tracking margins are 25% of initial 0.2 m/s and 0.6 rad/s commands; stop and
residual margins distinguish useful arrest from continued travel against a
0.5 m evaluation goal radius. These are broad engineering tolerances, not safety
proofs or hardware calibration. They were not relaxed after failure. At the
subsequent reduced command limit, linear tolerance is 50% of commanded speed.
The restricted sampled-command qualification is therefore explicitly weaker
than high-fidelity trajectory tracking.

The original cylinder-wheel asset failed tracking. Analytic cylinder collision
replacement and acceleration drives alone also failed. A prospective sphere-wheel
collision proxy, existing articulation/visual asset and acceleration angular
joint drives restored forward motion. This diagnoses a dependence on collision
geometry but does not identify the precise cylinder/solver failure. It does not
simulate mecanum rollers or establish real wheel physics. Existing asset files
were not changed. Proxy chassis box dimensions are 0.290x0.235x0.080 m, wheel
collision radius 0.040 m. Angular-drive stiffness is zero, damping 1000, type
acceleration. All are prospective simulation settings, not measured hardware values.

The 0.2 m/s combined-turn tests still failed after calibration. A restricted
configuration was separately declared and tested at 0.1 m/s, +/-0.4 rad/s,
using yaw gains 1.5 for zero-forward and 0.8 for moving commands. All six sampled
cases passed. Pure turning still produces about 0.12 m translation over three
seconds; do not describe it as accurate rotation in place. There is no continuous
command-envelope guarantee. Forward, left/right, combined left/right and stopping
traces, wheel mappings and failures are retained outside Git.

The nominal mecanum command map orders FL,FR,RL,RR and uses r=0.040 m,
k=0.0775+0.085 m. With lateral command zero it becomes paired left/right wheel
rates `(v-k*w)/r,(v+k*w)/r`. Indices were obtained from actual DOF names; joint
velocity targets and realized wheel rates were logged. Both direction signs and
finite-difference pose motion were checked against velocity readbacks. The
geometry is provisional and the empirical yaw gains are simulator-specific.

## Collision positive control

The same articulated configuration starts clear of a static wall and drives
forward into it. Rigid-body contact schemas are installed before physics views
are created. Events decode both actual actor paths. The final positive control
reported 1,316 robot-wall events; the five free-space cases reported none. Earlier
failed attempts that never reached the wall do not validate the detector. Contact
persist events are not independent collisions. Evidence supports one controlled
contact episode and five noncontact episodes in the final configuration; it does
not establish sensitivity for every obstacle, grazing contact or hardware collision.

## Matched live checkpoint integration

The released checkpoint and six-step adapted checkpoint use identical three held-out
engineering routes: S-bend variant0 and branch variants0/1. The word junction is
an existing route label; these fixtures are corridors, not architectural junctions.
Execution was batched pretrained first, then adapted, rather than the earlier proposed alternating order. System/order confounding precludes performance claims. Both arms used the same fixed saved RGB goals, route seeds, initial conditions,
fixture, lighting, camera, controller, 20 simulation-second timeout and stop rule.
Comparison used start tolerance 0.001 m/0.005 rad, exact goal-image hashes and
exact fixture/controller/camera/readback equality. Actual initial pose differences
were at most 0.016 mm and 0.000016 rad. No randomized simulator disturbance was
introduced; route seeds identify deterministic configurations, not replicated
stochastic worlds. These are engineering episodes, not an untouched test set.

The live camera records 320x240 RGB at 12 simulation Hz with 120 Hz physics.
Actual rates are read back. Each admitted frame is independently checked using
unchanged timestamp tolerances and exact source/recording digests. Raw RGB
passed the fixed contrast/edge/extreme-pixel screen. Representative saved frames
were visually reviewed. That screen is not proof of geometric visibility everywhere.

ViNT receives six chronological RGB observations at 4 Hz and a goal RGB image.
Startup repeats the initial image. Official 4:3 center crop, resize and ImageNet
normalization are used; software tests verified exact official tensor equality.
No pose, yaw, measured velocity, obstacle geometry, collision state, map or action
history is a model input. Simulator state sets initial/goal demonstration captures
and supplies evaluation and labels only. The execution adapter also consumes
acquisition timestamps and its clock for scheduling/watchdog checks; those are
not network features. The RGB-only claim describes the policy input boundary,
not an absence of clocks or motor-command bookkeeping.

Waypoint index2 uses the frozen TRAIN-only normalization unit
0.049994826316833496 m and the same reference differential controller for both
arms, clipped to v<=0.1 m/s and |w|<=0.4 rad/s. A common experimental stop is latched
after three predictions with temporal-distance output <=1 and selected XY
waypoint distance <=0.15 m. This is an uncalibrated termination heuristic, not
native ViNT stopping authority or the proposed research safety layer. No simulator
goal-distance threshold triggers deployment stopping.

Success requires a stop decision within 0.5 m, settled final position within that
radius, and no reported contact. Correct and premature stopping use evaluator
pose at the stop decision. Report episode counts and stop-event denominators;
precision is undefined with no stop events. Arrival is separately any frame
within 0.5 m. Collision episodes mean at least one reported nonfloor fixture
contact. Path length includes initial-to-first motion. Efficiency is success
weighted Euclidean distance to the 0.5 m goal region divided by max(shortest
distance, actual path). This is a primitive unobstructed-route engineering metric,
not an established benchmark SPL score.

The recorded perception-to-command interval begins at RGB-buffer access, includes
history copying, preprocessing, synchronized inference, waypoint mapping and first
joint-target submission. Rendering/acquisition, earlier buffer residence and
physical response are unavailable in this measurement. Report those missing
boundaries explicitly; do not call it measured camera-exposure-to-motor latency.
Background simulator, collection and training load varied. Cold starts and missed
250 ms policy deadlines remain in the results; no timing superiority claim follows.

Initial live recorder sidecars label all runs NOT_APPLICABLE_DEMONSTRATOR, including
those live episodes. Its policy field is stale; the executable source and runtime
policy manifest establish actual RGB inputs. Similarly the historical R8 annotation
calls physics_substeps intent-only although the new runner consumes it; the
120/12 Hz runtime readback establishes actual execution. Raw records are preserved
with these inconsistencies disclosed. The corrected recorder preserves explicit RGB policy inputs and the runner overrides the consumed-field annotation; a12frame live check and subsequent matched repeat validate these repairs. No historical evidence is rewritten.

Fixed goals come from raw collection05. The live R3 time refers to a discarded local goal capture, not the fixed goal image. The independent report verifies the exact source PNG hash and records its observed original capture time and separate simulation-clock epoch. This supplements provenance without fabricating synchronization across runs. Goal views may differ because the original teacher uses cylinder geometry/settling and an earlier obstacle position; both arms receive the same reference. This mismatch is an alternative explanation for failure, not evidence of a deficient architecture.

## Dataset expansion and learning curves

The existing 6/2/2 split has zero cross-split scene-ID, route-ID or exact JPEG hash
intersection. Its five fixtures share a procedural corridor template, textures,
stripes and floor patterns. Translated variants are correlated. Identifier
separation does not establish architectural/environment independence.

Prospective expansion adds five partition layouts with changed corridor widths,
doorway position/width and obstacle placements, each with five route behaviours:
straight, gentle left/right, S-bend and a double-turn route. These are distinct
parameterized layouts within a common primitive family. Shared appearance and
behaviour motifs remain limitations; no unseen-domain claim follows. All are
training-only; existing development/test images, labels, names and sampled goals
remain frozen. The original TRAIN normalization is retained for comparison.

Demonstrations still use an explicitly privileged kinematic teacher. This supplies
valid observed RGB/XY/yaw supervision, not qualification of a physical controller.
Every candidate receives strict alignment, motion, image, runtime and no-reported-
contact checks; failures and repaired recollections remain separate. Data collection
failure cannot be removed from the admission denominator. The interrupted first
expansion was marked provenance-invalid because executable source changed during
collection; it is excluded and preserved. Retries execute immutable external
source snapshots. A stale sensor failure is recollected with bounded zero-time
re-renders; timestamps are never relabelled or tolerances relaxed.

Learning-curve comparisons use nested training trajectory subsets, fresh starts
from the same released checkpoint, seeds0/11/22, identical 20 optimizer steps,
batch4, AdamW lr1e-5, weight decay0.001, bf16 and frozen batch normalization. This
fixes updates and sampled examples, not epochs or corpus exposure. Small budgets
are feasibility diagnostics and cannot establish data sufficiency. Report finite
losses, changed weights, strict reload and fixed development waypoint ADE/FDE.
Development has 57 action-valid pairs out of83; pairs within a trajectory are
correlated. Do not treat pair count as independent experimental sample size.
The six-trajectory run's first development-only implementation still evaluated
the adapted engineering test set; this bug is preserved in its frozen source
and repaired for subsequent runs. The engineering test was already inspected;
no untouched confirmatory or real test data were used.

Future 50/100/200 points require actual admission and multiple-seed training, not
extrapolated results. Expand geometric classes and long/short/turn/occlusion/start
conditions; use coverage and learning-curve uncertainty to decide collection scale.
Training trajectories are not guaranteed sufficient at any named size. Later
navigation evaluation must compare frozen pretrained and selected adapted weights
on new simulator conditions and supervised real routes with qualified camera,
controller and independent stop/watchdog. Real-transfer results are not yet available.
