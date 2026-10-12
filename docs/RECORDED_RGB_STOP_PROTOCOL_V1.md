# Recorded RGB encoder/reference and mock STOP qualification v1

**Bounded recorded-component replay only; no encoder inference before source
freeze. Navigation, fitting, native graph construction and physical STOP remain
BLOCKED.** Branch `agent/research-three-model-plan`; baseline
`9cb73aa43e186028d3824c19862eb42381d5b53a`.

The [implementation](../scripts/recorded_rgb_stop_v1.py) and
[fixed manifest](../configs/eval/recorded_rgb_stop_v1.json) qualify authentic
encoder-forward/reference paths and source-bound belief replay against existing
admitted DEV RGB. The [independent review](RECORDED_RGB_FIDELITY_REVIEW_V1.md)
records native source and adaptation boundaries. No closed pilot outcomes,
training labels, pose labels or threshold selection are used.

## Inputs and selection before outputs

The immutable admission/finalization transaction covers four DEV trajectories
of 36 processed RGB frames each, with empty TRAIN/TEST. Select the first DEV
trajectory lexically: `prospective_v1_layout0_route0`. References are numeric
frames 0,4,8,12,16,20,24,28; queries are 1,5,9,13,17,21,25,29. The goal is reference
frame28, identity-only. Bind every frame path/hash to admission and bind its
completed finalization before loading inputs. No visual or encoder outcome can
change this fixed selection.

Raw image hashes/order remain unchanged. PlaceNav uses native OpenCV BGR→RGB
and ULVN uses PIL RGB; decoded RGB arrays must agree for this shared-input
qualification. Native preprocessing then remains model-specific. The processed
JPEG manifest supplies frame order, not per-image capture timestamps. The prior
nominal capture spacing near one-third second is not recast as four-Hz
acquisition; recorded frame indices and a separate virtual four-Hz adapter
clock are reported. No cadence-invariance claim follows.

## Authentic encoder and normalization paths

PlaceNav commit1720be0146355999ce669d92a5655f02d80d6a45 selects CosPlace
EfficientNet_B0/512D. Execute its authenticated native layers/network/BaseModel/
CosPlace forward definitions. Its inference preprocessing is uint8 RGB→ToTensor
→Resize(H64,W85,antialias=True)→ImageNet normalization, with float32 output;
`efficientnet_85x85.pth` naming does not change inference dimensions. Replace
only the module-local pretrained-backbone transport factory with weights=None;
all persistent state keys must be covered and load strictly before eval/forward.
This is a declared constructor/loading adaptation, not original network-fetch
execution or a weaker checkpoint substitute.

The official README Drive release was retrieved once: 18,952,687 bytes,
SHA256 `36751d751cf70820e8ea0d1da7873e58194c8e35cfc29ad323ba58b50d021867`.
This first authenticated-route retrieval hash is not independently
publisher-certified. Native source/license notices and weight bytes stay
external. Acquisition took4.324 seconds.

ULVN ROS commite2f47fe3e2757a1ebdc041f4364dddd26a19f9f5 is bound transitively to
MegaLoc5fe0dd697c4a70ba3e23607f6716ab3c606b16db and HF revision
a0f34722c4297ff787e022433799250180860af7. The 914,577,436-byte safetensors artifact
matches published LFS SHA256
`d4f9f2bcb60018f91eb6a8e061ed054fd55654e10c2569cf13841ea986ffb4f8`;
one acquisition took38.116 seconds. Construct the authenticated local MegaLoc,
load full state strictly and eval; no torch.hub/HF inference-time transport is
called. Native RGB→Resize320²→ToTensor→ImageNet normalization and internal
320→322 tensor resize/antialias are preserved. Actual output is8448D;
the ROS wrapper's out_dim512 is metadata, not a projection.

ULVN mapping references pass native MegaLoc plus wrapper normalization. Query
images also pass MyVPR's extra normalization. Cached goal features from the
same bound reference RGB receive that extra MyVPR stage on CUDA, then native BASS
normalization. This explicit cached-goal seam avoids an extra encoder call;
there is no universal descriptor renormalizer. Reject nonfinite/zero/nonunit
outputs without repairing native values. Full identity cannot be forced when
native descriptor goal localization is ambiguous or selects another reference.

The existing versioned native-closure interpreter supplies pinned Torch2.7.0
+cu128, torchvision0.22.0+cu128, OpenCV4.10.0, Pillow11.3.0, NumPy1.26.4 and
safetensors0.7.0. No ambient environment or dependency installation changed.
Worker-local Python connection/DNS audit refusal is tested; this is not an OS
network sandbox. Published local code paths deliberately avoid implicit
checkpoint downloads. Actual device/backend identity is recorded at execution.

## Graph, belief and mock adaptation

Use an explicit fixed ordered chain with unit forward edges, shared reference
access/order, no pose/depth. This is a graph adaptation; native RAVEL graph
construction stays BLOCKED because it performs forbidden data-dependent
threshold estimation plus SuperPoint/LightGlue verification. Never label the
chain native graph fidelity or actual navigation qualification.

Native PlaceNav belief/MAP terminal logic and ULVN ROS weighted BPL/BASS/
conjunction/sticky arrival logic reuse authenticated source definitions. Replay
all eight query descriptors twice from fresh belief/planner/mock state and
compare complete recorded state outputs exactly. These resets reuse cached
descriptors; encoder-forward determinism is NOT tested. None-subgoal publication
and unsupported goal behavior stay explicit, without forced terminal indices.

Mock STOP has only in-memory active/queued motion and targets. A true native
publication cancels both, sets zero mock target and latches STOP. Repeated
false/true/absent publications cannot restart motion; cancellation clears motion
without clearing a true latch; only explicit fresh-episode reset clears it.
Stale-episode calls fail. No command callback, ROS publisher or hardware path
exists. This adaptation does not establish native ULVN actuator STOP.

## Frozen budget, evidence and validation

Sixteen selected images × two authentic encoders = **32 forward calls**.
No extra goal/reset/re-encoding calls are permitted. The parent enforces a
conservative **120-second whole-worker timeout**, counting CPU loading as
reserved GPU time, within the300-second overall envelope. Zero fallback to CPU
inference is allowed. Raw output acceptance cap is16MiB: parent verification refuses larger results;
this is not an operating-system filesystem quota. Fixed descriptor shapes bound
the nominal payload. Keep descriptor tensors/images/
weights/raw logs external; attempts, partial rows and terminal worker/parent
outcomes persist, including first failure/timeout. No automatic retry follows.

Preparation used the accepted600-second CPU-only/4GiB acquisition allowance;
two downloads completed in42.44 seconds and no GPU inference occurred there.
No new source search or asset retrieval is needed. The prior29 prerequisite
failures remain unresolved and are not rerun unchanged.

Sixteen hermetic mock/schema/network/admission controls PASS; targeted Ruff
PASS. Add their exact node IDs to ordinary-hermetic ownership while retaining
all old nodes and resource owners. Independent bounded review precedes source
freeze; root commits/pushes before the single measured replay:

```sh
timeout 330s env PYTHONPATH=/home/favl/projects/navfm-research-planning/src /home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/recorded_rgb_stop_v1.py --freeze REVIEWED_COMMITTED_SHA --out /home/favl/navfm-runtime-evidence/recorded-rgb-stop-v1-01/result.json
```

The worker cap is120seconds even though the outer guard permits parent cleanup.
Record results only after that attempt. The closed pilot, held-out geometry,
illumination pause, CAD/plant/contact blockers, feasibility study and larger
benchmark authorizations remain unchanged.
