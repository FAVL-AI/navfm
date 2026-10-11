# Native NoMaD EMA smoke v3 result

The single fresh-release NoMaD smoke **PASS** verifies adaptation plumbing, not learning benefit or navigation. Source freeze: `1e436983dd75bfa0632934a7c1def74cbc1e5164`. The prior v2 partial failure and GNM result are preserved; GNM was not rerun.

The only integration change replaces the two removed Diffusers 0.29.2 lookup expressions with the authenticated Transformers 4.57.6 integration API. Native EMA math, data, optimizer, normalization and six-update budget remain unchanged. No installed package was changed. [Reviewed contract](NATIVE_EMA_INTEGRATION_V3.md).

| Measured check | Result |
|---|---|
| Actual CPU EMA control | Counter 1 copies trainable/frozen values; counter 2 matches nonzero native decay; serialized restore gives identical next shadows |
| CPU native closure | PASS, 17 imports, NoMaD train/development batches, origin/hash validation |
| GPU transactions | Six COMPLETE backward/optimizer/scheduler/EMA transactions; finite gradients, updated model and shadows |
| Actual readbacks | Optimizer 1–6, scheduler 1–6, EMA 1–6; final counter 6 |
| Changed parameters | 628 parameter tensors changed from fresh release |
| Strict loads | Released initialization, complete resume and EMA deployment reload PASS |
| Development isolation | Successful fenced evaluations before/after; no optimizer/EMA/model-stat/RNG mutation by evaluation |
| Resource completion | CUDA; worker 7.120642 seconds under 150-second watchdog; child reaped |
| Provenance | Shared pre/post integrity PASS; all six ledger artifact hashes verified |

Raw initialization is the released checkpoint, with its released EMA copied into the raw model and initial shadows. Release SHA256: `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333`. The exported deployment role is EMA. Six updates use batch 4: 24 optimizer-sample draws over four fixed pairs/two anchors, not 24 independent observations. Train losses are 0.142650, 0.014614, 0.005083, 0.010680, 0.011108 and 0.009296. Seed 0; Torch 2.7.0+cu128/CUDA 12.8; deterministic algorithms, cuDNN benchmarking and cuDNN deterministic mode are false.

The same two eligible development pairs use five physical waypoints at 0.0499948263 m spacing. NoMaD's native horizon remains eight. Common ADE changes 0.072812 → 0.066702 m, while FDE worsens 0.131571 → 0.141086 m and distance MAE worsens 7.221789 → 7.402651 steps. This tiny plumbing smoke does not establish adaptation improvement. GNM and NoMaD are now independently smoke-qualified; no long training, physical-plant qualification or live navigation was performed.

## Preserved evidence

External root: `/home/favl/navfm-training-evidence/native-adaptation-smoke-v3-01/`. Evidence includes the six-transaction phase journal, batches, pre/post provenance, process log, strict resume and EMA weights. Native file records number 2242 before / 3762 after; selected dependency objects 1231 / 1365; upstream objects 4 / 17. These counts describe imports at each attestation, not identical namespace populations.

| Artifact | SHA256 |
|---|---|
| Ledger | `575d2588348a9ed7f3930d3ca354d0937d080f4feb0e1dbc0bc5336d5bad340c` |
| Report | `a05626a3fbbd1183cd946541a58d8c7c9fc0154d213fe9e7d7966d3d02ddd85d` |
| Provenance | `7695a7ef62cb35980237715ba25d56ea7445f93bee8a428bc9ba49f578d31608` |
| Resume | `3b3cff77359ad5e8b8bb9e4161b800821b3155e9e343561cc96a999410680650` |
| EMA deployment | `9b8e3d5442676aeda12f8901d36cc9c9a66dc526d9c85dc63b8a6834d3cbcd5f` |
| CPU proof 02 | `a024f2020198df71c16e3f9a0923609f33f8fbe3f19b0135fcef3af3856db310` |

Five focused controls and Ruff passed. The first CPU invocation failed before native imports because its project import path was absent; that report remains external. Corrected proof 02 passed before the frozen GPU attempt. An initial lint invocation reported that Ruff was absent from the worker environment; the installed standalone Ruff performed the successful check. Neither preparation failure is a model outcome. All old freezes and generated evidence remain outside the report-only commit.

Next decision: select and freeze any longer adaptation experiment separately using qualified release initialization, declared split fences and selection rules; the smoke does not justify a performance claim or automatic continuation.
