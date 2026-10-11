# Three-model navigation preparation v1

Status: PREPARATION ONLY; NOT FROZEN; NO TRAINING, SIMULATION OR EVALUATION RUN AUTHORISED BY THIS DOCUMENT. Base: merged main `8800def599b57a6ba9fbf252cabfecd257e5b206`. Experimental results: not yet available for this proposed comparison.

## Current evidence and limits

| Item | Verified scope | Remaining gap |
| --- | --- | --- |
| Integration | Main run 38102330977 attempt 2 passed all eight checks; exact-source resource evidence preserved externally | Software/resource qualification is not navigation performance |
| Dataset format | Existing admission records use chronological JPEG plus measured position[N,2]/yaw[N], processing index/time maps, train-only action unit 0.049994826316833496 m | New corpus identity/admission must be checked before training; kinematic demonstrations do not validate robot dynamics |
| Initial corpus | Recorded six train, two dev and two formerly test trajectories; junction test routes exposed in diagnostics | Former test is development evidence, not confirmatory |
| Expanded adaptation | Recorded 31 train trajectories, 945 pairs, 20 epochs/4,720 steps, seeds 0/11/22; epoch 20 selected on development distance MAE | Metadata/report evidence only in this preparation; no weights loaded or training reproduced |
| ViNT artifacts | Release path checkpoints/vint.pth exists, 430,167,114 bytes; recorded digest 155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f. Adapted epoch_020.pth records are under option1-arrival-n31-e20-seed{0,11,22}-20261009-01 | Rehash and strict reload later under an authorised frozen compatibility check; presence is not validation |
| GNM / NoMaD | Local release files exist, respectively 104,806,886 / 76,473,631 bytes; loader records GNM training-dict and NoMaD bare EMA state-dict formats | No newly verified adapted checkpoint or equal-budget training/navigation evidence established here |
| Prior single-far-goal ViNT | Four development pairs: correct stops 0/4 in both arms, completion 0/4; released contacts 4/4, adapted 3/4; adapted wrong stop 1/4 | No competence, safety or generalisation claim; smaller contact count is not automatically a safety gain |
| Later chain ViNT | Four development routes/two scenes/one seed: correct stops 2/4 released vs 3/4 adapted; wrong-chain adapted wrong stops 4/4 | Different navigation stack from single-far-goal comparison; tiny development evidence, not unseen-layout performance |
| Initialization | Two-case scripted replay success is limited to proxy state; actual learned handover numerical gate failed despite discrete agreement | Existing recovery gates and failures remain immutable; no efficacy expansion |
| Cleanup | Metadata inspection found runner directories/helpers present and listener failed; no service actions taken | Final host cleanup is not claimed complete |

Sources: `docs/OPTION1_TRAINING.md`, `docs/OPTION1_RESULTS.md`, `docs/ARRIVAL_RESEARCH_DECISION.md`, `configs/train/option1_vint_smoke.yaml`, `configs/eval/option1_pretrained_vs_finetuned.json`, `docs/OFFLINE_NUMERICAL_V1_RESULT.md`. Prior attempts remain evidence, including timeouts, contact, failed collection and failed handover. These records do not establish model superiority.

Metadata-only checks found training_report.json with recorded PASS and epoch_020.pth present for each seed 0/11/22 directory. The report checkpoint field names smoke_weights.pth, whereas the selected research checkpoint is epoch_020.pth; reconcile the exact selected artifact/digest/epoch before execution rather than assume the filenames are interchangeable. No checkpoint tensor was read.

The tracked held-out layout specification was inadvertently read beyond its top-level status during this preparation, exposing its geometry and route definitions. No held-out images, outcome data or episodes were accessed or executed. That specification is therefore **not uninspected**; its geometry will not guide selection or tuning. Where genuinely uninspected confirmatory geometry is required, an independent process must create and seal a replacement specification before protocol freeze. Do not generate or inspect that replacement in this milestone. Existing tracked status says not collected/not scored; this is a recorded status, not a new filesystem audit. Illumination remains paused and real robot actuation unauthorised.

## Exact inventory pointers (metadata only)

| Manifest / artifact | Identity state |
| --- | --- |
| `/home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01/admission.json` | Recorded PASS, 39 attempted/35 admitted/4 rejected; dataset digest 7e2b3738c3026e9e170d1a635d3172e92767428ec577bdb85a9b64501f02cbc3; not rehashed. This record says collision_positive_control_verified=false; detector qualification remains necessary. |
| Same directory `/upstream` | Recorded training snapshot; separately freeze actual source identity, do not substitute dirty current clone |
| `configs/splits/arrival_split_v2.json` | Tracked split specification, 31 train trajectories plus four exposed development routes; inherited recorded split digest f09cb892a6ade892a0fc67943c91a41dbbf3a4c2aea98d33aeda67a3e9458fef, not newly rehashed |
| `/home/favl/navfm-training-evidence/option1-arrival-n31-e20-seed{0,11,22}-20261009-01/{training_report.json,epoch_020.pth}` | Metadata files present; selected checkpoint identity requires epoch-specific reconciliation. Training report retains steps_requested=6 and one-epoch configuration, so that inherited report alone does not attest the claimed 20-epoch run. Its admission_digest e7938615... differs from the earlier expanded dataset digest; reconcile versioned admission before replication. |
| `/home/favl/projects/navfm/checkpoints/{vint,gnm,nomad}.pth` | File presence/size checked only; release ViNT recorded SHA above; GNM/NoMaD new digest verification and adapted training evidence not established |
| `configs/eval/option1_pretrained_vs_finetuned.json` | Prior smoke comparison, d0f412e6 adapted checkpoint; not the selected epoch-20 comparator |
| `docs/ARRIVAL_RESEARCH_DECISION.md`, `/home/favl/navfm-runtime-evidence/arrival-closedloop-{released,ft-seed0}-20261009-01` | Authored prior development analysis and external evidence pointers; no raw episodes opened here |

No weight bytes were hashed/read in this preparation. Recorded digests are evidence pointers, not fresh byte verification. Actual training roots, complete raw-to-processed mapping and versioned admission/selection manifest remain freeze blockers; do not infer them from directory names.

## Pinned upstream and model-specific requirements

The local upstream base is `dca79815b704e5aa9c6bdc3082351f9e3b2848c2`; its working tree has modifications in training/configuration/data/deployment files. Future execution must freeze an explicit patch/snapshot digest, not describe this clone as pristine. The following values were read from **Git blobs at that base**, avoiding dirty configuration ambiguity:

| Model | Input size | Historical context plus current | Horizon | Additional contract |
| --- | --- | --- | --- | --- |
| ViNT | 85×64 | 5 + 1 RGB | 5 waypoints | Goal RGB, temporal-distance head; model-specific action scaling |
| GNM | 85×64 | 5 + 1 RGB | 5 waypoints | Architecture/checkpoint trust and exact load compatibility; never transfer stop-head weights by assumption |
| NoMaD | 96×96 | 3 + 1 RGB | 8 waypoints | nomad_vint encoder; 10 diffusion iterations; fixed sampler, RNG, sample count, goal-mask and action aggregation; EMA provenance |

The official [repository](https://github.com/robodhruv/visualnav-transformer) supplies the three models, custom trajectory format and training/deployment code. Pinned [ViNT config](https://github.com/robodhruv/visualnav-transformer/blob/dca79815b704e5aa9c6bdc3082351f9e3b2848c2/train/config/vint.yaml), [GNM config](https://github.com/robodhruv/visualnav-transformer/blob/dca79815b704e5aa9c6bdc3082351f9e3b2848c2/train/config/gnm.yaml), [NoMaD config](https://github.com/robodhruv/visualnav-transformer/blob/dca79815b704e5aa9c6bdc3082351f9e3b2848c2/train/config/nomad.yaml) and [navigation source](https://github.com/robodhruv/visualnav-transformer/blob/dca79815b704e5aa9c6bdc3082351f9e3b2848c2/deployment/src/navigate.py) are the compatibility references. Native preprocessing/context must be preserved; equal tensor shapes are not a fair-model requirement. Distances are temporal labels, not metres or automatically calibrated stopping probabilities.

## Stage 1: development qualification, then released versus adapted ViNT on unseen layouts

Question: under one frozen RGB-only navigation system, does adaptation change correct stopping and collision-free completion on previously unseen simulated layout/scene groups? Unseen means geometry disjoint from training, development and all inspected layout specifications; a new numerical start tuple in a known scene is only a new experimental start. First use development-only technical qualification, then freeze the replacement independently sealed test specification and protocol before opening confirmatory layouts. This is an empirical hypothesis, not a proposed novel method.

Before any launch, freeze a finite development qualification manifest; separately freeze the unseen-layout evaluation population before its sealed specification is opened. Use metadata-only exclusion against prior inspected tuples for new experimental starts, without confusing this with layout independence. Keep layouts independent by scene/route group, including augmented/relit copies. Start with one technical pair, then a separately justified small paired pilot; no automatic batch. Order is counterbalanced and fixed before outcomes. Fix release and adapted checkpoint hashes, dev-only checkpoint selection rule, exact source/runtime/assets, image acquisition/readbacks, history cadence and initial buffer/state, topological-chain source and node sampling, search/window/confirmation/lost-state behavior, controller gains/limits/action units, stop rule, task timeout, simulator stepping and contact measurement. The comparison changes only checkpoint identity. Declare the permitted deployment reference chain: if teaching/goal-map traversal is part of the task, generate the same RGB chain once under the frozen fixture and provide it identically to both arms. Record this map-building cost and distinguish mapped navigation from map-free claims. Offline reference-chain acquisition/node sampling may use explicitly declared reference geometry if allowed by the task and frozen equally. Any privileged teaching traversal is separated from RGB-only deployment. Live ground truth must not select policy nodes, reveal progress or stop; evaluation-rollout images must never construct their own prior reference chain. Use a deployment-qualified controller, not the kinematic teaching mechanism.

Ordinary navigation episodes need a new clean-start physical/controller/history/readback and actual policy-state eligibility contract. They do not inherit a kidnap/recovery learned-handover requirement unless the chosen implementation actually restores or replays learned state. Fresh-process bootstrap/eligibility and timestamped command replay are candidate mechanisms only when used; in that case require actual arm-specific replay/handover validity before task scoring. Retain strict same-input reproducibility; independently justify any live-image behavioral-state/physical-command agreement criteria using separate prospective development data, not the maxima of the earlier failed numerical diagnostic. Do not alter or retroactively pass existing gates. Initialization qualification ends before task decisions are scored. Prior failed recovery handover remains a separate immutable result, not a blanket blocker for ordinary clean-start navigation.

Train only on admitted TRAIN demonstrations; labels may use measured ground truth. Deployment receives RGB/history/goal/topological images only; ground truth may initialise and evaluate, never select nodes, correct actions or terminate a policy. Freeze the training budget and checkpoint-selection rule before starting: optimizer, LR/scheduler, BatchNorm treatment, augmentation, replay ratio, effective batch/accumulation, precision, seed and epoch/update budget. The existing 20-epoch selection is prior development evidence; a new claimed replication requires exact artifact/source provenance and a predefined selection rule, not choosing the best live result.

## Stage 2: GNM and NoMaD compatibility and adaptation

First qualify each model on the same admitted trajectory identities and its official model-specific sampling/preprocessing. Check strict load, output units/shapes, loss masks, finite gradients, parameter change, save/reload and deterministic seeded sampling where applicable under a separately authorised small technical contract. NoMaD needs its diffusion/goal-mask loss and EMA handling; ViNT's trainer/checkpoint resume path is not automatically valid. Record admitted pair counts per model because horizons differ.

Define equal budget before outcomes on two axes: a common demonstration/scene allocation and a common measured compute budget (GPU-seconds, peak memory, inference wall-clock limit). Report optimizer updates/epochs/pair exposures additionally. Equal epochs alone do not mean equal data exposure or compute; exact equal updates may disadvantage the diffusion objective. Freeze the chosen primary budget and justified model-specific optimisation settings, plus a sensitivity comparison if affordable, before results. Use the same number of independent training seeds per adapted model; distinguish training-seed replication from repeated policy sampling. If a model cannot meet the declared runtime budget without changing its native algorithm, report that constraint rather than silently reducing NoMaD diffusion iterations or dropping failed runs.

## Stage 3: matched three-model system comparison

After compatibility and intended-start qualification, compare predeclared ViNT, GNM and NoMaD checkpoint roles on identical route/goal populations and task-level motion/time budgets. Keep downstream controller, measured contact definition and task completion semantics common. Explicitly freeze whether the system comparator uses native stopping or a shared calibrated stop layer; model-specific distance scales make a shared numeric threshold unjustified without development-only calibration. The three native stacks estimate system differences, including their declared adapters/history/sampling/stopping. A pure checkpoint effect is identifiable only in the within-ViNT fixed-stack contrast; do not claim the cross-model design separates backbone from downstream system effects. NoMaD sample count/RNG/aggregation and each model's history window remain declared algorithmic differences, not hidden treatment changes.

| Metric | Definition and denominator |
| --- | --- |
| Correct stop | Latched policy stop inside frozen goal region; all attempted episodes, plus stops denominator |
| Wrong stop | Latched policy stop outside region; all attempts and all stops; never folded into timeout |
| Completion | Correct stop without non-floor fixture contact; all attempts |
| Collision | Any measured non-floor fixture contact; all attempts; additionally event count, moving time and path/rotation exposure |
| Delay | Correct-stop cumulative proportion by fixed simulation time over all attempts; report actual terminal times and competing wrong-stop/crash/operator-stop classes. Horizon censoring applies only to intact unfinished episodes; do not average successes alone as overall speed |
| Runtime delay | RGB-ready to command submission plus inference/preprocessing/controller breakdown; p50/p95 with sample counts and deadline misses, including diffusion budget |

Arrival without stop, missed arrival/overshoot, abstention, timeout, crash, integrity failure and operator stop remain distinct secondary outcomes. Exact-node localization is primary where a topological recovery task is separately declared; ±1 node is secondary, not interchangeable with goal-region completion. No goal radius or stopping criterion is tuned on evaluation outcomes.

Freeze terminal precedence, measured exposure window and any post-stop tail separately. Earlier qualifying outcomes are not erased by later collection timeout; integrity failures prevent efficacy interpretation. All attempts remain in the ledger; no outcome-based replacement, retry or omission. Predeclare only narrowly permissible technical retry rules before launch; report both attempts. Halt on integrity failure. Progress beyond each small stage needs evidence-based justification; no reopening the halted recovery pilot.

Analyse paired route-level differences and scene-group uncertainty; frames, repeated tensors, diffusion samples and seeds on one route are not independent starts. Report per-route/per-seed counts and uncertainty, including negative outcomes. Use a power/precision justification based on independent scene groups before any confirmatory sample size is chosen; the current small fixtures support engineering diagnosis only. Goal-swap/goal-blind and deliberate-contact/no-contact controls must be declared and qualified, without consuming sealed confirmatory data for calibration.

## Freeze blockers and next decision

1. Cleanup outcome remains to be established; no resource-validation rerun is needed for this planning document.
2. Complete dataset/admission/processing/split/checkpoint manifests and source/runtime digests must be reconciled without loading held-out images or weights during preparation.
3. Freeze actual intended-start eligibility, all policy mutable-state/history/reset fields and supported acquisition provenance; learned-handover criteria remain unresolved.
4. Freeze task controller/chain/stop contract, model-specific adapters and budget interpretation, and exact finite staged launch IDs before any training/evaluation. Predeclare pilot advance/stop criteria, minimum admissible measurement completeness and uncertainty/precision decision rule before outcomes; no automatic expansion.
5. Independently replace/seal confirmatory specification if an uninspected test is required; do not reuse exposed specification as uninspected.

Next action is bounded review of this preparation and selection of the first compatibility/initialization contract. Review is not executable freeze or launch permission. All runtime evidence remains outside Git; only authored planning documents may be committed after review. Prior freezes/failed experiments are immutable. No efficacy, safety, sim-to-real or superiority claim follows from this plan.
