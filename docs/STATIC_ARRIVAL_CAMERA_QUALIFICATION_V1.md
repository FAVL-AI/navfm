# Static-arrival camera qualification v1

**Status: prepared for approval; not executed.** This freezes one small camera check on the already-specified `legacy_corridor_scene_0` fixture. Its geometry is bound to the existing F0 schedule and constructed through the same `legacy_boxes` builder. The fixture specification is exposed; this qualification would create new technical RGB captures. Their new technical episode identity and files are permanently excluded from fit, threshold-selection, descriptive-assessment, scoring, and any future calibration dataset. The builder checks the full planned schedule for exact episode-ID and body-pose overlap; both sets are empty. The scene specification and appearance family still overlap planned F0, so this check exposes scene-0 camera appearance. It does not touch other scheduled episodes or assessment scenes.

The exact ordered schedule is three references followed by five queries under `camera_qualification_v1_legacy_corridor_scene_0`. Each frame has a distinct immutable ID. These are eight static pose observations, not a continuous-motion trajectory. The bound body poses, in `(x m, y m, yaw rad)` order, are:

| Order | Image ID | Role | Body pose |
|---:|---|---|---|
| 1 | `camera_qualification_v1_reference_00` | Reference | `(1.03, 0.33, 0.07)` |
| 2 | `camera_qualification_v1_reference_01` | Reference | `(1.37, 0.33, 0.07)` |
| 3 | `camera_qualification_v1_reference_02` | Reference | `(1.71, 0.33, 0.07)` |
| 4 | `camera_qualification_v1_query_00` | Query | `(2.05, 0.33, 0.07)` |
| 5 | `camera_qualification_v1_query_01` | Query | `(2.39, 0.33, 0.17)` |
| 6 | `camera_qualification_v1_query_02` | Query | `(2.73, 0.33, 0.27)` |
| 7 | `camera_qualification_v1_query_03` | Query | `(3.07, 0.33, −0.03)` |
| 8 | `camera_qualification_v1_query_04` | Query | `(3.41, 0.33, 0.07)` |

The camera is 320×240 RGB with 68° horizontal FOV, 0.55 m height and 0.20 m forward offset. It uses the existing training lighting, eight warm-up steps, 16 simulation steps per second, and four held simulation steps per capture. This is a nominal 0.25-second hold/4 Hz target, not a guarantee of exact wall-clock or rendering cadence. Native `rendering_time` and rational `rendering_frame` values are retained; timestamps must be ordered and lie inside the authored pose hold, and actual intervals remain reportable without a new 4 Hz tolerance. No time is inferred from frame index. No evaluator labels are generated or passed to capture code.

The child harness constructs `IsaacApp` before importing Omniverse, camera, or USD modules, then imports and calls the production worker's `_geometry`, `_set_lighting`, and `_capture_frame` functions. It uses the same app/camera setup and verifies the same training-scene geometry digest. The target interpreter's installed `isaacsim` distribution metadata reports version `5.1.0.0`; this is bound and checked by the worker before app launch. The app's `(5, 0)` value is only its 5.x compatibility branch, not an observed simulator version. Parent admission additionally verifies the exact frame inventory/order, captured-image hashes and dimensions, raw RGB usability recorded from the cloned snapshot, same-snapshot identity/clock/pose metadata, strictly ordered native clocks, four-step hold duration, the existing camera timestamp window, float32-aware position readback, quaternion readback, normal SDK-context return, child return code, timeout state, reaping, and finalization hashes. The terminal/registry records bind hashes for the capture report and every image/metadata file; admission rechecks those hashes. If a capture criterion fails, the worker best-effort records requested and actual pose readbacks plus a cloned raw frame under failure evidence. A hard kill can still interrupt a write, which remains a FAIL. There are no geometric labels in the output. The SDK context returning and child exit 0 do not independently prove every SDK resource was cleaned up.

One bounded independent source integration review checked the chain from the pinned config and source hashes, through parent-generated input and nonce, into the qualification child. It confirmed that Omniverse, camera, and USD modules load only after `IsaacApp` construction; the child imports the production capture helpers, not a copy of their algorithms; and the label-generation function is not imported or called. It also confirmed zero planned episode/image/exact-pose collisions, matching scene-0 geometry, bounded exceptional cleanup, and completion-marker issuance only after terminal/registry persistence and artifact re-verification. The parent uses a distinct one-shot external registry and emits `qualification_complete.json`, never a dataset-admission marker. The CLI requires an explicit execution flag, exact clean HEAD, current source/interpreter hashes, a new external output path, and the bound Isaac worker interpreter. Reviewer model/settings were requested as Astra ultra; runtime identity/settings could not be independently verified. The review did not run simulator or camera code.

The proposed cap is **120 seconds for the complete qualification attempt**, not per frame or family. It begins at runner-script entry after Python startup and the small standard-library imports, and covers source/config preflight, reservation/input writes, child startup, Isaac startup, scene construction, warm-up, all eight captures and incremental image/metadata writes, SDK-context return, child termination/reaping if needed, output verification, terminal records, and qualification-marker finalization. The first 90 seconds are the child-execution allowance, the next 10 seconds are reserved for TERM/KILL and reaping (five seconds each), and the final 20 seconds are reserved for parent verification/finalization. Exception and cancellation handling also attempts TERM/KILL and reap within the reserved cleanup window, recording signal, wait, and reap failures. The parent checks the elapsed limit after finalization and revokes the marker on overrun. The output and registry terminal records must both say `finalization_complete=true` for a success marker to be admitted, and the marker binds both terminal hashes and the capture-artifact inventory. This cap is a **proposal**, not a measured feasibility result. Eight frames cannot establish that one 176-frame family fits within 600 seconds, and this attempt does not qualify all five families.

This is a technical capture qualification only. A PASS would support the tested scene-0 capture path and cadence. It would not complete the full family gate, admit the capture images as calibration data, establish encoder behavior, validate proximity labels, or establish physical stopping/navigation.

## Validation without simulator execution

CPU tests use only a harmless subprocess fixture and synthetic JPEG/metadata records. They exercise the exact parent supervisor and admission verifier, including ordering/label/snapshot rejection, worker failure, timeout/reap, one-shot registry use, and finalization-marker failure. These tests are process-contract checks only; they are not camera, rendering, cadence, or Isaac qualification.

## Approval command

After reviewing the exact commit, run once from a clean worktree and substitute its full SHA:

```sh
PYTHONPATH=src:scripts /home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/static_arrival_camera_qualification_v1.py \
  --freeze FULL_APPROVED_COMMIT_SHA \
  --out /home/favl/navfm-runtime-evidence/static-arrival-camera-qualification-v1/attempt-01 \
  --execute-approved
```

The command consumes one external registry identity. Preserve all partial images, readbacks, child output, and failure records. No retry, automatic family capture, model inference, fitting, scoring, collection, or navigation follows this qualification.
