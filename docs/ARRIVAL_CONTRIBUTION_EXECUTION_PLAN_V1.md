# Arrival contribution execution plan v1

**DRAFT_NOT_FROZEN; DESIGN_ONLY; experiments NOT RUN.** Branch
`agent/research-three-model-plan`, inspected baseline
`1416793c88f52fa2e5eefb26022fae38c00eca16`. This is a reviewable proposal,
not permission to train, collect, score, simulate or actuate a robot.
Scientific comparison and claim boundaries are in
[the contribution review](ARRIVAL_CONTRIBUTION_REVIEW_V1.md).

The machine-readable [draft](../configs/eval/arrival_contribution_design_v1.json)
is checked by [the design validator](../scripts/arrival_design_contracts_v1.py).
Its SHA-256 binding is a draft consistency check, not preregistration or a test
seal. Changing the draft requires joint review and updating that binding;
a frozen successor needs a new version and an independently reviewed source
commit. The validator has no model, controller, collection or simulator entry
point and cannot grant launch authorization.

## Protected state and evidence

Preserve existing experimental freezes, old arrival measures/splits, source
format modules, robot assets, checkpoints and all 768 valid pilot outcomes.
The pilot covers two accessed layouts/four routes/32 pairs, not independent
benchmark samples. Keep held-out geometry sealed, illumination paused, real
actuation unauthorized and CAD/plant/controller qualification unresolved.
No original gate is reclassified. The prior one-third-second capture cadence
versus four-Hz training remains a hypothesis/confound, not an established cause.

All future data, images, weights, dense outputs, logs, private seed identities,
attestations and checkpoints remain external. Repository changes contain only
reviewed design prose, config, validator and focused software controls.
Independent custody must be a different human with independent seed control
and an external attestation; a self-written seal does not qualify. No such
custodian is appointed here; test access remains BLOCKED.

## Milestones and boundaries

1. **Current design review:** challenge the scoped alias-aware arrival
   hypothesis against PlaceNav/ULVN-style RGB temporal-belief comparators;
   verify matched sensing, reference traversal cost and static/dwell controls.
   Accept or reject this proposed design without running experiments.
2. **Separate apparatus proposal:** qualify loaded CAD geometry, plant,
   low-level IMU controller and clean-start camera/history conditions. The
   existing known-camera fixture qualification is insufficient for navigation.
   This milestone remains BLOCKED and needs its own authorization.
3. **Separate development proposal:** disjoint TRAIN/development/calibration
   layouts, fixed matcher/calibrator/reference alignment and thresholds;
   release/adapted GNM/ViNT/NoMaD ladder; predeclared constrained champion
   selection and all seeds 0/11/22. Faithful mechanisms need implementation
   review; adapted STOP comparators must be named as adaptations. Test outcomes
   cannot tune a threshold, select a checkpoint or drop a seed.
4. **Feasibility and resource decision:** establish champion wrong-location
   rate, development completion/time eligibility and upper bounds on paired
   layout SD. A baseline below the five-point practical reduction floor makes
   the proposed effect infeasible; more layouts cannot repair that floor. The
   assumed ten-point reduction also requires a baseline rate at least .10.
   Both development eligibility checks remain UNKNOWN.
   Establish joint power and an exact analysis/CI implementation before freeze.
   If the budget or variance bound fails, revise before freezing; no automatic
   expansion or convenient smaller test is allowed.
5. **Independent test preparation:** appoint an independent human custodian;
   attest layout-disjoint TRAIN/development/calibration/test ownership and
   fix opaque test identities, factorial assignment and all seed inclusion.
   Unavailable custody means BLOCKED. Predeclare allocation, missingness,
   all-attempt denominators and matched reference acquisition. A hash alone
   proves bytes, not independence.
6. **Freeze and separately authorize:** reviewer accepts a new version with
   executable method, scoring and layout-level analysis contracts, complete
   resource budget and clean source identity. Run only after that authorization.
   No current script implements these future runtime milestones.

## Planning arithmetic and resource envelope

The three co-primary gates form an intersection-union claim: all must pass
one-sided alpha .025, with paired layout means. Wrong-location STOP reduction
requires the upper confidence bound below -.05; collision-free completion
requires the lower bound above -.05; restricted completion-time increase
requires the upper bound below +5 seconds. Secondary ablation/comparator rows
remain descriptive. This protects the joint type-I error; it does not imply
80% joint power.

The calculator uses `ceil(((z_.975 + z_.80) * SD / gap)^2)` for a marginal
paired-layout normal approximation. Assumed alternatives are -.10 wrong-stop
risk difference, zero completion difference and zero time difference, giving
.05/.05/5-second gaps. These are proposals, not pilot effect estimates.

| Assumed binary SD / time SD | Layouts for each marginal gate |
| --- | ---: |
| .10 / 10 seconds | 32 |
| .15 / 15 seconds | 71 |
| .20 / 20 seconds | 126 |

Proposed planning uncertainty targets are 95% risk-difference CI half-width
at most .035 and time-difference half-width at most 3.5 seconds. With central
SD .15 / 15 seconds and 80 layouts, the normal approximation gives .03287 /
3.28696 seconds; these are conditional calculations, not guaranteed observed
interval widths. Student-t intervals and joint operating characteristics need
qualification before freeze.

Eighty independent layouts is conditional: development upper SD bounds must
support at most .15962876753 for binary paired differences and 15.96287675308
seconds for time differences. Baseline wrong-stop rate and actual SD are
UNKNOWN. The approximation ignores small-sample/tail and variance-estimation
uncertainty; empirical or conservative joint planning must be resolved before
freeze. Frames, routes, seeds and diffusion draws do not increase the number
of independent layouts.

Per layout, eight feasible cases are fixed as two base start-goals × two alias
levels × two illumination levels. Two goal-mismatch controls are analyzed
separately because they lack an achievable requested goal. Three seeds are
averaged within layout; additional diffusion replicas are zero. Four test arms
(champion, full, minus alias margin, minus ordered history with matched dwell)
yield **9,600 episodes**, including controls. The primary pair alone yields
**4,800 episodes**. At 120 decision seconds plus two seconds of post-stop
observation reserve, ceilings are **325.33** and **162.67 simulated hours**.
These are maximum simulated-duration allocations, not measured wall time or
GPU hours. Separate proposed ceilings below account for preparation and
training; actual throughput and rendering overhead remain unmeasured.
The proposal allocates finite ceilings, all **PROPOSED_NOT_AUTHORIZED**:

| Stage | Episode-equivalent cap | Wall/GPU-hour ceiling at 600 seconds each |
| --- | ---: | ---: |
| Apparatus qualification | 40 | 6.67 |
| Prior RGB reference acquisition | 200 | 33.33 |
| Development and calibration including comparator selection | 1,600 | 266.67 |
| Primary test pair, alternative to full test | 4,800 | 800 |
| Full four-arm test including primary pair | 9,600 | 1,600 |
| Training, separately allocated | not an episode allocation | 72 wall/GPU hours |

With preparation plus the full test, the maximum reserved one-GPU process time
is 1,978.67 wall hours and 1,978.67 GPU hours including serialized training. Proposed hard
ceilings are **2,000 wall hours, 2,000 GPU hours and 500 GiB external storage**.
The primary and full-test rows are alternatives, not additive. The 600-second
per-process wall cap is an assumption independent of the 122-second simulation
budget; a stalled process consumes its wall allocation and counts as failure.
This conservative GPU accounting reserves one GPU for the whole process, even
when idle; actual GPU utilization is measured separately. Qualification and
reference counts are provisional resource allocations, not a specified or
executed qualification protocol. They must be justified before freeze.

Measured throughput, peak GPU memory, storage and actual monetary cost are
UNKNOWN and block resource approval. These substantial ceilings do not imply
affordability or feasibility. Any prospective overrun refuses further work;
expansion requires a new reviewed resource decision.

Scoring preserves the 0.5-m goal-image capture region and legacy final-one-second
settling threshold below .01 m. Wrong-location STOP is distinct from legacy
aggregate wrong_stop, which also includes settling failures. Completion keeps
collision-free correct-stop semantics. Restricted completion time assigns 120
seconds to unsuccessful/refused/missing attempts, rather than treating them as
right-censored or analyzing successful episodes only. A technical failure with
unobservable STOP location has an UNKNOWN wrong-location endpoint, never a
filled zero. Retain every attempt without replacement; missing mandatory
endpoints block efficacy adjudication. Worst-case bounds may be reported
separately but cannot silently impute success.

Secondary diagnostic arrival delay is conditional on first goal-region entry
by 110 simulation seconds: cap subsequent qualified-stop delay at ten seconds;
no qualifying stop or a competing failure assigns ten seconds. Report entry
fraction beside this conditional metric. It is descriptive and cannot replace
the all-attempt restricted completion-time co-primary endpoint. Ground truth initializes
and evaluates; it cannot trigger policy STOP, choose live nodes or correct
navigation. Ground truth may supply admitted offline training labels; it
never enters the verifier as raw pose or live policy feedback. Any oracle row
is evaluation-only. The two-second reserve is
outside the policy horizon and cannot provide further policy decisions.
Decision horizon, reserve, dwell, delay and four-Hz observation scheduling use
simulation time. Per-process timeout and inference latency use wall time and
are reported separately. Neither clock is substituted for the other.

Contact scoring requires observable unintended robot/environment contacts,
excluding the specifically qualified support wheel/floor pairs. Retain raw
events, timestamps and the exact filtering identity. Existing fixture-only
contact filters do not automatically qualify a new scene. Contact
observability is BLOCKED; collision-free completion cannot be accepted until
that sensor/filter contract is demonstrated.

## Routine validation and commit boundary

From the repository, use the established external development environment:

```sh
env -u PYTHONPATH /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/arrival_design_contracts_v1.py
env -u PYTHONPATH /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python -m pytest -q tests/test_arrival_design_contracts_v1.py
/home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/ruff check scripts/arrival_design_contracts_v1.py tests/test_arrival_design_contracts_v1.py
```

Focused controls exercise absent subject, draft drift, self-seal substitution,
unqualified motion, illumination authorization drift, test tuning, best-seed
selection, successful-only denominators, frame independence, cadence changes,
invalid planning numbers, variance sensitivity and budget arithmetic. These
prove draft software refusal/consistency, not scientific validity, actual
custodian independence or physical apparatus readiness.

Before a commit, run the required repository `make verify` in its declared
software environment, report actual failures without weakening them, inspect
only intended tracked/staged files for attribution/private artifacts, and
review the exact diff. The commit boundary is this design-only additive
proposal; no source format module, old freeze or runtime artifact changes.
Root review precedes any commit; publication remains a separate decision.

## Preparation validation result

The final 22 focused design controls PASS, as does targeted Ruff. Separate
semantic controls exercise draft custody/authorization/sensing/denominator
refusals before byte-binding comparison; on-disk drift and boolean/numeric
schema confusion are separate controls. This is software consistency only.
The population manifest explicitly adds these 22 unmarked, ordinary-hermetic
nodes to the existing 3,091, giving 3,113. Every old node/resource marker,
upstream required pin and resource owner remains unchanged; total/hermetic
digests are recomputed. The pre-existing aggregate resource-union pin was
140, while the unchanged baseline node/marker map already derives 205. Its
count/digest are mechanically corrected to 205; the added 22 hermetic nodes do
not affect that union. All ten derived digests now reconcile, and every
individual resource set, required upstream pin and owner remains unchanged.
Twenty-one focused ownership/schema controls PASS. Collection-only inspection
has 3,061 nodes, zero collection errors and zero unexpected nodes; 52
Torch/upstream-dependent nodes cannot collect in this environment. Shared
resource-marker assignments match exactly. This collection inspection is not
an executed full population or owner proof.

The required full software command actually run was:

```sh
env -u PYTHONPATH PATH=/home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin:$PATH make verify
```

Ruff PASS; mypy PASS across 89 source files; full pytest **47 failures**.
`NAVFM_UPSTREAM` was not supplied by this command and is unset in the checked
shell. This was a no-Torch development environment, not an admitted upstream
or resource-owner proof. Failures classify as:

| Count | Actual failure category |
| --- | --- |
| 14 | `test_arm_lifecycle.py`: `execute_arm()` rejects the test's `environment_capture` keyword; an applicable source/API contract mismatch |
| 2 | `test_check_test_population.py`: existing upstream expectation is 42/old digest while the unchanged upstream manifest is 44/current digest; a software pin mismatch |
| 4 | Missing immutable V1 archive / three required historical capture files |
| 1 | Missing required alternate interpreter resource |
| 26 | Missing Torch, diffusers, transformers, matplotlib or patched upstream; includes prerequisite-masked negative controls and the compatibility fixture's failed project-validator check |

These are actual failed checks, not a green suite or a blanket environmental
excuse. The newly added test file has no failures. No baseline full-suite rerun
was performed, so this audit does not claim a measured before/after proof for
all 47. Existing source/API and upstream-pin discrepancies remain unresolved;
no unrelated implementation, historical evidence or gate was changed. The
initial focused invocation also failed during inherited ROS plugin import
(`lark` absent); clearing `PYTHONPATH` then produced the focused PASS above.
External verification logs/reports remain outside the repository. No simulator,
training, collection, benchmark scoring or real robot actuation was executed.
