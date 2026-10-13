# Prospective camera qualification v1: incomplete terminal report

The authorized `seal → qualify` milestone stopped at **qualification FAIL** from exact freeze `cfdb4033a88265f8d143a40a38a98ca2ccc09003`; [protocol](PROSPECTIVE_OFFLINE_DATA_V1.md). CPU seal completed PASS, privately, with directory 0700/file 0600 verified. No private seeds, specification contents or commitment values are published. No fresh-layout RGB collection, model scoring, training, navigation or robot process ran.

## Saved frame checks versus overall admission

The single 120-second known-fixture process was reaped after 59.438263 seconds. Launcher error was `ValueError: stage incomplete`. Its final preserved capture snapshot is still `STARTED`, despite **19/19 candidate frames recording PASS**. Thus the overall camera acquisition gate remains **NOT ESTABLISHED**; the saved candidate checks do not override the failed terminal contract.

| Known technical route | Expected | Saved PASS |
|---|---:|---:|
| layout 0 forward/history | 16 | 16 |
| layout 0 reverse | 1 | 1 |
| layout 1 forward at 100 m offset | 1 | 1 |
| layout 1 reverse at 100 m offset | 1 | 1 |

All saved pixels use the same cloned callback frame as native rational ReferenceTime and rendering_time; shape 240×320×4. Captured timestamps span 1.166666701–7.166666880 seconds, strictly increasing globally across route transitions. Each retained frame is 0.333333343 seconds after pose authoring and exactly at its recorded hold end. All recorded RGB-usability, camera orientation and represented-float32 pose checks passed. Actual-versus-expected float32-position maximum residual is 0 m; original requested-world residual reaches 3.051758e−6 m at the 100 m branch, preserved rather than misclassified as motion. Nineteen JPEGs and all frame/readback metadata remain external. These are recorded checks, not an independent pixel-phase calibration or physical robot motion result.

## Bounded finalization diagnosis

Frozen `prospective_capture_v1.py` assigns overall PASS in memory at the end of the IsaacApp context. It does not persist that terminal assignment inside the context: the terminal atomic snapshot is deferred to the outer Python finally block. `IsaacApp.__exit__` calls `close`, which calls installed `SimulationApp.close`; the installed implementation ends in `shutdown_and_release_framework`, with installed default fast_shutdown=True and source comments describing process termination (no actual runtime flag readback was retained). The last worker-log lifecycle marker is `Simulation App Shutting Down`; no terminal capture snapshot follows it. This supports a shutdown/finalization ordering defect as the explanation for the absent terminal record, rather than a recorded frame-criterion failure. The exact child return code was not retained by this launcher, so no specific child exit status or C++ termination branch is invented.

The process log also contains native interpolation warnings; those warnings alone do not identify the terminal-record cause or prove sensor failure. No runtime repair, second process, tolerance change or retroactive PASS reclassification was performed. The source defect is localized to durable completion ordering; a future separately versioned correction can persist the completed measurement capsule before SDK shutdown and retain the child's exit status while preserving all 19 criteria. That correction and a new qualification attempt are not executed here.

## Source identity and preserved evidence

External qualification root: `/home/favl/navfm-training-evidence/prospective-offline-v1-qualify-01/`. All 26 ledger-bound artifacts were rehashed, including 19 JPEGs, four trajectory-label pickles, known specification, capture report and process log. The private seal artifacts remain unchanged and private; their values/hashes are deliberately absent from this public report. `result-integrity.json` stores the derived scalar audit externally. Partial and successful candidate records are retained, while the stage's original FAIL/STARTED statuses remain immutable.

| Qualification evidence | SHA256 |
|---|---|
| Capture snapshot | `7feea1620049f7eccb205bbb938e81627c911398d55794e0397ea420afcaddfa` |
| Stage ledger | `b8504b20a98f898e1f46d9be7002bf548edecb2025dde837961410971278bb59` |
| Frozen capture source | `c94f7e0ca1fc735e3b1d6b4edeae5e212a4139ffa26dd86756b95311d527208d` |
| Frozen launcher source | `37b4acb179616a765a36b8a8059b1d61d32af6667efc522ca42b628113793681` |
| Worker process log | `df1b24ad03c952043bd0e3bc47c2ffefc7cb21eb16706802a4e5c4f09b66e209` |
| IsaacApp source | `27a94026c4b6a370971a34f5e7d7ee8674aebcf4aa97e2c96299d62df6694b87` |
| Installed SimulationApp source | `7cbaa6f00e935a6f14bf1c28ec0db089fd924e931f3b0deee07a822f9b7d0090` |

Validation: exact clean source/input/metadata/empty-registry/fresh-output preflight PASS; seal permission/status checks PASS; saved qualification population/readback/scalar audit and 26 artifact hashes PASS; overall terminal admission FAIL. Source tests were not rerun for this result-only report. No generated geometry, images, labels, seeds, arrays, weights or logs enter Git. Original source freeze and all earlier failures stay protected.

Next decision: a narrowly versioned terminal-report correction with the same sensor criteria, followed only by an explicitly admitted new known-fixture qualification. Fresh collection and both scoring stages remain NOT RUN; no physical-plant or navigation admission follows this report.
