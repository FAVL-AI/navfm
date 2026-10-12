# Alias-aware decision-rule comparison v1

**Decision:** retain both decision rules as detached candidates. The existing
hard alias-margin veto remains the legacy behavior. A probability-only variant
is now explicit for controlled development comparison. Neither is selected as
empirically superior, and the synthetic coefficients below are not calibrated
probabilities. The goal-region feature remains a separate annotated-map
variant; the current deployment path is closed as documented in
[`GOAL_REGION_REFERENCE_POSE_AVAILABILITY_V1.md`](GOAL_REGION_REFERENCE_POSE_AVAILABILITY_V1.md).

## Compared rules

Both variants use the same camera-derived terminal score and alias margin, the
same externally supplied probability threshold and identical dwell-clock,
maximum-observation-gap, and reset mechanics. Cancellation occurs when a
sample is ineligible under the selected rule:

- **A — hard veto:** probability must meet its threshold and alias margin must
  meet its explicit floor before dwell can accrue.
- **B — probability only:** probability must meet its threshold; the margin is
  still computed but does not veto dwell eligibility.

The implementation exposes the choice as a required boolean in
`ArrivalDecisionConfig`. Both options remain detached from navigation and
simulator launchers.

## Synthetic decision-code checks

CPU-only tests pass synthetic four-frame similarity matrices through the
production ordered-feature, probability-map, and dwell-state code. The fixed
logistic coefficients isolate the gate behavior and are not fit from data.

For the near-goal counterexample, the strongest nonterminal score is `0.9`, the
terminal score is `0.6`, and the margin is `-0.3`. With the same illustrative
probability above `0.8`, rule A remains ineligible under a `0.2` margin floor;
rule B accrues dwell and latches after the same one-second dwell. This
demonstrates that removing the hard veto resolves that structural rejection
for this fixture.

For a synthetic distant terminal lookalike, terminal score `0.95` exceeds the
strongest earlier score `0.65`, yielding a positive `0.3` margin and a
probability above threshold. Both rules accrue dwell and latch. This is a
counterexample to treating B as a complete ambiguity solution.

When the same camera feature sequence is paired synthetically with different
geometric labels, both rules produce identical decisions for each label. A
deterministic camera-only rule cannot recover a label absent from its inputs.
The checks also verify that changing the veto policy does not alter latch
reset or restart-of-dwell behavior.

These fixtures show decision mechanics only. They do not establish visual
discrimination, real calibration, fewer wrong stops, preserved completion,
bounded task time, physical STOP, or navigation performance.

## Evidence needed to test the trade-off

Testing requires deployment-matched RGB history/reference inputs and
independently acquired geometric near-goal and wrong-location labels, with
timestamps and episode/layout identities. Calibration, threshold selection,
and assessment groups must be separated without using the excluded accessed
pilot for fitting. A later closed-loop comparison also requires qualified
motion, observable contact outcomes, matched completion and stopping-delay
endpoints, and a frozen evaluation population. Until then, neither rule's
calibration quality nor the research hypothesis is established.

No real data, evaluator poses, images, encoders, fitting, collection,
simulation, navigation, or launcher integration were used in this change.
