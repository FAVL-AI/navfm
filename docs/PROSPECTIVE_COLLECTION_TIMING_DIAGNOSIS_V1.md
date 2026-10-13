# Preserved collection timing diagnosis

Read-only milestone on `agent/research-three-model-plan`, baseline `574419a918893409dac521666f0180c18cb1f82f`. Attempt source remains `e23fb89c07d3a346f1e21da51a086ba1afe909a2`. The original **FAIL / dataset not admitted** is unchanged: no second process, scoring, source repair, deadline change or seed regeneration.

## Recorded timeline and clock scope

| Observation | Recorded value | Interpretation |
|---|---:|---|
| Specification file mtime | 2026-10-11 23:44:25.141632 UTC | Filesystem reference, not exact parent launch time |
| SDK `app ready` | 4.080 s | Child log elapsed clock; origin not cross-calibrated to parent |
| SDK startup complete | 5.824 s | Same child log clock |
| First JPEG mtime | +8.515887 s after specification mtime | File modification observation; not exact acquisition event |
| Last JPEG mtime | +113.294606 s | Same filesystem reference; first-to-last span 104.778718 s |
| Last capture snapshot mtime | +113.327605 s | Snapshot modification, not an exact frame completion event |
| Completion capsule mtime | +113.342605 s | Durable measurement existed near the end of the execution allowance |
| SDK shutdown marker | 114.382 s | Child log clock; does not prove shutdown completion |
| Last process log mtime | +114.798589 s | Last modification, not process exit time |
| Parent execution deadline | start +115 s | Frozen formula: 120 seconds minus five-second reaping reserve |
| Timeout catch / signal / observed exit timestamps | UNKNOWN | Parent does not record these individual wall events |
| Final parent record | timeout=true, exit=0, reaped=true | Actual preserved statuses; occupied wall 115.480048 s |

The frame `rendering_time` runs from 1.1666667014360428 to 48.83333478868008 **simulation seconds**; it is not wall time. File mtimes are not exact acquisition, atomic-replacement, fsync-completion or shutdown event timestamps. The child log's elapsed origin differs from the unrecorded parent monotonic start, so their numbers cannot be subtracted as an exact shutdown duration.

## Source-supported interpretation

Frozen launcher lines 100–111 wait for the remaining execution allowance, mark `timeout=true` on `TimeoutExpired`, then poll and send SIGKILL only if the child still appears live. The record stores no signal-request event. Actual exit 0 therefore does not establish that a signal was sent, a kill occurred, or a particular race happened. The actual Python 3.11.15 `subprocess.Popen._wait` implementation checks nonblocking child status before deciding its deadline expired; a later poll can observe a different status. This is a possible ordering, not an authenticated event timeline for this attempt.

The guarded insertion persists the completed capsule immediately after the original PASS assignment inside the SDK context; context exit then calls SDK close. Parent verified all 144 frames/149 measurement artifacts, but admission deliberately vetoes a timeout even when the child later has exit 0. The legacy post-shutdown snapshot remained `STARTED`; SDK cleanup is independently unobserved. This behavior matches the reviewed contract rather than proving an admission bug.

Most of the filesystem-observed span was occupied by acquisition/image persistence, and the completed capsule appeared close to the execution boundary. That supports **late measurement completion**. It does not isolate rendering versus persistence cost, establish a uniquely slow shutdown, prove a framework defect, or justify a longer cap. No camera, wait, gain or shutdown correction is selected from these records.

Next concrete decision is instrumentation-only: a future version could record parent monotonic launch/deadline/timeout-catch/poll/signal-request/reap events and child measurement-persist/close-entry/close-return events with explicit clock origins. This proposal is not implemented or executed here and does not retroactively admit the dataset. Any subsequent data protocol must disclose that these layouts were acquired/accessed; they must not be relabelled genuinely uninspected.

## Provenance and safety

The preserved ledger, capsule and process log retain SHA256 `eb5e28dd23a79e1c0ee2382285cb827bd6d86893bebac93915d6c16c226a0d3f`, `a338e07cafbc69a128ff5d696e1161abe9e9ef1588dfef0b2f18a04fc1de4773`, and `12db81b66a109be700b741f095f9a7e73d21654e07f8439665d8bbdc96798986`. External root: `/home/favl/navfm-training-evidence/prospective-collection-v1-01`. The inspected worker-standard-library source `/home/favl/miniforge3/envs/isaac/lib/python3.11/subprocess.py` hashes to `baa9f9138d8d20df6284f67e7d2e790f847f65e2c5370de322d54cccd737f2d9`.

Validation was limited to frozen source inspection, allowlisted SDK lifecycle lines, frame-clock scalars and filesystem metadata; no RGB, geometry, model contents, simulator or tests were opened/run. Private seed/specification values remain undisclosed. Raw evidence and all original seals/registries remain external and unchanged; no admission file exists. Publication boundary is this findings document only.
