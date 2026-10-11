# Observer-window v2: acquisition passes, learned handover fails

Recorded 2026-10-10. Frozen analysis decision: **INITIALIZATION_HANDOVER_FAIL**.
The repaired acquisition observer passes both launches; complete initialization/learned-policy handover equivalence fails. No recovery efficacy was tested.

## Scope and preserved evidence

Source/config/finite manifest freeze: `9120decc6376db0f4f5bcece58e2866e488fdace`. Design: `docs/OBSERVER_WINDOW_V2_PROTOCOL.md`; bounded executable review: `gates/redteam/observer-window-v2-executable-review-20261010.md`. All 31 inherited protected files remain byte-identical to `d74927f7f2e88dd75e20f13646dc22f8e05c5671`; its failed reference and six recorded artifact hashes remain unchanged.

Only these two development processes ran, once each:

- `v2-A-s_bend_run_0000-R2_recover-r1-reference`
- `v2-A-s_bend_run_0000-R2_recover-r1-replay`

Both individual traces PASS, including source/asset preflight and postflight. Each contains 42 captures, 114 render calls, 560 physics callbacks and seven pre-kidnap CUDA policy invocations. Totals: 84 captures, 228 calls, 1,120 callbacks and 14 invocations. All 84 capture-image hashes were checked. There were zero post-kidnap policy/recovery invocations, retries or timeouts. Requested learned commands were ignored; frozen scripted commands controlled motion. Ground truth served initialization/evaluation only.

## Acquisition event window

All 12 raw acquisition events are retained: six per launch. Both launches have the same ordered classification. Correct own render product is `/Render/OmniverseKit/HydraTextures/Replicator_01`.

| Event sequence | Active call | Classification | Own acquisition enter/completion/RGB-read ordinal |
|---|---|---|---|
| 0 | null | outside_boundary_call | 0 / 1 / 2 |
| 1 | null | unrelated_product | unrelated product |
| 2 | 113 | superseded_boundary_acquisition | 5 / 6 / 7 |
| 3 | 113 | unrelated_product | unrelated product |
| 4 | 113 | qualified_final_boundary | 10 / 11 / 12 |
| 5 | 113 | unrelated_product | unrelated product |

Native resume registration order 0 is a source-established registration witness, rather than a runtime getter. Actual callback entry/completion/RGB-read order is measured. Native acquisition delegates exactly once before measurement parsing. Event 4 is selected by final completed own-product acquisition order within boundary call 113, before comparing its RGB digest; it matches saved boundary RGB and sensor/simulation time. Outside/unrelated events receive no freshness credit. No old attempt was reclassified.

## Physical history and learned-state comparison

All 38 chronological physical/history comparisons PASS. Root/camera positions, yaw, joints, velocities, controller state, held commands and relative history ages have zero measured pair difference; computed root/world-camera quaternion error is at most 0.000002958 degrees. Maximum grayscale mean absolute difference is 0.2923828125, below the frozen 2.5 bound. Images are not pixel-identical.

Initial simulation time is 1.7250000899657607 seconds in both launches. Boundary time is 4.725000246427953 seconds. Six live history samples correspond to physical steps 6, 12, 18, 24, 30 and 36, with ages approximately 2.5, 2, 1.5, 1, 0.5 and 0 seconds. Sensor and simulation timestamps agree; pair age differences are zero. Public timeline and simulation clocks remain distinct; zero-physics renders do not imply an unchanged public timeline.

Actual learned runtime/backend/checkpoint match. Both use the pinned original CUDA runtime, model evaluation mode, Torch 2.7.0+cu128/CUDA 12.8 and the same GPU. All seven discrete before/after policy states and predictions match, including nodes, search-window selection, flags and counters. Boundary discrete state also matches. Nevertheless, all seven complete numerical invocation comparisons FAIL at the unchanged absolute 0.001 / relative 0.00001 tolerance. Initial pre-invocation state matches; later six pre-states and all seven post-states fail numerical comparison through stored distance history. Full boundary policy state fails.

The table gives maximum absolute differences by invocation; window distances, requested-goal distance, predicted distance and normalized waypoint fail their frozen numerical bound in every row. Requested command differs beyond its bound at steps 0 and 6 only.

| Physical step | Window distances | Requested-goal distance | Predicted distance | Normalized waypoint | Requested command |
|---|---|---|---|---|---|
| 0 | 0.049312592 | 0.005538940 | 0.038307190 | 0.007753916 | 0.005473993 |
| 6 | 0.029499054 | 0.016838074 | 0.007762909 | 0.003321707 | 0.002337801 |
| 12 | 0.032203674 | 0.019866943 | 0.009086609 | 0.005978882 | 0.000000000 |
| 18 | 0.044162750 | 0.014049530 | 0.018478394 | 0.006122112 | 0.000000000 |
| 24 | 0.046974182 | 0.005905151 | 0.008705139 | 0.009395599 | 0.000000000 |
| 30 | 0.055519104 | 0.013504028 | 0.055519104 | 0.011553735 | 0.000000000 |
| 36 | 0.068376541 | 0.001548767 | 0.068376541 | 0.006015003 | 0.000000000 |

Worst deviations are 0.068376541 for window/predicted distances, 0.019866943 for requested-goal distance, 0.011553735 for waypoint and 0.005473993 for requested command. Matching discrete outputs does not override the numerical gate. Pixel differences within the image bound coexist with numerical differences; their contribution and any runtime numerical variability are not isolated. Neither rendering nor CUDA is established as the cause. Original pilot image mismatch cause remains UNKNOWN.

## Halt and next decision

Frozen pair gate records `passed=false` and `continue_next=false`. Execution STOPPED after this pair. Cross-repetition/cross-arm validity and learned-policy handover remain unvalidated; no recovery, safety or general start-procedure claim follows. The original pilot remains INCONCLUSIVE with 24 arm attempts unrun. No further launch, threshold change or efficacy batch is authorised by this result. The next decision is a separately reviewed, narrowly bounded input/numerical-equivalence investigation, preserving these failures. Held-out geometry remains sealed, illumination paused and robot actuation unauthorised.

## Validation and artifact safety

76 focused tests PASS. Final source verification: ruff PASS, mypy (89 files) PASS, and exactly three preserved failures:

- `tests/test_environment_identity_v8.py::test_v8_accepts_the_repaired_tree`: archived identity FAIL versus PASS.
- `tests/test_environment_identity_v8.py::test_attempt_001_pre_capture_is_preserved_byte_for_byte`: missing archived `runs/bo10/intervention/arm_a/pre_capture.json`.
- `tests/test_environment_identity_v8.py::test_regeneration_on_an_unchanged_tree_is_idempotent`: REFUSED versus FROZEN.

Docs-only completion uses diff/attribution checks; source verification was not repeated. Evidence remains external at `/home/favl/navfm-runtime-evidence/replay-recovery-validation-v2-20261010-01`. No runtime artifacts, images, logs or weights are committed. Frozen analysis is unchanged; the difference audit is descriptive read-only analysis of saved records.

| External artifact relative to evidence root | SHA256 |
|---|---|
| `analysis.json` | `f5e50a41a45d3f688e9976e8da02c9f17b5603a8735ee425d091be404cee077f` |
| `ledger.jsonl` | `b887e7ef2d41d21b543b047286021aa3558307549111c9df52acfef2bc962aa0` |
| `pair-difference-audit.json` | `336b3d472adf64af519b1ee5b27a3df438ddb289f0c93c416833f6e07f0cd1ab` |
| `verification.log` | `828a624b86d0416bedf456aa80e0ad97b50259d4a3b1e3be09b7979d549936cc` |
| `v2-A-s_bend_run_0000-R2_recover-r1-reference/trace.json` | `36598fd6bb4391598286616b7a4896c653866d823b32af1f695c73dcee747104` |
| `v2-A-s_bend_run_0000-R2_recover-r1-reference.log` | `2097a7ab49709d104a118a0ca0a98e0e3fe004c9b3e1a07bb368c9969f4ee144` |
| `v2-A-s_bend_run_0000-R2_recover-r1-replay/trace.json` | `896812e0b294fef9af1116ed7232a6a566917e5377604f6eabd57e052cd23153` |
| `v2-A-s_bend_run_0000-R2_recover-r1-replay.log` | `f2f1154bde21d01db2cace80191bdae06ecb5dfa3a4f74b66c0df36404254be4` |
