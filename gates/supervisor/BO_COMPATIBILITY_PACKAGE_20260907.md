# Dataset format, framework compatibility and evaluation metrics

Frank Asante Van Laarhoven · Newcastle University · 2026-09-07

Prepared for Prof. Bo Wei, answering the three questions in sequence.

---

## 1. What you asked

1. Review the formats of existing datasets, with real examples and references.
2. Show whether our newly collected data can be used **directly** by the
   GNM / ViNT / NoMaD code.
3. Review the metrics used by the existing papers, with the correct source paper
   for each metric.

**Short answer to question 2, stated precisely:**

> We use the published GNM/ViNT/NoMaD framework directly. Our trajectories are
> written in its native processed format — numbered forward-facing RGB images
> plus `traj_data.pkl` containing `position [T,2]` and `yaw [T]`. The official
> loader has been executed against our data and accepts it. That proof currently
> runs on a **synthetic** trajectory; the same proof on a newly collected
> Hospital trajectory is the one outstanding item.

---

## 2. Existing dataset formats

### 2.1 GNM / ViNT / NoMaD — the format that matters for compatibility

This is the primary target, because it is the framework we use. Taken from the
official repository, pinned in our project at commit `dca7981`:

    <dataset>/<trajectory_name>/
        0.jpg
        1.jpg
        ...
        T.jpg
        traj_data.pkl

`traj_data.pkl` is a pickled dictionary:

| Key | Type | Meaning |
|---|---|---|
| `position` | `np.ndarray [T, 2]` | xy-coordinates of the robot at each image observation |
| `yaw` | `np.ndarray [T,]` | yaw of the robot at each image observation |

Each `.jpg` is a temporally labelled forward-facing RGB observation. The
repository also documents how to register a custom dataset for training.

*Source: `robodhruv/visualnav-transformer`, README, read from our pinned clone.*

### 2.2 R2R (Room-to-Room)

A benchmark of natural-language navigation instructions paired with routes
through real building scans, on a navigation graph. Each item pairs an
instruction with a path between viewpoints. Different task from ours — the input
is language, and the agent moves between graph nodes rather than executing
continuous control.

Its results table reports **Trajectory Length (m)**, **Navigation Error (m)**,
**Success (%)** and **Oracle Success (%)**.

*Anderson et al., CVPR 2018.*

### 2.3 VLN-CE

Removes the navigation graph: the agent executes low-level actions in a
continuous 3D environment rather than hopping between viewpoints. The authors
name the task **Vision-and-Language Navigation in Continuous Environments
(VLN-CE)**, and build it by transferring R2R data into the continuous setting —
**4,475 trajectories converted from the R2R train and validation splits**.
Closer to our setting in that control is continuous, but still a
language-conditioned task.

*Krantz et al., 2020.*

### 2.4 Why R2R and VLN-CE are secondary here

They are useful for the metrics discussion in §5, but they are not the
compatibility target. Your question is whether our data works in
GNM/ViNT/NoMaD, so the visualnav-transformer format is the one we must match.

---

## 3. Our Hospital format

### 3.1 Model-facing — identical to the published format

    HospitalDataset/trajectory_0001/
        0.jpg
        1.jpg
        ...
        T.jpg
        traj_data.pkl        position [T,2], yaw [T]

Our writer enforces the two invariants the loader depends on:
`len(position) == number_of_jpg_files`, and yaw is **unwrapped** (the reference
loader differences yaw without angle wrapping, so an un-unwrapped trajectory
crossing ±π would produce a corrupted action label).

*Source: `src/navfm/schema.py`, `src/navfm/writer.py` in our repository.*

### 3.2 Research sidecar — kept separate

    HospitalDataset_provenance/trajectory_0001/
        scene identity and digest
        camera identity
        robot identity
        controller identity
        start condition
        goal identity
        timestamps
        software/environment identity
        checksums
        admission status

**These fields are not required by the published loader-facing trajectory
format.** They live in a separate directory precisely so the model-facing folder
stays byte-for-byte the shape the official loader expects.

### 3.3 One clarification about H7/H7R

The 33 historical H7/H7R recordings are **LEGACY DIAGNOSTIC DATA — NOT ADMITTED
FOR TRAINING**. They are kept as evidence of earlier collection attempts, not as
a dataset to fine-tune on.

---

## 4. Direct framework compatibility — what has actually been executed

### 4.1 Executed proof (synthetic trajectories) — COMPLETE

`tests/test_upstream_compat.py`, run against the pinned official code:

| | |
|---|---|
| Upstream | `third_party/visualnav-transformer` @ `dca79815b704e5aa9c6bdc3082351f9e3b2848c2` |
| Interpreter | `~/.venv-train/bin/python`, Python 3.11.15, torch 2.11.0+cu128 |
| Result | **4 passed** |

The official reference `Dataset` class indexes and loads our trajectories, and
the sample it returns satisfies the framework's contract:

- `__getitem__` returns the expected 7-tuple;
- `obs_image` has shape `3 × (context + 1)` channels;
- `actions` are `horizon × 4` as `dx, dy, cos θ, sin θ`;
- the `(cos, sin)` columns are unit-norm;
- `distance` is `int64`;
- our `to_local_coords` matches the reference implementation **bitwise**;
- the NoMaD specification also loads (`test_nomad_spec_also_loads`).

This is execution against the official code, not a shape comparison.

### 4.2 What is still outstanding

The trajectories in that test are **synthetic**. The final proof is the same
chain on a newly collected Hospital trajectory:

    admitted Hospital trajectory -> official loader -> valid batch -> model input

**Status: `SYNTHETIC_COMPATIBILITY_COMPLETE` / `HOSPITAL_COMPATIBILITY_OUTSTANDING`.**

I am not describing Hospital compatibility as complete until that has run.

### 4.3 The single blocker

> The final real-Hospital loader proof is waiting on admission of a newly
> collected Hospital trajectory; current Hospital scene admission remains
> pending.

---

## 5. Evaluation metrics and their correct sources

Each metric below is attributed to the paper that introduced it. **SPL, CLS,
nDTW and SDTW come from three different papers, none of which is the R2R paper** —
attributing them all to R2R is a common and avoidable error.

| Metric | Meaning | Required inputs | Primary source | NavFM status |
|---|---|---|---|---|
| **SR** — Success Rate | Fraction of episodes ending within the success criterion of the goal | goal, success threshold | **Anderson et al., CVPR 2018** — reported as "Success (%)" in Table 1 | AVAILABLE |
| **NE** — Navigation Error | Distance from the agent's stopping point to the goal | goal position, final pose | **Anderson et al., CVPR 2018** — reported as "Navigation Error (m)" in Table 1 | AVAILABLE |
| **SPL** | Success weighted by (normalized inverse) Path Length: `(1/N) Σ Sᵢ ℓᵢ/max(pᵢ,ℓᵢ)` | success flag, shortest-path length `ℓ`, actual path length `p` | **Anderson et al., *On Evaluation of Embodied Navigation Agents*, 2018** — §4 eq. (1); Recommendation 3 adopts it as the primary measure | AVAILABLE once a trusted shortest-path length exists |
| **CLS** — Coverage weighted by Length Score | Fidelity of the executed path to the intended path | **reference path** | **Jain et al., *Stay on the Path*, ACL 2019** | **BLOCKED (proposed — §5.1)** |
| **nDTW** | Normalised dynamic time warping; softly penalises deviation from the reference path | **reference trajectory** | **Ilharco et al., NeurIPS 2019** | **BLOCKED (proposed — §5.1)** |
| **SDTW** | nDTW constrained to successful episodes | **reference trajectory** + success criterion | **Ilharco et al., NeurIPS 2019** | **BLOCKED (proposed — §5.1)** |
| Collision metric | — | — | **Definition and source to be fixed to the exact baseline protocol being reproduced** | **NOT YET DEFINED** |

### 5.1 Path-reference metrics — a proposal for your confirmation

My current proposal is to keep Coverage weighted by Length Score (CLS),
normalized Dynamic Time Warping (nDTW) and Success-weighted normalized Dynamic
Time Warping (SDTW) blocked until the reference path / navigation representation
used for evaluation is versioned and reproducible. These metrics evaluate
trajectory/path fidelity — the Ilharco et al. paper states that nDTW "softly
penalizes deviations from the reference path" and that SDTW constrains it "to
only successful paths" — so without a trustworthy reference path they would
produce numbers with no defensible meaning.

I would like to confirm with you whether you agree with keeping them blocked at
this stage, rather than reporting values from an insufficiently controlled
reference path. **This is my proposal, not a settled decision.**

### 5.2 Why the collision metric is not yet defined

There is no single canonical collision metric. *On Evaluation of Embodied
Navigation Agents* mentions "number of infractions (e.g., contact with
obstacles)" only as an auxiliary suggestion, not a defined metric. These are
genuinely different quantities and should not be merged:

    collision count · collision rate · collision-free success · safety violation rate

I will cite whichever definition we reproduce, from the paper we compare
against, once that comparison target is fixed. SaferPath is the likely
comparison target, but I have not yet read its collision-metric definition, so I
am not citing it as the source.

---

## 6. Why we record provenance alongside the data

The GNM/ViNT/NoMaD model only needs its normal trajectory files: the numbered
images and `traj_data.pkl`. Alongside those, we separately record which scene,
scene version, camera, robot and controller produced each trajectory, where it
started, what the goal was, when it was collected, which software versions were
used, and checksums of the files themselves.

The reason is simple: the older H7/H7R recordings looked format-correct, and it
was still not possible to prove afterwards which scene version and controller
had produced them, so they could not be used as scientific evidence. Recording
that information at collection time is what lets a trajectory be admitted as
evidence rather than merely loaded. It sits in a separate folder and does not
change what the model loader sees.

---

## 7. Status summary

| | Status |
|---|---|
| Existing dataset formats reviewed | Complete for the compatibility question |
| Our Hospital format defined | Complete, and enforced in code |
| Official-loader compatibility, synthetic | **Complete — executed, 4 passed** |
| Official-loader compatibility, real Hospital trajectory | **Outstanding — the one open item** |
| Metrics reviewed with verified sources | Complete |
| Path-reference metrics (CLS/nDTW/SDTW) | Proposed blocked — §5.1, awaiting your confirmation |
| Collision metric | Not yet defined; awaiting choice of comparison protocol |
| Provenance layer explained | Complete |

The RQ1/RQ2/RQ3 ordering is **draft direction awaiting your view**, not settled.
Likewise the comparison with SaferPath is a hypothesis I have not yet tested
against a systematic literature review, so I am not claiming novelty for it.

---

## 8. References

1. P. Anderson, Q. Wu, D. Teney, J. Bruce, M. Johnson, N. Sünderhauf, I. Reid,
   S. Gould, A. van den Hengel. *Vision-and-Language Navigation: Interpreting
   visually-grounded navigation instructions in real environments.* CVPR 2018.
   arXiv:1711.07280.
2. P. Anderson, A. Chang, D. S. Chaplot, A. Dosovitskiy, S. Gupta, V. Koltun,
   J. Kosecka, J. Malik, R. Mottaghi, M. Savva, A. R. Zamir. *On Evaluation of
   Embodied Navigation Agents.* 2018. arXiv:1807.06757.
3. V. Jain, G. Magalhaes, A. Ku, A. Vaswani, E. Ie, J. Baldridge. *Stay on the
   Path: Instruction Fidelity in Vision-and-Language Navigation.* ACL 2019.
   arXiv:1905.12255.
4. G. Ilharco, V. Jain, A. Ku, E. Ie, J. Baldridge. *General Evaluation for
   Instruction Conditioned Navigation using Dynamic Time Warping.* NeurIPS 2019.
   arXiv:1907.05446.
5. J. Krantz, E. Wijmans, A. Majumdar, D. Batra, S. Lee. *Beyond the Nav-Graph:
   Vision-and-Language Navigation in Continuous Environments.* 2020.
   arXiv:2004.02857.
6. D. Shah, A. Sridhar, N. Dashora, K. Stachowicz, K. Black, N. Hirose,
   S. Levine. `robodhruv/visualnav-transformer` — GNM / ViNT / NoMaD.
   Pinned here at `dca79815b704e5aa9c6bdc3082351f9e3b2848c2`.
7. L. Zhang, Z. Jiang, C. Chen. *SaferPath: Hierarchical Visual Navigation with
   Learned Guidance and Safety-Constrained Control.* ICRA 2026. arXiv:2603.01898.

Verification method for each reference is recorded in
`gates/supervisor/METRIC_REFERENCES_20260907.md`.
