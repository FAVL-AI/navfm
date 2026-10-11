# First learned-policy replay validation pair: result

Owner: Frank Asante Van Laarhoven <frankleroyvan@gmail.com>.

**HALTED: initialization integrity failure; learned-policy handover remains unvalidated.** Only the first R2 reference launch ran. Replay was NOT RUN. No pair equivalence, efficacy, recovery or safety claim follows. The original pilot remains INCONCLUSIVE and its image-mismatch cause UNKNOWN.

## Freeze and attempt boundary

The independently reviewed source/config/finite manifest was frozen at `d74927f7f2e88dd75e20f13646dc22f8e05c5671`. All 24 prior version-2 frozen files remain byte-identical to `0393d46e814c80f2cc53ff9570af2c4015da2e7a`; earlier freezes and all failed attempts are preserved. Metadata-only audit of 283 numeric tuple records found the proposed tuples absent from that inventory: new experimental starts, not research novelty.

Attempt `A-s_bend_run_0000-R2_recover-r1-reference` launched at 19:02:16.610849 UTC and exited at 19:06:28.704867 UTC on 2026-10-10. Startup initially repeated a local Hub launch warning, then the simulator advanced. The 600 s watchdog did not expire. Fixed bootstrap/eligibility, conditioning and all 36 scripted frames completed: 114 orchestrator calls, 42 saved captures, 560 measured physics callbacks and seven pre-kidnap actual CUDA policy invocations. Requested learned commands were recorded and ignored; physical motion remained scripted. Zero post-kidnap/recovery invocations occurred.

Actual runtime readback: Python `/home/favl/miniforge3/envs/isaac/bin/python`, torch `2.7.0+cu128`, CUDA `12.8`, device NVIDIA GeForce RTX 4080 SUPER, model eval mode. These are observed values rather than inferred from intent. This does not establish equivalence to replay, which never launched.

## Exact failed acquisition guard

The collector reports FAIL with literal `Acquisition not from boundary rerender`. The boundary is call index 113, requested delta 0, simulation time before/after 4.725000246427953 s, sensor time the same, and zero feedback callbacks. Public timeline advanced from 14.2500002856056 to 14.33333362142246 s; that is not physics advancement.

The observer recorded three supported events for product `/Render/OmniverseKit/HydraTextures/Replicator_01`:

| Observed event | Active render-call index | Raw RGB SHA256 |
|---|---|---|
| 0 | null | `621cd8f47bc3eec3840521a20c8fe1061603acb5144526fdc4079e5d267767a6` |
| 1 | 113 | `621cd8f47bc3eec3840521a20c8fe1061603acb5144526fdc4079e5d267767a6` |
| 2 | 113 | `d4917952c2f7c9cd55bd9c47ec9759f7daf6cacda1d1722ac20815216f1fdea9` |

All three report simulation/sensor time 4.725000246427953 s. Saved boundary RGB has event 2's raw digest. The frozen guard requires every event collected after observer arming to belong to the boundary call; event 0 has no active call index, so the attempt fails even though the last event is associated with call 113 and matches saved RGB. This is an event-window/provenance integrity failure. It does not prove stale boundary pixels or a renderer/API defect, nor identify why the extra event occurred. The evidence is not retroactively reclassified by selecting only its final matching event.

Collector failure occurred before its postflight/PASS block. App closure returned process exit 0; the runner correctly rejected the structured FAIL with `Trace cannot qualify`, recorded exit/halt, and launched nothing further. Runner source/asset postflight checks completed before the trace rejection; a subsequent read-only check also confirms exact source/config/assets and protected freeze bytes. No source change, retry, guard relaxation or extra render was made during or after collection.

## Preserved history boundary

Qualified initial time T was 1.7250000899657607 s. The six boundary observations were recorded as below; the last is the own post-kidnap current image, not a copied reference frame. The read-only history schedule check passes, but cannot override the acquisition failure.

| Physical step | Observation | Sensor = simulation time (s) | Relative age (s) |
|---:|---|---:|---:|
| 6 | script_05.png | 2.225000116042793 | 2.5000001303851604 |
| 12 | script_11.png | 2.725000142119825 | 2.0000001043081284 |
| 18 | script_17.png | 3.225000168196857 | 1.5000000782310963 |
| 24 | script_23.png | 3.725000194273889 | 1.0000000521540642 |
| 30 | script_29.png | 4.225000220350921 | 0.5000000260770321 |
| 36 | post_kidnap.png | 4.725000246427953 | 0 |

All 42 capture-file digests match the trace. Actual policy before/after initialization/reset snapshots and input buffers remain external. No reference/replay comparisons were available; no learned decisions are scored as efficacy observations. The forced-entry reset and timestamp contract are implemented, but this attempt does not validate their reproducibility or qualification on intended recovery starts.

## Validation, halt and next decision

59 focused tests pass (14 new boundary tests plus 45 preserved diagnostic/pilot tests); named lint and helper/runner type checks pass. Final full `make verify` before freeze passes ruff and mypy on 89 source files and fails exactly the three preserved cases in `tests/test_environment_identity_v8.py`:

- `test_v8_accepts_the_repaired_tree`: archived identity FAIL versus expected PASS.
- `test_attempt_001_pre_capture_is_preserved_byte_for_byte`: missing archived `runs/bo10/intervention/arm_a/pre_capture.json`.
- `test_regeneration_on_an_unchanged_tree_is_idempotent`: REFUSED versus expected FROZEN.

The two-launch authorization was a ceiling and required reference integrity before replay. This failed first reference therefore HALTED the pair: one attempt preserved, zero retries, replay NOT RUN. All other arms/repetitions/starts and all efficacy runs remain NOT RUN. Do not resume this frozen attempt or silently weaken its guard. Any later observer-window repair requires a separately reviewed contract and new named freeze, with this failure retained. No repair/relaunch/amended probe occurred this turn. Full learned-state, cross-repeat, cross-arm and intended-start matching remain unvalidated before efficacy.

Held-out geometry stays sealed, illumination paused and real robot actuation unauthorised. All raw images/traces/logs/weights remain external; only authored contracts/reports/checks are committed. Publication is confined to the authorised engineering branch; no merge or history rewrite.

## External evidence identities

| External artifact | SHA256 |
|---|---|
| `/home/favl/navfm-runtime-evidence/replay-recovery-validation-v1-20261010-01/analysis.json` | `99958dc01e32cefdf9360b8de56cb8f9b68b52eebe6d826ca7c853e23627613b` |
| `/home/favl/navfm-runtime-evidence/replay-recovery-validation-v1-20261010-01/ledger.jsonl` | `56948198600c5fdee4103e652bfe3e1393ad75920475638af2cd45ea03e34c28` |
| `/home/favl/navfm-runtime-evidence/replay-recovery-validation-v1-20261010-01/A-s_bend_run_0000-R2_recover-r1-reference/trace.json` | `f871364304ef4b3dd34cf3c86563e05b152762d411e5b7279cb7ac46fdd054b4` |
| `/home/favl/navfm-runtime-evidence/replay-recovery-validation-v1-20261010-01/A-s_bend_run_0000-R2_recover-r1-reference.log` | `9983abf3966ada9c3ba98f4e9869edc451e05f1bef5f0da3c078d0a14a11c732` |
| `/home/favl/navfm-runtime-evidence/replay-recovery-start-tuple-audit-20261010-01.json` | `d40154456d35b5483bd5265aeee0692b10422e723d6d6dbbe9e0c069a9ce0c3f` |
| `/home/favl/navfm-runtime-evidence/replay-recovery-validation-v1-20261010-01/verification.log` | `72d1f29f3cd2101ae366985620962105295eabdcda60862aa13405a82351f58a` |
