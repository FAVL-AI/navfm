# Prospective acquisition budget amendment proposal v1

**UNAPPROVED / UNEXECUTED.** Branch `agent/research-three-model-plan`, baseline `0bf3f6da728798c113f0d6da84fb19c983705573`. Preparation only: this proposal has no acquisition entry point and cannot authorize a run. Old 115+5-second failures and their admission decisions remain immutable. Previously acquired private layouts are **ACCESSED, not uninspected**; the original seal remains unchanged, with no replacement layouts or regenerated seeds.

## One bounded source pass

Pinned `IsaacApp.step` lines 222–231 invoke one `rep.orchestrator.step` with the configured dt/subframes and then read simulation time. Installed Replicator 1.12.27 /107.3.3 `orchestrator.py` lines 1502–1624 intentionally update until a frame is scheduled and, by default, wait for the dispatcher reference time to reach the capture time. Its primary source documents render waiting as necessary to match annotation/writer data to simulation state. Multiple internal app updates are therefore not demonstrated redundant capture calls.

Lines 450–466 and the subframe setter show effective RT subframes take the maximum of requested and global settings. The prior actual global value was not recorded; neither forcing it lower nor disabling render waiting is justified by this evidence. No documented configuration defect is established. **Performance investigation stops here; no performance correction is selected.** Source identities are pinned in the proposal JSON. No runtime, RGB/private geometry access or additional source search occurred.

## Proposed hard budget

| Disjoint accounting allocation | Seconds | Evidence/rationale |
|---|---:|---|
| Parent metadata/setup | 5 | Explicit engineering allowance, including launch preparation; not a measured upper bound |
| SDK startup/warmup | 15 | One instrumented context-entry interval was 5.512959 s; 15 s is a prospective allowance, not a confidence bound |
| Capture work excluding capture snapshots/label serialization | 135 | 552 completed app steps took 92.589550 s; proportional 576-step reference is 96.615182 s, not a guaranteed projection. Includes pose/frame checks and combined PIL encode/write; retained logging would consume this allowance too |
| Capture snapshot/label persistence | 10 | 552 snapshot calls took 4.274427 s. This separately accounts inline snapshot/label serialization, excluding PIL save already above; not all storage cost is isolated |
| Completion capsule/verification | 5 | Exact full cost is unmeasured; explicit prospective reserve |
| SDK shutdown | 15 | Completion cost is UNKNOWN; this reserve must be validated, not asserted sufficient |
| Child reaping/finalization | 5 | Preserves an explicit cleanup reserve; includes final evidence binding |
| **Hard total** | **190** | Sum of disjoint allocations, including startup, persistence, shutdown and reaping |

These are accounting allocations, not independently qualified phase deadlines. Inline/outer intervals may overlap; future enforcement must not double-count their wall time. A future launcher would enforce a single 190-second whole-process cap with a 185-second execution allowance and five-second cleanup reserve, record actual timeout/exit/reaping, and retain FAIL on a deadline breach. There is no change to frame count, four held steps per frame, image quality, timing/pose criteria or admission checks. A completed capsule alone cannot override process failure.

The old 144-frame collection capsule appeared near its 115-second execution boundary, while the separate instrumented known fixture reached only 138 frames. Instrumentation's completed BEGIN-to-call-start brackets contributed 2.611207 s but total child logging overhead was unavailable. Neither observation supports a high quantile, 95% margin, old shutdown explanation or guaranteed completion. The 190-second proposal is a conservative finite engineering allocation; **feasibility and shutdown margin are NOT DEMONSTRATED**. It is not an extension of either consumed attempt.

## Review/execution boundary

`prospective_budget_proposal_v1.py` validates exact phase membership/sum, the 190-second proposal, unchanged acquisition and exposure disclosure; it has no subprocess/simulator launcher. The JSON keeps `execution_authorized=false`. Seven focused controls reject authorization, missing phases, total drift, boolean allowance, held-step changes and false uninspected labelling. Population retains all prior nodes. Proposed publication contains only validator/config/tests/protocol and population metadata; raw evidence stays external.

Next decision: approve or reject this explicit budget amendment before any versioned acquisition continuation is implemented/launched. If approved later, bind its exact source/config, existing accessed specification and qualification identities in a new one-attempt protocol; do not retroactively admit old data, relax camera checks, silently regenerate layouts or start scoring. No new acquisition or scoring is authorized by this preparation document.
