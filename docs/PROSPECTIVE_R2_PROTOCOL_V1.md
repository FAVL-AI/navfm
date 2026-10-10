# Prospective R2 recovery, version 1

Status: FROZEN 2026-10-10 after independent bounded protocol and executable
review. No new collection has run. Metadata-only comparison across101 prior kidnap/smoke
attempt manifests found only prior tuples (0,0,0), (0.35,0.2,20),
(0.35,0.2,90), (0.5,0,180), (0.65,-0.2,-20). All proposed numeric
tuples differ; no images or model outcomes of proposed starts were inspected.

Owner: Frank Asante Van Laarhoven <frankleroyvan@gmail.com>.

## Question and evidence boundary

Does the existing R2 recovery bundle recover the exact pose-true node more often
than B1x under new, declared kidnapped starts on development layouts, without
more wrong first confident declarations in the shared36-decision horizon? The bundle includes scanning, bounded scan
budget and lost-entry limit, non-arrival relocalisation and terminal abstention.
This does not isolate scanning. Stage 2 was exploratory and tolerance-dependent;
stage 3 had no scorable recovery entry. Its RETAIN decision only guarded wrong
stops and contact incidence. Shorter exposure does not establish safer driving.

Hypothesis: R2 improves exact-at-declaration first-entry recovery with ten preterminal no-reentry decisions relative to B1x.
A tie, worse exact-node recovery, or increased wrong first confident declaration in the common horizon
contradicts this hypothesis on these starts. Thresholds and policy code stay fixed.
No claim about held-out layouts, illumination, transfer, novelty or significance.

## Fixed selection and sample

`configs/eval/prospective_r2_recovery_v1.json` declares all starts before outcomes.
Four already inspected development routes are crossed with four new numeric
perturbations: (arc fraction, lateral metres, heading offset degrees):
(0.23, 0.10, 45), (0.43, -0.10, -45), (0.57, 0.10, 135),
(0.77, -0.10, -135). There are 16 paired starts and 32 initial arm attempts.
No image inspection, geometric feasibility preview or model scoring of these
new poses is permitted before freeze. The two rear-facing heading offsets define
the hard subgroup (8 pairs) in advance; actual image informativeness is unknown.
This is a small fixed development sample, not a powered generalisation study.
Every declared start counts even if infeasible; no outcome-based substitution.

## Matched intervention and information boundary

Only R2_recover and B1x_exit run, using identical existing checkpoint, true chain,
goal images, radius 4, close threshold 3, maximum speed 0.1 m/s, 2 Hz decisions,
yaw-feedback controller and 600-frame budget. Both start with node 0, lost=true,
reset counters and six copies of the live initial image. No previous-run image
or state enters either history. R2 uses exit 5.880692958831787, two consistent
matches, 36 scan decisions, two lost entries and scan rate 0.4 rad/s; B1x uses
the same exit threshold and its unchanged moving global-argmin lost behaviour.
Physical starts are paired nominally. Predecision initial pose must lie within
0.02 m and 2 degrees of the declared teleport, and paired arms must differ by at
most 0.02 m, 2 degrees and 2.5 mean absolute grayscale levels in the initial image.
These conservative instrumentation bounds reuse existing fidelity thresholds;
they are unvalidated on these new starts. Exceedance invalidates the experiment
without deleting or substituting the pair. Both arms record initialized hidden
counters (zero, with R2 attempts=1 for the forced entry), six identical live-image
digests and all eight settling-step contacts. Settling is outside the primary
contact window but is disclosed, including infeasible start evidence.
simulation is not bit-deterministic. Ground truth sets the declared teleport and
scores poses only; it never selects a node or command for the deployed policy.

## Recovery measures and exhaustive outcomes

The experimental unit is the first forced lost entry at initialisation, including
an exit on decision 0. The first 36 policy decisions (indices 0 through 35) define
a common first-entry relocalisation horizon. A confident declaration is the first
lost-to-tracking state transition, independent of eventual arrival. Score the
selected closest_node against the nearest chain node to the pre-decision robot
position; Euclidean XY distance, lowest node index breaks ties. Exact node is the
primary measure. Absolute node difference <=1 is secondary, never a replacement
for exact-node scoring. Each must remain out of lost for ten subsequent preterminal policy
decisions. Post-stop or post-abstention filler records never count. The terminal
decision can declare a wrong first exit, but cannot provide tracking follow-up.
This means exact at declaration plus no re-entry, not continued exact localisation;
pose-node correctness during follow-up is separately reported. Ten observed decisions are required: late relocalisation, early task
end, or incomplete recording censors durability and counts as primary failure.
Report censored cases separately; never silently credit missing follow-up.

Each initial arm attempt has one primary outcome:

- correct_confident: exact-node first relocalisation within the common horizon,
  with all ten follow-up decisions observed and no lost re-entry;
- wrong_confident: first relocalisation within the horizon to any non-exact node,
  even if it later corrects or falls within +/-1;
- abstention: no first-entry relocalisation within the horizon and a declared
  non-arrival recovery_failed halt;
- failure: timeout without qualifying relocalisation, correct but unstable or
  censored recovery, invalid/missing evidence, crash or infrastructure failure.

Report tolerance outcomes in parallel with the same horizon and durability.
Report first-entry exit latency, node error, re-entry, follow-up censorship,
late first exits and all preterminal confident transitions (including wrong ones),
all later lost entries, correct/wrong arrival stops, non-arrival halts and timeouts.
A valid model failure or abstention is a valid experimental observation.

Pre-declared decision: SUPPORT on this sample only if R2 has >=12/16 primary
correct_confident outcomes, strictly more than B1x, >=6/8 in the hard subgroup
and strictly more there than B1x, with total primary wrong_confident within the common first horizon <= B1x.
This guard is limited to first declarations in the common horizon; later wrong
confident declarations are descriptive and cannot be presented as guarded.
These are operational thresholds, not statistical significance thresholds.
Contact incidence must not increase, raw or per metre, for a guarded retention
recommendation; exposure differences constrain interpretation. Integrity failure
means INCONCLUSIVE rather than SUPPORT. Otherwise the hypothesis is NOT SUPPORTED.

## Contacts and exposure

Report episodes with any contact, distinct from number of contact records, through
the first declared terminal frame plus24 capture frames, capped at the recorded
end, or through the full recording on timeout. The existing collector can record
a longer tail for early stops because its minimum duration is108 frames; extra
tail contacts and exposure are disclosed separately. Also report
path metres, simulated exposure seconds (including the first commanded interval), contact-bearing episodes per metre and
per second (undefined if denominator zero and contacts nonzero), translating
seconds and absolute heading rotation. Scans may creep; motion is measured from
recorded poses. Report paired start position/yaw differences and each arm's actual
initial-state/history provenance. Frozen imported scoring files must match their
committed bytes before scoring. Lower contacts with shorter exposure alone
cannot support a safety improvement claim.

## Attempts, retries and staged execution

Run prospective_r2_a first (four pairs), with R2 then B1x. Review only mechanical
integrity and evidence completeness to authorise the remaining fixed 12 pairs;
no success threshold, image informativeness or contact outcome controls expansion.
Remaining trials run b, c, d in declared order; arm order reverses on b and d.
No source or protocol changes while a collection runs. No large new batch is
justified beyond these fixed 32 initial arm attempts.

Each trial/arm collects its four routes. A route with collection status other than
PASS receives at most one infrastructure retry under the same committed protocol
and new output path; PASS refers to evidence validity, not navigation success.
Never retry a PASS episode for model performance, abstention, contact, timeout,
wrong node or an unfavourable start. Preserve every launch, crash, partial output
and retry. Initial attempts remain the primary denominator, with infrastructure
failures counted as failure. Retry outcomes are separately labelled sensitivity
analysis, never substitutes for the primary outcomes. Third attempts, retries
following PASS, undeclared starts or post-freeze drift invalidate the experiment.
If the first stage fails integrity, halt expansion and report the failure; any
instrument repair requires a new reviewed version and original attempts retained.

## Provenance and validation

Independent bounded protocol review must complete before freeze and execution.
Freeze config, this document, runner, scorer, imported scoring contracts, collector provenance instrumentation
and meaningful boundary/negative tests
in one named commit; launch only from a clean descendant with identical bytes.
The external launch ledger rejects all undeclared starts, extra routes, duplicate
launch identifiers and deviations from frozen initial cell order. Expansion
requires a uniquely recorded passing pilot gate before remaining launches.
The external launch ledger pins head, protocol and one shared robot digest, start/end UTC,
exit status and frozen route digest; runtime influencing source digests must match
the freeze. Qualification, checkpoint, chain and goal digests are verified by the
existing collector and scorer. All runtime evidence and logs stay outside git.
No push, held-out access, illumination experiment or real robot actuation.

Required checks: named-file formatting, ruff, mypy, focused protocol/scoring tests,
collector argument contract and scorer negative controls; full make verify with
NAVFM_UPSTREAM records the remaining environment-identity failures honestly.
Document all deviations and failed attempts. Interpretation needs independent
results review; the owner retains scientific judgement.

EXPERIMENTAL RESULTS: NOT YET AVAILABLE.
