# Static arrival-rule development acquisition proposal v1

**Status: PREPARATION ONLY; NOT EXECUTION-READY.** No RGB was decoded, no
encoder or model was run, and no collection, fitting, threshold selection,
simulation, or navigation occurred. This proposal closes the synthetic
decision-rule comparison at `7c1b56e2af491ce4d660eaa397eb10157068686a`:
neither detached rule is selected as better.

Evidence basis: [`ALIAS_AWARE_DECISION_RULE_COMPARISON_V1.md`](ALIAS_AWARE_DECISION_RULE_COMPARISON_V1.md),
[`ARRIVAL_TRAIN_RECORD_SCHEMA_INVENTORY_V1.md`](ARRIVAL_TRAIN_RECORD_SCHEMA_INVENTORY_V1.md),
[`ARRIVAL_TRAINING_GEOMETRY_AUDIT_V1.md`](ARRIVAL_TRAINING_GEOMETRY_AUDIT_V1.md),
[`arrival_split_v2.json`](../configs/splits/arrival_split_v2.json),
[`RECORDED_RGB_STOP_RESULT_V2.md`](RECORDED_RGB_STOP_RESULT_V2.md), and
[`NATIVE_RAVEL_FIXED_GRAPH_RESULT_V3.md`](NATIVE_RAVEL_FIXED_GRAPH_RESULT_V3.md).

## Question and claim boundary

On the same camera-derived features and geometric labels, does removing the
hard alias-margin veto reduce missed near-goal proximity declarations without
increasing declarations at spatially distant lookalike locations? This is a
static visual-discrimination question. The target is the already frozen
`arrival_measures_v1` definition: query XY is within **0.5 m** of the requested
goal image's capture position, in one authenticated scene coordinate frame.
It is not successful arrival, a correct or safe STOP, settled motion,
collision-free completion, or navigation success.

Compare the two existing detached rules on every identical query record:

- **A — hard veto:** shared calibrated probability passes its threshold and
  alias margin passes its floor.
- **B — probability only:** the same calibrated probability passes its
  threshold; the margin is computed but does not veto.

Only the per-observation eligibility decision is assessed. Dwell, cancellation,
latched STOP, physical motion and contact endpoints are outside this study.
Query pose and label are evaluator-only; the candidate receives RGB history,
the ordered RGB reference bank and requested goal-image identity only.
Reference poses may be retained in the protected label record, but are not
exported to the runtime bank or passed to either rule.

## Proposed observations and fixed sampling

Use only newly captured observations in the admitted **training** scene
families. Do not use the accessed two-layout pilot, existing exposed
development/retired-test outcomes, or any specified future held-out group.
The camera-teacher path is offline scripted observation acquisition; no robot
or qualified motion is required or implied.

Each of 20 acquisition episodes uses one scene-family/goal identity and has:

1. A separate, earlier reference pass with eight ordered RGB captures. Node 7
   is the requested goal image; node 6 is planned geometrically within the
   frozen 0.5 m goal region. The remaining nodes follow the predeclared route.
   This creates the required opportunity for a valid near-goal query to
   resemble a nonterminal goal-region reference. No pose membership is
   supplied to the runtime candidate.
2. A separate query pass with 36 RGB frames and native simulation timestamps.
   The first three frames in each of four preplanned observation segments
   warm the four-frame history; the following six decision frames per segment
   are retained. Each episode therefore has 24 scored query decisions, each
   using the current and immediately preceding three captured frames. Actual
   timestamps and intervals are recorded; frame rate is never inferred from
   indices.
3. The four segments are assigned before capture: (a) queries at or within
   0.5 m of the goal capture pose, including a different-view revisit of the
   nonterminal node 6 location; (b) ordinary boundary negatives with distance
   strictly above 0.5 m and below 1.0 m; (c) repeated-structure candidate
   negatives at least 1.0 m from the goal; and (d) ordinary route negatives
   at least 1.0 m from the goal. The 1.0 m boundary is a proposed sampling
   stratum equal to twice the frozen target radius, not a new arrival rule.
   Repeated-structure locations are selected from scene/layout specifications
   before images or candidate scores are inspected. All acquired cases are
   retained, even if they do not look confusing after capture.

The 1.0 m repeated-structure stratum is a **candidate lookalike** stratum,
not verified visual aliasing. If the study is to label cases “visually
confusing,” two independent raters must mark query/goal-image pairs from the
captured RGB while blind to geometry labels and all model scores. Preserve
both ratings and disagreements; do not discard cases based on either rating.
Without this separate blinded annotation, report only the predeclared
repeated-structure stratum and do not claim visually confusing coverage.

Capture metadata bind every image hash to scene-family, layout, acquisition
episode, reference/query role, route segment, frame identity, requested goal
identity, camera/fixture identity, native monotonic simulation timestamp and
same-snapshot evaluator pose. Record coordinate-frame identity, XY units in
metres and yaw units in radians. Reference/query captures must share an
authenticated scene coordinate frame. Exact byte-identical query/reference
images are invalid and retained as rejected records; near-duplicate views are
reported, not removed. Inference receives none of the evaluator pose, label,
scene geometry, segment class, timestamp, or rater annotations.

Population ceiling: **20 episodes, 160 reference images, 720 query images,
480 scored query decisions**. The four scenario strata have 120 decisions each
before partitioning. These are planned coverage quotas, not independent
sample counts or a power claim. Histories overlap; all frames, decisions,
references and duplicates stay grouped by acquisition episode and scene
family. Retain uncompleted, invalid and refused records in the denominator.

## Development grouping and exposure

Use the five appearance families implied by the frozen training inventory and
split documentation; keep all scene aliases together:

| Group | Training scene IDs | Role |
|---|---|---|
| F0 | 0, 5 | Fit |
| F1 | 1, 6 | Fit |
| F2 | 2, 7 | Fit |
| F3 | 8 | Decision-threshold selection |
| F4 | 9 | Assessment |

Acquire four distinct goal episodes per family. No image, reference bank,
query history, episode or exact duplicate crosses partitions. The calibration
fit uses only F0–F2; threshold selection uses only F3; the frozen assessment
uses only F4. All five families are from the model-training partition.
Project adapted encoders have prior exposure to these scenes; the eventual
pair-score encoder's exact exposure must be checked after its identity is
bound. F3 shares appearance parameters with exposed development scene 3; F4
shares them with the exposed retired-test
scene 4. Those old observations and outcomes remain unopened and excluded.
Accordingly, F4 is a prospective, within-training-family development
assessment—not independent-layout generalisation. One threshold family and
one assessment family cannot estimate between-layout variation; results are
descriptive and cannot support an efficacy or calibration-generalisation
claim.

This yields 12 fit episodes, four threshold-selection episodes and four
assessment episodes. Each partition has 72, 24 and 24 scored decisions per
stratum, respectively. The decisions remain correlated within their four
episodes and one scene family; those counts are denominators, not independent
sample sizes.

Fit one fixed logistic probability map on F0–F2 from the existing terminal
score and alias-margin features, with each episode receiving equal total
weight. Fit both rule variants from exactly the same map. Report its Brier
score and log loss as metrics on this deliberately stratum-balanced sample,
not as deployment-prevalence calibration. Also report AUROC and average
precision. Retain per-episode and per-stratum counts, scores and outcomes.

For a proposed, finite threshold-selection procedure, enumerate the unique
probability cutoffs in F3 for B and the unique probability/margin-floor pairs
in F3 for A. Select each rule's point by minimum Euclidean distance from its
F3 ROC point to `(false-positive rate=0, sensitivity=1)`; tie-break by higher
sensitivity, then higher probability cutoff, then higher margin floor. Freeze
the selected values before opening F4. This is an explicit balanced-error
development convention, not an established deployment cost function. Its
selection-set sample size is small and its selected thresholds are not
navigation operating points.

On F4, report paired A-versus-B changes in near-goal acceptance, all-negative
false acceptance, boundary-negative acceptance, repeated-structure-candidate
acceptance, and ordinary-negative acceptance. Include the raw probabilities,
margins and threshold decisions, full denominators, and per-episode tables.
Do not select a preferred stratum, episode, threshold or rule after seeing F4.
Do not treat the 480 decisions as independent observations.

## Finite proposed resource budget

This is a proposed ceiling for a later separately authorized execution, not
approval to run:

| Stage | Proposed maximum |
|---|---:|
| Camera-teacher acquisition | 5 scene-family processes × 600 s = 3,000 s wall time |
| RGB, labels, metadata and attempt records | 4 GiB total external storage |
| Frozen encoder/feature extraction | 1 process, 1 GPU, 1,800 s wall time |
| Logistic fit and F3 threshold enumeration | 300 s CPU wall time |
| Robot actuation / closed-loop navigation | 0 |

Each process has one whole-process deadline and an immutable attempt record;
no retry, replacement capture, automatic budget extension or outcome-based
stopping is allowed. Any timeout or incomplete partition remains incomplete.
The prior 144-frame pilot's 116.18 s completion is context only; it does not
prove margin for this 880-image plan. The proposed caps are engineering
ceilings, not throughput or statistical-power estimates.

## Execution blockers and exact prerequisites

Do not collect or score until all of these are bound and reviewed:

1. **Feature provenance:** `alias_aware_arrival.py` accepts a finite `4 × N`
   similarity matrix but does not define an encoder, checkpoint, preprocessing,
   scalar query/reference similarity transform or score scale. The recorded
   RGB qualification establishes two released encoders and descriptors, not
   this candidate's pairwise similarity matrix. The fixed RAVEL/LightGlue
   graph qualification does not establish a compatible scalar score either.
   Bind one authenticated implementation, exact checkpoint/source hashes,
   preprocessing and pairwise-score semantics, or this candidate cannot be
   tested on observations.
2. **Reference/cadence contract:** freeze the deployment-matched eight-node
   bank builder, node ordering, terminal-window value and query observation
   cadence before capture. The current code leaves its terminal window
   unspecified, and the prior reference-order chain is an adaptation, not a
   qualified deployed builder. Capture timestamps cannot repair an
   unspecified history/reference alignment.
3. **Acquisition access:** verify that the camera-teacher executable can load
   the five admitted training appearance families and emit the same-snapshot
   pose/time/camera records specified above. The prior camera-teacher
   qualification used a known fixture; the successful pilot used already
   accessed layouts. Neither establishes access or capture parity on these
   training families. This requires simulator/fixture access only; CAD,
   loaded-motion qualification and robot actuation are not prerequisites for
   this static image-label study.

The proposal has enough detail to guide a narrow source/configuration closure,
but it is **blocked before acquisition** by these concrete source, reference,
and training-scene access checks. Do not reopen the accessed pilot to fill
them. If any prerequisite is unavailable, report that exact handoff and stop.
The current user authorization covers preparation only.

The local `rio-research` skill and global research standard informed the
evidence labels, split/exposure boundary, and separation of static proximity
from stopping claims. Skill-retrieval search tools were unavailable. No
external skills or literature claims were needed for this data-contract
proposal.
