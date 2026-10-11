# Option 1 dataset and ViNT training engineering check

Branch `agent/engineering-recording`, starting at `9a28d761`. Hospital work is
paused; its `e7633fe` camera/recording milestone remains unchanged. This milestone
collects RGB demonstrations with aligned `position[N,2]` and `yaw[N]`, verifies
loader admission, and checks bounded fine-tuning and saved-weight reload. Ten
trajectories and a training smoke are not a sufficient training corpus or a
publication result. Improved navigation and sim-to-real transfer remain hypotheses.

## Collection and supervision

The local fixture uses five spatially separated procedural scene variants with
changed corridor width and wall/floor colors. One off-route obstacle
has the same local placement in each variant; routes vary their relation to it.
Two routes per variant cover straight, left/right turns, S-bend and junction
motions. The junction route is a branching polyline inside a wide corridor,
not a modeled architectural junction. These are simple corridor fixtures, not realistic buildings
or ten statistically independent environments. Layout and route lists are frozen
before collection, not chosen after seeing model results.

An image-qualification attempt exposed plain-wall endpoint ambiguity. It is
retained separately. The final fixture adds actual USD wall stripes and floor
tiles before capture; the image thresholds and alignment tolerances remain
unchanged. The scene has visible geometry landmarks, rather than recorded-image
overlays.

A privileged scripted teacher follows fixed polylines using simulator XY/yaw.
This is allowed demonstration generation and supervision, not a deployed RGB-only
method. Every label is read back from the actual simulated articulation after
capture. Requested commands are not used as synthetic position labels.

The first wheel-actuated attempt is retained as a separate failed collection:
translation worked, but a turning route's sustained0.7rad/s requests produced
only~0.02rad/s yaw response. That route timed out and is rejected. A body-velocity
repair with free wheel drives also failed to turn (0.03rad over the turning route)
and is retained separately. The admitted-collection attempt therefore uses an
explicitly kinematic pose-step teacher with free wheel drives (stiffness0,damping0).
It requests one bounded pose increment per12Hz step, then records actual rendered
images and post-step articulation readbacks. Requested positions are not labels.
This qualifies dataset/training plumbing only; it does not establish wheel physics,
physical demonstration fidelity, real turning response, or sim-to-real control.

Camera acquisition is320x240 RGB at12Hz simulation time, calibrated/read back
prospectively with the inherited camera attestation. Images are matched to the
post-step pose and rendering timestamp. The inherited strict alignment tolerance
is unchanged. Source snapshots preserve exact executable file digests. Contacts,
commands, timeouts and partial failures remain in raw evidence.

The landmarked batch has five global directional lights, which washed out the
right-turn endpoint images. Those two attempts fail the unchanged image screen
and are retained. Only rejected routes are recollected with one global key light
(intensity1500) and dome800; requested and observedUSD light values are recorded.
Accepted trajectories therefore intentionally span both illumination setups. One
offset left-turn attempt recorded base-link contact with the obstacle and was
rejected. Its route was recollected with the obstacle shifted fromx2.4 tox3.5;
all source conditions and rejected attempts are retained.

Processing keeps every third capture (indices2,5,8,...), giving4Hz chronological
RGB history, and applies the identical selection to measured position and
unwrapped yaw. JPEG bytes are unchanged; filenames are canonical unpadded indices.
Only position/yaw are stored in `traj_data.pkl`; raw-index/time/source mappings
live in `processing.json`. The official loader performs its4:3 crop and85x64
resize and training normalization. Runtime intrinsics refer to acquisition images,
not silently to resized model images. Separate NoMaD admission/training is pending.

## Admission and splits

Every raw episode must pass independent image/pose/transition/source digest
verification and the scientific preflight. Every processed image and position
must map exactly to its raw source. Images require grayscalep95-p05 contrast>=15,
mean horizontal/vertical absolute gradient>=0.3, and extreme-pixel fraction<0.95.
These declared engineering usability screens do not prove semantic visibility;
representative route images also require visual review.

Motion requires measured path length>=1m, net displacement>=0.5m, maximum
12Hz displacement<=0.12m, finite poses, teacher endpoint within0.2m, and completed
teacher termination. Recorded obstacle contacts reject a demonstration; detector
sensitivity is not assumed without positive controls. Rejections and failures
are retained, rather than replacing their status with recording PASS.

Scene-family and route-disjoint assignments were frozen prospectively:

| Split | Scene families | Trajectories |
| --- | --- | --- |
| Train | straight, left, right |6 |
| Development | S-bend |2 |
| Held-out engineering test | junction |2 |

These held-out simulation pairs were reused during debugging and the repeated engineering smoke and
cannot later be described as untouched confirmatory data. No real test data is
read, written or collected. Future confirmatory scenes/routes must be new.

Action normalization is the median nonstationary 4 Hz position-step length from
TRAIN only; measured distribution and selected unit are reported. Evaluation
converts normalized waypoint errors using this exact registered unit. Upstream distance supervision
is a temporal goal-offset/category label, not Euclidean metres. Positions/yaw
produce local waypoint and heading targets; they are supervision, never model inputs. Deployment
must use the same unit for the adapted model; comparison must freeze the same
controller mapping and action unit for both arms, not change scaling per outcome.

The existing dirty upstream clone is preserved. An external snapshot copies its
tracked training sources and adds only a dataset registry entry. Source hashes
and original base commit are recorded. All samples from every admitted split are
materialized with the project-patched official loader and checked for finite
seven-tuple tensors. The pristine loader file from the pinned upstream commit is
also instantiated against the same data, with all samples checked. Compatibility
is thus observed, not inferred from a matching directory structure.

Fixed dev/test pair identities, sampling seed, negative-goal flags, split digests,
and dataset hashes are frozen before model evaluation. Training sampling remains
seeded and stochastic. Frozen pairs do not cross split boundaries.

## Fine-tuning smoke

`configs/train/option1_vint_smoke.yaml` specifies full ViNT fine-tuning from the
existing digest-verified release checkpoint, batch4/effective4, lr1e-5, AdamW,
weight decay0.001, frozen BatchNorm, bf16, seed17 and zero loader workers.
`scripts/train_option1_smoke.py` bounds the existing trainer to six optimizer
steps. It calls the pinned upstream loss and reference preprocessing; guards
all loss scalars and gradients against nonfinite values; checks that parameters
change; saves weights; strictly reloads every tensor; and checks exact prediction
equality after reload. No checkpoint download or architecture substitution occurs.

Before/after offline evaluation uses exactly the same held-out observation/goal
pairs and negative flags. Report waypointADE/FDE in metres only on valid action
masks, with pair and valid-action denominators. Offline latency includes LMDB
read and label generation, preprocessing, inference, CPU metric calculation and
CUDA synchronization; it is not robot full-loop latency.
Navigation success, correct stopping, robot collisions and real execution latency
remain NOT RUN for these adapted weights. Neither pretrained nor adapted ViNT
has a native terminating action in this integration.

## Reproducible commands

Run from `/home/favl/projects/navfm-engineering-recording`. New output directories
are required; completed evidence cannot be overwritten.

```bash
OMNICLIENT_HUB_MODE=disabled /home/favl/miniforge3/envs/isaac/bin/python \
  scripts/collect_option1.py --actuation pose_step \
  --robot /home/favl/projects/navfm/assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd \
  --out /home/favl/navfm-runtime-evidence/option1-20261007-new

# Actual admission combines retained batch05 and repaired right-turn batch06.
NAVFM_UPSTREAM=/home/favl/projects/navfm/third_party/visualnav-transformer \
  .venv/bin/python scripts/admit_option1.py \
  --collection /home/favl/navfm-runtime-evidence/option1-20261007-05 \
  --collection /home/favl/navfm-runtime-evidence/option1-20261007-06 \
  --collection /home/favl/navfm-runtime-evidence/option1-20261007-07 \
  --out /home/favl/navfm-runtime-evidence/option1-admitted-20261007-02

PYTHONHASHSEED=17 .venv/bin/python \
  scripts/train_option1_smoke.py --steps 6 \
  --dataset /home/favl/navfm-runtime-evidence/option1-admitted-20261007-02 \
  --out /home/favl/navfm-training-evidence/option1-vint-20261007-04
```

Raw images/manifests/source snapshots, processed trajectories, loader caches,
pair files, training reports and weights are external and are never staged.

## Matched evaluation and collection scale proposal

`configs/eval/option1_pretrained_vs_finetuned.json` freezes matching requirements
and three proposed engineering pairs. Adapted checkpoint identity is filled from the successful training/reload report. Live comparisons require qualified actuation,
disabled-path replay controls, contact detector positive/negative controls,
visible image goals, identical preprocessing/history/action unit and observer.
Stopping/safety remains a separate unresolved algorithm, not a proxy threshold.
Retain every failure, timeout and intervention and count all attempted episodes.

Next collection scale should be driven by coverage and learning curves. Proposed
first expansion:20 independent training layouts with10 routes each (200 demos),
plus5 new development layouts and5 new held-out simulation layouts with10 routes
each. Freeze assignments before collection. Include both turn directions, varied
route lengths, junctions, lighting, goal appearance and obstacle placements;
report actual speed/yaw/image distributions, not just trajectory counts.

Train nested25/50/100/200 trajectory subsets with at least3 training seeds and
fixed development populations. Plot training and development waypoint errors
against admitted moving frames and routes. If error remains unstable, add
coverage or label/controller repairs; do not assert200 trajectories suffice.
Choose the training scale only after curve trends and matched navigation failures
identify whether the limiting factor is data coverage, model fit or transfer.
Confirmatory sample size remains pending matched-pilot variability and a meaningful
navigation effect; engineering episodes must not be reused as confirmatory tests.
