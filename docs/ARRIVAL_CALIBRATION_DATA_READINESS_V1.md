# Alias-aware arrival calibration data readiness v1

**Outcome: NOT READY — no calibration or threshold-selection split is
recommended.** This is a metadata-only assessment of the committed candidate at
`34532d1b270621b213008532dcddcd0e0a4c06c1`. It does not read trajectory
pickles, RGB, descriptors, checkpoints, or evaluation outputs, and it performs
no fitting, inference, collection, or simulation.

## Metadata reviewed

- `docs/OFFLINE_NATIVE_EVALUATION_V1.md` records 31 training trajectories and
  four exposed evaluation routes. Two routes originally marked test have been
  retired to development; the 48-pair positive/cross-route-negative catalog
  uses these exposed routes and is ineligible for calibration or threshold
  selection.
- The external admitted-training `admission.json` records 35 admitted
  trajectory-level entries: 31 train, two development,
  and two formerly test entries. Records include trajectory, route, scene and
  split identities plus aggregate motion/image-usability fields. The manifest
  has no per-frame timestamp, arrival-label, wrong-location-label, or
  descriptor fields. No image or trajectory content was opened.
- `configs/splits/arrival_split_v2.json` says the existing development and
  retired-test groups are not appearance-disjoint from training: scene
  appearance parameters partially overlap across partitions. It specifies
  future held-out groups as **NOT COLLECTED**. These identifiers are not a
  current fitting or threshold-selection population.
- `docs/PROSPECTIVE_COLLECTION_RESULTS_V2.md` records an admitted 144-frame,
  four-route, two-layout pilot with ordered labels and timestamps. Those
  layouts and outcomes were accessed; this assessment excludes them from
  fitting and threshold selection as required. The collection is not an
  independent benchmark.

## Feature-to-data requirements

| Candidate input | Required evidence | Readiness |
|---|---|---|
| Four ordered query/reference similarity rows | Frame-level query and reference identities, chronological ordering and timestamps; pinned encoder/matcher outputs with preprocessing and descriptor provenance | **Not established.** Current admission is trajectory-level; the exposed offline pair catalog is not an ordered reference-similarity matrix. Producing descriptors requires inference, which was out of scope. |
| Requested-terminal score and alias margin | A fixed requested-goal reference identity, declared terminal-reference window, and identified visually similar incorrect reference(s) | **Not established.** Existing native positive and cross-route-negative pair labels are prediction labels, not verified visual-alias labels. No eligible alias-example inventory is recorded. |
| `requested_goal_valid` calibration label | A prespecified, independent rule mapping each query frame and requested goal to valid/invalid arrival, with pose/time provenance and missingness handling | **Not established by the reviewed manifests.** Aggregate motion and pair-distance metadata do not provide this frame-level label. Do not infer it from model scores or pilot outcomes. |
| Episode/layout grouping | Stable episode, source-trajectory and layout identities across fit and selection partitions | **Partially available, insufficient for a clean split.** Trajectory/route/scene identities exist, but documented appearance overlap prevents treating current train/development partitions as layout-independent. Episode balancing does not remove this leakage. |
| Threshold-selection outcomes | A separate, untouched calibration-selection population with correct-stop, wrong-location-stop and task-completion labels | **Unavailable.** Exposed development outcomes are ineligible; future held-out groups are specified but not collected. |

## Decision and exact gap

The current metadata cannot establish a valid frame-level calibration table or
enough visually similar wrong-location examples. It also cannot support a
layout-disjoint split for fitting versus threshold selection. This is an
evidence gap, not a finding that the underlying training files necessarily
lack every field; inspecting those files would exceed this metadata-only
assessment.

Therefore no fitting split, threshold split, sample-size claim, or compute
budget is proposed. The next prerequisite is an explicitly authorized
**metadata/schema-only inventory of admitted training records**, without
opening RGB or running encoders, that verifies per-frame query/reference IDs,
timestamps, pose/goal fields, source trajectory and layout keys, and label
derivability. If that inventory establishes those fields, a separately
reviewed plan must still identify alias-hard negatives and genuinely disjoint
fit/threshold groups before calibration. Any future evaluation data and all
accessed pilot outcomes remain excluded.

No change was made to the arrival component, scientific endpoints, splits,
apparatus gates, checkpoints, or data. No Astra review was requested because
the data needed to make substantive calibration choices are not established.
No tests or model/simulator runtime were needed for this documentation-only
record.
