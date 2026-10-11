# Initialization/history diagnostic result v 2

Owner: Frank Asante Van Laarhoven <frankleroyvan@gmail.com>.

**VERIFIED ON TWO SCRIPTED TECHNICAL CASES:** fresh-process command replay passes the frozen observable-state and six-frame history contract on both known development cases and both fixed repetitions. The original pilot image-mismatch cause remains UNKNOWN. The halted recovery pilot remains INCONCLUSIVE; no recovery or safety claim follows.

## Frozen scope and execution

Version 2 was independently reviewed and frozen at `0393d46e814c80f2cc53ff9570af2c4015da2e7a`. All 18 version 1 frozen files remain byte-identical to `f831a110e6854c919a21c8397eee950cf79b77fd`; the original prospective freeze `54bfc239b3f8d4e5443212822582711b78925bbd` is preserved. Version 1's failed attempt remains recorded without retry or retrospective repair.

All eight declared processes completed PASS in fixed order: `s_bend_run_0000-r1-reference`, `s_bend_run_0000-r1-replay`, `s_bend_run_0001-r1-reference`, `s_bend_run_0001-r1-replay`, followed by the same four identifiers with `r2`. There were zero retries, timeouts, unknown readbacks or source/asset drift. Both mechanical continuation gates passed. The evidence contains 376 captures, 1016 orchestrator calls, 24 eligibility captures and 16 method traces. No learned model was invoked; policy-state comparisons use the initialized proxy only. Ground truth was used for initialization/reset and evaluation.

## Startup and observed clocks

Each process used exactly one unqualified zero-delta bootstrap followed by three fixed live eligibility frames. Bootstrap changed public status STARTING to STEPPED. Simulation time stayed at 0.058333336375653744 s and controller feedback remained zero: **zero physics advancement**. Public timeline time nevertheless advanced from 0.1666666716337204 to 0.2500000074505806 s. The bootstrap sensor time was zero and its image received no observation/history credit.

Every subsequent positive scripted/conditioning call had ten physics callbacks and the required 1/12 s simulation advance; every zero-delta rerender had zero callbacks and zero simulation advance. All qualified captures had sensor time equal to simulation time. Actual eligibility DLSS mode was 0; the preserved transition to mode 2 occurred after goal conditioning. Readback/provenance checks passed. This resolves the version 2 startup eligibility contract, separately from the original paired-image mismatch; it does not isolate an underlying simulator defect or historical carryover cause.

## Matched method comparisons

All within-reference comparisons and cross-repetition comparisons were retained. Continuous reference cross-repetition comparisons pass 2/2. The table distinguishes reproducibility from equivalence to the reference.

| Method | Within-reference | Same-method cross-repetition | Overall full start contract |
|---|---:|---:|---|
| Command replay | 4/4 PASS | 2/2 PASS | PASS on the two tested cases |
| Direct root reset | 0/4 PASS | 2/2 PASS | FAIL |
| Direct full observable-state restore | 0/4 PASS | 2/2 PASS | FAIL: temporal/index history |

Command replay has zero measured physical/controller-state deltas, exact history indices and ages, and maximum six-buffer grayscale MAD 0.7037890625, below the unchanged 2.5 bound. Continuous-reference cross-repetition maximum MAD is 0.2838411458. Pixel values are not identical. The first numeric image difference in each declared chronological initial/script sequence occurs at initial observation step 0. All 148 paired snapshots (37 per pair) satisfy the comparison bounds; there is no replay bound violation.

Direct root reset leaves joint/velocity/controller/history differences: maximum joint-position delta 0.0016775131, joint-velocity delta 1.9890737422, root-velocity delta 0.1681423594, controller-integral delta 0.0025083185, history MAD 18.6282682292 and age error 2.5000001304 s. Its tiny root-pose difference does not establish equivalent initialization.

Direct full restore passes the observed physical/controller and image bounds (maximum history MAD 1.4315885417). It fails full history equivalence because the previous five relative ages shift by approximately 0.6666667014 s and the live physical-step index is 44 rather than 36. This demonstrates temporal/index mismatch under the non-restored clock, not a rendering or physical restoration failure. Same-method repeatability does not repair reference equivalence. Comparator first-failing-field order is not temporal or causal ordering.

## Validated recommendation and limits

For these two cases, use a fresh process, the fixed zero-delta bootstrap and three eligible live frames, identical goal/start conditioning, then replay the same 36 commands and form the six-frame buffer from that process's own live captures at physical steps 6,12,18,24,30,36 (stored indices 5,11,17,23,29,35; ages 30,24,18,12,6,0 steps). Require the same measured state/settings/history and provenance guards. The continuous reference uses the same schedule. Root-only teleport or this full observable-state restore does not satisfy the complete history contract.

This recommendation is limited to the tested scripted technical cases and initialized proxy state. Learned-policy handover, arbitrary layouts, recovery rates and robot safety were not tested. Fresh-process replay matching does not explain which hidden component produced the original reused-process image divergence. Version 1's CPU-versus-original-CUDA numerical mismatch remains separately preserved. No remaining prospective recovery starts were run, no tolerance changed and no illumination experiment occurred. Held-out geometry remains sealed and real robot actuation unauthorised.

## Validation

All 45 focused tests pass (13 version 2, 20 version 1, 12 prospective pilot); named source lint and helper/runner type checks pass. Final `make verify` with `NAVFM_UPSTREAM` passes ruff and mypy and fails exactly the three preserved environment-identity tests:

- `test_environment_identity_v8.py::test_v8_accepts_the_repaired_tree`: archived identity FAIL versus expected PASS.
- `test_environment_identity_v8.py::test_attempt_001_pre_capture_is_preserved_byte_for_byte`: missing archived `runs/bo10/intervention/arm_a/pre_capture.json`.
- `test_environment_identity_v8.py::test_regeneration_on_an_unchanged_tree_is_idempotent`: REFUSED versus expected FROZEN.

The full-check log remains external at `/tmp/navfm-initialization-v2-final-verify-20261010.log`. Only scoped engineering-branch publication and a draft pull request are authorised after outgoing-history checks; no force push, history rewrite or merge. Future learned-policy/recovery experiments require a separate reviewed prospective protocol; this diagnostic does not reopen the halted pilot.

## External evidence identities

Raw images, traces, logs and weights remain outside git. Artifact paths below are relative to `/home/favl/navfm-runtime-evidence/initialization-diagnostic-v2-20261010-01`.

| External artifact | SHA256 |
|---|---|
| `analysis.json` | `46aa7b85b54ec217f57b9ca86872c932a8cdb49b7331c23f144f90abc7db1c91` |
| `ledger.jsonl` | `075240176800dd22eaa1755b2dc2faa7b9e9045b9c0ae940fd2ef3c59cf331d2` |
| `s_bend_run_0000-r1-reference/trace.json` | `ead4342f56f07c5660eadde05edc2a384f956ffbffc03ba2082809834daf811e` |
| `s_bend_run_0000-r1-replay/trace.json` | `452432e8d529836dd2ab1bde3b746a9ca3304959297638fa37885e63d1807f23` |
| `s_bend_run_0000-r2-reference/trace.json` | `85f3e00db0f372ac8197ba3ab46f460d5eb01b79208721bc65bc2d16a5db1f4b` |
| `s_bend_run_0000-r2-replay/trace.json` | `624dd20cb5a5caf2a54e0d7fd89005881e8ed53e90d0e951d12c6a2fbbebb947` |
| `s_bend_run_0001-r1-reference/trace.json` | `13889b8cd0019b4a843a23e6fcbe108c8e283b01d2ce782d08b07986a7785257` |
| `s_bend_run_0001-r1-replay/trace.json` | `b986337f863d6cf6d06efba68b3179291f7a78076c7394ef293f66b9fe8b0b70` |
| `s_bend_run_0001-r2-reference/trace.json` | `9870723cacbea0835397aaeea6a5d0b4f56e8463f77043d83e01fdf03d5f1ec9` |
| `s_bend_run_0001-r2-replay/trace.json` | `1f88572d0ed6d9f38fbe5226e9c3835dca9c3b43723cdbdc75ba77946f009499` |
| `s_bend_run_0000-r1-reference.log` | `afb4d1cbc0b6ca3b8e06b92355241222af9c0ab6104f4d30d6c1a5341a067f21` |
| `s_bend_run_0000-r1-replay.log` | `5093651a2168211a551a106a57219cbf93bf76e44400bb057719eb67c08d3c9c` |
| `s_bend_run_0000-r2-reference.log` | `6eba32531955b3a6b4704fdf1aae646a6b62bdd82d14d22c9001e98c886b7917` |
| `s_bend_run_0000-r2-replay.log` | `60a05a3dbec6024054b099f5f273f772baaf479ef24eb763b0cf82c488ce7814` |
| `s_bend_run_0001-r1-reference.log` | `c9740410a9b2d2d59d5113beb6e9549d88bd661365c4b19b8e8855231e90f103` |
| `s_bend_run_0001-r1-replay.log` | `09e4721ecb9e29cc9544f8d140c11a332ced9bbdf1dbdceb39f0a2020f19d35e` |
| `s_bend_run_0001-r2-reference.log` | `e2036e28a9972210619d9937a0b39548ad85500289daf5adece47a266cfa5ac4` |
| `s_bend_run_0001-r2-replay.log` | `c3d47935f7ab3e0ae8ef9e161eb220ff5c4caeac0ac23f4233f152a634c56783` |
