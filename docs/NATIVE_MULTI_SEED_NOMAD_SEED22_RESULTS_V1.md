# Native adaptation v1: NoMaD seed 22

The final authorized slot completed **4,720 updates, PASS**, from unchanged source freeze `e94b6968b1d958a7254ac2ca8da42ba1c4d7a686`. [Protocol](NATIVE_MULTI_SEED_ADAPTATION_V1.md). Only NoMaD 22 ran in this milestone; all prior runs/failures are preserved.

Fresh released NoMaD EMA `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333` initialized raw parameters/shadows. Qualified EMA integration unchanged; no smoke/partial/adapted initialization. All 4,720 optimizer/scheduler/EMA transactions completed with finite gradients/raw states/shadows; actual counters 1–4,720, final EMA 4,720. Each five-phase journal count is 4,720; 628 changed parameter tensors. Strict released/resume/EMA deployment reloads and every development model/optimizer/EMA/statistics/RNG fence PASS.

Worker wall 594.188117 s; occupied launcher wall 598.174851 s below 3,600 s. CUDA kernel-active time unmeasured; child reaped/shared integrity PASS. Six consumed reservations total 21,600 s; all slots finished, no retry/extension.

The frozen native development objective selects **update 1,180**; all dev evaluations use RNG 909, goal masks `[0,0,0,0]`, diffusion timesteps `[9,5,0,3]`. Four exposed pairs include only two action-valid common five-waypoint pairs, spacing 0.049994826316833496 m. No goal-masked dev evaluation is claimed.

| EMA / update | Native dev objective | Distance MAE [steps] | Common ADE [m] | Common FDE [m] |
|---|---:|---:|---:|---:|
| Released | 0.010168 | 7.221789 | 0.072812 | 0.131571 |
| 236 | 0.006842 | 7.134837 | 0.030963 | 0.067687 |
| 472 | 0.008698 | 7.152238 | 0.024387 | 0.053173 |
| 1180 — selected | 0.006646 | 6.948804 | 0.026755 | 0.052653 |
| 2360 | 0.008156 | 7.271839 | 0.023944 | 0.050263 |
| 4720 — final | 0.007917 | 7.218577 | 0.034332 | 0.071123 |

Native eight-waypoint loss remains separate from common five-waypoint metrics; native eight-waypoint ADE/FDE was not separately produced. Exploratory repeatedly exposed development data does not establish generalization, stopping or navigation. Selection unchanged, no best-seed choice.

Exposure: 18,880 sample draws/1,704 unique pairs/852 anchors/1,148 RGB endpoints/9,438 negative draws. Separate conditioning masks: 9,444 masked/9,436 conditioned. Per-sample diffusion assignments 18,880; counts retained externally. Optimizer data training-only; dev evaluation-only. Repeated/overlapping examples are not independent.

External root: `/home/favl/navfm-training-evidence/native-multiseed-v1-nomad-seed22-01/`. All 19 artifact hashes verified. Raw/resume containers preserve raw model/optimizer/scheduler/EMA/RNG state; checkpoint resumes additionally record catalog cursor/hash, while final-root resume uses the bound final report/catalog context. Deployment exports contain EMA. No logs/weights/dense provenance in Git.

| Artifact | SHA256 |
|---|---|
| Ledger | `419352eca62eba653db3932fc0a3ea6f741b8f0ced25a1522e892f2ddd2bee35` |
| Report | `11f0ba8e3f5195cec4d6a9232d46b0def270bc12a1f4a1500f870db8c51704d3` |
| Selected EMA `nomad/update_01180/deployment_weights.pth` | `4d5e534ecd8056dde1679399702d20225b710811e6a326b5638fbf436e76c723` |
| Selected raw/resume+EMA `nomad/update_01180/resume.pth` | `db4c000d3d947e3f12763371e0358a93ae618bf9602a9b1cbe60073dc24abd7a` |
| Final EMA `nomad/deployment_weights.pth` | `b0996e20612b46e890d7680a8888340305aa87341f920a859b226de0d5057d69` |
| Final raw/resume+EMA `nomad/resume.pth` | `224a8f672ee8b8426eee32d09eb74775f755221132f749dc417eebb8634ac36e` |

Validation: exact source/input/dependency/schedule/registry/fresh-output preflight; chronological actual optimizer/sched/EMA counters, finite gradients, selection recomputation, strict reload/development fences and 19 artifact hashes PASS. Canonical source ran detached; report branch restored after reaping. Preparation tests/Ruff not repeated for result-only publication. No additional runtime.

Next decision: [all-six development consolidation](NATIVE_MULTI_SEED_CONSOLIDATED_RESULTS_V1.md); no further training follows.
