# NavFM

**Reproducible visual-navigation research: model fidelity, arrival decisions, and simulator qualification.**

NavFM is a doctoral research codebase for camera-only, image-goal navigation. It studies released GNM, ViNT, and NoMaD systems, develops detached arrival-decision candidates, and qualifies the measurement and simulation paths needed to evaluate them responsibly.

**Research status — 13 October 2026**: the three-model offline pilot is complete. Recorded comparator integration is qualified within its tested scope. Independent navigation performance, improved stopping, sim-to-real transfer, and state-of-the-art performance remain unestablished. This is a research artifact, not a certified robot-control product or a completed publication benchmark.

[Results and limitations](#evidence-and-current-status) · [Reproduction](#reproduction-and-validation) · [Research design](#research-design) · [Artifact map](#repository-map) · [Citation](#citation-and-licensing)

---

## Research overview

A successful execution is not sufficient evidence of a valid navigation experiment. Model loading, parameter use, data semantics, metric definitions, simulator behavior, and process admission must each be checked. NavFM retains immutable source and input identities, finite execution budgets, negative controls, complete outcome populations, and failed attempts alongside successful measurements.

The current scientific question is whether an arrival rule can reduce wrong-location voluntary stops while preserving collision-free completion and bounded task time, against a strong stopping comparator using the same navigator and information budget. Temporal belief, alias features, and dwell logic are candidate mechanisms; their combination is not established as novel.

The [contribution review](docs/ARRIVAL_CONTRIBUTION_REVIEW_V1.md) and [execution design](docs/ARRIVAL_CONTRIBUTION_EXECUTION_PLAN_V1.md) document the hypothesis, related-work boundary, comparators, statistical assumptions, and unresolved prerequisites.

---

## Evidence and current status

| Workstream | Recorded result | Scope and evidence |
|---|---|---|
| Three-model offline pilot | 768 valid retained outcomes across 12 fixed checkpoint roles | 32 pairs, four routes, two already accessed layouts; [consolidated report](docs/PROSPECTIVE_THREE_MODEL_CONSOLIDATION_V1.md). Not 768 independent samples. |
| Recorded RGB-to-belief integration | 32 encoder forwards completed | Tested reference/query path and mock STOP only; [report](docs/RECORDED_RGB_STOP_RESULT_V2.md). |
| LightGlue checkpoint transport | 251 parameters and one buffer matched the native construction bitwise | Exact authenticated legacy-key transport; [CPU qualification](docs/RAVEL_CANONICAL_TRANSPORT_RESULT_V2.md). |
| Native fixed-mode graph construction | 28 pairs, zero technical failures; 28 edges pruned to 7, all eight nodes connected | Construction on fixed recorded references; no topology-accuracy or navigability claim; [report](docs/NATIVE_RAVEL_FIXED_GRAPH_RESULT_V3.md). |
| Saved-graph ULVN integration | 16 updates across two fresh-state episodes; two arrival publications and two mock STOPs | Cached descriptors, native belief/routing, software cancellation; [report](docs/SAVED_GRAPH_ULVN_REPLAY_RESULT_V1.md). |
| Arrival-rule candidates | 66 focused synthetic tests passed in consolidation | Explicit hard-veto versus no-veto policy; neither empirically superior nor calibrated; [comparison](docs/ALIAS_AWARE_DECISION_RULE_COMPARISON_V1.md). |
| Camera qualification v2 | Eight frames and 16 image/metadata hashes verified; overall FAIL | Child exceeded its execution allowance after close returned; no admission; [report](docs/STATIC_ARRIVAL_CAMERA_QUALIFICATION_RESULTS_V2.md). |
| Signal-free teardown diagnostic | Worker returned; process survived until deadline SIGTERM | Cause and complete SDK cleanup unresolved; [report](docs/STATIC_ARRIVAL_POST_CLOSE_SIGNAL_FREE_RESULTS_V2.md), [upstream issue #877](https://github.com/isaac-sim/IsaacSim/issues/877). |
| Physical apparatus and navigation | Blocked | CAD, loaded motion, actual STOP, contact filtering and other admission gates; [readiness record](docs/SIMULATION_APPARATUS_READINESS_V1.md). |

These are historical, source-bound results, not assertions that every check passes on a fresh machine. Raw evidence is held externally; compact reports identify the measured scope and artifact hashes.

### Offline pilot: results with counter-evidence

Average displacement error (ADE; metres) below is descriptive. Adapted values retain all three preselected seeds, 0/11/22. Each system is compared with its own released checkpoint.

| System | Released ADE | Adapted mean ADE | Adapted seed range |
|---|---|---|---|
| GNM | 0.030442 | 0.014369 | 0.011849–0.017128 |
| ViNT | 0.079904 | 0.020137 | 0.019134–0.022018 |
| NoMaD | 0.059792 | 0.009970 | 0.007176–0.012481 |

**Counter-evidence**: ViNT positive temporal-distance error worsened for every adapted seed despite improved waypoint errors. The complete report retains endpoint metrics, route cells, dispersion, and paired differences.

**Comparability limits**: adaptation procedures and exposure differ; GNM/ViNT use raw weights while NoMaD uses EMA weights. GNM/ViNT produce one draw per pair and NoMaD four. Capture/training cadence differs. Latency scopes differ: ViNT includes its state/RNG fence, and NoMaD includes native decode/transfers. These timings are not a matched pure-forward speed benchmark or an Orin deployment estimate. No best seed is selected from these results.

---

## Research design

The proposed joint target is at least a five-percentage-point reduction in wrong-location stops, while ruling out more than five points of completion loss and five seconds of added restricted task time. These are prospective criteria, not achieved effects. Layout-level independence, comparator fidelity, calibration isolation, and feasible resource requirements must be established before confirmatory evaluation.

| Stage | Established work | Remaining question |
|---|---|---|
| Hypothesis and design | Arrival endpoint, matched comparator plan, explicit claim boundaries | Does the candidate improve the joint outcome? |
| Initial measurements | Offline pilot and bounded component qualifications | Do component results transfer to closed-loop behavior? |
| Failures and refinement | Retained source-loading, launcher, motion and teardown failures; tested narrow repairs | Which outstanding apparatus conditions can be qualified? |
| Method development | Synthetic hard-veto/no-veto counterexamples and annotated-map variant | Can deployment-available inputs discriminate distant lookalikes? |
| Further experiments | Development acquisition proposal and conditional feasibility design | Inputs, calibration protocol, apparatus and budgets remain gated. |
| Conclusion | Measurement and software behavior are documented | Novelty, independent generalisation and improved stopping remain untested. |

The [development feasibility protocol](docs/ARRIVAL_DEV_FEASIBILITY_EXECUTION_V1.md) is separate from the [static acquisition proposal](docs/STATIC_ARRIVAL_RULE_DEVELOPMENT_ACQUISITION_V1.md). Neither is authorized by this README. The 80-layout study and 2,000-GPU-hour ceiling remain unapproved; the five-family acquisition budget remains unapproved.

---

## Data and inference boundaries

- The admitted training-record inventory covers 31 trajectories. Indexed position/yaw arrays support geometric proximity in documented coordinates; timestamps and successful-arrival outcomes are absent from those inspected records. See the [schema inventory](docs/ARRIVAL_TRAIN_RECORD_SCHEMA_INVENTORY_V1.md).
- The frozen 0.5 m goal-image region is a geometric label, not evidence of settling, collision-free completion or physical STOP.
- Accessed development routes and pilot outcomes cannot become independent confirmatory evidence. The accessed pilot remains excluded from calibration.
- Episode-balanced fitting does not create independent layouts. Repeated frames, routes, draws and seeds must retain their actual statistical roles.
- Query ground truth must not enter inference. The goal-region feature requires deployment-available reference annotations; the current bank does not supply them. See the [pose-availability boundary](docs/GOAL_REGION_REFERENCE_POSE_AVAILABILITY_V1.md).
- Identical visual features with different geometric labels remain indistinguishable to the tested rules. Synthetic tests do not prove perceptual discrimination.

---

## Reproduction and validation

The package declares Python 3.10 or newer; ordinary CI targets Python 3.10–3.12. Isaac, model, archive and alternate-interpreter workloads have separate pinned environments and prerequisites. Installing the package does not provision or authorize those workloads.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

# Focused, synthetic-only arrival-component checks.
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src \
  python -m pytest -q tests/test_alias_aware_arrival.py

# Repository-wide static checks.
ruff check src tests scripts
mypy
```

For the ordinary resource-excluded test population, follow [ci.yml](.github/workflows/ci.yml), including its population ownership gate. The [population manifest](tests/population_manifest.json) assigns resource-dependent tests to their declared owners; excluding them is not evidence that they passed. `make verify` runs the broader suite and can fail when required resources are unavailable.

The last reported workstation-wide verification retained 29 prerequisite failures: 24 dependency failures, four missing archives and one unavailable interpreter. The consolidation check passed 66 arrival-component tests, repository-wide Ruff and mypy (92 source files) on Python 3.12. PR #3 still has failing CI checks, including resource-contract and resource-approval gates; these local checks do not supersede them. Consult current CI separately from historical reports. See [reproduction guidance](docs/REPRODUCTION.md), [data contract](docs/DATA_CONTRACT.md), and Makefile.

Do not run historical one-shot launcher commands as generic examples. They bind exact commits, external inputs, registries and attempt directories; consumed slots remain consumed. No renderer, encoder, fitting, scoring, collection or navigation run is launched by the commands above.

---

## Evidence and admission

Every measured report should distinguish:
1. Task measurements and completeness.
2. Artifact integrity and provenance.
3. Observed shutdown-call behavior and independently established cleanup evidence.
4. Actual process exit, timeout, signals and reaping.

A report on disk is not proof of clean process exit. A timeout or forced termination remains a failure under its frozen admission contract. Neither API wording nor a returned close() proves full SDK cleanup. A prospective disposable-worker design would require its own contract and validation; it does not retrospectively admit failed captures.

---

## Repository map

| Path | Purpose |
|---|---|
| `src/navfm` | Data validation, collection contracts, model interfaces and research components |
| `scripts` | Preparation, qualification, replay and reporting entry points |
| `configs` | Versioned inputs, splits, policies and execution bounds |
| `tests` | Synthetic, integration and explicitly resource-owned checks |
| `docs` | Protocols, reviews, measured results and limitations |
| `gates` | Earlier reproduction, compatibility and simulator evidence records |
| `.github/workflows` | CI and resource-validation ownership |

Earlier findings remain available in the [pre-consolidation README](https://github.com/FAVL-AI/navfm/blob/1de79941552717e5740be75295567d7c9b6513bb/README.md). Its dated workstream statuses are historical, not the current project summary.

---

## Publication and contribution policy

This repository supports preparation of an auditable research artifact; it is not presented as an accepted paper, a complete independently reproducible dataset release, or a SOTA result. Public code and compact reports do not replace access to the external evidence needed to repeat resource-dependent experiments.

Changes should state the scientific question, exact input/source identities, expected behavior, validation performed, failures and claim limits. Preserve frozen protocols and original failures. Keep weights, recordings, CAD, credentials and raw runtime evidence out of Git. External assets retain their own licensing and access conditions. Do not weaken admission criteria to obtain a passing label.

Local teardown investigation is closed as an unresolved, upstream-reported milestone. Runtime probes remain paused; issue #877 stays open for maintainer triage. Camera qualification, physical navigation gates and acquisition approvals remain unchanged.

---

## Citation and licensing

Maintained by Frank Asante Van Laarhoven, School of Computing, Newcastle University.

Use [CITATION.cff](CITATION.cff) and include the exact commit and relevant result report when citing this software. No paper DOI or publication acceptance is asserted. Project code is licensed under MIT; third-party code, datasets, pretrained weights and manufacturer assets are not relicensed by this repository.

Primary navigation implementations and publications are documented through the [Visual Navigation Transformer reference implementation](https://github.com/robodhruv/visualnav-transformer):
- Shah et al. GNM: A General Navigation Model to Drive Any Robot. ICRA 2023.
- Shah et al. ViNT: A Foundation Model for Visual Navigation. CoRL 2023.
- Sridhar et al. NoMaD: Goal Masked Diffusion Policies for Navigation and Exploration. ICRA 2024.

For arrival comparators and the novelty assessment, use the source-linked [literature review](docs/ARRIVAL_CONTRIBUTION_REVIEW_V1.md).
