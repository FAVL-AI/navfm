# Immutable RAVEL launcher record lifecycle v3

Branch `agent/research-three-model-plan`; baseline
`a7aa68a950f9af614c3111365c284f3ce40968f0`. The earlier [duplicate-write failure](NATIVE_RAVEL_GRAPH_CONTINUATION_RESULT_V2.md)
remains preserved. The shared write_json exclusive-create contract is unchanged.
The real parent now writes attempt.json once as PREFLIGHT_STARTED and a distinct
worker_start.json as LAUNCH_REQUESTED. That record is launch intent, not evidence
that a child started; actual exit/timeout/reaping comes from real Popen supervision.
Record/proof failures have a durable parent terminal and no child claim. Existing
output directories refuse via an exclusive sibling refusal sidecar and preserve
all existing files. No graph parameter, data, model/source/policy or constructor
proof changes; production still uses180worker/360parent/16MiB/SP56LG28/VPR0.

The [CPU check](../scripts/check_ravel_launcher_lifecycle_v3.py) executes the
actual CLI parent for six fixed technical enum cases with harmless subprocess
workers. No worker-command string is accepted in production. This explicit
CPU-only technical entry requires CUDA hidden, forbids graph --worker, and may
exercise a dirty-tree development snapshot; production retains exact clean-freeze
admission. Synthetic success is only PASS_LAUNCHER_LIFECYCLE_ONLY. Production
requires PASS_NATIVE_FIXED_GRAPH_ONLY, so the test cannot attest a graph result.
The technical timeout is0.1s, distinct from unchanged180s production; entire
six-case CPU check cap30s/per CLI5s,0 models/forwards/GPU. Actual qualified
constructor proof is consumed as metadata without reconstruction.

| Case | CLI exit | Terminal/child evidence |
| --- | ---: | --- |
| success | 0 | PASS_LAUNCHER_LIFECYCLE_ONLY; child exit 0, timeout False, reaped True |
| preflight_reject | 1 | FAIL; child exit None, timeout None, reaped None |
| worker_fail | 1 | FAIL; child exit 7, timeout False, reaped True |
| timeout | 1 | FAIL; child exit -9, timeout True, reaped True |
| write_failure | 1 | FAIL; child exit None, timeout None, reaped None |
| populated_directory | 1 | FAIL_POPULATED_DIRECTORY_REFUSED; child exit None, timeout None, reaped None |

Each fresh case retains immutable attempt.json. Success/worker-failure/timeout
also retain worker_start.json and parent_status.json; proof/record-write refusal
retains parent_status.json with child lifecycle not applicable. The write-failure
case preserves its conflicting worker_start.json fixture. Populated-directory
refusal preserves the preexisting attempt and records a sibling refusal.json.
All child processes were waited/reaped; the timeout child was killed and waited.

The first technical check caught a synthetic-success exit-label mismatch before
any graph attempt; its evidence remains in ravel-launcher-lifecycle-v3-01.
After correction, all six actual CLI cases passed in 0.969s. Final evidence stays
at `/home/favl/navfm-runtime-evidence/ravel-launcher-lifecycle-v3-02`, result SHA256
`7fd06fe403248c7fc0559bbe2b00756e36f45961f9d1953e28ef0def7088f75a`.
Nineteen existing hermetic proof/graph guards and Ruff pass. No pytest nodes or
resource owners were added/dropped;3201 expected nodes remain. The six external
CPU cases have explicit command ownership in the lifecycle manifest.

Only after narrow review and source freeze may one separately authorised fresh
graph qualification run at `/home/favl/navfm-runtime-evidence/ravel-fixed-graph-v3-01`.
No six-constructor/encoder repeat, fitting, collection, simulation, navigation or
actuator operation is authorised. Neither preserved failed graph invocation is
relabeled successful. No graph attempt occurred during this lifecycle repair.
