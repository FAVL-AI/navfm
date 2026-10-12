# NoMaD accessed-pilot scoring result v2

Branch `agent/research-three-model-plan`; execution freeze `bebf498395c6097b2825679a4c1847bf87f32795`. The single authorized NoMaD process **PASS**: release plus three previously selected EMA deployments, 32 fixed pairs/role and four fixed coupled draws/pair give **512/512 attempted/returned/valid outcomes**, zero missing and invalid rate 0/512. All four strict loads/state fences and the completed scoring/dataset transactions verify. No retry, reselect, GNM rerun, adaptation, collection, simulator/navigation or robot process occurred.

The already accessed two-layout/four-route kinematic pilot has 16 positive and 16 cross-route negative pairs. All four draws contribute equally to expected error; no oracle-best sample. Positive ADE/FDE cover the common first five waypoints in metres; temporal-distance labels are steps. Negative category target 20 is artificial and separate from physical distance. This is neither a genuinely uninspected/independently sealed benchmark nor executed navigation.

| Fixed role | Positive ADE m | FDE m | Temporal MAE steps | Negative category MAE | Native wrapper ms |
|---|---:|---:|---:|---:|---:|
| Release | 0.059792305 | 0.105892690 | 3.929195 | 17.024407 | 25.020001 |
| Selected seed 0 | 0.010253757 | 0.018566488 | 2.894875 | 9.822191 | 25.120338 |
| Selected seed 11 | 0.012480807 | 0.023224216 | 2.988469 | 9.667485 | 26.362067 |
| Selected seed 22 | 0.007175758 | 0.012866859 | 3.161428 | 8.857212 | 25.862168 |

| Role / route index | ADE m | FDE m | Temporal MAE steps | Negative category MAE |
|---|---:|---:|---:|---:|
| Release / 0 | 0.057378816 | 0.104352843 | 3.462102 | 17.421570 |
| Release / 1 | 0.069950387 | 0.121398189 | 4.370671 | 17.256589 |
| Release / 2 | 0.055835327 | 0.096008797 | 4.369191 | 17.510938 |
| Release / 3 | 0.056004689 | 0.101810930 | 3.514814 | 15.908531 |
| Seed 0 / 0 | 0.013921430 | 0.025169561 | 3.864269 | 10.223456 |
| Seed 0 / 1 | 0.009324125 | 0.015946918 | 1.968781 | 10.084004 |
| Seed 0 / 2 | 0.006604249 | 0.012110329 | 2.333159 | 9.751431 |
| Seed 0 / 3 | 0.011165224 | 0.021039144 | 3.413290 | 9.229872 |
| Seed 11 / 0 | 0.015822093 | 0.029764917 | 3.905433 | 8.905727 |
| Seed 11 / 1 | 0.011553176 | 0.020997740 | 2.071162 | 10.195402 |
| Seed 11 / 2 | 0.008596027 | 0.015396046 | 2.648773 | 10.442477 |
| Seed 11 / 3 | 0.013951932 | 0.026738163 | 3.328508 | 9.126336 |
| Seed 22 / 0 | 0.012347561 | 0.023162049 | 4.843544 | 5.661736 |
| Seed 22 / 1 | 0.005191178 | 0.009260305 | 2.242336 | 10.448002 |
| Seed 22 / 2 | 0.004865918 | 0.007585437 | 2.493414 | 10.698627 |
| Seed 22 / 3 | 0.006298376 | 0.011459646 | 3.066416 | 8.620483 |

Each route cell averages four positive or four negative pairs, with four draws averaged per pair. Role means use all 16 eligible pairs/category. All selected aggregate errors are lower than release here, but seed 22 has the lowest waypoint error and the largest selected temporal-distance MAE. No best seed, architecture winner, generalization or navigation conclusion follows.

Raw JSON retains **512 action/distance arrays with content hashes**: actions [1,8,2], distance [1,1]; values finite and exact nested shape retained, original tensor binary dtype unknown after `.tolist()`. Source roles/pair/draw population replay and raw hashes verify. Native file attestation 2250→3768/final 3768; selected dependency 690→1365, upstream 0 initially loaded→17 after. Dataset binding before/after PASS and all 152 admitted artifact hashes remain unchanged. Completed scoring marker binds the PASS ledger/reservation and four output artifacts.

External launcher elapsed **37.548457670s**; saved **37.132759423s** is pre-final-persistence, not end-to-end. The 1800s cap respected. CPU preprocessing mean **21.272625ms/pair** includes input/label preprocessing and excludes CUDA transfer. Synchronized batch 1 native wrapper timing excludes seed setup/preprocessing/persistence but includes NoMaD action decode/get_action CPU roundtrip and transfers inside predict; it is not pure GPU denoising or Orin latency. Collection SDK cleanup remains independently unobserved.

| Checkpoint | SHA256 |
|---|---|
| Release | `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333` |
| Selected seed 0 / update_00236 | `7a6eaa288071a4925f25180385c4cf32430894e068017358d75528d7aaa89ba9` |
| Selected seed 11 / update_00236 | `8bb36d3ca1f206bc93635f28358ef948370e462731d2b67b6e15416d6b7872d7` |
| Selected seed 22 / update_01180 | `4d5e534ecd8056dde1679399702d20225b710811e6a326b5638fbf436e76c723` |

Exact paths are frozen in config/external report, with no smoke-weight substitution or new selection. Evidence root: `/home/favl/navfm-training-evidence/prospective-scoring-v2-nomad-01`. External fixed summary: `/home/favl/navfm-training-evidence/prospective-scoring-v2-consolidation-01/summary.json`, SHA256 `864c768a3e47504ceff5bb4859d163f60e472ef454df4463a08c1235ce44a944`.

| Identity | SHA256 |
|---|---|
| ledger.json | `a22999cf7d11b1cdaaf56a433a15189741583cd990a7f236c9c8344b3eefc3ea` |
| scoring_complete.json | `baaa3cb2ef9698efd09237c10c8858a29d216f66bca6973f69d9cb8f81c914e9` |
| report.json | `4808c7db9661d34281bd60a82b6d49c55a1c190d2bb563939ac76b45b6a8a32e` |
| provenance.json | `8fde4c35d8aacde64ce72a30a699bd4ce9e77b324aba0fb32173fd58adffe960` |
| dataset_binding.json | `0911b11a227bad44b86ff24a4bc8ef4c03adc569269923abde81a5dacbe18c90` |
| observation.json | `626c4fbd0419ea86f420856072b30d8e0d2f763c7cc243971f9ae4fee84c2ea0` |

Validation: exact freeze/source/checkpoint/input/dataset eligibility preflight; expected 512 identities, all finite/retained outcomes, strict-load/state fences, full native provenance, completed scoring/registry/artifact binding, source/input postflight. Canonical workspace was restored to the clean planning branch after child reaping. No tests rerun. Raw arrays, private specifications/RGB/labels, weights and logs remain external; only this authored result is published. No additional runtime is performed.
