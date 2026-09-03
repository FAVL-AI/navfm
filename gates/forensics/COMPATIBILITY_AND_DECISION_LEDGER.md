# Compatibility and decision ledger — the causal record

Every entry carries the chain from what was observed to what is now claimed, including the field that is easiest to leave out and hardest to reconstruct later: **why the checks that were already running did not see it**.

Twenty-one entries. Sixteen are defects caught before any admitted result existed; two (`FL-003`, `FL-011`) are findings about the released upstream artefacts and their sampling semantics rather than about this work; one (`FL-008`) is an open gate scope issue awaiting a decision that is not engineering's to make; one (`FL-012`) is an error in this work's own verification harness, caught by review rather than by any check here — which is why it is recorded at full severity rather than quietly fixed.

Author: Frank Asante Van Laarhoven · 2026-08-13

---

## Ranked summary

Severity is `impact x detectability x propagation`, each 1-5, with **detectability inverted** — 5 means almost nothing would have revealed it. Irreversibility is a separate flag and is deliberately not folded into the score; a cheap permanent mistake and an expensive recoverable one need different responses.

| Rank | ID | Finding | Impact | Undetectability | Propagation | Severity | Band | Irreversible |
|---|---|---|---|---|---|---|---|---|
| 1 | `FL-019` | A zero produced by a run that never started, reported as a clean result | 5 | 5 | 5 | **125** | CRITICAL | no |
| 2 | `FL-001` | Waypoint un-normalisation missing; the safety clamp hid it | 5 | 5 | 4 | **100** | CRITICAL | no |
| 3 | `FL-006` | Wheel radius inherited from a different robot | 4 | 5 | 5 | **100** | CRITICAL | no |
| 4 | `FL-016` | Asset mirrors report a complete closure while missing every material module | 5 | 5 | 4 | **100** | CRITICAL | no |
| 5 | `FL-018` | A repair verified by the same defective discovery that caused the fault | 5 | 5 | 4 | **100** | CRITICAL | no |
| 6 | `FL-013` | optimizer.step() returning is not evidence the model changed | 4 | 5 | 4 | **80** | CRITICAL | no |
| 7 | `FL-014` | A training smoke test could quietly mutate a released checkpoint | 5 | 4 | 4 | **80** | CRITICAL | yes |
| 8 | `FL-002` | Wheel joints imported with zero stiffness and zero damping | 5 | 5 | 3 | **75** | CRITICAL | no |
| 9 | `FL-009` | Installing a dependency would have broken the freeze audit before it ran | 5 | 5 | 3 | **75** | CRITICAL | yes |
| 10 | `FL-012` | An invented loss passed the first train-path harness | 5 | 5 | 3 | **75** | CRITICAL | no |
| 11 | `FL-007` | Corrections that did not propagate — the dominant protocol defect | 4 | 4 | 4 | **64** | CRITICAL | no |
| 12 | `FL-015` | The poor navigation images were the world, not the camera | 4 | 4 | 4 | **64** | CRITICAL | no |
| 13 | `FL-021` | Tightening a threshold fixed a false positive and created a false negative | 4 | 4 | 4 | **64** | CRITICAL | no |
| 14 | `FL-003` | About 19% of the released ViNT checkpoint is never executed | 3 | 5 | 4 | **60** | CRITICAL | no |
| 15 | `FL-017` | The camera-view acceptance test passed both known-bad frames | 4 | 5 | 3 | **60** | CRITICAL | no |
| 16 | `FL-004` | Camera parented to a prim named top_arm_mount but sitting at chassis height | 4 | 4 | 3 | **48** | HIGH | no |
| 17 | `FL-020` | A URL validated as a filesystem path, refused before anything ran | 4 | 4 | 3 | **48** | HIGH | no |
| 18 | `FL-008` | G2 mis-scoped in both directions | 4 | 3 | 3 | **36** | HIGH | no |
| 19 | `FL-005` | Stale pilots reported as fresh output | 3 | 4 | 2 | **24** | MODERATE | no |
| 20 | `FL-011` | NoMaD produces 29 samples where GNM and ViNT produce 30 | 2 | 4 | 3 | **24** | MODERATE | no |
| 21 | `FL-010` | A pre-execution gate audit run after execution, reported as failure | 2 | 3 | 2 | **12** | MODERATE | no |

---

## `FL-019` — A zero produced by a run that never started, reported as a clean result

**Severity 125 (CRITICAL)** · impact 5 · undetectability 5 · propagation 5 · irreversible: no · status CLOSED

**What was observed.** Three times in one session a null result was read as a clean one. A `pgrep -f` wait loop matched its own wrapper's command line, so a background job waited a day, ran nothing and wrote a 0-byte file while every status check said 'in progress'. A closure repair reported FULL_RENDER_CLOSURE true using the same traversal that caused the defect. And a scene test reported `mdl_error_count = 0` because its preflight had refused the URL and exited before Isaac started.

**Root cause.** Measurements were represented as bare values. A value carries no record of whether the machinery that produces it ever ran, so `0` from a live measurement and `0` from an inert one are the same token. Every consumer then reads the second as the first, because that is the reading that requires no further work.

**Why existing checks missed it.** There was nothing to miss: the artefacts were well-formed and their values were the values a healthy run produces. Detection requires a fact the artefact did not carry -- whether the measurement executed over a non-empty population. No amount of care applied to the value can recover it.

**Scientific risk had it survived.** The general form is severe. `0 collisions` from a robot that never moved, `0 invalid rows` from a validator over an empty input, `0 NaN gradients` from a backward pass that did not run -- each is a safety or correctness claim supported by an absence of observation rather than an observation of absence.

**Alternatives considered.**
  - Add liveness assertions to each gate individually
  - Require reviewers to check that a run produced output
  - Make liveness part of the measurement's type, enforced at construction

**Decision.** `src/navfm/measurement.py`: a `MeasurementEnvelope` carrying liveness, value and provenance together. It refuses at construction to hold a value while liveness is incomplete, and reports RUN_LIVE_NO_MEASUREMENT rather than MEASURED_ZERO when the examined population is empty. Status is five-valued -- NOT_RUN, RUN_FAILED, RUN_LIVE_NO_MEASUREMENT, MEASURED_ZERO, MEASURED_NONZERO -- because the four ways of lacking an answer need different responses and a boolean collapses them into the one that resembles success.

**Decision rule.** MEASUREMENT = LIVENESS + VALUE + PROVENANCE, never MEASUREMENT = VALUE. A reported zero is a conclusion only after liveness is established; otherwise it is missing evidence wearing the appearance of success. Null execution and zero outcome must never share a representation.

**Rejected, and why.** Per-gate liveness assertions and reviewer discipline were both rejected: this failure occurred three times in one session inside an audit explicitly built around the declared-versus-observed distinction. Intent is demonstrably not the control; the type is.

**Correction.** Envelope type with `require_evidence()` that raises rather than returning a value, `not_run()` for the honest empty case, and pessimistic liveness defaults so a forgotten field yields NOT_RUN rather than a silent pass.

**Validation.** 28 tests, each of the three incidents encoded as a case that must not pass: a scene that never loaded, a job that never ran, and a validator over an empty population. A stationary robot is asserted not to prove zero collisions.

**Regression control.** `value` is refused at construction when liveness is incomplete, so a gate cannot emit a bare number without the proof that it measured anything.

**Evidence.**
  - src/navfm/measurement.py
  - tests/test_measurement.py

**Impact on results.** No published result rested on one of the three: the closure repair was caught by an unchanged render, the inert job by an empty output file, the unloaded scene by a REFUSED line. All three were caught by observation, none by a check.

**Claim boundary.** The type is in place with tests. Migration of the gates is staged: scene load, render, dependency audit, training smoke and evaluation first.

**Not claimed.** Not a claim that existing gates already emit envelopes. Until a gate is migrated, its zeros carry the same ambiguity described here.

**Propagation.** Applies to every gate in the repository and to future safety metrics, where the failure mode is worst -- a stationary robot produces a perfect collision record.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-001` — Waypoint un-normalisation missing; the safety clamp hid it

**Severity 100 (CRITICAL)** · impact 5 · undetectability 5 · propagation 4 · irreversible: no · status CLOSED

**What was observed.** ViNT waypoints were passed to the controller without being scaled by the dataset's metric spacing, making every commanded velocity roughly eight times too fast. The robot's motion looked plausible in both pilots.

**Root cause.** The model predicts waypoints in units of dataset waypoint spacing, not metres. The conversion is implicit in the reference deployment code and was not carried across as a named step, so there was no place for it to be absent from.

**Why existing checks missed it.** The 0.45 m/s saturation limit returns an identical command for the correct 0.48 m/s and the wrong 4.0 m/s, because both exceed it. The safety limiter erased the difference before any assertion could see it. Every downstream artefact -- trajectory shape, pose log, image sequence -- was byte-identical under both the correct and the incorrect scaling.

**Scientific risk had it survived.** Every collected trajectory would encode a control law eight times too aggressive, while remaining indistinguishable from correct data in the regime where the clamp is active. The error would surface only in slow manoeuvres, i.e. precisely the fine control a navigation claim rests on.

**Alternatives considered.**
  - Scale inline at the call site in the collection script
  - Raise the velocity limit so the difference becomes visible
  - A named, separately tested conversion function

**Decision.** Added `unnormalise_waypoint` to `src/navfm/control.py` as a named conversion with its own tests, and a test that asserts the concealment property itself.

**Decision rule.** When a safety mechanism can make a wrong value observationally identical to a right one, the conversion must be a named, independently tested unit -- because no integration test downstream of the clamp can ever discriminate.

**Rejected, and why.** Raising the velocity limit to expose the error was rejected: it would trade a silent correctness bug for a real collision risk on hardware, and it fixes the detector rather than the defect.

**Correction.** `unnormalise_waypoint(waypoint, *, metric_waypoint_spacing, waypoint_spacing=1)`, scaling only the x/y components and refusing non-positive or non-finite scales.

**Validation.** 22 tests in `tests/test_vint_action_bridge.py`, including `test_saturation_HIDES_the_scale_error_at_realistic_magnitudes`, which asserts that correct and incorrect commands are equal after clamping -- the test exists to document why the bug was invisible, not merely to check the fix.

**Regression control.** The concealment test fails if anyone removes the clamp or changes the limit, forcing a conscious decision rather than a silent change of detectability.

**Evidence.**
  - src/navfm/control.py — unnormalise_waypoint
  - tests/test_vint_action_bridge.py — 22 tests

**Impact on results.** No published result depended on it: the affected pilots are SIMULATION_DEVELOPMENT and carry admission_status NOT_ADMITTED. Had it reached a training run, every action label in that run would have been wrong by a constant factor.

**Claim boundary.** The conversion is correct for the GO Stanford metric spacing under the pinned reference configuration, verified against the upstream deployment constant.

**Not claimed.** This does not establish that the resulting velocities are correct for the physical Yahboom. The wheel radius remains a PROVISIONAL_SIMULATION_VALUE, so the metres are correct in simulation and unverified on hardware.

**Propagation.** Applies to every consumer of model waypoints: the collection script, the Navigation State panel's runtime, and any future deployment path. All three now route through the single named function.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-006` — Wheel radius inherited from a different robot

**Severity 100 (CRITICAL)** · impact 4 · undetectability 5 · propagation 5 · irreversible: no · status CLOSED

**What was observed.** The upstream Yahboom URDF specifies wheel radius 0.048 m in nine places, with a comment reading 'same as X3'. The M3 Pro is not an X3.

**Root cause.** A value copied across robot models without re-measurement.

**Why existing checks missed it.** It corrupts every commanded velocity and every odometry displacement by the same 20% factor. Uniform corruption passes every internal consistency check, because consistency is exactly what it preserves.

**Scientific risk had it survived.** A 20% error in every velocity and every recorded position, landing directly in the `position` array that becomes the action label.

**Alternatives considered.**
  - Keep 0.048 m as upstream-sourced
  - Block all simulation work pending caliper measurement
  - Adopt 0.040 m marked PROVISIONAL_SIMULATION_VALUE

**Decision.** Adopt 0.040 m, explicitly marked PROVISIONAL_SIMULATION_VALUE in the ledger.

**Decision rule.** Simulator engineering proceeds open-by-default on a documented, plausible, sourced value, provided the value is never claimed as measured and the marker travels with it.

**Rejected, and why.** Blocking on calipers was rejected because it would halt simulation development over a parameter that no simulation-stage claim depends on; the marker carries the uncertainty instead.

**Correction.** 0.040 m in all nine places in the vendored URDF fork.

**Validation.** Cross-repo forensic audit identified the same 0.048 error across three repositories; the URDF's own comment supplies the origin.

**Regression control.** The PROVISIONAL marker blocks promotion of any physical claim until a measurement with a recorded method replaces it.

**Evidence.**
  - assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf
  - docs/HARDWARE.md

**Impact on results.** Affects all simulated velocities and displacements. No admitted result depends on it; every simulation artefact is NOT_ADMITTED.

**Claim boundary.** A provisional simulation parameter, sourced and documented.

**Not claimed.** Not a measurement. 0.040 m has not been verified against the physical robot and must not be cited as a hardware specification.

**Propagation.** Propagates to every kinematic quantity in simulation, and to the G1 physical measurement task which must resolve it.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-016` — Asset mirrors report a complete closure while missing every material module

**Severity 100 (CRITICAL)** · impact 5 · undetectability 5 · propagation 4 · irreversible: no · status CLOSED

**What was observed.** The hospital and warehouse mirrors both record `closure_complete: true` with zero unresolved references -- 293 and 53 files respectively, each with a digest. Loading the hospital renders a uniformly red frame. There are zero `.mdl` files on disk in either mirror, against 10 and 13 MDL modules referenced.

**Root cause.** The closure walker followed USD-to-USD references to a fixed point but did not follow MDL material-module references. Materials are referenced by a different mechanism, so they were never enumerated and their absence was never noticed.

**Why existing checks missed it.** Every check upstream of the renderer succeeds. The stage opens, 1917 prims load, geometry is present, the camera renders, depth is finite and plausible. The closure manifest is not merely silent about the problem -- it positively asserts completeness, which is worse than saying nothing.

**Scientific risk had it survived.** Collecting a 'photorealistic hospital' dataset whose observation distribution is flat fallback colour. Every geometric property would be right and every appearance property wrong, and the resulting data would look like a valid indoor navigation corpus.

**Alternatives considered.**
  - Trust the closure manifest's completeness flag
  - Collect anyway and note the appearance caveat
  - Audit the stage directly and block on the defect

**Decision.** Both scenes marked NOT eligible. `scripts/audit_scene_assets.py` opens each stage, counts referenced MDL modules against files on disk, and the manifest takes eligibility from that audit rather than from the closure flag.

**Decision rule.** A provenance manifest is evidence about what a tool looked for, never proof of what an asset contains. Eligibility is decided by inspecting the loaded stage.

**Rejected, and why.** Collecting with an appearance caveat was rejected: appearance is the entire input to a visual navigation model, so a caveat would not scope the defect, it would only label it.

**Correction.** In-stage eligibility audit; manifest records `closure_flag_disagrees_with_audit: true` for both scenes.

**Validation.** hospital_v1: 10 MDL modules referenced, 0 on disk. simple_warehouse_v1: 13 referenced, 0 on disk. Both eligible=false. The rendered hospital frame has 96% of its saturated pixels in a single hue bucket.

**Regression control.** `build_scene_manifest.py` refuses to mark a scene eligible without an audit on record, and defaults to not eligible when none exists.

**Evidence.**
  - gates/scenes/SCENE_ELIGIBILITY.json
  - gates/scenes/SCENE_MANIFEST.json
  - gates/scenes/views/hospital_v1/pov_00.png

**Impact on results.** Blocks navigation-pilot collection until materials are obtained. No data was collected in either scene, so no artefact is contaminated.

**Claim boundary.** Concerns the two local mirrors at their current state on this machine, audited in-stage under Isaac Sim 5.1.0.0.

**Not claimed.** Not a claim that the upstream NVIDIA assets are incomplete. The defect is in the local mirroring, not necessarily in the source.

**Propagation.** Applies to every mirrored asset produced by the same closure tool, in this repository and in the sibling robotics repositories that share the mirror.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-018` — A repair verified by the same defective discovery that caused the fault

**Severity 100 (CRITICAL)** · impact 5 · undetectability 5 · propagation 4 · irreversible: no · status CLOSED

**What was observed.** After fetching the 10 MDL modules the dependency walk reported as missing, the mirror recorded FULL_RENDER_CLOSURE true with zero unresolved, and the scene rendered exactly as before -- still hue-collapsed, byte-identical composition. The repair verified itself as complete while changing nothing observable.

**Root cause.** `Usd.Stage.Traverse()` does not descend into instance prototypes. These scenes are heavily instanced: most walls and doors live under `/__Prototype_*`. The walk therefore enumerated 10 material modules and 20 textures where the scene actually requires 69 and 252 -- it was hiding roughly 85% of the material graph. Both the original closure manifest and my repair used that same walk, so the repair's completeness check asked the identical narrowed question and got the identical reassuring answer.

**Why existing checks missed it.** The completeness check and the discovery step shared an implementation. A verification derived from the same enumeration as the fix cannot detect an enumeration fault -- it will report success precisely when the enumeration is wrong in the same way for both. The MDL compiler was the only component with an independent view, and its errors were being read as noise.

**Scientific risk had it survived.** A scene certified render-complete, collected in, and published as a photorealistic interior while the majority of its materials never resolved. Every provenance field would be present and correct, and the observation distribution would still be wrong.

**Alternatives considered.**
  - Trust FULL_RENDER_CLOSURE and proceed to collection
  - Treat the unchanged render as a caching artefact and re-run
  - Take the renderer's own compile errors as the independent oracle

**Decision.** Treat the MDL compiler's `could not find module` errors as the authority over the dependency walk, and fix the traversal to include instance proxies and every prototype explicitly. Recount: 69 modules and 252 textures, all present.

**Decision rule.** A repair must be verified by an oracle independent of the discovery that produced it. When the fix and its check share an enumeration, the check confirms the enumeration, not the fix.

**Rejected, and why.** Accepting FULL_RENDER_CLOSURE was rejected because the render had not changed. An unchanged observable after a repair claimed complete is evidence against the claim, not an anomaly to explain away.

**Correction.** Traversal now uses `Usd.TraverseInstanceProxies` and walks `stage.GetPrototypes()` directly; relative paths resolve against the authoring layer rather than the root.

**Validation.** Referenced counts moved from 10 to 69 MDL modules and 20 to 252 textures, with 321/321 present and zero unresolved, reproduced across two independent runs.

**Regression control.** The mirror manifest records referenced counts per class, so a future traversal regression appears as a drop in what is asked for rather than as a clean pass.

**Evidence.**
  - gates/scenes/mirror_manifest_hospital_v1.json
  - scripts/mirror_scene_closure.py — discover_usd_dependencies

**Impact on results.** No data collected under the false completeness. It converts FL-016 from a small gap into an order-of-magnitude error: the original mirror was not missing 10 files but 321, while asserting completeness throughout.

**Claim boundary.** Concerns dependency discovery for instanced USD scenes under Isaac Sim 5.1.0.0.

**Not claimed.** Complete closure is not a claim that the scene renders correctly. Whether 321/321 clears the hue collapse is a separate gate and was unresolved when this entry was written.

**Propagation.** Applies to every mirrored asset produced by the same walk, and to any audit whose completeness check reuses the enumeration under test.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-013` — optimizer.step() returning is not evidence the model changed

**Severity 80 (CRITICAL)** · impact 4 · undetectability 5 · propagation 4 · irreversible: no · status CLOSED

**What was observed.** A train-path proof can call `backward()` and `optimizer.step()` and return cleanly while most of the intended network receives no useful gradient. In this run, 16 of ViNT's 504 trainable tensors and 16 of NoMaD's 644 received no gradient at all.

**Root cause.** The invocation and the effect are different events, and only the invocation is observable without extra work. This is the same class as the Yahboom commanding 0.45 m/s while moving 0.001 m.

**Why existing checks missed it.** There was no earlier check. A harness that asserts 'no exception raised' is satisfied by a completely disconnected model, because a zero gradient is not an error condition.

**Scientific risk had it survived.** Certifying that data can train a model when in fact the training path is partially or wholly disconnected -- with a well-formed evidence file to support it.

**Alternatives considered.**
  - Assert that backward() raised no exception
  - Assert on the aggregate count of changed parameters
  - Record per-tensor deltas, and name every tensor that did not move

**Decision.** Measure and record: parameters with gradients, with non-zero gradients, with NaN gradients, with Inf gradients, the global gradient norm, per-tensor before/after norms and digests for a watched set, and the full name list of every tensor the step did not move.

**Decision rule.** Verify the effect, never the invocation. This applies system-wide: commanded velocity against achieved displacement, optimizer step against parameter delta, camera mount name against measured height.

**Rejected, and why.** An aggregate count was rejected because 'most of them moved' is exactly how a genuinely disconnected branch survives review -- and it would have concealed the 16 dead tensors that turned out to be a real property of the released checkpoints (FL-003).

**Correction.** Per-tensor gradient and parameter-delta audit in the harness.

**Validation.** GNM 324/326 non-zero gradients and 326/326 changed; ViNT 486/504 and 488/504; NoMaD 628/644 and 628/644. Zero NaN and zero Inf gradients across all three. The excess of changed over non-zero-gradient tensors is AdamW's decoupled weight decay acting on zero-gradient parameters, which is expected.

**Regression control.** The harness returns FAIL if zero parameters change, if any gradient is NaN or Inf, or if no parameter receives a non-zero gradient.

**Evidence.**
  - gates/compatibility/{gnm,vint,nomad}_backward_optimizer_smoke.json

**Impact on results.** Turned a proof that a function was called into a proof that the model changed. Also produced FL-003, which only this check could surface.

**Claim boundary.** Establishes that one optimizer step measurably updates the in-memory model for each of the three architectures on this data.

**Not claimed.** Not a claim that training would converge, that the updates are in a useful direction, or that the data is admissible for training.

**Propagation.** The rule applies to every actuation-like operation in the system, simulated, numerical or physical.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-014` — A training smoke test could quietly mutate a released checkpoint

**Severity 80 (CRITICAL)** · impact 5 · undetectability 4 · propagation 4 · irreversible: yes · status CLOSED

**What was observed.** The train-path proof loads released weights and runs an optimizer step. Nothing in that sequence inherently prevents a save path from writing back to `checkpoints/*.pth`, and the resulting file would still load.

**Root cause.** Checkpoint files are the reproduction chain's fixed point -- R6 strict load, R7 determinism and G0.c all cite their digests -- and the smoke test is the first code in the repository that both reads them and mutates a model.

**Why existing checks missed it.** A mutated checkpoint is a valid checkpoint. It loads strictly, produces finite outputs, and passes every structural check. Only a digest comparison against the recorded value can see it, and the digest would have been recomputed from the mutated file if it were re-recorded.

**Scientific risk had it survived.** Silent invalidation of R6, R7 and G0.c: their evidence cites digests that would no longer correspond to the file on disk, and the reproduction ladder would rest on an artefact modified by an engineering test.

**Alternatives considered.**
  - Rely on the smoke test not containing a save call
  - Copy checkpoints to a scratch location before testing
  - Hash the released file before and after and require equality

**Decision.** Hash each released checkpoint before and after every model's run and require equality. The model exists in memory only; no state is persisted.

**Decision rule.** Where an artefact is a fixed point of the evidence chain, immutability is asserted by measurement on every run that touches it -- never inferred from the absence of a write in the code.

**Rejected, and why.** Relying on the absence of a save call was rejected because it is a property of the current code rather than of the artefact, and it silently stops holding the first time someone adds checkpointing to the harness.

**Correction.** Before/after SHA-256 on every checkpoint, per model, as a PASS condition.

**Validation.** `checkpoint_unchanged: true` for all three models across all runs, with both digests recorded in each artefact.

**Regression control.** The check is a PASS condition of the harness, so any future write fails the run rather than being noticed later.

**Evidence.**
  - gates/compatibility/{gnm,vint,nomad}_backward_optimizer_smoke.json

**Impact on results.** Preserves the validity of R6, R7 and G0.c, all of which cite checkpoint digests.

**Claim boundary.** Concerns the released checkpoint files during train-path smoke testing.

**Not claimed.** Not a claim that the checkpoints match upstream's originally published files; that is R5's separate result.

**Propagation.** Applies to every future harness that loads released weights, including fine-tuning and evaluation.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-002` — Wheel joints imported with zero stiffness and zero damping

**Severity 75 (CRITICAL)** · impact 5 · undetectability 5 · propagation 3 · irreversible: no · status CLOSED

**What was observed.** A pilot produced 40 perfectly-formed frames -- correct dtypes, contiguous images, aligned poses, unwrapped yaw -- of a robot that had moved 0.001 m while its own log reported a commanded 0.45 m/s.

**Root cause.** The URDF importer created the wheel degrees of freedom with no drive gains. The articulation accepted velocity targets and applied no torque.

**Why existing checks missed it.** The output file satisfies every Option 1 format check and loads cleanly in all three models. Format validity and physical validity are independent properties, and only the first was being checked. Nothing in the schema can express 'the robot did not move'.

**Scientific risk had it survived.** A dataset of stationary observations labelled with non-zero actions. Training on it would teach the inverse of the intended mapping while every data-quality check reported healthy.

**Alternatives considered.**
  - Trust the importer's defaults
  - Assert on commanded velocity only
  - Compare commanded velocity against achieved displacement

**Decision.** Set `kps=0, kds=1e4` on the wheel DOFs, and record the commanded-to-achieved ratio in every collection record.

**Decision rule.** A recording pipeline must assert on a physical quantity it did not command. Checking that the command was issued verifies the sender, not the world.

**Rejected, and why.** Asserting only on commanded velocity was rejected because that is the quantity the defect leaves intact -- it is the reason the failure was silent.

**Correction.** Explicit wheel drive gains at articulation setup; ratio recorded per run.

**Validation.** Commanded 0.450 m/s against achieved 0.491 and 0.505 m/s across two pilots (ratios 1.09 and 1.12), over paths of 4.867 m and 4.968 m.

**Regression control.** The ratio is written into every trajectory record, so a future zero-motion run is visible in the artefact rather than requiring someone to watch the viewport.

**Evidence.**
  - gates/kpi/ENGINEERING_RECORD.md §2 row 1
  - pilot records under ~/navfm-data

**Impact on results.** Caught before any admitted data existed. The affected run was discarded; no downstream artefact consumed it.

**Claim boundary.** Establishes that the simulated robot moves under command in Isaac Sim 5.1 with the stated gains.

**Not claimed.** The ratio of ~1.1 is not a calibration result. It is an unexplained 10% overshoot that remains open, and it is not claimed that simulated dynamics match the physical robot.

**Propagation.** Affects every trajectory collected in simulation. The ratio check now runs in the collection script and the Navigation State runtime.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-009` — Installing a dependency would have broken the freeze audit before it ran

**Severity 75 (CRITICAL)** · impact 5 · undetectability 5 · propagation 3 · irreversible: yes · status CLOSED

**What was observed.** NoMaD's vendored diffusion policy requires `einops`, absent from the training environment. The obvious fix is `pip install einops`.

**Root cause.** Environment identity is defined by a digest over the pip freeze output, so any install changes the identity of the environment under audit.

**Why existing checks missed it.** Nothing would have failed. The install succeeds, NoMaD builds, the audit runs -- and reports on an environment that no longer matches the one whose identity was recorded. The check would have passed while measuring the wrong thing.

**Scientific risk had it survived.** The G0.c freeze audit would certify an environment digest that no artefact was actually produced under, silently invalidating the reproducibility chain it exists to establish.

**Alternatives considered.**
  - pip install einops into the training environment
  - Stage the dependency outside the environment and pass it on the path

**Decision.** Stage to `/tmp/navfm-r6-deps` with `pip install --target` and pass `--extra-syspath`. The environment is never modified.

**Decision rule.** Never mutate an environment whose identity is part of the evidence. Dependencies needed for verification are staged outside it and named explicitly at the call.

**Rejected, and why.** Installing was rejected because the cost is invisible: it does not fail, it quietly changes what the audit is about.

**Correction.** `--extra-syspath` on the verification harnesses; nothing installed.

**Validation.** Environment identity `4408691cfeb89860...` unchanged across the entire session, verified before and after the NoMaD work.

**Regression control.** The harnesses refuse to auto-discover interpreters or install anything, and name the missing requirement instead (the F-M1-1 rule).

**Evidence.**
  - scripts/verify_r6_strict_load.py
  - scripts/verify_train_path_compatibility.py

**Impact on results.** Preserved the validity of G0.c, R6 and R7, all of which cite the environment digest.

**Claim boundary.** Concerns environment identity for the reproduction ladder evidence.

**Not claimed.** Not a claim that the staged `einops` version matches what upstream used; it is recorded, not verified against their environment.

**Propagation.** Applies to every verification harness that needs a dependency the environment lacks.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-012` — An invented loss passed the first train-path harness

**Severity 75 (CRITICAL)** · impact 5 · undetectability 5 · propagation 3 · irreversible: no · status CLOSED

**What was observed.** The first version of the train-path harness reported PASS for all three models. Its NoMaD objective was hand-written: `noisy = actions + noise * 0.1` with a plain MSE, no delta computation, no normalisation, no DDPM scheduler, no goal mask, no masked reduction. GNM and ViNT used a plain MSE in place of upstream's masked `action_reduce`.

**Root cause.** The harness was written to demonstrate that a gradient could flow, and a loss that produces a gradient is trivial to write. Reaching for the pinned implementation is a strictly harder path with an identical-looking result.

**Why existing checks missed it.** Every check passed, and passed honestly: the losses were finite, the gradients were non-zero, the parameters moved. Nothing in a train-path proof can distinguish the real objective from a plausible one, because both make `backward()` work. Only reading the pinned source distinguishes them.

**Scientific risk had it survived.** A claim that our data survives the official training path, evidenced by a path that was not the official one. It would have been wrong in the specific way that is hardest to detect later: the artefact is well-formed, the numbers are finite, and the label on the box is the only thing that is false.

**Alternatives considered.**
  - Keep the simplified loss and note it as an approximation
  - Import or transcribe the pinned implementation for every model

**Decision.** GNM and ViNT now call upstream `_compute_losses` directly. NoMaD's training loss has no callable -- it is inline in `train_nomad` -- so it is transcribed line-for-line with its source range recorded, including `get_delta`, `normalize_data` against `ACTION_STATS`, the real DDPM scheduler configured as in `train.py` L214-219, goal masking, and both masked reductions.

**Decision rule.** A compatibility proof must exercise the implementation it claims compatibility with. Where upstream exposes a callable, call it. Where it does not, transcribe it and record the source range so the transcription can be audited.

**Rejected, and why.** Noting the simplification as an approximation was rejected: the claim being made is specifically about the official path, so an approximation of it is not a weaker version of the claim but a different claim wearing its name.

**Correction.** Harness rewritten against pinned source; `_compute_losses_nomad` explicitly identified as the eval/logging path (it runs full diffusion sampling) and therefore NOT the training objective.

**Validation.** All three PASS on the official losses. GNM total 0.104939, ViNT 0.084481, NoMaD 0.036361, with NoMaD's stochastic state frozen and recorded (timesteps, noise digest, goal mask).

**Regression control.** `gates/forensics/training_path_crosswalk.json` pins file, function and line range for every element of each model's training path, so a future drift from upstream is a diff rather than a discovery.

**Evidence.**
  - gates/forensics/training_path_crosswalk.json
  - gates/compatibility/{gnm,vint,nomad}_loss_smoke.json
  - third_party/visualnav-transformer/.../training/train_utils.py L36-96, L613-657

**Impact on results.** No published result affected -- the flawed harness existed for one iteration and was replaced before commit. Caught by review, not by any check in this repository, which is itself the finding.

**Claim boundary.** The losses now executed are upstream's, at dca7981, for a single batch on CPU.

**Not claimed.** Not a claim that upstream's objective is scientifically correct. Conformance to a reference is not correctness of the reference.

**Propagation.** Applies to every harness that claims to exercise an official path: evaluation, fine-tuning, and any future baseline reproduction.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-007` — Corrections that did not propagate — the dominant protocol defect

**Severity 64 (CRITICAL)** · impact 4 · undetectability 4 · propagation 4 · irreversible: no · status CLOSED

**What was observed.** Adjudication rounds 3 through 6 of Amendment 5 were each decided by the same class of defect: prose corrected in one place while a summary, preamble or adjacent sentence retained the superseded claim. Round 7's single defect was the same provenance claim ten lines above the sentence fixed in round 6.

**Root cause.** A document with a narrative section and a summary section has two statements of every fact, and editing is naturally local.

**Why existing checks missed it.** Each individual correction was correct. No check compares a document against itself, and a reviewer reading for correctness reads the corrected passage.

**Scientific risk had it survived.** A pre-registration that authorises what its preamble forbids is unexecutable, and the reader follows whichever half they read. In round 4 the preamble forbade training while three steps authorised it.

**Alternatives considered.**
  - Fix defects as found
  - Re-adjudicate the whole document after every correction

**Decision.** Re-adjudicate the entire amendment after every correction round, until a round returns zero defects.

**Decision rule.** A correction is not complete until the document is re-read whole. Local edits to a document with redundant statements of fact are presumed incomplete.

**Rejected, and why.** Fixing defects as found was rejected empirically: it produced rounds 5, 6 and 7, each surfacing a stale copy of a fact already corrected.

**Correction.** Eight rounds; the eighth a four-lens panel with two skeptics per claim.

**Validation.** Round 8 returned zero surviving defects. Iteration signature 4-6-3-3-2-3-1-0.

**Regression control.** Amendments are appended, never edited, and the frozen section is verified byte-identical with `cmp` after every write.

**Evidence.**
  - gates/redteam/trigger3-amendment5-2026-08-13.md
  - PREREGISTRATION.md — Amendment 5

**Impact on results.** 22 defects caught before the amendment was committed. The finding is the pattern, not the individual defects.

**Claim boundary.** Concerns the adjudication of Amendment 5 and the protocol documents.

**Not claimed.** Not a claim that the resulting protocol is scientifically correct -- only that it is internally consistent and executable.

**Propagation.** Applies to every future amendment, and to the paper, where the same narrative-plus-summary structure recurs.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-015` — The poor navigation images were the world, not the camera

**Severity 64 (CRITICAL)** · impact 4 · undetectability 4 · propagation 4 · irreversible: no · status CLOSED

**What was observed.** Robot POV frames from pilot_0001 and pilot_0002 are dominated by black empty space above and floor below, with a few untextured primitives. The natural reading is that the camera is aimed wrongly and needs pitching down.

**Root cause.** The camera is correct. Its USD rotation (90, 0, -90) maps the camera's -Z view direction onto the robot's +X with +Z up, giving optical axis [1, 0, 0], pitch 0.0 deg, and intrinsics of 60.4 x 47.2 degrees -- comparable to a RealSense D435. The world is the defect: a 40 m ground plane and one distant light in an unbounded void, with no walls, no ceiling and no sky dome. With the camera level at 0.280 m the horizon falls on the image centre, so the upper half of every frame is rays terminating in nothing (black) and the lower half is floor.

**Why existing checks missed it.** The camera acceptance test asked whether the camera was mounted at the right height on the right link and pointing forward. All three were true. No check asked what the camera could see, because scene content was not modelled as part of the camera contract at all.

**Scientific risk had it survived.** Pitching the camera down to 'fix' the black region would have traded void for more floor, degrading the viewpoint while appearing to address the complaint -- and would have silently changed the mount geometry that the +8.8 to +37.9 degree yaw experiment established as behaviourally significant.

**Alternatives considered.**
  - Pitch the camera down to reduce the black region
  - Lower the camera back toward chassis height
  - Diagnose the optical axis analytically, then test the world

**Decision.** Keep the top-arm mount and the optical axis unchanged. Classify the sparse world as ENGINEERING_CONTROL_WORLD and source a real Isaac USD environment for navigation pilots.

**Decision rule.** Before altering a component to fix an observation, establish that the component is the cause. Here the optical axis was computable in closed form and turned out to be exactly correct.

**Rejected, and why.** Pitching down was rejected on measurement: at 0.280 m with a 47.2 degree vertical field, downward pitch increases floor fraction, which is already 41% in the control world.

**Correction.** No camera change. Two-tier scene policy introduced, with the control world retained for physics and regression and explicitly barred from navigation claims.

**Validation.** Same robot, same camera, same intrinsics, rendered in both worlds: background fraction 33% in the control world against 0% in a bounded interior, and median forward depth 1.65 m against 8.99 m. The camera never changed.

**Regression control.** `scripts/camera_view_acceptance.py` measures composition from the depth buffer on every scene, so a viewpoint regression is a number rather than an opinion.

**Evidence.**
  - gates/scenes/camera_view_control_blocks_v1.json
  - gates/scenes/views/control_blocks_v1/pov_00.png
  - gates/scenes/SCENE_MANIFEST.json

**Impact on results.** Prevented a change to the camera mount that would have degraded the viewpoint and invalidated comparison with the existing pilots.

**Claim boundary.** The optical axis is forward and level, established analytically from the USD transform and confirmed by rendered composition in two worlds.

**Not claimed.** Not a claim that 0.280 m, the mast geometry or the 18 mm focal length match the physical Yahboom. All remain PROVISIONAL_SIMULATION_VALUE.

**Propagation.** Scene identity now belongs in the same versioned contract as the camera: both are part of the data-generating process, and a change to either changes the observation distribution.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-021` — Tightening a threshold fixed a false positive and created a false negative

**Severity 64 (CRITICAL)** · impact 4 · undetectability 4 · propagation 4 · irreversible: no · status CLOSED

**What was observed.** After `background_fraction_max` was tightened from 0.35 to 0.10 to stop the control world passing, the Office scene failed on 33.9% background -- while rendering a legible interior with carpet, a structural pillar and a window wall, under 185 correctly resolved materials and zero runtime errors.

**Root cause.** The observable was semantically wrong, not badly calibrated. It asked 'how many pixels have no depth return inside the canonical 100 m clip?' while the scientific question was 'how much of the forward view is genuinely an unbounded, non-environment void?'. Those are different estimands. A window onto a city skyline beyond the far clip scored identically to the control world's black nothing.

**Why existing checks missed it.** The metric was doing exactly what it was written to do, and its first recalibration was driven by a scene where the two estimands happened to coincide -- in an unbounded void, missing depth really is void. The divergence only appears in a bounded scene with a window, which is the case the metric was never tested against.

**Scientific risk had it survived.** Rejecting every architecturally realistic environment -- offices, warehouses and hospitals all have windows and openings -- and thereby selecting a canonical world biased toward sealed, windowless geometry for a reason having nothing to do with navigation.

**Alternatives considered.**
  - Loosen the threshold until Office passes
  - Exclude the upper image region from the background measurement
  - Split the observable into four classes and reject on true void alone

**Decision.** Classify every pixel as NEAR_SCENE, DISTANT_SCENE, VALID_ENVIRONMENT_BACKGROUND or TRUE_VOID, and move the rejection criterion onto true void. DISTANT_SCENE is established by an independent probe -- a second camera parented to the same link with identical intrinsics, differing only in far clip, which is set from the measured stage diagonal rather than chosen. The threshold stays at 0.10.

**Decision rule.** A threshold cannot repair a semantically wrong observable. Missing depth within a sensor's range is not equivalent to absence of scene geometry, and negative evidence requires proof that the observable was capable of seeing the thing claimed absent.

**Rejected, and why.** Loosening the threshold until Office passed was rejected outright: it tunes the gate to the candidate in front of it, and would have left the metric unable to distinguish a void from a window in every future scene. Masking the upper image region was rejected for the same reason -- it hides the disagreement rather than resolving it.

**Correction.** `scripts/scene_visibility_classification.py`, emitting MeasurementEnvelope.

**Validation.** Control world, the discriminating case: true void 0.3894, distant scene 0.0, still FAIL -- the classifier does not rescue a genuine void, because DISTANT can only be earned by a positive observation. Office pose A decomposes its 33.9% background into 8.7% distant scene and 25.3% environment dome with 0.000 true void; pose B facing inward is 100% near scene. The class mask shows blue aligning with the skyline buildings and yellow with the sky above them.

**Regression control.** The control-world frame is retained as a negative fixture that must keep failing on true void while Office must not, so a future change collapsing the classes breaks one of the two.

**Evidence.**
  - gates/scenes/scene_visibility_control_blocks_v1.json
  - gates/scenes/scene_visibility_office.json
  - gates/scenes/visibility/office/A_window_classes.png

**Impact on results.** No scene was selected under the wrong metric, and no data collected. Office's original rejection is now demonstrated to have been a false negative rather than assumed to be one.

**Claim boundary.** Establishes that Office's apparent background is distant geometry and sky rather than void, at two audited poses under Isaac Sim 5.1.0.0.

**Not claimed.** Not a claim that Office is eligible. Only two poses were measured, no corridor or goal-style viewpoint, and the material, hue, structure and depth checks have not yet been run through this gate. The environment-background rule is also currently coarse: every unexplained pixel is forgiven whenever the stage has any dome light, so a scene with a dome could in principle launder a real void. That is a known weakness, not a validated criterion.

**Propagation.** Applies to every scene that will ever be audited, and to any future metric where sensor range limits are mistaken for absence -- including collision clearance and goal visibility.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-003` — About 19% of the released ViNT checkpoint is never executed

**Severity 60 (CRITICAL)** · impact 3 · undetectability 5 · propagation 4 · irreversible: no · status CLOSED

**What was observed.** In the train-path proof, 16 parameters of ViNT and the same 16 of NoMaD received no gradient and were unmoved by an optimizer step: 5,714,384 elements (19.21%, 22.9 MB fp32) for ViNT and 3,351,760 (17.59%, 13.4 MB) for NoMaD.

**Root cause.** Two independent upstream constructions. (a) `vint.py:41,46` read `obs_encoder._fc.in_features` and `goal_encoder._fc.in_features` as a shape lookup while the forward pass calls `extract_features`, so both EfficientNet classifier heads are carried and never called. (b) `self_attention.py:31-32` passes `self.sa_layer` to `nn.TransformerEncoder`, which deep-copies it -- verified directly, `enc.layers[0] is l` is False with no shared storage -- leaving the prototype layer registered, serialised, and unexecuted.

**Why existing checks missed it.** Every existing check is satisfied by this state. Strict load compares key sets and the keys match on both sides. Inference compares outputs and the outputs are correct, because the dead tensors are not in the graph. A loss curve descends normally. Only a check that asks which specific tensors an optimizer step moved can see it, and that check existed only because the train-path proof needed to distinguish 'the backward pass ran' from 'the backward pass did something'.

**Scientific risk had it survived.** Published parameter counts read off the checkpoint overstate the trainable model by ~19%, fine-tuning budgets over-provision by the same fraction, and AdamW allocates optimizer moments for 5.7M tensors that never receive a gradient.

**Alternatives considered.**
  - Report the aggregate 'parameters changed' count only
  - Treat 488/504 as within tolerance and move on
  - Name every unmoved tensor and trace each to upstream source

**Decision.** Record the exact tensor names, element counts and checkpoint fraction in the machine-readable result, and trace both causes to specific upstream lines.

**Decision rule.** 'Most parameters moved' is how a genuinely disconnected branch survives review. A proof that a training path is connected must be per-tensor or it is not a proof.

**Rejected, and why.** Accepting 488/504 as good enough was rejected: the 16 are not a rounding error, they are a structural property of the released artefact, and the same reasoning would have hidden a real disconnection of identical size.

**Correction.** None applied to upstream. This is a finding about the distributed files, not a defect in our code; `parameters_unchanged` now carries names, counts and share.

**Validation.** `gates/forensics/train_path_compatibility.json`; the deep-copy mechanism confirmed by direct object-identity and storage-pointer comparison rather than inferred from the documentation.

**Regression control.** The train-path harness fails if zero parameters move, and records the unmoved set every run, so a change in the dead set is visible as a diff.

**Evidence.**
  - gates/forensics/train_path_compatibility.json
  - gates/forensics/SAMPLE_COUNT_AND_DEAD_WEIGHT.md
  - third_party/visualnav-transformer/.../vint/self_attention.py:31-32
  - third_party/visualnav-transformer/.../vint/vint.py:41,46,82,85,105

**Impact on results.** No result is invalidated. Strict load still passes 3/3 and inference is unaffected. It changes arithmetic that gets published: ViNT's 29.7M parameters are 24.0M executed.

**Claim boundary.** A property of the released `vint.pth` and `nomad.pth` under the pinned reference architecture at commit dca7981, on a strict=True load.

**Not claimed.** Not a claim that the models were trained incorrectly. The prototype layer never participated in training either, so the released weights are exactly what the published procedure produced. It is a claim about what the files contain.

**Propagation.** Affects any parameter count, memory estimate or optimizer configuration derived from these checkpoints, including our own fine-tuning plans and any figure quoting model size.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-017` — The camera-view acceptance test passed both known-bad frames

**Severity 60 (CRITICAL)** · impact 4 · undetectability 5 · propagation 3 · irreversible: no · status CLOSED

**What was observed.** The first version of the camera-view acceptance test returned PASS for the control world's black void and PASS for the uniformly red hospital render. Both frames are rejected by a human on sight.

**Root cause.** Two errors. The background threshold was set at 0.35 by estimation before any measurement, and the control world reads 0.33 -- inside the limit by luck. And the metric set was entirely geometric, so a scene whose materials had all fallen back scored perfectly: background 0%, structure 53%, forward depth 8.99 m.

**Why existing checks missed it.** This was the check. Nothing sits above it. It was written to measure composition rather than to be shown failing, so it was never run against a frame that should fail -- the exact omission the standing instructions name as a recurring genus.

**Scientific risk had it survived.** A gate that certifies any viewpoint is worse than no gate, because it converts an open question into a recorded PASS.

**Alternatives considered.**
  - Keep the geometric metrics and rely on human review for appearance
  - Tighten the threshold and add appearance metrics, then prove both directions

**Decision.** Tighten `background_fraction_max` from 0.35 to 0.10 against measured data, add dominant-hue and colour-diversity metrics, and re-run against both known-bad frames to confirm each is rejected for its own reason.

**Decision rule.** A verification must be shown to fail when its subject is defective, using a real defective input, before its passes are trusted.

**Rejected, and why.** Relying on human review for appearance was rejected: it is exactly the supplementary evidence the gate is supposed to make unnecessary at scale.

**Correction.** Thresholds recalibrated against measurement and recorded as recalibrated; two appearance metrics added.

**Validation.** Control world now FAILS on background 33% > 10%. Hospital now FAILS on 96% of saturated pixels in one hue. Each fails for its actual defect, not incidentally.

**Regression control.** Both known-bad frames are retained under `gates/scenes/views/` as the fixtures the check must keep rejecting.

**Evidence.**
  - gates/scenes/views/control_blocks_v1/pov_00.png
  - gates/scenes/views/hospital_v1/pov_00.png
  - scripts/camera_view_acceptance.py — THRESHOLDS

**Impact on results.** No collected data affected -- the check had certified nothing before it was corrected. Second instance this session of a green check that was wrong, after FL-012.

**Claim boundary.** The corrected check discriminates between these two defect classes on these fixtures.

**Not claimed.** Not a claim that it detects every bad viewpoint. It is a floor, and the thresholds are engineering values recalibrated after seeing data, not pre-registered criteria.

**Propagation.** Applies to every acceptance gate written in this project: each needs a known-bad fixture it demonstrably rejects.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-004` — Camera parented to a prim named top_arm_mount but sitting at chassis height

**Severity 48 (HIGH)** · impact 4 · undetectability 4 · propagation 3 · irreversible: no · status CLOSED

**What was observed.** After adding the top-arm mast to the URDF, acceptance reported a camera mounted on `top_arm_mount` while the camera was in fact at 0.120 m, chassis height.

**Root cause.** The URDF importer flattens the link hierarchy, making nominal children into siblings. The prim carrying the expected name was not at the expected place.

**Why existing checks missed it.** The check asked whether the camera's parent was *named* `top_arm_mount`. Name is not geometry. The assertion was true and the configuration was wrong.

**Scientific risk had it survived.** Every trajectory would come from the wrong visual domain while the record asserted the corrected viewpoint -- a domain error certified as fixed.

**Alternatives considered.**
  - Trust the parent prim's name
  - Assert on the measured world-space height

**Decision.** Resolve the mount by traversing for the link, and derive `mounted_on_top_arm` from measured height (> 0.15 m) rather than from the parent's name.

**Decision rule.** Assert on the physical quantity that matters, never on a label that is expected to correlate with it. Names are metadata; geometry is the claim.

**Rejected, and why.** Name-based resolution was rejected outright -- it had already produced a false PASS twice.

**Correction.** Traversal-based resolution plus a measured-height assertion in acceptance.

**Validation.** Camera measured at 0.2800 m from ground, 0.2400 m above `base_link`. Acceptance correctly FAILED twice before the fix, which is the evidence that the check discriminates.

**Regression control.** The height assertion fails on any future build that re-flattens the hierarchy.

**Evidence.**
  - scripts/build_yahboom_twin.py
  - assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf

**Impact on results.** Empirically material: with start, goal, seed, policy and physics held fixed and the camera the only change, pilot_0002 yaw went from +8.8 deg to +37.9 deg.

**Claim boundary.** The simulated camera is at 0.2800 m in the current twin, measured from the transform, not read from a name.

**Not claimed.** Not verified against the physical Yahboom's actual mast height. The URDF mast is a represented structure, not a measured one.

**Propagation.** Invalidated the earlier pilots as evidence of the corrected viewpoint. Those are retained as a separate camera-domain experiment rather than deleted, since they are evidence of the domain effect.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-020` — A URL validated as a filesystem path, refused before anything ran

**Severity 48 (HIGH)** · impact 4 · undetectability 4 · propagation 3 · irreversible: no · status CLOSED

**What was observed.** `camera_view_acceptance.py` preflighted its scene argument with `Path(args.scene).is_file()`. Given an Omniverse asset URL that is always false, so the script printed REFUSED and exited -- and the surrounding measurement reported zero MDL errors for a scene that had never been opened.

**Root cause.** Local filesystem paths and remote asset URIs were treated as one namespace. They are different addressing schemes with different resolvers, and only one of them answers `is_file()`.

**Why existing checks missed it.** The preflight behaved exactly as designed and its refusal was printed. The defect was that the refusal was invisible to the measurement wrapped around it, which counted error lines in output that was never produced.

**Scientific risk had it survived.** Any scene addressed by URI would be silently excluded from evaluation while the run reported a clean result -- and the native asset root is the correct way to reference these scenes, so the defect specifically blocked the working path.

**Alternatives considered.**
  - Require all scenes to be local files
  - Validate by addressing scheme, deferring URI existence to the runtime resolver

**Decision.** Detect the scheme and validate with the resolver appropriate to it: filesystem for local paths, the Omniverse runtime for URIs. URI existence is never tested with `Path.is_file()`.

**Decision rule.** An identifier is validated by the resolver that owns its namespace. A check that cannot succeed for a valid input is not a strict check, it is a broken one.

**Rejected, and why.** Requiring local files was rejected: it is what forced the hand-built mirror, which produced FL-016 and FL-018 and never resolved MDL correctly.

**Correction.** Scheme detection in the preflight, with the incident recorded at the call site.

**Validation.** With the fix, the Office scene loads from the asset root: 4713 prims, 140 meshes, 121 lights, 185 materials, zero MDL errors and zero error lines -- against 138 MDL errors from the local mirror.

**Regression control.** The gate now reports whether an artefact was written alongside its error count, so a refused run cannot present as a clean one.

**Evidence.**
  - scripts/camera_view_acceptance.py
  - gates/scenes/camera_view_office_remote.json

**Impact on results.** Established that the native resolver handles the full USD, MDL and texture graph correctly, and that the hand-built mirror was the defect rather than the assets.

**Claim boundary.** Concerns scene addressing in the acceptance gate under Isaac Sim 5.1.0.0.

**Not claimed.** Not a claim that the Office scene is eligible. That run FAILED its own gate on background fraction, and the metric cannot yet distinguish an unbounded void from a legitimate view through a window.

**Propagation.** Applies to every script taking a scene or asset argument, and retires the local mirror as the acquisition path.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-008` — G2 mis-scoped in both directions

**Severity 36 (HIGH)** · impact 4 · undetectability 3 · propagation 3 · irreversible: no · status CLOSED

**What was observed.** The G2 gate condition requires four design decisions together with the estimator's type-I error rate on simulated null data and its tolerance. `gates/g2_decisions.json` holds four entries.

**Root cause.** The tracking file was built from an enumeration of the design decisions and silently dropped the conjunctive fifth requirement.

**Why existing checks missed it.** Four of four entries present reads as complete. Nothing compares the tracking file against the gate condition that defines it.

**Scientific risk had it survived.** Closing G2 with four of five requirements met, and a type-I error rate that was never measured, on an estimator whose false-positive behaviour is the thing the gate exists to bound.

**Alternatives considered.**
  - Close G2 on the four recorded decisions
  - Record the fifth requirement as an explicit open item

**Decision.** Filed as a failure record and surfaced as an open item requiring Frank's and Rui's decision. G2 remains open.

**Decision rule.** A gate closes on its stated condition, not on its tracking artefact. Where the two disagree, the condition wins and the artefact is the defect.

**Rejected, and why.** Closing on four was rejected: it would step over the fifth silently, which is the specific failure the record now exists to prevent.

**Correction.** `gates/failures/F-G2-1.md`; the fifth requirement named in the open items.

**Validation.** The gate condition text and the tracking file compared directly.

**Regression control.** G2 cannot be marked closed while the null-simulation harness is absent.

**Evidence.**
  - gates/failures/F-G2-1.md
  - gates/g2_decisions.json

**Impact on results.** No result affected; G2 has not closed and no experiment depends on it yet.

**Claim boundary.** Concerns the G2 gate's scope and its tracking artefact.

**Not claimed.** Not a claim about the estimator's actual type-I behaviour, which is unmeasured.

**Propagation.** Blocks the E2 decision pack until the null-simulation harness exists and its tolerance is declared in advance.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-005` — Stale pilots reported as fresh output

**Severity 24 (MODERATE)** · impact 3 · undetectability 4 · propagation 2 · irreversible: no · status CLOSED

**What was observed.** Two pilot directories were treated as products of the corrected camera build. Their `camera_prim` field read `base_link` and their mtimes were 30 minutes old.

**Root cause.** A collection run failed to overwrite, and the reading order started from the numeric results rather than from the contract fields.

**Why existing checks missed it.** The numbers agreed to three decimal places with the previous run -- because they were the same files. Agreement was read as reproducibility.

**Scientific risk had it survived.** Chassis-camera data presented as top-arm data, with an apparent replication to support it.

**Alternatives considered.**
  - Compare summary metrics between runs
  - Verify the camera contract field before reading any result

**Decision.** Verify the contract field first, before any other field, on every artefact.

**Decision rule.** When a run is supposed to change a condition, check the condition before checking the outcome. Identical outcomes are evidence of identical inputs at least as often as they are evidence of reproducibility.

**Rejected, and why.** Metric comparison across runs was rejected as the primary check: it is satisfied most strongly by exactly the failure it needs to catch.

**Correction.** Stale pilots deleted; collection re-launched; contract read first.

**Validation.** Fresh pilots carry the corrected `camera_prim` and the measured height.

**Regression control.** Collection records now embed the camera contract, so a stale artefact is self-identifying.

**Evidence.**
  - gates/kpi/ENGINEERING_RECORD.md §2 row 6

**Impact on results.** No admitted data affected; the error was in reading, and lasted minutes.

**Claim boundary.** Applies to the audit procedure for collection artefacts.

**Not claimed.** Not a defect in the collection code itself.

**Propagation.** Applies to every future re-collection where a condition is meant to change.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-011` — NoMaD produces 29 samples where GNM and ViNT produce 30

**Severity 24 (MODERATE)** · impact 2 · undetectability 4 · propagation 3 · irreversible: no · status CLOSED

**What was observed.** On the same 40-frame Yahboom pilot, the three official dataset classes yielded GNM 30, ViNT 30, NoMaD 29 samples. The number was recorded before it was understood.

**Root cause.** Model-specific sampling semantics, traced to `vint_dataset.py::_build_index` L219-221: `begin_time = context_size * waypoint_spacing`, `end_time = traj_len - end_slack - len_traj_pred * waypoint_spacing`, and every value in `range(begin_time, end_time)` is appended. There is no rejection branch in the source. GNM and ViNT use context 5 / horizon 5 giving range [5,35) = 30; NoMaD uses context 3 / horizon 8 giving range [3,32) = 29. The accepted index set was verified to equal the rule's range exactly for all three models.

**Why existing checks missed it.** Nothing was wrong, so nothing fired. Loader acceptance asks whether a dataset opens; it has no opinion about how many samples it should contain. The risk was not a failed check but an unexplained number sitting in a results table, where it would eventually be read as either a defect or a licence to force symmetry.

**Scientific risk had it survived.** Two opposite errors. Treating 29 as a defect and patching upstream to force 30 would fabricate a sample NoMaD's contract does not admit. Treating it as noise would leave a population difference undocumented in any comparison across the three models.

**Alternatives considered.**
  - Assert that 29 is expected from the arithmetic
  - Patch upstream so all three yield 30
  - Trace every candidate index through the pinned source and prove the rule

**Decision.** Preserve 29. Emit a per-candidate index trace (`gates/forensics/nomad_sample_index_trace.csv`) and per-model population files asserting candidate = accepted + rejected, with the accepted set compared against the rule's range.

**Decision rule.** Scientific comparability means the same evidence standard, not identical internal implementation. A model-semantic difference is preserved and documented; it is never normalised away to make a table symmetrical.

**Rejected, and why.** Forcing 30 was rejected because it would invent a sample outside NoMaD's admissible range and make the comparison less valid, not more. Asserting '29 is expected' from arithmetic alone was also rejected -- the arithmetic had to be shown to be the arithmetic the source actually performs.

**Correction.** None needed. Classified DESIGN / MODEL-SEMANTIC, not defect and not off-by-one.

**Validation.** Exact answer: NoMaD *gains* candidate indices [3, 4] at the front, because it needs only 3 context frames against 5, and *loses* [32, 33, 34] at the back, because it predicts 8 steps ahead against 5. Net -1. No sample is silently lost; conservation holds for all three (40 = 30 + 10, 40 = 30 + 10, 40 = 29 + 11).

**Regression control.** The harness computes the predicted count from each config and asserts it against `len(dataset)` and against the accepted index set. A horizon change moves the count and the assertion reports it.

**Evidence.**
  - gates/forensics/nomad_sample_index_trace.csv
  - gates/compatibility/{gnm,vint,nomad}_sample_population.json
  - third_party/visualnav-transformer/.../data/vint_dataset.py L219-221

**Impact on results.** No result changes. The population difference is now a documented property of NoMaD's contract rather than an unexplained number, and any future three-model table must state it.

**Claim boundary.** Holds for the pinned upstream at dca7981 with waypoint_spacing 1 and end_slack 0. The rule is general; the specific counts are for a 40-frame trajectory.

**Not claimed.** Not a claim that 29 and 30 samples give equivalent statistical power, nor that the three models can be compared on equal footing without accounting for the population difference.

**Propagation.** Applies to every dataset built for these three models and to any table reporting sample counts across them.

**Attribution.** Frank Asante Van Laarhoven

---

## `FL-010` — A pre-execution gate audit run after execution, reported as failure

**Severity 12 (MODERATE)** · impact 2 · undetectability 3 · propagation 2 · irreversible: no · status CLOSED

**What was observed.** A freeze audit run post-hoc reported '2 of 16 FAILED', which was recorded and then found to be a category error: the audit checks conditions that hold before execution, and it was run afterwards.

**Root cause.** The audit's temporal precondition was not encoded in the audit.

**Why existing checks missed it.** The audit produced a well-formed result with a plausible failure count. Nothing in the output indicates when it was valid to run.

**Scientific risk had it survived.** Either a false alarm that discards valid evidence, or -- the worse direction -- a post-hoc pass read as a pre-execution guarantee.

**Alternatives considered.**
  - Delete the erroneous result
  - Annotate it in place with the category error

**Decision.** Annotate in place. The wrong result and its correction both stay in the record.

**Decision rule.** Erroneous results produced by this work are annotated, never deleted. A record that shows only correct conclusions cannot be audited for how it reached them.

**Rejected, and why.** Deletion was rejected: it would leave a clean record that misrepresents the process, and remove the evidence that the audit needs a temporal precondition.

**Correction.** Annotation recording the category error alongside the original output.

**Validation.** The freeze audit's valid scope stated explicitly in the archived record.

**Regression control.** The precondition is now stated in the audit's own output.

**Evidence.**
  - gates/G0/ freeze audit archive

**Impact on results.** No result affected. The finding is about how audits are scoped and retained.

**Claim boundary.** Concerns the freeze audit's temporal scope.

**Not claimed.** Not a claim that the two flagged items were correct -- they were out of scope.

**Propagation.** Applies to every gate script with a temporal precondition.

**Attribution.** Frank Asante Van Laarhoven

---

# Scope decisions

Distinct from the findings above, and deliberately kept separate: a finding
records something that went wrong, a scope decision records a boundary chosen
on purpose. Conflating them would make "we decided not to" indistinguishable
from "we failed to", which is the ambiguity these records exist to remove.

| ID | Decision | Date | Digest effect |
|---|---|---|---|
| `SD-001` | [`candidate_policy.py` owns target-directed interventions only; volumetric overlap and footprint sweep stay under the footprint/oracle contract](../scenes/candidate_policy_scope_decision.md) | 2026-09-03 | none — no implementation or serialization changed |

## `SD-001` — Target-directed interventions and volumetric operations are different measurements

**Observed.** Sprint 2A found five consumers running five different physical
interventions under one contract label. Sprint 2B extended the shared policy to
express them, and the compatibility matrix then reported the footprint oracle as
only PARTIAL, because its `overlap_box` and `sweep_box_closest` calls could not
be represented as ray candidates.

**Why the checks that were already running did not see it.** They could not: this
is not a defect any check can detect. The matrix asked "is every operation
representable?", which silently assumed every collision operation belonged in one
policy. The question itself was wrong, and a passing or failing test would have
been equally uninformative about that.

**Decision.** The gap is not a missing implementation. A target-directed probe
asks whether a declared object caused an observation; a footprint sweep asks
whether a robot volume can occupy a space. Different estimands, different
contracts. No `VolumetricPolicy` is added.

**Evidence.** `scripts/validate_physx_footprint_oracle.py` declares no target in
any of its three operations, and `check()` adjudicates occupancy and traversability
rather than collider identity. The word `target` does not occur in the harness.

**Impact on results.** None. No consumer routes through the shared policy yet, and
the policy digest is unchanged at `2cec5cf6bc23edb8`.

**Claim boundary.** Concerns ownership of measurement semantics only. Establishes
nothing about any scene.

**Attribution.** Frank Asante Van Laarhoven
