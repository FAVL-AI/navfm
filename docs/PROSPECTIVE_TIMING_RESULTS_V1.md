# Known-fixture timing diagnostic result v1

Branch `agent/research-three-model-plan`; source freeze `f19a638cca3c8a6775fa7075c4f0222b34568800`. The one authorized diagnostic **FAIL**: 138/144 known-fixture frames completed PASS before the unchanged watchdog. No completion capsule or dataset admission exists. No private specification, fresh layout, scorer, training, navigation or robot process was accessed/launched. Original collection FAIL remains unchanged; no retry or corrective runtime followed.

## Measured process timeline

Parent events use one host monotonic nanosecond domain with explicit process clock IDs and paired wall anchors. Relative to the first parent event:

| Event | Seconds | Observation |
|---|---:|---|
| Launch request / return | .004365 / .006468 | Child created |
| Wait begin | .008123 | Original deadline policy unchanged |
| Timeout caught | 115.000075 | 115-second execution allowance expired |
| Poll | 115.002356 | Child still appeared live |
| SIGKILL request / call return | 115.003816 / 115.005743 | Request recorded; call return is not independent delivery proof |
| Reap return | 115.371868 | Observed child status −9 |
| Parent finalization event | 115.748177 | Available files retained/hashes bound |

Occupied wall was **115.752406 seconds**, timeout=true and child_reaped=true. Unlike the old collection's uninstrumented timeout, this attempt records the request and observed status separately. SDK close entry/return was not observed; cleanup remains independently unverified. This does not establish the old attempt's shutdown cause.

## Fixed call-interval reduction

All 1,520 timed call pairs that began have matching END records. The 552 completed app steps equal four per completed frame. Durations below begin after BEGIN-event fsync and end before END-event fsync; SDK entry is inclusive and may contain nested initialization/warmup work. They are call scopes, not additive isolated hardware costs.

| Scope | Complete calls | Sum seconds |
|---|---:|---:|
| SDK constructor (configuration object only) | 1 | .000003438 |
| SDK context entry/startup | 1 | 5.512959391 |
| sim.step, including synchronous renderer/orchestrator work | 552 | 92.589549753 |
| Camera pose setter | 138 | .159269177 |
| Cloned current-frame read | 138 | .021629546 |
| PIL image save: encode and write combined | 138 | .084321252 |
| Atomic capture snapshot writes | 552 | 4.274426737 |
| Completion capsule / SDK close | 0 / 0 | NOT OBSERVED, not zero cost |

The dominant completed measured call scope is the unchanged app-step path. Pinned `IsaacApp.step` invokes one synchronous `rep.orchestrator.step` with the frozen dt/subframes and then reads simulation time. This does not isolate GPU rendering, physics, synchronization or internal framework overhead; no redundant step call is demonstrated. PIL conversion/argument preparation occurs outside the timed save; encode versus file write is not separately resolved. Snapshot time cannot be treated as all persistence cost, and overlapping inclusive intervals must not be summed with parent wall time.

Instrumentation is intrusive: completed BEGIN-event-to-call-start brackets sum **2.611206641 seconds**, including journal/fsync and small Python call-entry overhead. That excludes END/other event writes and is not total instrumentation cost. The child never reached its total-overhead final marker. Parent reported .018734370 seconds of logging before its final event. These observations cannot be used to subtract instrumentation from the old run or infer how an uninstrumented repetition would finish.

## Integrity, provenance and next decision

Parent 10 and child 3,455 JSONL events have exact sequence order; timed interval clocks are ordered and all 146 final artifact hashes match. Six preparation tests plus three lifecycle-failure controls (9 total) and Ruff PASS; population 3036 retains 3027 prior nodes. Source/input preflight PASS. The review caught and resolved logging-induced orphan risk before launch: unconditional kill/reap survives failed launch/poll/signal-request journal writes. Measurement/process completeness remains FAIL; no threshold/deadline modification.

External acquisition evidence: `/home/favl/navfm-training-evidence/prospective-timing-v1-01`. CPU-only fixed reduction: `/home/favl/navfm-training-evidence/prospective-timing-v1-reduction-01/summary.json`, SHA256 `cc7c6d0d97acafa4e773cfe429965adfa520c15e651e21d52ad199cd583a3f40`. It binds consumed input hashes and scope formulas separately from the original ledger; no original evidence file was rewritten.

| Artifact | SHA256 |
|---|---|
| ledger.json | `2382e38a736cfab8e2294c5bcbde991f3cda64c395091de9e53def7e0edc0671` |
| parent_events.jsonl | `7dcbd24d89358acdc0e38b3e682e3b3eeef4ea31c07236989bfcc9ba89891cbe` |
| child_events.jsonl | `5848f7ad069d5ca567fc6a30edda8c9627ce53a853f280650a41db717317be61` |

Next concrete decision is bounded inspection of the synchronous app-step/render path for a source-supported performance correction that retains all four held steps and camera criteria. These records do not select a renderer change, reduced hold, larger cap or shutdown workaround. No intervention is implemented. Raw images/labels/events remain external; this known-fixture timing diagnostic neither admits the previously acquired private pilot nor makes those layouts uninspected again.
