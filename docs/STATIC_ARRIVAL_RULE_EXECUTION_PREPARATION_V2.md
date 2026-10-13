# Static arrival-rule execution preparation v2

**Status: score and selection contracts specified; collection is blocked.**
This is not an execution authorization or a runnable collection freeze. No
encoder forward, image decoding, collection, fitting, threshold search,
simulation or navigation occurred. The v1 proposal remains unchanged at
`f7cc624`.

## Resolved score contract

Use the qualified **ULVN MegaLoc** path only. Do not use CosPlace: its
checkpoint is marked `RETRIEVED_UNCERTIFIED_HASH` in
`configs/eval/recorded_rgb_stop_v1.json`. The MegaLoc checkpoint has the
recorded expected LFS SHA-256
`d4f9f2bcb60018f91eb6a8e061ed054fd55654e10c2569cf13841ea986ffb4f8`;
the pinned MegaLoc source commit is
`5fe0dd697c4a70ba3e23607f6716ab3c606b16db` and the ULVN source commit is
`e2f47fe3e2757a1ebdc041f4364dddd26a19f9f5`. The recorded RGB qualification
tested eight reference and eight query images per encoder, with finite,
unit-norm MegaLoc descriptors of width 8448 under the declared runtime.
This binds the released implementation and descriptor path; the cosine
matrix below is a **new candidate score adapter**, not native ULVN or RAVEL
score parity.

Preprocessing is the pinned ULVN MegaLoc `build_transform(320, 320,
"megaloc")`: RGB PIL image, resize to 320×320, tensor conversion, then
ImageNet channel normalization (means 0.485/0.456/0.406; standard deviations
0.229/0.224/0.225). `MyVPR.encode` L2-normalizes its descriptor. The adapter
defensively normalizes again in float64 and computes cosine similarity as a
dot product, clipped only for floating-point roundoff to `[-1, 1]`.

Reference order is route order from earliest node `R0` to requested goal
`R7`; the requested goal must be the last reference. Each query decision
uses four consecutive captures, passed newest-first as `I[t]` through
`I[t-3]`. For `H[k,j] = cosine(I[t-k], R[j])`, the existing feature code
computes `S(j) = mean(k=0..3, H[k, max(0,j-k)])`. The terminal window is
fixed to one node (`R7`); earlier references supply the alias competitor.
This index shift assumes each history sample advances one reference-node
interval. Equal capture cadence alone does not verify that assumption against
a deployed reference builder, so this remains a declared development
adaptation.

The adapter binds ordered record IDs and SHA-256 image-content hashes. It
rejects repeated IDs, query/reference ID or byte-hash overlap, malformed
shapes, mismatched descriptor widths, non-finite values, zero or overflowing
norms, and non-finite cosine outputs. The synthetic tests exercise the
production adapter and preserve history/reference order. No learned encoder
was run for these tests.

Verified encoder exposure is limited to its prior 16 query/reference frames
from the already-accessed two-layout pilot in the recorded RGB qualification.
No evidence establishes prior MegaLoc inference on the proposed new training
captures. MegaLoc pretraining-corpus overlap with the simulator scenes is
unknown. Neither fact supports an independent-layout generalization claim.

## Acquisition and timestamp contract

The existing camera-teacher source uses a 12 Hz simulation configuration and
four `sim.step()` calls while holding each camera pose. This implies a
nominal interval of one third second; it is not a substitute for measured
timing. A future acquisition must persist each frame's native
`rendering_time`, rational `rendering_frame` identity, same-snapshot camera
pose and content hash. Histories are selected from four consecutive query
captures by recorded order, newest-first for scoring; timestamps must be
strictly increasing in acquisition order and every actual interval must be
reported. No interval may be reconstructed from frame number or assumed rate.

The geometric label anchor is the **camera optical-center XY position** for
both query and requested-goal image, from the same-snapshot camera pose, in
the shared scene frame and metres. The current teacher code also records the
base/teacher pose and offsets the camera by 0.2 m along heading; those values
must not be mixed. The frozen 0.5 m label means only geometric proximity to
the requested goal image. It is not successful arrival, safe stopping or
collision-free completion. Query pose and labels remain evaluator-only.

The proposal's intended population remains 20 episodes / 160 references /
720 queries / 480 decisions, grouped into F0–F4 as documented in v1; it is
not executable yet. The source inspection found the exact blocker:

- `scripts/prospective_capture_v1.py` accepts only
  `two-static-rooms-v1`, builds boxes from that sealed specification, and
  does not call the training-scene `legacy_boxes` builder.
- `scripts/run_prospective_collection_v2.py` validates the same two-room
  seal/recipe before launching that capture script.
- Training geometry is available through `src/navfm/collection/scene_layouts.py`
  and is used by `scripts/collect_option1.py`, but that collector creates the
  articulated M3 Pro/control stack. It is not the requested camera-only,
  non-actuating teacher path.

The missing dependency is one source-backed **camera-only training-scene
adapter** plus frozen per-episode reference/query pose schedules and bindings
for each scene's half-width, partitions and lighting. These inputs are not
present in the current camera-teacher seal or collection config. The earlier
known-fixture and accessed-pilot runs do not establish access to these five
training scene families. Do not bridge the gap by using the articulated
collector, by relabeling the two-room fixture, or by constructing an
unreviewed scene schedule.

The split is development-only: F0–F2 fit, F3 threshold selection, F4
assessment. F3 (scene 8) and F4 (scene 9) share appearance parameters with
previously exposed development/retired-test scenes 3/4. The proposed four
F4 episodes belong to one exposed scene family; they support descriptive
paired counts only, not layout-level uncertainty, independent generalization
or efficacy inference. The 480 correlated decisions are not independent
observations. Previously accessed pilot outcomes stay excluded.

## Fixed development-selection rule

Fit one episode-balanced logistic probability map on F0–F2 (`l2=0.2`,
maximum 100 Newton iterations); use that same fitted map for rules A and B.
All F3 episodes must contain both geometric classes; otherwise stop threshold
selection rather than silently dropping an episode.

1. On F3, select one shared probability cutoff `tau` for both rules by
   maximizing the mean of per-episode balanced accuracy for rule B. Enumerate
   the unique values in `{p, nextafter(p, -infinity), nextafter(p, +infinity)}`
   for each distinct fitted F3 probability `p`, retaining only legal
   `0 < tau < 1` values and deduplicating identical decision masks. This
   covers saturated outputs while respecting the decision config's strict
   bounds. Resolve exact score ties by the numerically smallest `tau`.
2. Hold that `tau` fixed. For rule A only, select alias-margin floor `m` by
   maximizing its mean per-episode balanced accuracy on F3. Enumerate the
   observed distinct margins, the nonbinding cosine floor `m=-2`, and
   `nextafter(max_margin, +infinity)` to represent veto-all; deduplicate
   identical decision masks. Resolve exact ties by the numerically smallest
   floor. Compare mean balanced accuracies as exact count-derived rational
   values, without a floating tolerance.
3. Rule B uses the same `tau` and ignores the margin. Report this as a veto
   ablation at B's selected operating point; A has the additional selected
   floor. Exact count-based balanced-accuracy comparisons are used, with no
   floating tolerance or outcome-based tie adjustment.

Balanced accuracy is a class-equal **development convention**, not an
invented safety-cost ratio, deployment prevalence estimate or acceptable
error rate. It provides no operational safety guarantee. With a shared
probability cutoff, A's positive decisions are necessarily a subset of B's:
removing the veto cannot worsen missed positives or reduce false positives
on the same records. The empirical question is whether recovered positive
decisions come with additional false positives. F4 results remain descriptive
paired counts and per-episode tables; no threshold/rule selection follows.

## Source checks and limits

CPU checks passed: `prospective_capture_v1.py --help`,
`run_prospective_collection_v2.py --help`, and deterministic construction of
legacy training-scene geometry for IDs 8 and 9. These do not start Isaac or
prove simulator-stage access. The detailed v1 proposed resource caps remain
unapproved ceilings and cannot be used until the camera-only adapter and
pose/scene schedule are supplied and separately frozen.

A bounded independent methods review accepted the score path with the
self-match/norm corrections above, accepted the shared-cutoff veto ablation
with per-episode balanced accuracy as a development convention, and
confirmed the capture-path blocker and descriptive-only F4 scope. Reviewer
runtime identity and reasoning setting were not independently verified.

**Decision:** stop before collection. The next concrete dependency is the
camera-only training-scene adapter and frozen pose/lighting schedule—not
another proposal, encoder run, fitting step or simulator attempt. The 190 s
acquisition cap and other resource ceilings remain proposals.
