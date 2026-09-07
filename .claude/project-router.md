# PROJECT ROUTER AND PRE-EXECUTION GATE

This instruction MUST be checked before EVERY project execution.

No repository-changing, experimental, analytical or deliverable-producing work
may begin until PROJECT_PREFLIGHT is complete.

The GLOBAL RESEARCH, TRUTH AND EXPERT STANDARD always applies.

## A. PROJECT_PREFLIGHT

Before acting, determine:

PROJECT:
TASK:
REQUESTED OUTPUT:
ACTIVE SUPERVISOR DELIVERABLE:
RELEVANT RESEARCH QUESTION:
TASK CLASS:
SOURCE OF TRUTH:
EXISTING EVIDENCE:
MISSING EVIDENCE:
SUCCESS CRITERIA:
FAILURE/STOP CONDITIONS:
SPECIALIST RULES TO LOAD:
PERMITTED NEXT ACTION:

Do not continue until these are resolved sufficiently for the task.

## B. ROUTE BY TASK TYPE

Select the relevant specialist instruction(s).

DATASET / DATA COLLECTION
→ dataset compatibility + provenance rules

GNM / ViNT / NoMaD
→ official-framework reproduction rules

METRICS / EVALUATION
→ metrics provenance + statistical evaluation rules

LITERATURE REVIEW
→ primary-paper systematic-review rules

NOVELTY / RESEARCH GAP
→ comparative-method + novelty-evidence rules

ISAAC SIM / PHYSICS
→ runtime evidence + scene-admission rules

ROBOT EXECUTION
→ hardware + ROS2 + safety + execution-evidence rules

SAFETY / HOCBF / QP
→ control/safety validation rules

SOFTWARE ENGINEERING
→ implementation + CI + testing rules

WEEKLY REPORT / SUPERVISOR COMMUNICATION
→ Bo/Rui reporting rules

A task may activate multiple routes.

Load only relevant specialist rules, but NEVER skip the global standard or
supervisor priority.

## C. CURRENT SUPERVISOR PRIORITY — PROF. BO WEI

Until explicitly superseded, the immediate research deliverable is:

1. review formats of existing datasets using real examples and references;

2. prove the NEW collected data are directly compatible with the published
   GNM / ViNT / NoMaD framework;

3. review the metrics used by existing papers and provide the correct paper
   source for each metric.

Do not let interesting downstream work replace these deliverables.

The current proof of compatibility must include actual execution:

  hospital trajectory
      ->
  published/compatible folder structure
      ->
  official loader
      ->
  valid sample/batch
      ->
  GNM/ViNT/NoMaD-compatible model input

"Looks like the format" is insufficient.

## D. DATA FORMAT TARGET

Primary compatibility target:

Official visualnav-transformer / GNM family processed format:

  <dataset>/<trajectory>/
      0.jpg
      1.jpg
      ...
      T.jpg
      traj_data.pkl

where:

  position = [T,2]
  yaw      = [T]

Use the official repository as source of truth.

Additional NavFM evidence/provenance MUST be a sidecar layer that does not break
the published loader-facing format.

## E-0. DOMAIN RULE — HOSPITAL IS A BRANCH, NOT THE ROOT

Hospital is the preferred application environment. It is **not** the root of the
dependency tree, and it must never become the single blocking dependency.

If Hospital cannot currently satisfy the fixed collection/admission contract, do
not fabricate compatibility and do not stay blocked. Evaluate candidates in
order and select the FIRST that passes the complete admission test:

    1. Hospital
    2. Office
    3. Warehouse
    4. another available Isaac environment meeting the same preregistered criteria

Selection is decided by the admission matrix, not by preference.

If Office or Warehouse is used, state exactly:

    "This closes the new-data framework compatibility and collection-pipeline
     proof. It does not substitute for the later Hospital-domain dataset."

**Never relabel Office or Warehouse data as Hospital data.** Bo asked for new
Hospital data; that request stays incomplete until Hospital data exists.

For the BO-03 engineering proof, Hospital-specific semantics are NOT required.
For the final Hospital-domain thesis experiment, they are.

### Long-horizon means structure, not wall-clock

Declare the threshold before collection: minimum duration, frame count,
travelled distance, meaningful heading/route changes, start-goal separation, and
enough temporal length for context-window sampling. Recording for a long time is
not a long-horizon trajectory.

### Camera contract

Compatibility does not require the camera to sit where the original GNM robots'
cameras sat. It requires a forward-facing robot-mounted RGB stream with a fixed,
declared, reproducible extrinsic, and a trajectory transformed into the exact
published loader format. Freeze camera identity, pose, field of view, resolution
and extrinsics in the provenance layer. Judge "forward-facing" geometrically,
never from the camera's name, and prove the check can fail (rotate 180 degrees,
detach from the robot, wrong prim -- each must be rejected).

### Goal image independence

The goal image must be sealed before motion and must not be the final
observation frame. That substitution is the H7/H7R defect.

## E. HOSPITAL DATA

Historical H7/H7R recordings are:

  DIAGNOSTIC / LEGACY

unless separately admitted.

Do not use them as training data merely because images/odometry exist.

New data must satisfy the current admission protocol before training.

## F. EVIDENCE-AND-PROVENANCE LAYER

Explain it simply when required:

The model only needs the loader-compatible trajectory.

The research additionally needs evidence proving:

  which robot
  which camera
  which scene
  which scene version
  which controller
  start condition
  goal identity
  collection time
  software/environment identity
  checksums
  admission status

This sidecar information exists for reproducibility and data admissibility.

It is not claimed to be a requirement of the original GNM/ViNT/NoMaD loader.

## G. METRIC SOURCE RULE

Never write a list of metrics without mapping every metric to its originating
or canonical paper.

Current examples:

  SR / NE:
    R2R/VLN evaluation literature

  SPL:
    Anderson et al.,
    "On Evaluation of Embodied Navigation Agents"

  CLS:
    Jain et al.,
    "Stay on the Path: Instruction Fidelity in Vision-and-Language Navigation"

  nDTW / SDTW:
    Ilharco et al.,
    "General Evaluation for Instruction Conditioned Navigation using Dynamic
    Time Warping"

Collision metrics:
  cite the exact experiment/paper whose definition is being reproduced.

Do not calculate path-reference metrics when their required reference path/oracle
is unavailable or unversioned.

Record them as BLOCKED.

Every citation above must be verified against the primary source before it goes
into supervisor-facing material. A reference supplied in conversation is a lead,
not a verification.

## H. CURRENT NOVELTY DISCIPLINE

Current possible research direction:

  learned visual-navigation backbone
      +
  explicit temporal stopping reliability
      +
  delay/uncertainty-aware runtime assurance

Comparison target includes SaferPath and other relevant safety-navigation work.

But this remains:

  NOVELTY HYPOTHESIS

until systematic literature review establishes the gap.

Do not allow novelty discussion to delay Bo's current dataset/metrics
deliverable.

## I. SUPERVISOR QUESTIONS LEDGER

Maintain explicit status in `gates/supervisor/BO_QUESTIONS_LEDGER.md` for:

BO-01 existing dataset formats + real examples + references
BO-02 our dataset format
BO-03 direct GNM/ViNT/NoMaD loader compatibility
BO-04 existing metrics + paper provenance
BO-05 explanation of evidence/provenance layer
BO-06 novelty comparison with SaferPath
BO-07 RQ1/RQ2/RQ3 status
BO-08 blocked path-reference metrics
BO-09 baseline reproduction status
BO-10 new Hospital collection status
BO-11 fine-tuning/comparison status

For each use:

  COMPLETE
  PARTIAL
  BLOCKED
  NOT STARTED
  AWAITING SUPERVISOR DECISION

Never call something COMPLETE because it has merely been discussed.

## J. SUPERVISOR COMMUNICATION RULES

Professor-facing material must:

  answer the exact question asked;
  use plain English;
  present evidence before interpretation;
  use complete searchable references;
  distinguish completed work from plans;
  avoid unexplained project jargon;
  avoid speculative branches unless requested.

For weekly updates:

  first-page plan must come from the previous agreed plan/revision;
  use the agreed template;
  preserve agreed structure;
  cite papers in a standard consistent format;
  do not replace agreed deliverables with new work.

RQ1/RQ2/RQ3 are NOT supervisor-approved. They are draft thesis direction
awaiting discussion, and must be described that way.

## K-0. PARALLEL TRACKS

These advance independently. Do not serialise them behind Hospital.

    TRACK A  official reproduction on published datasets/checkpoints -> BO-09
    TRACK B  new-data collection + official loader proof              -> BO-03, BO-10
    TRACK C  metric computability decision                           -> BO-08
    TRACK D  literature/SaferPath comparison                         -> BO-06
    TRACK E  fine-tuning, only after A and B                         -> BO-11

Tracks A, C and D require no scene admission and must not wait for it. If an
official asset is missing, return a precise asset blocker rather than leaving a
row at "not yet final".

## K. EXECUTION PRIORITY

When multiple valid tasks exist, choose in this order:

  supervisor-requested prerequisite
      >
  evidence needed to prove prerequisite
      >
  reproduction
      >
  data admission
      >
  baseline evaluation
      >
  literature-gap confirmation
      >
  new method
      >
  fine-tuning
      >
  extensions

Do not optimise for the most technically interesting task.

Optimise for the next evidence-backed research dependency.

## L. PRE-EXECUTION OUTPUT

Before substantial work, internally establish and, when useful, report:

  ROUTE:
  WHY THIS ROUTE:
  CURRENT REQUIREMENT:
  EVIDENCE NEEDED:
  NEXT SAFE ACTION:
  WHAT WILL NOT BE DONE:

Only then execute.

## M. EDIT SAFETY

Any edited Python file must pass, BEFORE any test or scientific execution:

  python -m py_compile <file>   (or ast.parse)
  focused lint / static checks

No scientific execution may start with syntactically invalid edited code.
A syntax failure is a development failure, never a scientific result.

## N. RELATIONSHIP TO THE STANDING-INSTRUCTIONS FILE

The repository-root standing instructions win wherever the two differ. They
carry the authorship rule, the gate discipline, the frozen pre-registration, the
honesty markers and the adversarial-review triggers. This router adds supervisor
sequencing and a pre-execution checkpoint; it relaxes nothing.
