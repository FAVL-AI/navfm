# NavFM

**Evidence-governed reproduction, data-contract validation, and simulator
admissibility for visual robot navigation.**

NavFM is a doctoral research repository studying whether published
visual-navigation systems can be reproduced faithfully, whether newly collected
robot trajectories preserve the data semantics those systems require, and whether
a simulator is physically trustworthy enough to support subsequent experiments.

It targets three published navigation models — **GNM** (General Navigation
Model), **ViNT** (Visual Navigation Transformer) and **NoMaD** (Goal-Masked
Diffusion Policies for Navigation and Exploration) — together with an Isaac Sim
digital twin of the Yahboom ROSMASTER M3 Pro.

The contribution is not a new navigation architecture. It is an evidence trail:
fixed data contracts, model-path reproduction, controlled evaluations,
simulator-admissibility tests, negative results, contradictions, failure
analyses, and explicit claim boundaries.

---

## Abstract

A visual-navigation experiment can complete successfully while changing what the
experiment means. A checkpoint may load without all parameters executing; a loss
may be finite while optimising the wrong objective; a scene may render correctly
while missing floor collision; a physics query may return a plausible hit while
interrogating the wrong object; and a non-empty sample may still be too small or
too biased to support a scene-level claim.

NavFM treats these as research problems rather than implementation details. The
programme establishes a reproducible path from published model release to
model-ready trajectory data and then to physics-valid simulation. The method is
**evidence gating**: a claim is admitted only after its measurement is live,
causally relevant, reproducible, and bound to immutable provenance.

## Research questions

1. **Model reproduction** — can the released GNM, ViNT and NoMaD implementations
   load, execute their official training computations, backpropagate and update
   parameters under a controlled environment?
2. **Data compatibility** — can new robot trajectories be represented in the same
   model-ready format without changing the semantics the released loaders expect?
3. **Evaluation reproducibility** — can a frozen ViNT evaluation be repeated on a
   fixed population with explicit dataset, checkpoint, batch and metric
   provenance?
4. **Simulator admissibility** — before collecting training data, does the chosen
   Isaac Sim world provide trustworthy support surfaces, blocking geometry,
   target-specific physics behaviour and a valid robot-camera viewpoint?
5. **Measurement validity** — when two evidence channels disagree, is the defect
   in the asset, the runtime representation, the sampling policy, or the
   measurement instrument?

---

## Current verified results

### 1. Option 1 data contract is implemented

```
trajectory_x/
├── 0.jpg
├── 1.jpg
├── ...
├── T.jpg
└── traj_data.pkl
    ├── position   # numeric array, shape [T, 2]
    └── yaw        # numeric array, shape [T]
```

`position[t] = [x, y]` is the robot position for image `t`; `yaw[t]` its heading.
Raw simulator records, ROS bags and HDF5 remain provenance sources and are
converted before model use. A 40-frame pilot yields `0.jpg … 39.jpg`,
`position [40, 2]`, `yaw [40]`.

The same trajectory produced **30 GNM, 30 ViNT and 29 NoMaD** samples. The NoMaD
count follows from its own context/horizon window (`[3, 32)` against `[5, 35)`)
and is expected, not missing data — derived in
`gates/forensics/SAMPLE_COUNT_AND_DEAD_WEIGHT.md`.

### 2. GO Stanford loader incompatibility traced and corrected

The released corpus contains 3,696 trajectories with valid directory structure,
but `position` and `yaw` stored as object-type arrays of arrays where the loader
expects direct numerical arrays. The correction changes representation only, at a
fixed NumPy version, and is treated as a compatibility repair rather than new
data.

### 3. Three-model train-path reproduction

| Model | Valid samples | Training-loss smoke | Non-zero gradients | Parameters changed | Result |
|---|---:|---:|---:|---:|---|
| GNM | 30 | 0.104939 | 324 / 326 | 326 / 326 | PASS |
| ViNT | 30 | 0.084481 | 486 / 504 | 488 / 504 | PASS |
| NoMaD | 29 | 0.036361 | 628 / 644 | 628 / 644 | PASS |

All losses finite; repeated execution under the frozen repeatability check gave a
maximum absolute difference of `0.00e+00`.

These values show each released training path is **executable under the checked
data contract**. Losses are not compared across models — GNM, ViNT and NoMaD
optimise different objectives — and are not claims of relative quality or of
reproducing any paper's benchmark.

### 4. Controlled ViNT evaluation on frozen pairs

| Quantity | Value |
|---|---|
| Frozen GO Stanford pairs | 41,872 |
| Strict total loss | 0.18026807678384063 |
| Historical comparison value | 0.17398 |
| Ratio | 1.036143 |

Recorded as corroborative reproduction evidence. Not a claim of superiority,
exact replication, or a matched three-model benchmark.

### 5. Checkpoint loading is not evidence of parameter use

A parameter-execution audit found loaded checkpoint elements that never executed
in the tested upstream graphs: **ViNT 19.21%**, **NoMaD 17.59%**. The unused
paths trace to classification heads read only for shape metadata and an orphaned
transformer prototype submodule. This is not checkpoint corruption; it is a
narrower methodological point:

> **Loaded is not executed; executed is not differentiated; differentiated is not
> updated.**

---

## Simulator and robot evidence

### Yahboom digital twin

| Quantity | Measured value |
|---|---|
| Collision-envelope length | 0.235 m |
| Collision-envelope width | 0.195 m |
| Collision-envelope height | 0.280 m |
| Circumscribed planar radius | 0.152 m |

Measured from the robot's own collider set, not assumed. The navigation camera is
mounted on the raised top arm; external simulator views are evidence views only.

### Scene collision coverage: authored state

Support surfaces and blocking structures are audited separately because their
absence has **opposite causal meanings**: missing blocker collision manufactures
false free space, missing support collision manufactures false non-navigability.
An aggregate over both destroys the distinction that decides the answer.

| Scene | Support collision | Blocking collision | Interpretation |
|---|---:|---:|---|
| Office | 5.6% of 36 | 100% of 285 | Systematic authored support defect established |
| Hospital | 82.0% of 128 | 100% of 1,066 | Strongest authored candidate; behavioural status pending |
| Warehouse | 30.6% of 36 | 100% of 106 | Structural significance unresolved |

Authored-state evidence only. These percentages do not establish admissibility,
and their spatial structure — *which* surfaces are missing — remains the
load-bearing open question.

### Dense-scene physics finding

The original Hospital blocker audit classified 8/8 targets geometrically
reachable, yet only 3/8 probes hit the declared target; five hit structurally
distinct objects. A short-range local isolation diagnostic then showed 4 of those
5 targets *were* causally hittable from an alternative local direction. The fifth
(`wrong_1`) remains unresolved.

Structural inspection falsified the convenient explanation that the returned
prims were alternative names for the same object: they shared no collision owner,
rigid body or prototype. The supported finding is:

> **Geometric reachability is not causal targetability.**

A probe can point toward the correct target region while a different object
becomes the physical cause of the observation. The measurement chain was
consequently refined to:

```
GEOMETRIC_REACHABILITY → CAUSAL_TARGETABILITY → QUERY
    → IDENTITY → INVARIANCE → REPRESENTATIVENESS → SCENE VERDICT
```

### Latest Hospital remeasurement: NO_EVIDENCE

```
support:   fired 8, reachable 7, not_targetable 7, probative_population -1
blocking:  fired 8, reachable 8, not_targetable 8, probative_population  0
```

A negative population is impossible; it arose from subtracting counts drawn from
different probe populations, invalidating the representativeness calculation. A
second defect surfaced simultaneously: the audit generated a **two-direction**
blocker intervention policy while the isolation diagnostic used a **four-face
±X/±Y** policy. Two tools claimed one behavioural contract while asking different
physical questions.

Required corrections and their current state:

| Correction | Status |
|---|---|
| Probe-identity accounting — populations from explicit ID sets, never subtraction | **Done** (`src/navfm/population.py`) |
| Contract-owned candidate generation — one finite policy, consumed by both tools | **Outstanding** |
| Representativeness before contents — disqualify thin samples before judging them | **Done** |

> **No candidate scene can be validly measured until the policy defect is
> closed.** This is not "Hospital nearly passing". While the diagnostic and the
> audit run different physical experiments under one contract label, no
> behavioural result about Hospital, Office or Warehouse is admissible.

---

## Failure-driven methodology

Failed measurements are preserved, because several of the strongest findings came
from tests that initially appeared to pass.

| Failure | Why the initial result was unsafe | Resulting rule |
|---|---|---|
| GO Stanford object arrays | Valid structure still failed tensor conversion | Lossless numeric correction with provenance |
| Finite loss, wrong objective | A hand-written loss passes while changing training semantics | Use official model-specific losses; record loss provenance |
| Filesystem asset closure | All referenced files existed while materials rendered wrongly | Independent runtime resolver plus render validation |
| Shared repair and verifier | A repair and its checker shared one traversal defect | Verify repairs with an independent oracle |
| Null execution read as zero | "0 errors" can mean the audit never ran | MeasurementEnvelope: liveness + value + provenance |
| Scene-level DomeLight inference | Scene metadata labelled pixels without pixel evidence | Positive per-pixel evidence; HDR observability |
| AABB free-space selection | Dense mesh bounds erased genuine navigable space | PhysX footprint scene queries |
| Generic collision hit | `hit > 0` passed when the wrong collider answered | Exact causal target identity required |
| First-N sampling | Blocking geometry starved support probes entirely | Role-stratified independent sampling |
| Shared-origin long rays | Different target labels, one physical intervention | Target-local probing; invariance review |
| Geometric reachability | Target region reachable while competing geometry answered | Pre-query causal-targetability stage |
| 1/8 reachable sample | A correct result on a tiny subset read as a scene verdict | Representativeness gate before contents |
| Negative probative population | Counts subtracted across different populations | Probe-ID populations; disjoint terminal dispositions |
| Diagnostic/audit policy mismatch | One contract label, two physical interventions | Candidate policy becomes contract-owned provenance |

## Measurement semantics

A measurement is admitted only when its execution is live and its provenance
present:

```
NOT_RUN · RUN_FAILED · RUN_LIVE_NO_MEASUREMENT · MEASURED_ZERO · MEASURED_NONZERO
```

A reported zero is a conclusion only after liveness is established; missing
evidence is never silently converted into a negative result. The same principle
applies to target-specific physics:

```
probe ran  ≠  target was interrogated  ≠  target caused the observation
           ≠  sample represents the scene
```

---

## Current research status

| Workstream | Status |
|---|---|
| Option 1 data contract | Verified |
| GO Stanford numerical compatibility correction | Verified |
| GNM / ViNT / NoMaD train-path reproduction | Verified |
| ViNT frozen-pair controlled evaluation | Completed, corroborative only |
| Yahboom digital twin and robot-camera data path | Verified for pilot collection |
| Office authored physics representation | Support defect established |
| Hospital authored physics representation | Measured; behavioural evidence pending |
| Warehouse authored physics representation | Measured; structural significance pending |
| Dense-scene causal-targetability concept | Supported by isolation diagnostic |
| Behavioural measurement instrument | **Incomplete — candidate policy not contract-owned** |
| Latest Hospital behavioural remeasurement | NO_EVIDENCE |
| `wrong_1` Hospital isolation case | UNRESOLVED |
| Canonical Isaac scene | NONE |
| New training-data admission | BLOCKED |

## Claim boundaries

**Supported:**

- the Option 1 trajectory structure is compatible with the checked released model
  paths;
- GNM, ViNT and NoMaD complete controlled training-path smoke executions under
  that structure;
- the frozen ViNT pair evaluation has been executed with explicit provenance;
- simulator physics requires separate authored-state, runtime,
  causal-targetability and representativeness checks;
- several plausible-looking measurement procedures were experimentally shown to
  answer the wrong question.

**Not claimed:**

- that GNM, ViNT or NoMaD paper benchmark numbers have been reproduced;
- that the three smoke losses are comparable;
- that any candidate Isaac scene is the canonical training world;
- that any behavioural scene measurement is currently admissible;
- that the current simulation pilots are admitted training data;
- that a sim-to-real performance improvement has been demonstrated;
- that a new navigation architecture or foundation model is introduced.

## Evidence organisation

The repository uses evidence-first artefacts rather than relying on narrative
summaries alone. Every path below was verified to exist at the commit that
introduced this document; where a planned artefact has not yet been generated it
is listed as pending rather than cited as though it existed.

```
gates/
├── compatibility/       # model-path and data-contract evidence
├── forensics/           # defects, contradictions, correction ledgers
├── reproduction/        # controlled reproduction evidence
└── scenes/              # scene, collision, targetability and measurement gates
```

**Model reproduction and data contract**

- `gates/compatibility/THREE_MODEL_TRAIN_PATH_MATRIX.md` — 18 contracts × 3 models
- `gates/compatibility/{gnm,vint,nomad}_training_contract.json`
- `gates/compatibility/{gnm,vint,nomad}_backward_optimizer_smoke.json`
- `gates/compatibility/{gnm,vint,nomad}_sample_population.json`
- `gates/forensics/SAMPLE_COUNT_AND_DEAD_WEIGHT.md` — the 30/30/29 derivation and
  the unexecuted-parameter census
- `gates/forensics/training_path_crosswalk.json` — file, function and line range
  for every element of each model's official training path

**Defects, contradictions and corrections**

- `gates/forensics/COMPATIBILITY_AND_DECISION_LEDGER.md` — causal ledger
- `gates/forensics/compatibility_decision_ledger.jsonl` — machine-readable form

**Simulator physics and measurement instrument**

- `gates/scenes/collision_probe_contract.json` — parent contract `480d9f07`
- `gates/scenes/collision_probe_contract_amendments.jsonl` — effective contract
  `24bf0a8c`, causal-targetability amendment
- `gates/scenes/collision_probe_regression_results.json` — 9 sparse regressions
- `gates/scenes/dense_targetability_regression_results.json` — 5 dense regressions
- `gates/scenes/physx_fixture_results.json` — footprint-oracle known answers
- `gates/scenes/physx_scene_query_capabilities.json` — measured robot footprint

**Scene admissibility**

- `gates/scenes/{office,hospital,warehouse}_collision_coverage_audit.json`
- `gates/scenes/hospital_blocker_contradiction_original.json` — frozen eight probes
- `gates/scenes/hospital_contradiction_hypotheses.json` — predeclared hypotheses
- `gates/scenes/hospital_isolation_diagnosis.json` — isolation diagnostic
- `gates/scenes/RENDER_VALIDITY_MATRIX.md`
- `gates/scenes/SCENE_MANIFEST.json`, `SCENE_ELIGIBILITY.json`

**Pending rendered summaries.** The following are planned human-readable
renderings of evidence that already exists in machine-readable form. They are
named here as outstanding work, not cited as results:
`COLLISION_COVERAGE_COMPARISON.md`, `COLLISION_PROBE_REGRESSION_MATRIX.md`,
`DENSE_TARGETABILITY_REGRESSION_MATRIX.md`, `HOSPITAL_BLOCKER_CONTRADICTION.md`,
`HOSPITAL_BLOCKER_ISOLATION_MATRIX.md`.

Where an artefact has been superseded, the old evidence is retained and the
change is recorded as an append-only amendment rather than silently overwritten.

## Reproducibility rules

1. Freeze expected answers before implementing the mechanism they test.
2. Preserve original preregistrations; corrections are append-only amendments.
3. A repair must be verified by an oracle independent of the discovery and repair
   mechanism.
4. A fixture passes only if the intended causal mechanism produced the expected
   result.
5. A metric is reported only when all required inputs exist and the evaluation
   actually ran.
6. Candidate-scene assets remain read-only during admissibility audits unless an
   explicit asset-authoring decision is made.
7. No training-data admission claim precedes the relevant scene, data and
   experiment-design gates.

## Researcher

Frank Asante Van Laarhoven is a PhD researcher in Computer Science at Newcastle
University, working on reproducible embodied navigation, camera-only stopping
reliability, simulator-to-real validation and deployment-time safety for mobile
robots. NavFM is maintained as a research evidence repository: results, failed
hypotheses, contradictions and corrective iterations are preserved so later
claims can be traced to the measurements that support them.

## Primary reference implementation

Reproduced against the published Visual Navigation Transformer implementation:
<https://github.com/robodhruv/visualnav-transformer>

- D. Shah et al., *GNM: A General Navigation Model to Drive Any Robot*, ICRA 2023.
- D. Shah et al., *ViNT: A Foundation Model for Visual Navigation*, CoRL 2023.
- A. Sridhar et al., *NoMaD: Goal Masked Diffusion Policies for Navigation and
  Exploration*, ICRA 2024.

## Citation

This repository documents ongoing doctoral research. If citing the software or
evidence repository before a formal paper release, use `CITATION.cff` and state
the exact commit used.
