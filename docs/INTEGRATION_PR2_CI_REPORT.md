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

## Genuine repairs and preserved contracts

All three checkout steps now fetch full history (`fetch-depth: 0`) because tests read historical frozen commits. Population membership is repinned from complete collection: 2,791 nodes, zero collection errors, all 777 earlier nodes and their ownership entries retained exactly, 2,014 added. Sets: hermetic 2,715; resource union 76; upstream 42; Torch 55; plot 1; corpus 1. Overlapping marker counts are not summed. Three new official-loader cases expand the independent upstream node digest/count from 39 to 42; substitution/drop controls remain unchanged in force.

The constructor-validation test is marked Torch because construction imports Torch/torchvision before validating its arguments. Its assertions are unchanged, and its existing resource owner executes it. No host/evidence test is exempted, no population gap added, no check disabled and no evidence fabricated.

Python 3.10 compatibility repair is authorised for a separate integration worktree/candidate: replace the two UTC aliases with equivalent `datetime.timezone.utc`. The original engineering freeze bytes/commits remain preserved. That candidate will have a new software source identity; no prior experiment is reclassified or relaunched. This first CI repair checkpoint does not claim the source fix has already been validated.

## Local verification and remaining blockers

- 100 population/rule controls PASS.
- Documented `PATH=.venv/bin:$PATH NAVFM_UPSTREAM=/home/favl/navfm-runtime-evidence/option1-admitted-20261007-02/upstream make verify`: ruff/mypy89 PASS, exactly three existing V8 failures below.
- Clean no-Torch Python 3.11 hermetic CI selector: 2,710 PASS, three FAIL, two skips, zero collection errors, exactly 2,715 executed node IDs. Membership now matches; the ownership gate still correctly FAILS the unexpected archived-manifest skip. The other skip is the already-declared historical open gap.
- Admitted-upstream resource selector (`torch or upstream or plot`): all 75 union nodes PASS, zero collection errors.
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
