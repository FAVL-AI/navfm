# PR 2 CI integration diagnosis

2026-10-10. PR 2 normal merge/main publication is authorised subject to meaningful checks; **integration remains BLOCKED**. No experiment was run. Initial failed run: `38084117484`, engineering head `5a3e093a7678b7f68ac5d124ca3c97bb6e2a0b59`.

## Every failed check

| Check | Initial failed steps | Diagnosis |
|---|---|---|
| test (3.10) | Typecheck; population ownership | `datetime.UTC` unavailable on 3.10 at execution_environment.py:615 and execution_manifest_v2.py:339. Tests never started, so report absent. |
| test (3.11) | Hermetic unit tests; population ownership | 24 failed test IDs: shallow history provenance cascades, unowned Torch constructor, live/archive V8 failures; stale population plus three unexpected resource skips. |
| test (3.12) | Hermetic unit tests; population ownership | Same 24 failed IDs and ownership/resource causes. |
| upstream-compat | Complete unit tests; population ownership | 23 failed IDs (Torch provisioned); same history/live/archive causes, stale population and resource skips. |
| go-stanford-corpus | Owned tests; population ownership | 24 failed IDs; same history/unowned Torch/live/archive causes, stale population and resource skips. Released corpus node itself did not fail. |

## Fresh hosted verification and lifecycle cause

Run `38085487891` tests integration candidate `9fc5f3727fd9ca9c17dc95738ae329d30689feb4`. All five jobs remain FAIL: `test (3.10)`, `test (3.11)`, `test (3.12)`, `upstream-compat`, and `go-stanford-corpus`. Each reports nine failed test IDs and a failed population ownership gate. The UTC typecheck, historical commit lookup, Torch ownership and expanded population defects no longer appear; this does not establish successful integration.

Each job retains the three V8 failures listed below and these six lifecycle failures:

- `tests/test_arm_lifecycle.py::test_rehearsal_completes_the_whole_lifecycle[ARM_A_CONTROL]`
- `tests/test_arm_lifecycle.py::test_rehearsal_completes_the_whole_lifecycle[ARM_B_TREATMENT]`
- `tests/test_arm_lifecycle.py::test_the_arms_differ_only_in_the_treatment_factor`
- `tests/test_arm_lifecycle.py::test_calling_an_exactly_once_producer_twice_is_detected`
- `tests/test_arm_lifecycle.py::test_invoking_a_producer_out_of_order_is_detected`
- `tests/test_arm_lifecycle.py::test_v3_readiness_is_measured_against_the_manifest_it_describes`

Targeted source inspection establishes why rehearsal is host-coupled: `RehearsalRuntimeAdapter` substitutes the simulator boundary, while `_capture_environment` still calls the real `capture_arm_environment`. That shared capture validator rejects absent critical fields and Isaac interpreter probe errors even for SELFTEST labels. Its default interpreter is `~/miniforge3/envs/isaac/bin/python`, which the hosted workflow does not provision. The normal lifecycle stops at `PRE_ENV_CAPTURED`; the deliberately reordered control stops at `POST_ENV_CAPTURED`. Missing `collect_config` and unmet multiplicity/order expectations are downstream cascades, not evidence of six independent orchestration defects. Saved logs expose capture FAIL, not complete capture reasons; the source dependency diagnosis is not a reconstructed host measurement.

The three unexpected resource skips remain the two GPU/hold-stack checks and archived-manifest check listed below. Existing ownership gates correctly reject them. No synthetic successful capture, new skip exemption, weakened readiness assertion or production change is introduced. Remaining readiness requires an appropriate real resource owner and preserved archive evidence; hosted CPU success cannot stand in for that validation. No simulator, model, experiment or additional test execution occurred during this final diagnosis.

External failed-log evidence: `/home/favl/navfm-runtime-evidence/pr2-ci-38085487891-failed.log`, SHA256 `cdec86ff4ed575a458a5aff37841f6c84f20c449ba299f7d4d5e22fc4f08a018`. Raw logs remain outside Git. **Normal merge/main publication remains blocked; no bypass is authorised.**

## Genuine repairs and preserved contracts

All three checkout steps now fetch full history (`fetch-depth: 0`) because tests read historical frozen commits. Population membership is repinned from complete collection: 2,791 nodes, zero collection errors, all 777 earlier nodes and their ownership entries retained exactly, 2,014 added. Sets: hermetic 2,715; resource union 76; upstream 42; Torch 55; plot 1; corpus 1. Overlapping marker counts are not summed. Three new official-loader cases expand the independent upstream node digest/count from 39 to 42; substitution/drop controls remain unchanged in force.

The constructor-validation test is marked Torch because construction imports Torch/torchvision before validating its arguments. Its assertions are unchanged, and its existing resource owner executes it. No host/evidence test is exempted, no population gap added, no check disabled and no evidence fabricated.

Python 3.10 compatibility is repaired in isolated candidate commit `680a631c2d5b5c97930d1362aa5969680fb00393`: two `_dt.UTC` uses become equivalent `_dt.timezone.utc` in execution_environment.py and execution_manifest_v2.py. The candidate branch is `agent/pr2-ci-integration` at `/home/favl/projects/navfm-pr2-ci-integration`. Original engineering checkpoint `aa51007db39db67a9d35e970a9c576f128909d7b` remains clean in its separate worktree, and its historical freeze source/assets still verify. Candidate software source identity differs; old freeze launch guards are not asserted valid on this changed candidate. No previous experiment is reclassified or relaunched.

## Local verification and remaining blockers

- 100 population/rule controls PASS.
- Documented `PATH=.venv/bin:$PATH NAVFM_UPSTREAM=/home/favl/navfm-runtime-evidence/option1-admitted-20261007-02/upstream make verify`: ruff/mypy89 PASS, exactly three existing V8 failures below.
- Clean no-Torch Python 3.11 hermetic CI selector: 2,710 PASS, three FAIL, two skips, zero collection errors, exactly 2,715 executed node IDs. Membership now matches; the ownership gate still correctly FAILS the unexpected archived-manifest skip. The other skip is the already-declared historical open gap.
- Admitted-upstream resource selector (`torch or upstream or plot`): all 75 union nodes PASS, zero collection errors.
- Candidate typecheck: all 89 source files PASS on actual Python 3.10.12, 3.11.15 and 3.12.13. No target version is overridden.
- Candidate Python 3.10 no-Torch hermetic suite: 2,710 PASS, the same three V8 FAIL, two skips and zero collection errors. No additional UTC-script runtime failure appeared. Timestamp/manifest controls (48 tests) also PASS on 3.11 and 3.12.
- Candidate documented admitted-upstream `make verify`: ruff/mypy89 PASS, exactly the same three V8 failures. No source identity pin or readiness gate was altered to accept the changed candidate.
- Manifest-only owner-completeness PASS is ownership coverage, not successful execution or environmental attestation.

Meaningful V8 failures remain:

1. `tests/test_environment_identity_v8.py::test_v8_accepts_the_repaired_tree`: current physical/interpreter host does not satisfy the archived frozen contract.
2. `tests/test_environment_identity_v8.py::test_attempt_001_pre_capture_is_preserved_byte_for_byte`: missing `runs/bo10/intervention/arm_a/pre_capture.json`. That path is absent from available Git history; full checkout cannot create the evidence.
3. `tests/test_environment_identity_v8.py::test_regeneration_on_an_unchanged_tree_is_idempotent`: refuses while host/archive requirements fail.

Original hosted logs also have three unexpected skips:

- `tests/test_arm_environment_guard.py::test_nvidia_hold_guard_passes_on_this_machine`
- `tests/test_arm_environment_guard.py::test_hold_list_is_not_a_substitute_for_the_loaded_stack`
- `tests/test_collector_wiring_and_runner.py::test_manifest_v1_is_now_stale_and_refused`

The first two are frozen-GPU/driver/hold-stack resource ownership/provisioning gaps on hosted CPU runners. The third requires absent historical runtime manifest evidence. They are not resolved by installing CPU Torch, and they are not silently exempted. The existing separately declared open gap `test_freeze_audit_negatives.py::TestIdentityCheckCanFail::test_perturbed_executable_identity_fails` remains tracked rather than newly baselined.

New hosted outcomes are pending publication; none are called green. Merge/main push must wait for meaningful checks, with no bypass. PR metadata permission is a separate limitation. Raw CI logs, reports and environments remain external; an unsuitable initial local Python 3.13/ROS-plugin setup failed before collection and is retained separately (`pr2-ci-hermetic-20261010-01`); the actual reproduction uses clean Python 3.11 (`-02`). Original experimental freezes and failed artifacts are unchanged.

| External evidence | SHA256 |
|---|---|
| `/home/favl/navfm-runtime-evidence/pr2-ci-38084117484-failed.log` | `b5a8685ffda0a0aa5a430d0166ef44d62a6bc0259f22952b9a0ffc51ad648d48` |
| `/home/favl/navfm-runtime-evidence/pr2-integration-collection-20261010.json` | `573d2cbaad1bd4c02c2f4f61ca2885712b9e60544b73636ee0db98fca03f5870` |
| `/home/favl/navfm-runtime-evidence/pr2-integration-make-verify-20261010.log` | `0b21e8bc2d19c5ed9e079cab1cc37590283324a2ab8bf16be796d6bfe794952b` |
| `/home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/population.json` | `3c4cae1f0f3618c3d25525b283d110030f49a68145115d32f1a1c30f52b21153` |
| `/home/favl/navfm-runtime-evidence/pr2-integration-resource-population-20261010.json` | `90c15941846a02e8d8fb1144782bd9bcd19f3570e28200aaa6e8fc8cfcff9522` |
| `/home/favl/navfm-runtime-evidence/pr2-ci-compatibility-20261010/type310.log` | `14c86ee194cc9406b4f38866ce2eb1ba7e54c55437faf1ccc89f0195c485674d` |
| `/home/favl/navfm-runtime-evidence/pr2-ci-compatibility-20261010/type311.log` | `14c86ee194cc9406b4f38866ce2eb1ba7e54c55437faf1ccc89f0195c485674d` |
| `/home/favl/navfm-runtime-evidence/pr2-ci-compatibility-20261010/type312.log` | `14c86ee194cc9406b4f38866ce2eb1ba7e54c55437faf1ccc89f0195c485674d` |
| `/home/favl/navfm-runtime-evidence/pr2-ci-compatibility-20261010/target311.log` | `6dd786dc72d45e02d32f9a2c96fbee7f0ea69261b610e86a41d1a671dd0186ef` |
| `/home/favl/navfm-runtime-evidence/pr2-ci-compatibility-20261010/target312.log` | `6dd786dc72d45e02d32f9a2c96fbee7f0ea69261b610e86a41d1a671dd0186ef` |
| `/home/favl/navfm-runtime-evidence/pr2-ci-compatibility-20261010/population310.json` | `3c4cae1f0f3618c3d25525b283d110030f49a68145115d32f1a1c30f52b21153` |
| `/home/favl/navfm-runtime-evidence/pr2-ci-compatibility-20261010/make-verify.log` | `2daefb9a19c7bdee5036eaa5b5b4066f5611fe792b0497c3d35470b38818c582` |

## Explicit software source identity transition

The historical source is retained in the original engineering worktree and Git history; the equivalent timestamp repair has new SHA256 identities. Runtime assets and scientific experiment sources other than these two integration files are unchanged.

| File | Original aa51007 SHA256 | Candidate 680a631 SHA256 |
|---|---|---|
| `src/navfm/execution_environment.py` | `6ef80e460625c47fffd8c47035fa85f59f4f045dcfe6b304beff1667e643633d` | `44d3d6c596b36a878bd61141aad6cf79d15e95344103cae0c26cd370ed5bf148` |
| `src/navfm/execution_manifest_v2.py` | `d02238a1e451d4f33559874c2192f5c9663f8baae2b0586c9db77b2e9696717e` | `f4dc972621d17d2dff2fbec6b9718448b0fd41f23fc92ff1fadb97589b6ecde9` |
