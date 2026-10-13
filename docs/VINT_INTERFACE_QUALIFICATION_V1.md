# Native ViNT interface component qualification v1

Status: REVIEWED SOURCE FREEZE / native checkpoint component NOT RUN / pair scoring FORBIDDEN. Branch `agent/research-three-model-plan`, baseline `a703d2f96b5ad8706d639d24e553d3e74eeb9881`. GNM/NoMaD pilot source/results remain closed and immutable; no retuning/reselection. This milestone qualifies an interface, not performance.

| Fixed identity | SHA256 |
|---|---|
| Official release | `155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f` |
| Prior selected seed0 / epoch20 | `c7686983099080649dde0eaf79575149c26239321e23cf96788b3dd25b0d5d7c` |
| Prior selected seed11 / epoch20 | `f6383c6a59bdd3dad980cc64e934edfe378ccceb942650c12c673309792bb44c` |
| Prior selected seed22 / epoch20 | `e94a42fe547644b01b0093a3e8f550e78668f14e61786b1c9e2c25e446d616a1` |

All four weights were rehashed without loading tensor contents. Preserved reports/epoch20 curve entries bind the adapted hashes and20epochs×236updates=4720; [prior reconciliation](NATIVE_ADAPTATION_SMOKE_V1.md) explains stale top-level six-step/default metadata. Prior research records selected epoch20 using development distance evidence; this protocol fixes those identities without a new choice based on pilot outcomes. Historical training-engineering records do not establish independent reproduction or navigation performance. Exact paths/report hashes and source closure are bound in config/external provenance.

Pinned native `vint.yaml`, `data_utils.py` and ViNT forward support85×64 RGB, five history frames plus current in chronological18channels, separate3-channel goal, ImageNet mean/std after native aspect crop/resize/[0,1] conversion. Native architecture is built as ViNT, not GNM. Forward already cumulatively sums XY deltas into five waypoints and normalizes its cosine/sine heading pair; raw action shape[B,5,4], distance[B,1]. Shared five-waypoint metrics are structurally compatible only after one XY multiplication by0.049994826316833496m; no second cumsum, angle-as-XY or temporal-distance-as-metres conversion. Near-zero/nonunit heading, wrong context/shape, nonfinite output or denominator mismatch fails component admission.

**One process,150seconds total**,145-second child allowance plus5-second cleanup reserve. Serial four identities, two fixed synthetic chronological histories/goals per identity, one native forward plus one strict-reload forward each (eight batch forwards total). Synthetic RGB128×96 fixed modular ramps at ticks0..5 and goal9, cases0/1; no dataset pair, trajectory label, private geometry/RGB, simulator or model score. Seed4080 is fixed; exact reload-output agreement is an observed-session control, not universal CUDA determinism. Raw nested output arrays and their content hashes are saved before validation; explicit output-shape fields are added only after validation and reload. Strict source-authenticated release loading permits the legacy trusted object container only for the pinned release; adapted state dictionaries use safe loading.

Evaluation reuses the existing native state/RNG fence under eval/no_grad. No optimizer or training step exists; setup/model construction can consume RNG, while prediction restores Python/NumPy/Torch/CUDA RNGs and module modes and rejects state mutation. Strict reload must reproduce state and native outputs, all distance/action values finite and heading direction defined. Installed/upstream attestation is checked before and after; native attestation is also checked in finalization; the external closure adds only three component sources, preserving package/generated rules. Atomic partial reports/provenance plus fail-closed final marker/registry retain every failure; one external attempt, no retry or automatic scoring. Source/input freeze precedes GPU construction.

```sh
PYTHONPATH=src NAVFM_UPSTREAM=/home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01/upstream /home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/run_vint_interface_qualification_v1.py --freeze FULL_REVIEWED_COMMIT --out /home/favl/navfm-training-evidence/vint-interface-v1-qualification-01
```

Seven-file preparation boundary: adapter, component worker, one-shot launcher, config, this protocol, tests and population manifest. Ten focused controls PASS, including actual native CPU preprocessing/context normalization, real strict missing-key rejection and eval/RNG/mutation checks, plus pure horizon/heading/units/denominator/nonfinite and150-second persistence-overrun controls. CUDA was hidden for tests; no real-checkpoint/model component construction yet. Torch/upstream node ownership and digests retain all prior nodes. No full software suite is rerun.

CAD handoff: one bounded local PATH availability check found no CAD Exchanger/HOOPS executable. No installed version/license capability, STEP export or core geometry validation is established. Preserved manufacturer Parasolid remains available but unconverted; [the existing conversion packet and unsent manufacturer request](M3PRO_CAD_CONVERSION_PACKET_V1.md) are the concrete handoff. No install, purchase, network search, message, simulator/plant candidate or robot action occurred.

Next: publish the reviewed source/config commit and exact preflight, then only the authorized component qualification. Even PASS does not include ViNT in pair scoring: publish the measured qualification/interface first, then separately freeze/authorize any three-model evaluation. Raw weights, outputs/provenance and CAD remain external; no generated artifacts in Git.
