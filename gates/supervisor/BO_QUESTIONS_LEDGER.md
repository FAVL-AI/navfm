# Supervisor questions ledger — Prof. Bo Wei

Last updated 2026-09-07 with the compatibility package
(`BO_COMPATIBILITY_PACKAGE_20260907.md`) and verified references
(`METRIC_REFERENCES_20260907.md`).

Status vocabulary: COMPLETE · PARTIAL · BLOCKED · NOT STARTED · AWAITING SUPERVISOR DECISION.

Nothing is COMPLETE because it has been discussed. COMPLETE means the evidence
exists in this repository and can be re-derived from it.

Bo's governing sequence, which overrides internal task appeal:

    existing dataset format
      -> prove our new data loads directly in GNM/ViNT/NoMaD
      -> review existing metrics with proper paper references
      -> reproduce baselines
      -> only then literature gap / novelty / fine-tuning

| ID | Question | Status | Evidence today | What is still required |
|---|---|---|---|---|
| BO-01 | Existing dataset formats, real examples, references | COMPLETE | Package §2; refs verified in `METRIC_REFERENCES_20260907.md` | — |
| BO-02 | Our dataset format | COMPLETE | Package §3; enforced in `schema.py`/`writer.py` | — |
| BO-03 | Direct GNM/ViNT/NoMaD loader compatibility | **COMPLETE** | A newly collected Hospital trajectory (`hospital_bo10_run_00001`) is consumed by all three pinned data paths at upstream `dca7981`: GNM 1190 samples / 7-tuple / action [5,4] / context 5; ViNT 1190 / 7 / [5,4] / 5; NoMaD 1189 / 7 / [8,2] / 3. Distances int64, actions finite, no synthetic fallback. Evidence `gates/BO10/loader_compatibility_run00001_20260910.json`. | None for compatibility. Sample counts differ by design — the frameworks' temporal and action specifications differ |
| BO-04 | Existing metrics + paper provenance | COMPLETE | Package §5; every source opened, method recorded per row | Collision metric definition once a comparison protocol is chosen |
| BO-05 | Explanation of the evidence/provenance layer | COMPLETE | Package §6, plain English, H7/H7R as motivation | — |
| BO-06 | Novelty vs SaferPath | DEFERRED / NOVELTY HYPOTHESIS | SaferPath verified to exist (ICRA 2026) | Systematic literature review; SaferPath collision definition not yet read |
| BO-07 | RQ1/RQ2/RQ3 ordering | AWAITING SUPERVISOR DECISION | — | Not approved; described as draft direction |
| BO-08 | Path-reference metrics (nDTW/SDTW/CLS) | BLOCKED | Ilharco et al. verified: both require a reference trajectory | Trustworthy versioned reference paths |
| BO-09 | Published-result reproduction | **COMPLETE_WITH_EVIDENCED_LIMITATIONS** | ViNT +3.61%, GNM +13.888% (both executed, exactly repeatable, controls 17-19x worse); NoMaD executed blocker at `upstream.py:218` | None. No published number was reproduced; every ceiling is inherent to the release |
| BO-10 | New Hospital collection | **COMPLETE_FOR_COMPATIBILITY_PURPOSE** | One newly collected Hospital trajectory exists and is admitted under the frozen contract: 1200 frames, 1200 matching images, 25.707 m travelled, 3 distinct realised turn events, 1189 NoMaD windows, controller identity unchanged, goal image sealed pre-motion and distinct from the final observation, zero collision-guard rejections. **NAVIGATION_TASK_COMPLETION = FAIL/NOT ACHIEVED** — terminated at max_steps 1.679 m from the sealed goal against a 0.20 m tolerance; admitted because `reached_goal` is not among the frozen post-episode conditions, not because it was checked and passed. `run_00000` remains COLLECTED_NOT_ADMITTED. | **Q1: `Q1_FEASIBLE_WITH_MARGIN`** — the route needs 798 of 1200 steps at the commanded cruise ceiling, 66.4% utilisation, 402 spare; the budget was not structurally insufficient. **Q2: `Q2_SUBCRUISE_PROGRESS_DOMINANT`** — the 402 spare steps went 84.2 (20.9%) to the 2.456 m of extra path and 318.6 (79.1%) to travelling below cruise, and the accounting closes with zero residual. Within the sub-cruise term, 94.0% is the frozen cosine throttle acting on a mean 37.25° heading error to the current target vertex, sustained across 1180 of 1200 steps; turn-in-place is 6.0%. The loss sits on straight legs (68.6%) rather than in turn zones (31.4%). The base was never blocked or stalled and was still closing on the goal at max_steps. Evidence `gates/BO10/q2_margin_consumption_20260911.json`. **Q3: `Q3_STOP_TRIGGER_NOT_REACHED` — this is an APPROACH failure, not a STOP failure.** The stop branch's sole precondition (`control.py:224`, Euclidean goal distance < 0.20 m, evaluated before target selection and independent of it) was satisfied at 0 of 1200 steps; closest approach 1.6787 m, 8.39x the tolerance. The stop mechanism was never entitled to fire, so this run is evidence about stopping in **neither** direction. The final miss decomposes almost exactly into a 0.932 m shortfall along the route and a 1.396 m lateral offset (hypotenuse 1.6787 m, agreeing with the recorded distance to 0.0000 m); 69% of the squared miss is lateral. Terminal progress was `TERMINAL_PROGRESS_INSUFFICIENT`: 0.990 of the required rate on a route-progress basis but 0.807 on a goal-closure basis, the gap being the cross-track. The base was `STILL_CONVERGING` at max_steps. No causal verdict on target selection: the vertex rule and the speed law are confounded through a shared heading-error term. Evidence `gates/BO10/q3_terminal_approach_20260911.json`. **`TERMINAL_APPROACH_INTERVENTION_V1` is AUTHORISED and preregistered; `EXECUTION_STATUS = NOT_RUN`, `EXECUTION_GATE = BLOCKED` on an unusable GPU (kernel module 580.173.02 vs userspace 580.178.04, CUDA error 804). `SOFTWARE_PREFLIGHT = PASS`: immutability guard 8/8, target-selection controls 19/19, and the audit confirms arm B overrides `target` and nothing else with `control.py` unmodified. Arm order frozen A→B while results were impossible to observe — `gates/BO10/intervention_execution_preflight_20260911.json`** — `gates/BO10/terminal_approach_intervention_v1_20260911.json`, amendment TAI-V1-A1 adding cross-track error and `fraction_of_steps_within_lookahead_radius` as DECLARED SECONDARY outcomes before execution; primary outcome, factor and every acceptance rule unchanged, no new pass/fail threshold. Causal attribution of the realised-turn amplification remains UNRESOLVED from one trajectory. Hospital-domain dataset (as opposed to one trajectory) remains outstanding |
| BO-11 | Fine-tuning and comparison | **NOT_READY_INSUFFICIENT_ADMITTED_DATA** | One admitted trajectory exists. That is an execution/compatibility proof, not a dataset. | A collection-plan decision first: trajectory count, route and scene diversity, train/validation/held-out split with trajectory- and route-level leakage prevention, seeds, checkpoint, optimiser, learning rate, epochs, augmentation, evaluation metrics. One compatibility trajectory must not become both training and evaluation data |

## The compatibility target

Model-facing, exactly as the published framework expects:

    HospitalDataset/trajectory_0001/
        0.jpg 1.jpg ... T.jpg
        traj_data.pkl        position [T,2], yaw [T]

Sidecar, kept separate so the official loader is untouched:

    HospitalDataset_provenance/trajectory_0001/
        scene identity/digest, camera identity, controller identity,
        start pose, goal provenance, timestamps, robot identity,
        collection parameters, checksums, admission result

## What Isaac-collected new data does and does not prove

PROVES: simulator execution pipeline · new temporal RGB collection · camera
mounting and extrinsics · trajectory/pose recording · official loader
compatibility.

DOES NOT PROVE: physical-robot execution · sim-to-real transfer ·
Hospital-domain performance if collected in Office or Warehouse · deployment
safety.

## Domain rule

Hospital is the preferred domain, **not** the root dependency. If Hospital cannot
be admitted, the collection-pipeline and loader-compatibility proof is completed
in the first environment that passes the same admission criteria, and reported as:

> "The full collection and model-loading pipeline has been validated on the
> admitted <environment> while Hospital scene admission is still being resolved.
> The same frozen collection protocol will then be applied to Hospital without
> changing the loader-facing data format."

Office/Warehouse data is never relabelled as Hospital data.

## Standing corrections

- H7/H7R are **historical diagnostic recordings, not admitted training data**.
- Do not write that the published format "deliberately carries no provenance".
  Write that the loader-facing format requires numbered RGB observations plus
  `traj_data.pkl` with position `[T,2]` and yaw `[T]`, and that provenance fields
  are not required by that loader.
- Every reference in supervisor-facing material must be checked against the
  primary source first. A reference supplied in conversation is a lead.