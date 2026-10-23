# NavFM existing specification: collector blocker reconciliation

21 October 2026. RESEARCH; records-only follow-up. **Runtime preparation is stopped.**
This replaces the active pipeline-readiness proposal, not the historical results.
The former 10-hour/2-GB and conditional round-trip caps are withdrawn planning
examples; no new budget, proposal, qualification or execution is requested.

## Exact failure sequence and recorded cause

The earlier readiness synthesis stopped at an obsolete failure. The existing
successor records must be included:

| Record | Exact outcome | What it establishes |
|---|---|---|
| [Replay validation v1](REPLAY_RECOVERY_VALIDATION_V1_RESULT.md) | First reference fails `Acquisition not from boundary rerender`; replay not run | The guard included an own-product acquisition with null active-call index. Saved RGB matched the final boundary acquisition; stale pixels were not established. |
| [Observer-window v2](OBSERVER_WINDOW_V2_RESULT.md) | Both individual traces PASS; pair `INITIALIZATION_HANDOVER_FAIL` | Observer repair already works on this pair. All 38 physical/history comparisons and seven discrete outputs match, but all seven numerical invocation comparisons and full boundary state fail. |
| [Offline numerical diagnostic](OFFLINE_NUMERICAL_V1_RESULT.md) | Identical-input/state repeats bitwise stable; differing saved observation inputs reproduce original mismatch | Observation differences suffice to reproduce these prediction differences. Original image-generation cause remains UNKNOWN; neither CUDA nor rendering is established as the root cause. |

V1's smallest supported observer repair already exists in
`scripts/replay_recovery_contracts_v2.py`: classify callback membership by
render call/product and native completion order; select the final completed
own-product boundary acquisition before comparing the image digest. Outside-call
and unrelated-product events receive no freshness credit. This is not permission
to weaken v1 or retrospectively admit its failure. V2's two passing acquisition
traces are the recorded repair evidence; they do not establish general qualification.

The remaining learned-handover failure uses the unchanged absolute 0.001 /
relative 0.00001 criterion. Maximum window/predicted-distance difference was
0.068376541; requested yaw commands differed at steps 0 and 6 by 0.005473993 and
0.002337801 rad/s. Matching discrete states does not override this failure.
Image MAD below 2.5 did not imply numerical equivalence. The offline diagnostic
reconstructed all seven predictions per arm exactly; only stored distance history
differed in declared policy state. It did not observe additional output amplification
from that history in the tested sequence.

## Saved-input first-divergence audit (21 October follow-up)

Read-only comparison uses the two original v2 `trace.json` files and their saved
PNG files, plus existing offline worker `result.json` and hash-verified
`tensor-difference-summary.json`. No preprocessing, model or simulator is rerun.
All 14 unique model-history PNG file hashes match their trace records.

**Earliest model-input divergence is already in the initial captured image.**
At physical step 0 both ordered six-slot histories are
`[initial.png, initial.png, initial.png, initial.png, initial.png, initial.png]`.
Every slot records sensor and simulation time 1.7250000899657607 s and physical
step 0. Both images are 320×240 RGB, but file bytes and decoded RGB pixels differ
(maximum channel difference 6/255). File SHA-256:

- Reference: `31455adb1d3e4b182c811ed7a87291744da1c149489d5c2b20dec67ceef4b99e`.
- Replay: `a91418d26f1584021b8a293ecb4023df3dbff426c422cb93bedbaa7ad2687f8e`.

Initial camera world pose is exactly equal in the saved readbacks: position
`[1.4906339645385742, 60.565616607666016, 0.5899999737739563]`, quaternion
`[0.7012659311294556, 0.7012657523155212, -0.0906984806060791, -0.09069852530956268]`.
Local mount is equal too. Recorded rendering-frame rational values are 142/30
versus 137/30 despite equal sensor/simulation times. These are distinct clock
fields; their difference does not prove which acquisition or renderer state
caused the pixel difference.

At the last pre-kidnap learned invocation (physical step 36), the complete ordered
six-image history is below. Sensor and simulation timestamps agree both within
and between arms. Every paired image is 320×240 RGB; both file bytes and decoded
pixels differ. Camera world positions/quaternion components and local mounts
are exactly equal in the saved readbacks for all six pairs.

| Slot | Image ID | Physical step | Sensor/simulation time (s), both arms | Render numerator reference/replay (denominator 30) | Max RGB channel difference /255 |
|---|---|---:|---:|---|---:|
| 1 | `script_05.png` | 6 | 2.225000116042793 | 178 / 173 | 14 |
| 2 | `script_11.png` | 12 | 2.725000142119825 | 214 / 209 | 9 |
| 3 | `script_17.png` | 18 | 3.225000168196857 | 250 / 245 | 12 |
| 4 | `script_23.png` | 24 | 3.725000194273889 | 286 / 281 | 17 |
| 5 | `script_29.png` | 30 | 4.225000220350921 | 322 / 317 | 12 |
| 6 | `script_35.png` | 36 | 4.725000246427953 | 358 / 353 | 19 |

Across all seven learned invocations, history slot order, image IDs, physical
steps and sensor/simulation timestamps match. Thus different history selection
is not supported. These are corresponding captures from separate launches,
not reuse of one byte-identical capture. The raw pre-PNG sensor arrays for these
history frames were not retained; the earliest directly compared pixel evidence
is decoded lossless PNG, upstream of model preprocessing. A raw-sensor versus
image-save defect cannot be isolated from these artifacts alone.

Both traces record the same preprocessing: official 4:3 centre crop, PIL resize
to 85×64, ImageNet mean `[0.485, 0.456, 0.406]` and standard deviation
`[0.229, 0.224, 0.225]`, six RGB frames concatenated to 18 channels. Source:
`src/navfm/collection/rgb_baseline.py`. Initial recorded renderer settings match.
The prior CPU audit reconstructed all 168 actual-entry tensor hashes from saved
images with that pinned preprocessing. It is existing evidence, not a new run.

| Invocation | Observation shape/dtype | Reference actual-entry SHA-256 | Replay actual-entry SHA-256 |
|---|---|---|---|
| Step 0 | `[7,18,64,85]`, float32 | `f2f90805317472110a7737020277e41940661e036e7e90bffaa3c6e8101224ca` | `9cd9b7ff4239c16c576c73392b4ed2423ba06d7be58a19fb359def687cc7c6ac` |
| Step 36 | `[16,18,64,85]`, float32 | `c7ef0aee7a04f85c8d985f87886126539f0577066cdee17f44ccd2a572cd61a5` | `34c165b75af78b3ff87e53a6bcb1834c218881c0ed428b0b92678535691b327d` |

Goal/chain tensor hashes match between arms at both invocations (and all seven
in the prior audit). Original actual-entry tensor byte files were not retained;
hashes, shapes and dtype were. The evidence locates divergence before
preprocessing and does not support a differing preprocessing configuration as
its origin. It does not establish the image-generation cause.

**Stop at the missing evidence:** paired raw sensor-buffer bytes/digests before
PNG conversion for these exact frames, and a complete causally comparable
render/acquisition-state record explaining their different render-clock values
and pixels, are absent. Recorded poses/settings alone do not supply that state.
No repair is selected and the observer repair is not reopened.

### Collection dependency scope

The failed pair gate belongs to `run_replay_recovery_validation_v2.py` and its
learned-policy replay/handover contract. It blocks advancement of that replay-based
corrective experiment. It is not a universal dataset-admission dependency.
`run_prospective_collection_v2.py` uses `prospective_capture_collection_v1.py` and
`prospective_collection_contracts_v1.py`, a separate kinematic capture/admission
path; its [144-frame admitted result](PROSPECTIVE_COLLECTION_RESULTS_V2.md) is
positive evidence of ordinary kinematic collection under its own limited contract.
It does not establish physical ordinary collection or admissible expert correction.
Physical collection retains its independent plant/contact/lifecycle gates; do
not attribute those limitations to the replay handover mismatch. No ordinary
collection run is requested or authorised by this distinction.

## Smallest repair and the missing observation

**No additional collector repair is identified by the present evidence.** The
observer bug has a completed bounded repair; the next failure is not evidence
that the same observer still fails. An input-equivalence control has already
passed offline, but replaying saved tensors would bypass live acquisition and
would not repair or qualify physical corrective collection.

For a strict live-input handover repair, the missing causal observation is which
image-generation state or operation produces the reference/replay observation
changes despite matched measured physical/history state. Existing records do not
bind a causal difference in renderer temporal state, exposure, scene/actor state
or sensor production; these are possibilities, not diagnosed faults. Original
global backend flags were incompletely recorded, although saved-input tests
reproduce the observed predictions without changing initial policy state.
Without that observation, naming a renderer reset, exposure change or runtime
flag as the repair would be speculation.

Evidence of a successful future repair would have to retain source/scene/runtime
identity, native acquisition and physical/history checks, demonstrate equivalent
actual model-entry observation tensors and learned state, and pass the unchanged
numerical/command pair gates. The existing offline same-input control demonstrates
only the numerical part. Alternatively, a different task-based handover criterion
would require independent scientific justification; selecting tolerances from
these maxima would change the question, not fix the failed check. Neither route
is implemented, frozen or authorised here.

## Does an admissible corrective record already exist?

**None is established in the reviewed evidence.** This is bounded to the named
records, not a claim that every workstation file has been inventoried.

- V1 has zero post-kidnap/recovery invocations. V2 has zero in both traces;
  scripted commands controlled motion and requested learned commands were ignored.
  The offline diagnostic executes no commands. These are initialization evidence,
  not corrective demonstrations.
- The [144-frame admitted collection](PROSPECTIVE_COLLECTION_RESULTS_V2.md) is a
  two-accessed-layout kinematic offline pilot. Its admission does not establish
  a physically executed, expert-corrective trajectory.
- [Historical R2 analyses](PROSPECTIVE_R2_BASELINE_CHECK.md) preserve exploratory
  policy outcomes; stage 3 did not confirm recovery. A recovery label or rollout
  is not evidence of a qualified expert correction.

The missing record is a named, admitted trajectory from a documented learner
failure state, with valid achieved corrective motion, expert identity/actions,
image/pose timing, observed contacts, terminal outcome and source-bound admission.
No such record is linked by the reviewed inventories. Existing
[apparatus readiness](SIMULATION_APPARATUS_READINESS_V1.md) and
[loaded-motion results](MATCHED_DEVELOPMENT_NAVIGATION_V2_RESULT.md) remain separate
physical qualification limitations; the numerical diagnostic does not repair them.
The [static-camera lifecycle failure](STATIC_ARRIVAL_CAMERA_QUALIFICATION_RESULTS_V2.md)
is also a separate gate, not the cause of the v1 acquisition failure.

## Current decision and research position

Stop before collector repair implementation, runtime preparation, loader/training
round trips or collection. Preserve all failed attempts and successor evidence.
No captures, inference, calibration, threshold changes, protocol freeze or runtime
approval follows from this reconciliation. No latch audit is repeated.

For Bo: **V2b has a limited development result: three contact-free completions
out of four shortened-reference attempts versus none for C1 in stage 3, on exposed
conditions. Replay-based corrective collection remains blocked; ordinary kinematic collection has a separate, limited admitted result.
Illumination augmentation has not been tested.** This does not establish a validated
new direction, generalisation or an independent collision-risk reduction.

## Preservation and review boundary

The superseded bounded proposal is preserved outside the repository at
`/home/favl/.local/verification/navfm-prospective-v2b-20261021/bounded-pipeline-proposal-before-collector-forensics.md`.
Earlier withdrawn planning history remains at the previously recorded archive.
Only this existing specification is edited. Historical result records, source,
sealed tasks, runtime evidence and model artifacts are unchanged. Checks for this
follow-up are source/result consistency, selected recorded analysis hashes, local
links and whitespace; no experimental test is rerun.
