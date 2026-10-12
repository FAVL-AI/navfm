# Exact LightGlue legacy transport repair and CPU validation v2

Branch `agent/research-three-model-plan`; baseline
`e8563a7d39a202707a92ac65e699009396b2ed27`. The published
[initial CPU diagnosis](RAVEL_CHECKPOINT_DIAGNOSTIC_RESULT_V1.md) retains its
unchanged guard refusal: all251 trained parameters covered, no shape mismatch
or remap collision, but nine source-unused log_assignment.[0–8].r entries.
Their authenticated metadata is shape[1],float32,finite. Earlier graph failure,
checkpoint/source identities and all existing admission rules remain preserved.

The [versioned transport policy](../configs/eval/ravel_lightglue_transport_v2.json)
binds the exact native LightGlue source SHA, authentic asset SHA and full observed
effective configuration (including9 layers,256 dimensions and4 heads).
Only the nine defined unused entries may be removed from a copied local transport
mapping. Their shape/dtype/finite predicates and native remap collisions are
checked before copying; every remaining tensor object is retained unchanged.
No checkpoint file, recorded checksum, native constructor/body/remap or trained
parameter is rewritten. Unknown extras remain present for the unchanged guard
to refuse. This is a disclosed exact transport canonicalization, not blanket
strict=False acceptance or checkpoint replacement.

The shared production constructor path selects this canonical mode. The current
reusable matcher CPU preflight uses the same mode before future expensive
adapters; the initial diagnostic v1 explicitly selects raw mode to preserve its
original purpose. SuperPoint transport/configuration remain unchanged; this
fresh validation constructs no SuperPoint or global encoder model.

## Frozen CPU validation

The [validator](../scripts/validate_ravel_checkpoint_v2.py) invokes the exact
authenticated native analyzer LightGlue constructor assignment with CPU device.
Its raw-native oracle uses the original constructor without the project admission
guard only for this bounded CPU comparison; it is not inference admission.
The canonical candidate uses the actual guarded production class/transport.
Compare names, dtypes, shapes, torch.equal values and contiguous tensor bytes for
all251 parameters and1 computed buffer, with zero forwards.

Exactly6 constructor attempts: raw-native oracle, canonical guarded candidate,
missing trained parameter, unknown extra, wrong trained shape and remap collision.
Derived negative mappings are explicitly validation-only, created after verifying
the authentic original bytes; they never rewrite the checkpoint file/checksum or
enter production trust. Missing and extra keys must fail the existing native-load
admission guard; wrong shape must fail native load with durable pre-load metadata;
collision must fail before canonical copying. Eight additional pre-constructor
controls cover missing/tampered assets, altered source/asset/config bindings and
legacy shape/dtype/nonfinite predicates. Every outcome remains external.

60-second whole CPU worker,120-second outer launcher,16MiB raw-output acceptance
bound (not a filesystem quota),6 constructor attempts,0 forwards/GPU calls.
CUDA is hidden, Python network refused, existing authenticated sources/assets and
isolated dependency overlay reused. No source search, acquisition, image access,
reference repicking, encoder replay, matcher forward, graph, score, fitting,
simulator, navigation or actuator operation is authorised. One measured CPU
validation after reviewed clean freeze; no automatic retry on failure.

```sh
CUDA_VISIBLE_DEVICES='' timeout 120s /home/favl/navfm-source-evidence/ravel-fixed-assets-20261012-01/venv/bin/python scripts/validate_ravel_checkpoint_v2.py --freeze REVIEWED_CLEAN_SHA --out /home/favl/navfm-runtime-evidence/ravel-checkpoint-validation-v2-01/result.json
```

Eight new hermetic binding/budget tests plus17 existing guards pass; Ruff passes.
All3184 previous nodes/markers/resource owners remain,3192 expected nodes total.
The actual constructor evidence belongs to this separate explicit CPU command,
not a hermetic test or historical archive job. No fresh constructor ran before
this validation freeze. A passing result will qualify the constructor transport
and state equality only; it does not convert the earlier graph failure into a
pass or authorise a new graph/navigation attempt.
