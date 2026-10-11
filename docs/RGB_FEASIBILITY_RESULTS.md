# Executed engineering results and checkpoint

Repository `/home/favl/projects/navfm-engineering-recording`, branch
`agent/engineering-recording`, base `e7633fe`. Hospital instrumentation remains
unchanged. All evidence is external under `/home/favl/navfm-runtime-evidence`.

| Attempt | Outcome | Cause or observation | Repair / interpretation |
| --- | --- | --- | --- |
| rgb-simple-20261007-baseline-01 | Failed before episode | Failed to get root link transforms from backend | Preserve failure; inspect tensor-view lifecycle |
| rgb-simple-20261007-baseline-02 | Failed before episode | Robot prim deleted while used by tensor link view | Contact schemas moved before physics initialization |
| rgb-simple-20261007-baseline-03 | Recording PASS; timeout | 180 frames, 60 inferences; ~0.092 m travel despite repeated 0.2 m/s requests | Asset readback: wheel stiffness 625, damping 0.1; opposing position servo |
| rgb-simple-20261007-baseline-04 | Recording PASS; timeout | Prospective velocity drives stiffness 0, damping 10; 2.849 m travel | Passed goal without stopping; viable live RGB command path, unsuccessful terminal navigation |

Both completed episodes are retained; two startup failures are not silently
excluded. The repaired baseline is one completed episode, not three pairs.
Completed layer episodes: **0**. Completed matched pairs: **0**.

## Repaired baseline measurements

180 images at 640x480; 180 finite poses and aligned transitions; 60 model calls;
15.000000447 simulation seconds; zero missing recording frames. Independent
verification passed saved JPEG decoding, pose/time correspondence, transition
continuity, image/source hashes, and unchanged alignment tolerance. The verifier's
legacy stationary-instrumentation message does not classify this moving episode.

| Endpoint | Measured value | Denominator / boundary |
| --- | --- | --- |
| Correct stop events | 0 | 0 stop events; rate undefined |
| Premature stop events | 0 | 0 stop events; rate undefined |
| Terminal navigation success | 0 | 1 completed episode; no correct stop, timeout |
| Final position within 0.5 m | 0 | 1 episode; final distance 0.849376 m |
| Closest approach | 0.006405 m | Minimum over 180 evaluation captures, frame 125 |
| Captures inside goal radius | 63 | 180; arrival is not stopping |
| Reported collision episodes | 0 | 1 completed episode; detector positive control pending |
| Clearance-envelope violation duration | 0 s | 15.000000447 s, threshold <0.3 m; conservative visual-bound proxy |
| Path length | 2.849365 m | All 180 before-to-after transitions |
| Policy wall-clock latency p95 | 27.687 ms | 60 calls, preprocessing through synchronized inference/PD, cold start included |
| Policy maximum latency | 226.719 ms | 60 calls |
| Recording-loop wall-clock p95 | 474.021 ms | 180 loops; includes rendering and attestation |

No safety or superiority inference follows from these counts. Collision and
clearance measurements are not interchangeable, and contact sensitivity remains
unqualified. Failed startups have no navigation/contact observations.

## Evidence

For each completed run: `runtime_manifest.json`, `start.png`, `goal.png`,
`fixture.usda`, `trajectory/{0..179}.jpg`, pose pickle, transitions and metadata.
Baseline-03 also preserves the exact pre-repair runner/policy source snapshot
and wheel inspection log. Its recorded source hashes refer to that source version;
the current runner intentionally differs. Baseline-04 independently verified
against the executed source. Both completed runs preserve digest-named source
snapshots. A comment-only hook repair changed the current runner; the RGB verifier
checks the exact archived digest without relaxing source or recording checks.

Baseline-04 start/goal and final frame were inspected visually. The corridor,
blue obstacle and orange goal are visible at start. The final view shows the wall
ahead after the robot has passed the goal. This supports the observed overshoot;
it does not certify visibility for unexecuted routes.

Actual run command (from repository):

```bash
OMNICLIENT_HUB_MODE=disabled \
NAVFM_UPSTREAM=/home/favl/projects/navfm/third_party/visualnav-transformer \
/home/favl/miniforge3/envs/isaac/bin/python scripts/run_rgb_feasibility.py \
  --checkpoint /home/favl/projects/navfm/checkpoints/vint.pth \
  --robot /home/favl/projects/navfm/assets/robots/yahboom_m3_pro/yahboom_m3pro_physics.usd \
  --out /home/favl/navfm-runtime-evidence/rgb-simple-20261007-baseline-04 --steps 180
```

Verification and reproducible offline metrics:

```bash
.venv/bin/python scripts/verify_rgb_feasibility.py --manifest \
  /home/favl/navfm-runtime-evidence/rgb-simple-20261007-baseline-04/runtime_manifest.json
.venv/bin/python scripts/summarize_rgb_feasibility.py --manifest \
  /home/favl/navfm-runtime-evidence/rgb-simple-20261007-baseline-04/runtime_manifest.json
```

Validation: ruff passed all new Python files. Targeted pytest passed **98 tests**
with `NAVFM_UPSTREAM` set to the existing clone. An initial invocation had
94 passes and three `UpstreamNotFound` errors; correcting that environment
variable made all pass. No tests or timestamp tolerances were weakened.

## Exact unresolved blocker and next decision

`RGB_LAYER_UNRESOLVED`: located CBF requires privileged robot/obstacle geometry;
the learned temporal stop head is GNM-trained shadow-only, without documented
ViNT calibration or held-out stopping authority. The methods draft gives exact
entry points and input boundaries. Choose/provide the governing RGB-only layer
specification and in-domain calibration/validation plan. Only then can three
honest matched pairs run; no proxy second arm was created.

Before paired admission, implement that layer and verify disabled-layer replay
equivalence, deliberate-contact detector controls, and route visibility. The
three-pair configuration is prepared in `configs/pilots/rgb_simple_pairs.json`;
its blocked status is intentional. The confirmatory design is a proposal with
sample size pending paired pilot variability, not a falsely powered frozen test.
