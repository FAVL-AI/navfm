# Offline numerical diagnostic v1 result

Recorded 2026-10-10. **Identical input/state repeats are bitwise stable in this bounded offline test. Preserved reference/replay input differences reproduce the numerical mismatch.** The existing initialization/learned-handover FAIL remains unchanged; no efficacy was tested.

## Fixed scope and execution

Freeze `32b83460839fbad96267ae9f3acbf81543903ad2`, design `docs/OFFLINE_NUMERICAL_V1_PROTOCOL.md`, manifest `configs/eval/offline_numerical_v1.json`. Only `offline-numerical-v1-p1` and `offline-numerical-v1-p2` ran in the original pinned CUDA executable. Both PASS, 42 calls each: 28 isolated calls (all seven saved reference prestates, two input arms, two repetitions) and 14 full-sequence calls (one seven-invocation sequence per arm). Total 84 calls; zero retries/timeouts/new images/simulator launches/post-kidnap decisions. All commands were recorded and never executed. Source/assets were checked before/after; prior freezes and failures remain immutable.

Each isolated call restores the full declared policy state/config/search window, wrapper counters and common seeded RNG state. Each full sequence starts from the same initial state/RNG, then retains its own evolving state. Actual model-entry tensor bytes and raw-output bytes are hashed; shape/dtype, full outputs/predictions/states and decision margins are retained externally.

The executable/checkpoint match the original provenance. This does **not** verify every historical global backend flag or library state: original traces did not record them. Evidence hooks synchronize by copying tensors/outputs to CPU and can change execution timing. This diagnostic does not prove global CUDA determinism or isolate the original simulator/image-generation cause.

Observed settings in both processes: Torch 2.7.0+cu128, CUDA 12.8, NVIDIA GeForce RTX 4080 SUPER, four CPU threads, model eval; cuDNN benchmark false, cuDNN deterministic false, deterministic algorithms false (warn-only false), CUDA matmul TF32 false, cuDNN TF32 true, matmul precision highest, CUBLAS_WORKSPACE_CONFIG absent. Numerical/precision flags were read back and not changed. Python/NumPy seeds 0 are explicit offline controls; Torch seed 0 matches the original setup.

## Three comparisons

| Frozen comparison | Count | Identical entry tensors | Numerical agreement | Discrete agreement | Command agreement |
|---|---|---|---|---|---|
| Within-process identical input/restored state | 28 | 28 | 28 | 28 | 28 |
| Fresh-process identical input/restored state | 28 | 28 | 28 | 28 | 28 |
| Same-state reference/replay input contrast | 28 | 0 | 0 | 28 | 20 |
| Full-sequence reference/replay contrast | 14 | 0 | 0 | 14 | 10 |
| Fresh-process repeat of each full sequence | 14 | 14 | 14 | 14 | 14 |

The 28/14 contrast counts repeat seven saved input pairs; they are not independent experimental starts. All identical-input isolated comparisons have identical restored state and RNG digests, and bitwise identical raw outputs. Each arm's full sequence also repeats bitwise across fresh processes. For all 14 representative step/sequence input contrasts, observation tensor hashes differ while goal/chain tensor hashes match. Thus changes in these preserved observation inputs are sufficient to reproduce numerical output differences under this offline execution, without a different initial policy state. This is not a claim that all historical execution variation is excluded.

All seven per-arm predictions reconstruct the corresponding original observer-window v2 predictions exactly: maximum absolute reconstruction delta 0, all discrete fields identical. Both offline repetitions/processes agree. The same per-arm prediction values occur in isolated and full-sequence execution. Numerical disagreement is present at the first invocation; full-state history then retains differing distances. Only `state.history` differs; all other declared policy-state fields match. Sequence pre-state maximum numeric difference is 0 initially, 0.007875443 at step 6, 0.029499054 at steps 12–30, and 0.055519104 at step 36. Final post-state maximum is 0.068376541. These are stored-history differences; additional output amplification from accumulated state was not observed in this seven-invocation sequence.

## Differences and observed margins

Representative process 1, isolated same-state comparisons (full-sequence prediction differences are identical). Values are maximum absolute differences; frozen numeric criterion remains absolute 0.001 / relative 0.00001.

| Physical step | Window distances | Requested-goal distance | Predicted distance | Normalized waypoint | Requested command |
|---|---|---|---|---|---|
| 0 | 0.049312592 | 0.005538940 | 0.038307190 | 0.007753916 | 0.005473993 |
| 6 | 0.029499054 | 0.016838074 | 0.007762909 | 0.003321707 | 0.002337801 |
| 12 | 0.032203674 | 0.019866943 | 0.009086609 | 0.005978882 | 0.000000000 |
| 18 | 0.044162750 | 0.014049530 | 0.018478394 | 0.006122112 | 0.000000000 |
| 24 | 0.046974182 | 0.005905151 | 0.008705139 | 0.009395599 | 0.000000000 |
| 30 | 0.055519104 | 0.013504028 | 0.055519104 | 0.011553735 | 0.000000000 |
| 36 | 0.068376541 | 0.001548767 | 0.068376541 | 0.006015003 | 0.000000000 |

All seven window/requested-goal/predicted-distance/waypoint comparisons fail the existing tolerance. Requested commands fail at steps 0 and 6 only. The command discrepancies are yaw-rate differences: 0.005473993 rad/s at step 0 and 0.002337801 rad/s at step 6. Later matching commands are the fixed scan `[0, 0, 0.4]`; they do not establish general action robustness or equivalent motion under efficacy conditions. None were executed.

Across representative isolated/full-sequence observations, argmin winner/runner-up gap ranges 0.122215271–1.688992500. Minimum-distance minus close threshold ranges 11.893317223–16.041942596; minus bounded lost-enter 8.141317223–12.289942596; minus bounded lost-exit 12.678317223–16.826942596; minus recovery-exit 9.012624264–13.161249638. Requested-goal minus close threshold ranges 19.631790161–20.643299103. These sampled margins are descriptive, not certified robustness bounds. Actual discrete transitions, counters, selected nodes and search windows match; this does not validate post-kidnap recovery declarations.

## Criteria and next decision

The tested stronger criterion—identical preprocessed tensors/restored state yielding bitwise repeated outputs—is achievable here. The numerical agreement criterion fails for these differing preserved observations despite image MAD below 2.5. There is no established implication from that image bound to output agreement within 0.001. Discrete agreement is achievable for these observations, but requested-command agreement fails on the first two invocations; neither weaker criterion overrides full learned-handover failure.

A future strict numerical-equivalence procedure would need to control/validate actual preprocessed-input equivalence as well as policy state/runtime. A future task-based equivalence criterion would need independent justification for localization decisions, declaration errors, confidence margins and command/motion effects across intended starts, frozen before new outcomes. The image and output criteria are jointly achievable for identical inputs; the failure concerns their unsupported implication for varying inputs, not logical impossibility. Future behavioral-state and physical-command criteria must distinguish control-relevant state from retained passive audit history, preserve every history value, and use separate prospective data near relevant decision margins. Do not select tolerances from these observed maxima. These are proposed decision requirements, not new thresholds or launch authorisation. This small saved-input test cannot establish general decision invariance, safety or an efficacy-valid initialization procedure.

STOP after the fixed manifest. No new simulator/model process, recovery batch or gate change follows automatically. Original image-generation cause remains UNKNOWN; earlier halted recovery attempts remain preserved. Held-out geometry stays sealed, illumination paused and robot actuation unauthorised.

A single bounded read-only interpretation review accepted these conclusions and their limits; record: `gates/redteam/offline-numerical-v1-interpretation-review-20261010.md`.

## Checks and external evidence

89 combined focused tests PASS, including 13 new pure tests. Named final source ruff/mypy PASS. Full `make verify`: ruff PASS, mypy89 PASS, exactly three preserved failures: `test_v8_accepts_the_repaired_tree` (archived identity FAIL/PASS), `test_attempt_001_pre_capture_is_preserved_byte_for_byte` (missing archived pre_capture.json), `test_regeneration_on_an_unchanged_tree_is_idempotent` (REFUSED/FROZEN), all in `tests/test_environment_identity_v8.py`. No archived evidence was repaired or test weakened.

Raw evidence remains external at `/home/favl/navfm-runtime-evidence/offline-numerical-v1-20261010-01`. No runtime outputs, images, logs, tensors or weights are committed. Frozen analysis is unchanged; `difference-summary.json` is a read-only descriptive breakdown of saved results.

| External artifact relative to evidence root | SHA256 |
|---|---|
| `analysis.json` | `7c0e7d4d595177743eea59eaa503f1ba65f478a080ce7e3e5f05072324b295b8` |
| `ledger.json` | `5c8b11d131ec4e32ce45af9b0cbf61db33ffc01d5fa8555393a336e59cbe4375` |
| `difference-summary.json` | `8831feb73f5595c99f81506beacb2a4334ea3c6dc5adb9fee8886323d068b672` |
| `verification.log` | `0b21e8bc2d19c5ed9e079cab1cc37590283324a2ab8bf16be796d6bfe794952b` |
| `offline-numerical-v1-p1/result.json` | `8023357decda2c215c5b570b2012163c73919519639066310918dee6923cca1c` |
| `offline-numerical-v1-p1.log` | `c3fd0212ce6e5f92d881df92fe619766242144e734b000d5239d4ba509a0c776` |
| `offline-numerical-v1-p2/result.json` | `c5c32ccf526970744dd7712833cc55506cc4e9e71b5283d1c8a5664afaf98252` |
| `offline-numerical-v1-p2.log` | `c3fd0212ce6e5f92d881df92fe619766242144e734b000d5239d4ba509a0c776` |
