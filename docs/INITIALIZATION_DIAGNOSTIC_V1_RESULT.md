# Initialization/history diagnostic result v 1

Owner: Frank Asante Van Laarhoven <frankleroyvan@gmail.com>.

**BOUNDED UNRESOLVED.** The original paired image mismatch remains unexplained.
No start procedure is verified. The technical probe failed its timing/startup
contract before a capture or comparison method completed. The halted recovery
pilot remains INCONCLUSIVE; its matching bound and unrun starts are unchanged.

## Scope and provenance

The reviewed design and executable were frozen at
`f831a110e6854c919a21c8397eee950cf79b77fd`. The original prospective collector/protocol/scoring files at
`54bfc239b3f8d4e5443212822582711b78925bbd` remain byte-identical. The diagnostic
used only the eight existing pilot input histories. Part B planned two already
observed s_bend development start cases; only the first was attempted.
No new simulator image was model-scored, no
recovery batch repeated, and no retry, threshold change or illumination probe ran.
Raw evidence, images, traces, logs and weights remain outside git.

## First divergence in the existing eight attempts

The first differing image is the lossless initial observation before current-
episode decision 0, repeated six times in each arm's initial buffer. Decoded RGB
buffer digests match each arm's own image; cross-arm buffers differ. On the four
route pairs, grayscale MAD is 0.292799,8.242943,1.129232,4.724297. The second and
fourth violate the unchanged 2.5 bound. Resume is absent; first inference index 0
and sensor/predecision simulation timestamps agree. Replay indexing cannot
explain the onset. Prior episodes had arm-dependent motion/duration in a reused
simulator, so earlier physical or rendering history remains a competing cause.

Recorded startup DLSS mode 0 differs from later live mode 2; source changes it
before goal rendering. The original live-setting readback was at final capture,
so it cannot prove every initial-image setting. Fixed local camera/scene/config
identity and tiny XY/yaw differences do not establish initial full root/world-
camera, joint or renderer state equality; those initial readbacks were absent.
Root reset did not explicitly restore joint state or rendering history. A
brightness-fit association in the design is descriptive only and does not
repair the gate or identify an exposure, geometry or rendering cause.

## Retrospective reconstruction

All eight recorded first invocations were reconstructed twice on CPU from their
preserved decoded start RGB, six-copy history, fixed goal and JPEG chain. Model,
config, exact history/indexing, initial policy state/counters and chain provenance
checks passed. Repeats are exact 8/8; all 16 windows, discrete chain-state fields
(including argmin), and terminal states match the original records. This supports
input/implementation consistency for the recorded node choices, not pixel
matching or a recovery claim.

The original backend was CUDA in the simulator runtime for all eight attempts;
the CPU replay used the repository virtual environment. Numerical comparison
fails the predeclared absolute
1e-3/relative 1e-5 bound in all eight distance windows. Predicted-distance comparison
fails 6/8 and requested-goal distance 1/8. Waypoint and first-command comparisons
pass 8/8. No tolerance is recalibrated; the numerical discrepancy is preserved.
The maxima below are from the first CPU reconstruction; the second is identical.

| Arm | Existing route | Max absolute window delta | Waypoint delta | Command delta |
|---|---|---:|---:|---:|
| R2_recover | s_bend_run_0000 | 0.002993584 | 0.000193596 | 0.000000000 |
| R2_recover | s_bend_run_0001 | 0.006958008 | 0.000139266 | 0.000000000 |
| R2_recover | junction_run_0000 | 0.005480766 | 0.000051945 | 0.000000000 |
| R2_recover | junction_run_0001 | 0.003189087 | 0.000085115 | 0.000000000 |
| B1x_exit | s_bend_run_0000 | 0.002059937 | 0.000148535 | 0.000015681 |
| B1x_exit | s_bend_run_0001 | 0.002490997 | 0.000046492 | 0.000037540 |
| B1x_exit | junction_run_0000 | 0.002069473 | 0.000028312 | 0.000018708 |
| B1x_exit | junction_run_0001 | 0.004238129 | 0.000294924 | 0.000083657 |

These small numerical differences cannot explain why raw paired initial images
already differ. Backend/environment variation is a candidate explanation for
model-output differences, not an isolated cause: this replay changed both device
and runtime environment. Exact cross-environment numerical equivalence fails.

## Technical probe and staged halt

Only process `s_bend_run_0000-r1-reference` was attempted. The first ordinary
conditioning render requested 1/12 s advance. Before and after simulation time were
both 0.058333336375653744 s; sensor time was 0, and controller feedback updates were 0.
The camera had not yielded a usable synchronized observation. The failure was
before eight goal-conditioning steps completed and before DLSS mode 2 was set,
so there is no actual per-capture/initial settings readback. Actual getter
readbacks reported physics dt 1/120 s and rendering dt 1/12 s, and all four wheel
drives read stiffness 0, damping 1000, type acceleration. Requested/readback timesteps
do not prove the attempted orchestrator call advanced physics.

The structured trace is FAIL with the literal frozen exception
`Unexpected physics clock advance during render`. Here the violated contract is
missing requested advance, rather than an extra advance. Process exit 0 from app
closure was correctly rejected using the trace status. The 600 s watchdog did not
expire. Runner postflight source/asset checks passed with no drift; failed trace
never acquired a successful postflight/PASS status. There are no capture images,
no 36-step scripted motion, no six-buffer handover and no method comparisons.

The frozen mechanical continuation gate HALTED expansion immediately. Seven
remaining processes are NOT RUN, zero retries occurred, and all 16 planned method
traces are unobserved. Structured analysis reports mechanically_complete=false,
ledger_order_and_exit_integrity=false because the full declared sequence is
incomplete, comparisons=[], and verified_reproducible_methods=[]. No procedure
is credited for matching. The timing/startup harness failure is a separate
technical limitation; it does not identify the original image-mismatch cause.
No underlying simulator/API cause is isolated by this single attempted call.

## Validation and next decision

Twenty diagnostic tests and 12 frozen-pilot tests pass; named source lint and
analyzer/runner type checks pass. Final `make verify` with `NAVFM_UPSTREAM`
completed: ruff passes; mypy passes on
89 source files; pytest fails exactly the three preserved environment-identity
tests below. They remain failures, not passes or repaired evidence.

- `test_environment_identity_v8.py::test_v8_accepts_the_repaired_tree`: archived
  environment identity mismatch, observed FAIL versus expected PASS.
- `test_environment_identity_v8.py::test_attempt_001_pre_capture_is_preserved_byte_for_byte`:
  missing archived `runs/bo10/intervention/arm_a/pre_capture.json`.
- `test_environment_identity_v8.py::test_regeneration_on_an_unchanged_tree_is_idempotent`:
  observed REFUSED versus expected FROZEN.

The full-check log is external `/tmp/navfm-initialization-final-verify-20261010.log`.

A separately reviewed/frozen repair of technical startup readiness and render-
advance instrumentation is the next diagnostic decision. Preserve this failed
attempt; do not retrofit it, add adaptive warmup, loosen image/time guards or
repeat the halted recovery pilot. A repaired technical harness would still need
all predeclared cross-repetition state/history guards before a start recommendation.
The original image cause remains UNKNOWN. Held-out geometry stays sealed,
illumination paused, and real robot actuation unauthorised.

Only scoped engineering-branch publication and a draft pull request are authorised
following outgoing-history/artifact/privacy checks; no force push, rewrite or merge.

## External evidence identities

| External artifact | SHA256 |
|---|---|
| `/home/favl/navfm-runtime-evidence/initialization-diagnostic-v1-20261010-01/retrospective.json` | `d02cf5c0299f706a2d3dd7bb17b84e0f5a4b562c44eff15b2cc5e1b18c4f51c4` |
| `/home/favl/navfm-runtime-evidence/initialization-diagnostic-v1-20261010-01/retrospective.log` | `dfac55325883f0883c3fd9d7ca58bff25ef8cfed5645d49965c7034ad670e878` |
| `/home/favl/navfm-runtime-evidence/initialization-diagnostic-v1-20261010-01/ledger.jsonl` | `ac43c3ab87a1d8201e095cef9fc49b711e2c179387a557cae2acbcd16b91471a` |
| `/home/favl/navfm-runtime-evidence/initialization-diagnostic-v1-20261010-01/analysis.json` | `fbe2270af516af8e052dd49f5e35ccb07557da7d3147b509a69d62870f5d39ff` |
| `/home/favl/navfm-runtime-evidence/initialization-diagnostic-v1-20261010-01/s_bend_run_0000-r1-reference/trace.json` | `62cf05055816f27682e707126fceb6570ed30c9fd8c362f90c4021f3b8e4afbb` |
| `/home/favl/navfm-runtime-evidence/initialization-diagnostic-v1-20261010-01/s_bend_run_0000-r1-reference.log` | `56b96a09c95f8ce79d87edcb5ece8b492b2a5f470c8187e4fc31bbf6578f33e9` |
| `/home/favl/navfm-runtime-evidence/initialization-diagnostic-existing-observation-audit-20261010-01.json` | `ee35fdb3f80ee4a394fd95ae60b1cc04e46c40313db3cbb05606c73e33d6b998` |
