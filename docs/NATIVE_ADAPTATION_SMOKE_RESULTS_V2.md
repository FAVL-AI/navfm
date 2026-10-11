# Native adaptation smoke results v2

Source freeze: `7c0b4096009a70c8aff0b5f73e9ae3f8f664510f`. Exactly two fresh capped workers ran: **GNM PASS**, **NoMaD FAIL**. Both children were reaped and both shared pre/post provenance records passed. These are training-pipeline engineering outcomes, not navigation, comparative adaptation efficacy or deployment qualification. The original v1 failure remains unchanged.

| Measured result | GNM | NoMaD |
|---|---|---|
| Worker wall time / 150-second cap | 6.722 s | 4.464 s |
| Strict released checkpoint load | PASS | PASS |
| Completed optimizer+EMA transactions | 6 (no EMA in GNM) | 0 |
| Actual optimizer step readback | 1 through 6 | 1 in preserved partial state |
| Finite gradient guards | All six recorded PASS | First backward passed the source guard before optimizer execution; no completed update record |
| Changed state | 326 parameter tensors after six updates | 628 of 645 raw **state** tensors changed after the partial first update; not a measured parameter-only count |
| Strict resume/deployment reload | Both PASS | NOT ASSESSED |
| Selected output | Raw GNM checkpoint | No qualified adapted/EMA deployment checkpoint |
| Development isolation | Eval/no_grad fences passed before and after | Initial fence passed; post-update evaluation/reload NOT ASSESSED |

GNM's six native training losses were 0.0858665, 0.2092904, 0.0667551, 0.0248817, 0.0155517 and 0.0103472. Every optimizer step readback matched 1..6; training used 24 optimizer-sample draws, four fixed pairs and two observation anchors, not 24 independent examples. Development received zero optimizer updates. The unchanged state/RNG/EMA evaluation fences and strict full-state reload passed.

GNM development performance **worsened** on the two eligible fixed positive pairs: common five-waypoint ADE 0.0424609→0.0496082 m; FDE 0.0745936→0.1006221 m; distance MAE 7.28387→9.20938 steps (distance evaluation includes the declared negative cases). A falling training loss is not evidence of improved generalization. These tiny reused development pairs do not support a ranking or held-out claim.

NoMaD strictly loaded the released EMA checkpoint into its raw model and EMA shadow and completed its initial development evaluation. The first native loss/backward/AdamW step and scheduler step preceded `ema.step(model.parameters())`, which failed at installed `diffusers/training_utils.py:379` with `AttributeError: module transformers has no attribute deepspeed`. Diffusers 0.29.2 requests the legacy `transformers.deepspeed` export; installed Transformers 4.57.6 instead has `transformers/integrations/deepspeed.py`. This is an EMA integration/API compatibility failure, not a failed released checkpoint load or demonstrated model incompatibility.

The report's empty completed-update list does **not** mean zero optimizer calls. A bounded CPU-only read of the preserved partial checkpoint found step1 in all 628 optimizer parameter states, 628 changed raw state tensors versus the hash-verified release, and all 645 raw state tensors finite. Its EMA counter advanced to1; the failure occurred before any shadow update. Thus no complete optimizer+EMA transaction or six-update result passed. No training retry, package repair or long run followed. Initial NoMaD common-five ADE/FDE were 0.0728122/0.131571 m; there is no post-adaptation comparison.

The [v2 dependency amendment](NATIVE_ADAPTATION_DEPENDENCY_V2.md) preserves its preparation history: a 60-second CPU snapshot timeout caused by repeated package-tree traversal; all four batch failures under NumPy 1.26.0; successful capture03 after isolated LMDB1.7.5/NumPy1.26.4 installation; validation04's legitimate generated Torch path rejection; then final binding/generated-object correction and validation05 PASS. Both native trainer/model/loader paths and all four CPU batches passed before GPU. The inherited Isaac runtime was not modified; no dataset/cache rewrite or namespace alias was used. Installed code/binary members matched the authentic pinned wheels (LMDB6, NumPy508). The final proof binds consumed source/data/dependency hashes; only its own self-hash is excluded.

Validation: five focused v2 CPU controls, Ruff and diff checks passed; the prior16 reviewed implementation controls were retained without a broad rerun. Population grew 2975→2980 with all prior nodes preserved. Runtime source, input and installed dependency pre/post checks passed. All **11** ledger-listed artifact hashes were independently recomputed after child exit.

Evidence root: `/home/favl/navfm-training-evidence/native-adaptation-smoke-v2-01`. Ledger SHA256: `9c1083c5675faee7c252ccef7eb22eb7382678be4ab617ea6a111224edc8cc27`. `result-integrity.json` and `nomad-partial-state-audit.json` are external descriptive reductions; the original ledger/report/checkpoints remain unchanged.

| Artifact | SHA256 |
|---|---|
| `gnm/report.json` | `f98254d7936afd36601abc8faf675109cd6f7aa3fbda7328fdb8bbf1646ac770` |
| `gnm/provenance.json` | `21c1e95ad10fe0866e9b5d8e613f0767189ec5dbfdc914609048dbc462d47639` |
| `nomad/report.json` | `80ecafc7f639eb295b0cf1ef57076fd2f4291cdba0d89cd19db95334f9baa872` |
| `nomad/provenance.json` | `a75be4bed36fcd2a2ee398987a7c3a6790cd2d83dd1fe3be16e206e473db1c2f` |
| `gnm/deployment_weights.pth` | `71e9111bd79555e6fde9ecb8bd9e7dfe84a5e570faae25164b0975476b425e31` |
| `nomad/partial_state.pth` | `8d15d7ffd756e7eefde14c74df185bd1cdee877084597d2425975f15c01c5f80` |

Historical ViNT evidence remains separate: the [v1 reconciliation](NATIVE_ADAPTATION_SMOKE_V1.md) records three preserved 20-epoch/4720-update engineering curves, 15/15 saved checkpoint hashes and 34/34 source hashes per seed matched. Stale six-step/default metadata does not override the epoch records. No independent reproduction or current held-out performance is claimed.

Next decision: a versioned, source-authenticated EMA integration compatibility repair, first exercised by a bounded CPU parameter/shadow/counter/state-roundtrip check through the actual installed API. It must preserve the native EMA rule and distinguish the moved integration API from an invented alias. Only after that closure passes should a fresh capped NoMaD smoke be considered; no automatic retry or long training is selected here. All weights, raw logs and partial states remain external; no artifacts enter Git.
