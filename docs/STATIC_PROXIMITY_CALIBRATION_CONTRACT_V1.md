# Static proximity calibration contract v1

**Status: PREPARATION ONLY; calibration execution is blocked.** This contract
fixes a geometric prediction target and a candidate feature/comparator design.
It does not authorize image decoding, encoder inference, fitting, threshold
selection, collection, simulator work, or navigation. The machine-readable
binding is [`static_proximity_calibration_contract_v1.json`](../configs/eval/static_proximity_calibration_contract_v1.json).

## Research question and target

The bounded question is whether a frozen RGB/reference similarity signal can
estimate whether the robot is geometrically within the requested goal image's
capture region. For one query pose `q` and requested goal capture pose `g`, the
label is `1[||q_xy - g_xy||_2 <= 0.5 m]`. The inclusive 0.5 m radius comes from
the already frozen [`arrival_measures_v1`](../configs/eval/arrival_measures_v1.json)
definition; it was not selected from the geometry audit's quantiles. Distance
labels may be derived only within an authenticated trajectory coordinate frame.

This target means **geometric proximity**. It does not mean successful
arrival, a correct STOP, settled motion, collision-free completion, or that it
is safe to stop. Those endpoints require timed post-STOP motion and contact
evidence, which the admitted training records do not contain. In particular,
the existing 1 s settling and 0.01 m motion rules remain separate task
outcomes; they are not substituted into this static label.

## Bound inputs and what they establish

This preparation is based on the geometry audit at `29e6a0945471aced61f0eb63adf125694ed4f59a`.
Its bound training admission SHA-256 is
`e7938615e2f9fc40f7f5f664b834c7c92127dc78005a129f850ddcef52e487f3`; its
dataset-content digest is
`7e2b3738c3026e9e170d1a635d3172e92767428ec577bdb85a9b64501f02cbc3`. The
frozen split file digest is
`f09cb892a6ade892a0fc67943c91a41dbbf3a4c2aea98d33aeda67a3e9458fef`; the
measure-definition digest is
`082e34b10f8af411cb65bb5d72172c13d17f9430e7309c54c280f1bdfa11258e`.

The audit reports 31 training trajectories, eight scene groups, 1,255 indexed
frames and 50,632 ordered distinct within-trajectory pairs. Median distance is
0.5476 m and the 10th percentile is 0.1015 m. This confirms continuous
geometric coverage in those records, not calibration adequacy. Pairs share
frames and trajectories; reversed pairs repeat the same distance. **50,632 is
an output-row count, never an independent sample size or a power basis.** The
audit read pose metadata only and did not inspect images or descriptors.

The schema inventory confirms per-frame `position` in metres and `yaw` in
radians, aligned to indexed image filenames, but no recorded timestamps,
arrival outcomes, settling, contact, or STOP labels. Each trajectory has its
own coordinate frame; cross-trajectory distance labels are inadmissible absent
authenticated alignment. Existing development and retired-test groups are
exposed and partially appearance-overlap the training scenes. The six
specified future held-out layouts remain uncollected and forbidden for
calibration. The accessed pilot is excluded.

## Proposed static score and sampling contract

The candidate already implemented in
[`alias_aware_arrival.py`](../src/navfm/collection/alias_aware_arrival.py)
accepts four time-ordered query-history rows against an ordered reference
chain. For candidate reference node `j`, it computes
`S(j) = mean(k=0..3, sim[k][max(0,j-k)])`. Candidate calibration inputs are
the requested terminal's `S(j)` and the difference between that score and the
largest score before an explicit terminal-reference window. That window,
encoder, checkpoint, preprocessing, similarity scale, and invalid-score
policy are currently unspecified. The existing fixed RAVEL graph run used
SuperPoint/LightGlue for local matching and zero global-place-encoder forwards;
its two retrieved weight files are marked `RETRIEVED_UNCERTIFIED_HASH`. The
native PlaceNav/ULVN qualifications do not establish a general pairwise
similarity probability contract. Therefore no current encoder is admitted.

If prerequisites are later met, deployment-faithful samples must use live
query frames against a separately acquired prior reference traversal and an
explicit requested terminal, with query/reference pose alignment authenticated
for the geometric labels. Keep query and reference identities, source hashes,
reference order and acquisition provenance in every row. Exclude exact
`(trajectory_id, frame_index)` self-pairs and byte-identical query/reference
images. Report near-duplicate views; do not exclude them merely because their
poses are close, since they can be valid positives. No time-based exclusion
can be set from the current training records because their timestamps are
absent. The existing same-traversal geometry records cannot stand in for this
independent query/reference relationship.

A nonterminal reference may also lie within 0.5 m of the requested terminal,
so its high score can coexist with a positive target. The alias margin is only
a candidate predictor; a nonterminal score is not a negative label. Compare
the two-feature map against terminal-score-only logistic calibration under
identical groups and weights. Also report the constant group-prevalence
baseline. Do not claim alias-hard coverage unless independent visual evidence
later establishes such examples.

## Grouping, measures, and present execution decision

Any eventual partition must group by layout and keep a complete source
trajectory, its frames, references, exact/duplicate acquisitions, and
reversed pairs together. Use distinct permitted layout groups for fit,
operating-threshold selection, and assessment. Episode-balanced fitting gives
each episode equal total influence; it does not make episodes independent or
remove shared-layout dependence. The existing 31 trajectories are not split
here: the adapted feature extractors have already seen those training records;
existing development/retired-test data are exposed with documented appearance
overlap; future held-out groups are forbidden; and the dataset has no
deployment-matched separate reference traversal. Eight scene groups do not,
by themselves, justify an allocation or adequate support.

For a future admissible probability assessment, report Brier score, log loss,
calibration intercept/slope, AUROC and average precision, with uncertainty
calculated at the layout grouping level and per-layout results retained. At a
separately justified operating point, report false proximity declarations and
missed geometric proximity separately. No operating point is selected here:
the false-stop/missed-arrival trade-off and qualified motion policy are not
available. Do not turn a probability threshold into a STOP rule in this
contract.

The current finite budget is exactly **zero** feature extraction, zero model
inference, zero fitting, zero threshold-search trials, zero collection,
zero navigation, and zero GPU-hours. The geometry audit's 50,632 rows are a
historical result and will not be regenerated. A future extraction/fitting
cap cannot be justified until eligible groups, authenticated encoder and
checkpoint, reference-bank construction, threshold objective, and visual
negative coverage are specified. The JSON leaves those future caps null to
prevent an invented budget from being mistaken for approval.

### Execution gates

1. Authenticate a deployment-faithful ordered query/reference acquisition and
   coordinate-alignment contract.
2. Select and authenticate encoder source, checkpoint, preprocessing, output
   similarity semantics, and invalid-score handling.
3. Fix reference sampling, exact self-match exclusion, and terminal-window
   semantics before viewing scores.
4. Identify permitted layout-disjoint fit, threshold-selection, and assessment
   groups before feature extraction; do not split by frame or pair.
5. Define the operating objective without renaming proximity as successful
   arrival or safe STOP.
6. Establish visual evidence for any alias-hard stratum independently of model
   predictions.
7. Set a measured finite resource cap and obtain a separate execution
   decision.

Failure at any gate means stop without fitting and report the specific gap.
This static question remains separate from the temporal dwell latch, actual
arrival/STOP outcomes, qualified motion/contact measurement, and independent
navigation evaluation.

## Bounded critical review

One bounded review was requested from **Astra at ultra reasoning** for this
contract. Requested model/settings are recorded; runtime model identity and
reasoning configuration could not be independently verified. The review
recommended keeping the contract preparation-only and identified these
challenges, which are reflected above:

- A nonterminal pose can be inside the terminal's positive radius, so margin
  is a candidate feature to test against terminal-only score, not label logic.
- Ordered pairs, reversed pairs, frames, and trajectories are dependent; pair
  count cannot support sample-size or independence claims.
- Route IDs alone do not establish scene independence, and downstream scene
  splitting cannot undo the adapted encoder's prior exposure.
- A new split of current data cannot support unseen-layout generalization;
  new permitted groups and a deployment-matched query/reference relation are
  needed.
- Fixed RAVEL graph connectivity does not establish global pair-score quality;
  the retrieved weight hashes remain uncertified.

This critique is advisory, not evidence of calibration quality or human
approval. No changes to the target, metric freeze, exclusions, or prior audit
result were made. The `rio-research` skill materially informed the evidence
labels, falsification boundaries, and distinction between proposed design and
measured result; skill-retrieval search tools were unavailable.

## Result and next decision

**EXPERIMENTAL RESULTS: NOT YET AVAILABLE.** No images, features, model
checkpoints, data rows, or outcomes were read or generated for this contract;
no fitting or runtime validation occurred. The contract fixes the geometric
target and candidate comparisons but remains blocked on data provenance and
group eligibility. The next decision is whether to obtain a permitted,
deployment-matched calibration population and authenticated encoder contract.
Temporal dwell and the wrong-location STOP hypothesis still require measured
timing, qualified motion, and closed-loop evidence.
