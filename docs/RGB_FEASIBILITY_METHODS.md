# Simple corridor RGB navigation feasibility

Hospital collection is paused and its e7633fe instrumentation milestone is preserved.
These runs are engineering feasibility evidence, not confirmatory observations.
No baseline-versus-layer episodes have completed. No superiority or formal safety
claim, including comparison with SaferPath, is supported.

## Executed method

`run_rgb_feasibility.py` builds a local primitive corridor in Isaac Sim 5.1.0.0.
The M3Pro physics asset comes from the existing navfm project. The camera faces
robot +X at local offset (0.2, 0, 0.55) m, with clipping (0.05, 30) m,
requested 640x480 images and 64 degree horizontal field of view. A dome light
(intensity 800) and distant light (1500) illuminate gray walls and floor, a blue
off-route box, and an orange visual goal panel. Goal RGB is captured at (3,0),
yaw zero; start is (1,0), yaw zero. This is a prospective local configuration;
no Hospital calibration or rendering history is inferred from it.

Start and goal images visibly show corridor boundaries, obstacle and goal panel.
Runtime manifest observations distinguish requested values from camera,
render-product, renderer, physics, and timestamp readbacks. The strict inherited
preflight runs every frame. Images, recorded poses, transition continuity, source
hashes, and 12 Hz simulation cadence are independently verified without relaxing
alignment tolerance. Recording PASS is not navigation success.

The baseline is the existing released ViNT checkpoint:
`/home/favl/projects/navfm/checkpoints/vint.pth`, 430167114 bytes,
SHA256 `155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f`.
The registry/config evidence is `configs/train/vint_finetune_4080s.yaml` and
`docs/REPRODUCTION.md` in `/home/favl/projects/navfm`. Loading was successful
with strict state-dictionary matching in the simulator interpreter. No download
or replacement checkpoint was used. Loaded upstream commit and model config are
recorded in each manifest.

This is a direct image-goal adaptation, not the full topological navigation stack.
PIL resize uses the upstream image size; tensor normalization uses ImageNet
mean (0.485,0.456,0.406) and standard deviation (0.229,0.224,0.225), matching
upstream deployment preprocessing. Six chronological RGB control observations
and one goal RGB are the only model inputs. The initial history repeats the first
image. Model waypoint index 2 is scaled by 0.2/4 = 0.05 m; reference PD maps it
to differential v/w, limited to 0.2 m/s and 0.4 rad/s. Commands update at 4 Hz
and are held between 12 Hz physics frames. The baseline has no terminating action.
A 15-second simulation timeout is evaluator termination, not a correct stop.

The wheel mapping uses fl/fr/rl/rr joint names, wheel radius 0.040 m and
half-length plus half-width 0.0775+0.085 m, inherited from the existing robot
mapping. The asset's position servo stiffness 625 opposed velocity commands.
The prospective fixture config sets angular stiffness zero and damping 10 before
physics initialization; requested and observed USD drive values are saved.
This mapping still requires motion qualification from executed evidence, rather
than assuming a command constitutes displacement.

## Input boundary and unresolved research method

`RGBBaseline.step(history, goal)` receives only RGB arrays. It receives no poses,
obstacle coordinates, clearance, actual goal distance, contacts, or ground truth
velocity. Wheel actuation uses commands and static robot dimensions; it does not
read simulator yaw. Action history is not a model input. Temporal RGB history and
model prediction history must be distinguished from privileged state in any
future layer. An image-goal task also assumes a supplied goal image; it does not
infer a goal from language.

Simulator state is used only for setup, recording, and offline evaluation.
Evaluation poses and collision geometry must not enter the deployed policy/layer.

Located candidates are not an executable RGB-only second arm:

- `Fleet-Safe-VLA-OS/fleet_safe_vla/integrations/visualnav_transformer/fleetsafe_wrapper.py`
  exposes `FleetSafeWrapper.step(preprocessed, obs_vec, obstacle_positions)`.
  Its `YahboomCBFFilter.filter` reads robot XY from obs[16:18] and obstacle
  coordinates. No documented RGB geometry/uncertainty estimator was located.
- `gnm-vlnverse-baseline/scripts/robots/stop_head_shadow.py` exposes
  `StopHeadShadow`. It uses goal-distance and waypoint predictions, their window
  means/trends, a temporal MLP, and stored normalization/threshold/persistence.
  Existing weights are GNM-trained and shadow-only (SHA256
  `5339b75546c50529dfa69bae7f02e53224ad9afe99ce298e48c1acb0caf7188a`).
  Actual goal distance is an evaluation diagnostic, not a permitted deployed
  input. No ViNT calibration or validated stopping authority was located.
- That repository's `docs/experiments/PROJECT_BASELINE_STATUS.md` explicitly
  rejects two threshold-based stop-authority experiments and requires in-domain
  learned heads or richer rules with held-out authority validation.

The unresolved decision is which documented ViNT-compatible stopping and safety
algorithm governs the second arm, including its training/calibration data,
nonvisual inputs, stopping authority, and RGB-only obstacle/uncertainty estimation.
A GNM shadow score or privileged CBF cannot silently become the research method.
`--arm layer` therefore fails explicitly with `RGB_LAYER_UNRESOLVED`.

## Matched pilot and proposed confirmatory protocol

The first engineering pilot will use seeds 0,1,2, the same checkpoint digest,
fixture, camera, wheel gains, image goal, starts, controller, 180-frame timeout,
and obstacle configuration in both arms. Even seeds run baseline first; odd seeds
run layer first. Save each arm independently; retain all timeouts, crashes,
collisions, stops and interventions. Disabling the layer must produce identical
commands to baseline on a frozen RGB history replay before live pairs are admitted.
Check collision monitoring with deliberate contact and noncontact controls.
Qualify wheel motion before paired comparisons. A seed is a stochastic control,
not a distinct route; this one corridor cannot support generalization claims.

After three valid pairs, extend to ten pilot pairs only if both arms and evaluation
are qualified. Pilot episodes remain permanently excluded from confirmatory tests.
Freeze algorithm, checkpoint, thresholds, calibration split, routes, seeds, arm
order, metrics and analysis before confirmatory collection. New held-out routes
must include near-goal, look-alike premature-stop, blocked-goal and crossing
obstacle conditions; image appearance and geometry should both vary.

Primary endpoint proposed: collision-free correct terminal stopping within 0.5 m
of the image-goal capture position, without timeout. Report its paired difference
and interval. Secondary endpoints: premature stops, contact episodes, unsafe
clearance duration, latency and interventions. Keep arrival proximity separate
from terminal stopping. Report all assigned episodes by intention to execute;
crashes/timeouts are failures, with missing evaluation observations explicit.

A meaningful effect proposed for planning is a 20 percentage-point improvement
in primary success. Current completed comparisons = 0, so pilot variability is
unknown and a justified final sample size cannot yet be frozen. Estimate paired
indicator variance after the ten-pair pilot; for an initial two-sided 5%, 80%
power approximation use n=ceil((1.96+0.84)^2 * Var(layer-baseline) / 0.20^2),
then validate with an exact paired-binomial power calculation using observed
 discordance and conservative uncertainty. Example only: discordance 0.40 and
paired difference 0.20 implies variance 0.36 and about 71 pairs. This is not a
pilot-derived sample size. Freeze the final size and held-out scene distribution
before testing; do not repeatedly extend until significance is obtained.

## Metric definitions

`feasibility_metrics.summarize` is offline evaluation only. Correct stop events
have evaluated distance <=0.5 m at the stop's physics frame; premature stops are
outside that radius. Rates use stop-event denominators and are undefined when
there are no stops. Navigation success requires a correct terminal stop and no
reported obstacle contact. Final-position arrival is a separate diagnostic.
Contact episodes use all attempted episodes as denominator; absent reports do
not establish detector sensitivity until positive controls pass.

Unsafe duration sums actual simulation step durations where the world AABB of
measured local robot visual bounds has clearance <0.3 m to collision boxes.
This conservative envelope proxy is not exact surface distance or formal safety.
Policy p95 uses all inference calls including cold start, from preprocessing
through model execution, CPU transfer and PD mapping, with CUDA synchronization.
It excludes sensor acquisition and motor application. Recording-loop p95 also
includes rendering and per-frame attestation; it is not deployed policy latency.
Report maximum/cold-start latency because p95 can hide one large initialization
outlier. Path length includes each transition's before-to-after displacement.
