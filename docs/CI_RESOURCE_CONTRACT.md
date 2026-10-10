# CI resource ownership and workstation execution

The orchestration unit fixtures inject an explicit rehearsal-only environment-capture boundary. They traverse the same plan and test rejection, missing producers, multiplicity and ordering. Fixture records state `SYNTHETIC_ORCHESTRATION_FIXTURE` and `NOT_MEASURED`; REAL mode rejects injection before creating an output directory. The default capture remains a measured, fail-closed capture in both modes. These fixtures never establish physical or production readiness.

The population manifest assigns every collected node. `isaac_host`, `archive` and `alternate_python` belong to `resource-validation`; Torch/upstream/plot and corpus retain their existing owners. Historical contract checks invoking actual capture belong to the measured-host owner, including predecessor refusals. Pure schema/source/hash and injected negative controls remain hermetic. No old node is dropped; explicit per-node membership is in `tests/population_manifest.json`.

## Required checks and safe manual owner

Hosted `resource-approval` in the existing PR workflow first requires repository variable `NAVFM_APPROVED_RESOURCE_SHA` to equal the reviewed exact candidate and reads the configured environment protections: required independent reviewers, prevention of self-review and branch restrictions. Missing approval or unreadable/insufficient protection FAILS before the workstation job can queue. This makes the present PR owner structurally executable without first merging a new workflow into main, while permitting no workstation execution before explicit operator/security approval.

`resource-validation` depends on that approval and additionally uses protected environment `navfm-resource-validation` and dedicated label `navfm-resource-approved`. It has read-only repository permissions, does not persist checkout credentials, and executes no simulator, model inference, research trial or robot command. It runs actual environment preflight, ordinary/resource unit validation and complete outcome/population checks at the exact candidate revision.

Hosted `resource-contract` always runs after those jobs. It requires the current owner job to have completed SUCCESS and verifies that run's artifact independently; it does not require the overall run to succeed, avoiding a circular dependency. It fails on absent/failed/skipped owner, source/population mismatch, missing outcomes, any failure/skip/error, ownership mismatch or mismatched capture/inventory hashes. Assignment alone, unavailable runner queues and incomplete artifacts cannot pass it. The candidate remains REFUSED by the historical V8 live guard; CI proves that refusal instead of claiming old source identity.

The standalone `resource-validation.yml` remains manual only, with the same revision/environment safeguards. It is not yet registered on the default branch and cannot be assumed dispatchable until that operator-controlled bootstrap occurs. Present PR validation uses the approval-gated owner in existing `ci.yml`; no pre-merge workflow bootstrap or new permissions are assumed.

**No runner has been installed, registered or declared secure by this change.** Before enabling the workflow, inspect workstation storage/access, required external artifacts, installed interpreter identity, current driver/module/holds, test dependencies and working-directory isolation. Confirm GitHub runner inventory and registration permissions separately. A local absence of runner processes is not proof of GitHub registration absence.

Required security setup before any workstation job:

1. Use a dedicated unprivileged execution account and disposable checkout; deny robot/device actuation and isolate credentials, personal files, research outputs and deployment permissions. Limit access to the explicit read-only archive and interpreter paths. Reject arbitrary pull-request code or unreviewed revisions.
2. Configure the GitHub environment with required human reviewers, prevent self-approval, restrict allowed branches, and approve the reviewed exact workflow/source commit. The repository SHA approval variable is an additional gate, not a substitute for those protections. Revoke it after the run. Do not execute a revision different from the workflow run HEAD.
3. Review every job step and test before approving the revision. Provision dependencies through a separately reviewed environment recipe; this workflow installs nothing on the workstation. Require an approved clean development test interpreter (`NAVFM_RESOURCE_TEST_PYTHON`) with pytest/NumPy and no Torch/upstream collection dependencies, the existing pinned Isaac interpreter for read-only runtime probes, and an independently identified alternate interpreter, and valid loaded GPU/hold-stack measurements. Do not change driver holds or credentials to make a test pass.
4. Set `NAVFM_ARCHIVE_ROOT`, `NAVFM_RESOURCE_TEST_PYTHON` and `NAVFM_ALTERNATE_PYTHON` to approved external read-only locations. Hash and record the authentic bytes before execution. Set the exact SHA approval only after security review and request/review the protected-environment job in the current PR workflow. The standalone manual option requires separate default-branch bootstrap. Failure preserves raw artifacts and blocks integration.

## Archive recovery and historical scope

The authentic Attempt001 pre-capture recovered from the original worktree matches the independently recorded SHA256 `884aa505bc288a8c69bc17aea5e6b9e07114432f5fa5292917828d6ba75d105a`. It is not regenerated. The recovered V1 manifest SHA256 is `4021d69d8835d9c1afd0f0d8ccea85c167d48d16000ed6064e800d854eed7572`; this is a new recovery observation, with no earlier whole-file hash found. Its bound head `effcce1ee22e8480a4c43e656e7355e628cadcc5` is independently corroborated by tracked historical readiness/reachability records. Its stale-manifest test establishes refusal on the candidate, not retrospective byte-level attestation.

The existing V8 repaired-tree node now verifies actual source blobs at recorded seam commit `73653c26178cff36d50904ccb73a56314bccb94c` against the later frozen V8 source pins, and authentic Attempt001 host/runtime fields against retained V8 recorded values. The V8 gate was frozen later; it is not asserted present at the seam commit. Canonical regeneration reconstructs the archived payload from recorded inputs and compares it without writing any gate or sampling today's host. These archival checks do not assert current live-host equivalence. A separate measured control requires the candidate's historical V8 refusal and actual collector-source drift.

Raw captures, recovered manifests, logs, population reports and inventories remain external. Historical freezes, amenders, failed attempts and source commits remain immutable. Integration requires all declared owners to execute and every required check to pass; missing runner/security approval or evidence remains a visible failure.

## Local measured-node results

The following 49 nodes all passed in the local clean development test interpreter while probing the installed Isaac runtime and original archive. The candidate worktree was dirty during this validation: these results establish test behavior, not exact-commit GitHub owner attestation or production readiness. All raw outcomes are external.

| Node | Purpose | Owner | Actual result |
|---|---|---|---|
| `tests/test_arclength_treatment.py::test_v2_still_refuses_for_the_historically_correct_reason` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_arclength_treatment.py::test_v3_now_refuses_because_the_treatment_landed_in_the_pinned_seam` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_arm_environment_guard.py::test_hold_list_is_not_a_substitute_for_the_loaded_stack` | Actual loaded GPU/hold-stack validation and negative control | resource-validation (isaac_host) | PASSED |
| `tests/test_arm_environment_guard.py::test_nvidia_hold_guard_passes_on_this_machine` | Actual loaded GPU/hold-stack validation and negative control | resource-validation (isaac_host) | PASSED |
| `tests/test_arm_lifecycle.py::test_v3_readiness_is_measured_against_the_manifest_it_describes` | Real capture rehearsal/manifest readiness parity | resource-validation (isaac_host) | PASSED |
| `tests/test_collector_wiring_and_runner.py::test_manifest_v1_is_now_stale_and_refused` | Archived source/capture/canonical payload or stale-manifest provenance | resource-validation (archive) | PASSED |
| `tests/test_environment_identity_v3.py::test_current_tree_now_refuses_against_v3_because_the_treatment_landed` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v3.py::test_current_tree_still_fails_against_v2` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v3.py::test_the_guard_does_not_fall_back_between_versions` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v3.py::test_v2_and_v3_refuse_for_different_reasons` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v4.py::test_each_predecessor_refuses_for_its_own_reason` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v4.py::test_v2_still_refuses_the_post_seam_tree` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v4.py::test_v3_still_refuses_the_treatment_tree` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v4.py::test_v4_now_refuses_the_wired_tree` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v4.py::test_v4_remains_reachable_after_being_superseded` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v5.py::test_every_predecessor_still_refuses[V2]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v5.py::test_every_predecessor_still_refuses[V3]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v5.py::test_every_predecessor_still_refuses[V4]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v5.py::test_v4_refuses_for_the_wiring_transition` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v5.py::test_v5_now_refuses_the_lifecycle_tree` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v5.py::test_v5_remains_reachable_after_being_superseded` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v6.py::test_each_predecessor_refuses_for_its_own_reason` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v6.py::test_every_predecessor_still_refuses[V2]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v6.py::test_every_predecessor_still_refuses[V3]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v6.py::test_every_predecessor_still_refuses[V4]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v6.py::test_every_predecessor_still_refuses[V5]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v6.py::test_v5_refuses_for_the_lifecycle_transition_specifically` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v6.py::test_v6_now_refuses_the_real_mode_tree` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v6.py::test_v6_remains_reachable_after_being_superseded` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v7.py::test_every_predecessor_still_refuses[V2]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v7.py::test_every_predecessor_still_refuses[V3]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v7.py::test_every_predecessor_still_refuses[V4]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v7.py::test_every_predecessor_still_refuses[V5]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v7.py::test_every_predecessor_still_refuses[V6]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v7.py::test_v6_refuses_for_the_runner_transition_specifically` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v7.py::test_v7_now_refuses_the_repaired_seam_tree` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v7.py::test_v7_remains_reachable_after_being_superseded` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v8.py::test_attempt_001_pre_capture_is_preserved_byte_for_byte` | Archived source/capture/canonical payload or stale-manifest provenance | resource-validation (archive) | PASSED |
| `tests/test_environment_identity_v8.py::test_current_candidate_is_refused_by_historical_v8` | Current live V8 refusal with collector-source drift | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v8.py::test_every_predecessor_still_refuses[V2]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v8.py::test_every_predecessor_still_refuses[V3]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v8.py::test_every_predecessor_still_refuses[V4]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v8.py::test_every_predecessor_still_refuses[V5]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v8.py::test_every_predecessor_still_refuses[V6]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v8.py::test_every_predecessor_still_refuses[V7]` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v8.py::test_regeneration_on_an_unchanged_tree_is_idempotent` | Archived source/capture/canonical payload or stale-manifest provenance | resource-validation (archive) | PASSED |
| `tests/test_environment_identity_v8.py::test_v7_refuses_for_the_seam_repair_specifically` | Measured historical contract/version/source refusal | resource-validation (isaac_host) | PASSED |
| `tests/test_environment_identity_v8.py::test_v8_accepts_the_repaired_tree` | Archived source/capture/canonical payload or stale-manifest provenance | resource-validation (archive) | PASSED |
| `tests/test_freeze_audit_negatives.py::TestIdentityCheckCanFail::test_perturbed_executable_identity_fails` | Distinct executable identity rejection | resource-validation (alternate_python) | PASSED |

## Candidate validation and final clean-source procedure

Final collection has 2,812 nodes: every prior 2,791 node retained and 21 additional controls. Hermetic 2,687; resource union 125, including measured-host 44, archive 4 and alternate interpreter 1 (49 additional resource-owned nodes). The existing Torch/upstream/plot/corpus owners remain unchanged. Counts overlap and are not summed.

Preliminary dirty-candidate validation: 98 focused orchestration/population/attestation controls PASS. Ruff and mypy89 PASS. The full admitted-upstream `make verify` run executes 2,809 nodes, all PASS, with zero collection errors; three subsequently added tracked-source/HEAD negative controls pass in the focused run. The first installed-Isaac parent collection attempt fails before execution because the discovered upstream lacks lmdb; it is retained externally. A clean development parent executes 2,725 nodes, all PASS, including all 49 measured-resource nodes. Four bootstrap and three source-identity controls were added after that owner collection. These preliminary results are not an exact-HEAD owner bundle.

After committing this final source/config/documentation set, perform exactly one clean local preflight and owner validation with the approved development test interpreter, external authentic archive and distinct alternate interpreter; preserve all failures and bundle only if every executed outcome passes and the tracked HEAD/bytes are unchanged. Preflight and bundle reject dirty tracked files or changed HEAD/source bytes. The hosted verifier independently recomputes all tracked checkout hashes and binds the actual capture's repository HEAD. Untracked caches/external raw outputs do not affect that digest.

Commands (raw outputs external, no dependency installation or simulator invocation):

```bash
export PYTHONPATH=src
export NAVFM_RESOURCE_TEST_PYTHON=/home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python
export NAVFM_ARCHIVE_ROOT=/home/favl/projects/navfm
export NAVFM_ALTERNATE_PYTHON=/home/favl/projects/navfm/.venv-m1/bin/python
export RESOURCE_OUTPUT=/home/favl/navfm-runtime-evidence/pr2-resource-contract-20261010/clean-owner
"$NAVFM_RESOURCE_TEST_PYTHON" scripts/resource_ci.py preflight --output "$RESOURCE_OUTPUT"
"$NAVFM_RESOURCE_TEST_PYTHON" -m pytest -q -m "not torch and not upstream and not plot and not go_stanford" --population-report="$RESOURCE_OUTPUT/owner.json"
"$NAVFM_RESOURCE_TEST_PYTHON" scripts/resource_ci.py bundle --output "$RESOURCE_OUTPUT"
```

The exact clean-source result is recorded in the external bundle/canonical checkpoint after this commit; no automatic documentation edit invalidates its source identity. Local success does not satisfy the required GitHub owner artifact. Repository approval/environment permissions, workstation security configuration and runner registration remain separate operator prerequisites; no merge or bypass follows from local test success.

All preliminary evidence is under `/home/favl/navfm-runtime-evidence/pr2-resource-contract-20261010/`:

| Artifact | SHA256 |
|---|---|
| `resource-targeted.log` | `6a815566744da670e008f302da59809bc0995f85a3c15b9db59fe226544b5c46` |
| `owner-local.json` | `3d02142eb423dd07782bdead1f8378662c709b6ea9714dc825037df2fe644b33` |
| `owner-local.log` | `0132c4e2bd034dc798fd7f87fd43a6d823082d82e9e1bc0a9116cae003136ad4` |
| `full-final.json` | `6871fda417546b04c77c646a86daa799a3af7670b7c42685ce25ce60f8d351e9` |
| `make-verify-final.log` | `2634ac46196a40135061f05d1047c8db46240e28d4dbe04b10cdd77de2639e6f` |
| `collection-locked.json` | `d9691cbe0649614e37b68320cfe2a75374c44d214e2abb5fd92a5a15abcc1077` |
