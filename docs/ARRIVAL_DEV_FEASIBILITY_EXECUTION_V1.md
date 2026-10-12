# Small DEV arrival feasibility execution proposal v1

**DRAFT_NOT_FROZEN. PREPARATION_ONLY. Runtime NOT RUN.** Software preparation
baseline is `9108bbaa2b0be318113f2fbf02164abb87b2fa63` on
`agent/research-three-model-plan`. The [scientific review](ARRIVAL_FEASIBILITY_REVIEW_V1.md)
and [versioned config](../configs/eval/arrival_dev_feasibility_design_v1.json)
propose a bounded development study; the [validator](../scripts/arrival_dev_feasibility_contracts_v1.py)
only checks design restrictions and arithmetic. No method, comparator,
simulator, scoring or training runtime is implemented by this proposal.
The larger 80-layout/2,000-hour proposal remains UNFROZEN and NOT AUTHORIZED.

## Fixed comparison and data boundary

Nominate the closed-pilot NoMaD native adapted EMA checkpoint family with all
three existing seeds 0/11/22. This fixes a family, not a best architecture or
best-seed claim. Exact checkpoint/source digests remain null and BLOCKED until
a separately reviewed identity contract binds each role. Preserve all prior
pilot outcomes; they are not new feasibility observations or fitting labels.

Three mandatory arms share navigator, reference RGB, goal, low-level IMU
controller, motion limits, contact observation, four-Hz cadence and inference
budget: PlaceNav STOP adapter, ULVN STOP adapter and full candidate. These are
adapted comparator interfaces, not claims of official full-system reproduction.
PlaceNav retains VPR, Bayesian filtering and native MAP-equals-goal diagnostic;
ULVN requires graph-belief/entropy-fusion component parity, with a separately
specified terminal STOP extraction. Changing their navigator or STOP interface
must be documented and qualified. Neither unavailable comparator is quietly
replaced with a weaker one. Matcher, graph, thresholds, calibrator and controller
identities remain unbound. No contribution method is implemented here.

Fitting uses only admitted positive and negative labels from TRAIN or separate
DEV_FIT, disjoint from the six feasibility layouts, future TEST and prior pilot
outcomes. All fitting/selection consumes the six-hour allocation below. No
per-task, per-seed or outcome-based refit is allowed. Freeze trial IDs, labels,
assignments, thresholds and source identities before the first matched block.
Ground truth supplies admitted offline labels, initialization and evaluation;
it cannot choose live nodes, terminate a policy or enter as raw pose input.

## Slots and progression

Six new DEV layouts have two fixed reference routes each: one with naturally
repeated visual structure, one ordinary. Two fixed starts per route give four
feasible tasks/layout. There is no induced photometric or cadence intervention
and no alias-level crossing in this small study. Twelve prior reference chains
are shared across all arms/starts; report acquisition cost separately. Layouts
must be disjoint from TRAIN, calibration, accessed pilot and future TEST.
No independent test geometry is generated or inspected by this preparation.

Two mismatched/absent-goal control slots per layout are separate passive RGB
admission controls. A missing or unrepresentable map goal cannot be forced to
an existing map index. Such a slot is **NOT_RUN_UNSUPPORTED_GOAL_INTERFACE**,
with admission false acceptance/status reported separately. It produces no
fictional closed-loop outcome, wrong-location distance or achievable-goal
completion. All 108 controls are passive admission slots, never navigation episodes.
Unsupported-goal efficacy is NOT ADJUDICABLE. Retain all slot statuses without
pretending there are 324 closed-loop outcomes; W/C/Tstar apply only to the
216 prespecified feasible navigation attempts.

Six layouts × four feasible tasks × three arms × three seeds gives **216
feasible episode slots**; two controls/layout give at most **108 separate
control slots**, totaling **324 maximum slots**. Retain failures/refusals and
missingness, without replacement or best-seed selection. Actual layout/route/start IDs remain unbound and BLOCKED. The first matched
block is one prospectively predeclared DEV layout/task × three arms × three seeds: **nine
slots INCLUDED in 324**. Progression checks integrity/fidelity/motion/contact
and endpoint observability, never favorable outcomes. It is not an automatic
launch or favorable-result stopping rule. A failed integrity gate halts the
proposal; no repeat, adjustment or additional slot is implied.

## Finite clocks and resources

Policy observations/reference scheduling are four Hz in simulation time.
The decision horizon is 120 simulation seconds, with two additional simulation
seconds for post-STOP observation; no additional policy decisions occur in the
reserve. Wall-clock inference latency and 600-second per-process timeout are
separate. All durations and failure exposure must be recorded with their
actual clock, not converted silently.

| Proposed allocation | Ceiling |
| --- | ---: |
| Up to 216 navigation episodes × 122 simulation seconds | 7.32 simulated hours |
| Up to 324 slot processes × 600 wall seconds | 54 reserved wall/GPU hours |
| Twelve reference processes × 600 wall seconds | 2 reserved wall/GPU hours |
| Twelve comparator/measurement replay processes × 600 wall seconds | 2 reserved wall/GPU hours |
| All calibrator fitting and selection | 6 wall/GPU hours |
| Analysis | 2 wall/GPU hours |
| Known reserved total | 66 wall/GPU hours |
| Hard ceiling including unassigned headroom | 72 wall/GPU hours |
| External storage | 50 GiB |

The six hours of headroom never creates extra trials, retries or slots.
Conservative accounting reserves one GPU for each full process wall duration;
report measured utilization and peak memory separately. Actual wall throughput,
GPU memory and storage are UNKNOWN. Reaching a hard cap refuses further work;
no automatic budget expansion follows. No new foundation-model adaptation is
proposed. The twelve replay processes are comparator/instrumentation allocations,
not apparatus qualification. CAD/plant/controller/contact qualification is a
separate BLOCKED prerequisite, excluded from and unauthorized by this budget.

## Observations needed before a later decision

For every planned feasible attempt, record observable wrong-location STOP W,
collision-free legacy completion C, and restricted completion time Tstar.
W uses the frozen 0.5-m goal-image capture region; unavailable stop location is
UNKNOWN, never zero. Completion preserves the final-one-second motion below
.01 m and final-pose region semantics. Tstar is qualifying completion time by
120 seconds, otherwise 120 assigned to unsuccessful/refused/missing attempts,
not right-censoring. Missing mandatory endpoints prevent efficacy adjudication.
Secondary arrival delay is conditional on entry by 110 seconds, capped at ten
seconds with noncompletion/competing failure assigned ten; report entry fraction.

Contact observation must identify unintended robot/environment contact and
exclude only qualified wheel/floor support pairs, retaining raw events and the
filter identity. Missing contact observability blocks collision-free scoring.
All arms require clean-start physical/camera/history eligibility and a qualified
shared controller. The prior known-fixture camera qualification is insufficient.

Report paired layout means over all fixed tasks/seeds, baseline W/C/Tstar,
layout-level sample SD, separate stochastic/training-seed variation, per-process
wall time, reserved GPU time, peak memory and storage bytes. Six layouts give
no reliable attestation of an 80-layout joint-power assumption. Confidence/
variance uncertainty must be explicit; outcomes remain descriptive. They can
inform a subsequent human decision, never automatically authorize confirmatory
sampling or resources. Every empirical entry is currently UNKNOWN/NOT RUN.

## Preparation validation and commit boundary

```sh
env PYTHONPATH=/home/favl/projects/navfm-research-planning/src /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/arrival_dev_feasibility_contracts_v1.py
env PYTHONPATH=/home/favl/projects/navfm-research-planning/src /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python -m pytest -q tests/test_arrival_dev_feasibility_contracts_v1.py
```

Twelve focused controls PASS: finite slot/budget arithmetic, separate unsupported
controls, first-block inclusion, no runtime grant/fallback/reselection/test
access/outcome tuning/perturbation, cap overrun/nonfinite values and on-disk draft
binding. These prove design-software restrictions, not empirical feasibility,
comparator fidelity, sample power or actual custodial independence.
The combined preparation/ownership check runs 55 controls (22 existing design,
12 new feasibility and 21 ownership), all PASS; targeted Ruff PASS. The test
manifest retains every prior 3,113 node and adds twelve unmarked hermetic nodes,
for 3,125; all ten population digests reconcile and individual resource sets,
required upstream pins and owners remain unchanged. The full software rerun
at the separate repair boundary has 29 disclosed prerequisite failures; it is
not repeated for these pure additive design checks and is not claimed green.

The commit boundary is additive design config/validator/tests, execution and
scientific notes, plus exact new test-population membership. All old node IDs,
markers, resource owners and historical evidence stay unchanged. Raw outputs,
images, weights, logs, checkpoints, private assignments and seed attestations
stay external. Root and scientific readback precede this preparation commit.
No runtime, test access, actuation or 80-layout resource approval is conveyed.
