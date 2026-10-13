# Native RAVEL fixed-mode graph attempt result v1

**FAIL: adapter checkpoint-coverage guard refused admission.** The single first
matching attempt used freeze `5ae006facce2d7225e205b0fab24e424bb2e3a9b`.
Parent exit1, no timeout, child reaped. Worker status records SystemExit1 after
the native analyzer reported `native final checkpoint coverage incomplete`.
This establishes a guard refusal, not a bad checkpoint or a failed matcher.
No automatic retry, fitting, frame change or encoder repeat occurred.

The retained partial ledger has two WEIGHT_LOAD events and one MODEL_CONSTRUCTED
event: SuperPoint with no missing buffers/unexpected keys. LightGlue's verified
asset was loaded, but its adapter constructor was not admitted. There are zero
forward events, candidate-range events or pair attempts: zero SuperPoint,
LightGlue and global encoder forwards. The native fixed-parameter return branch
was not reached. No adjacency, pruned graph or28-pair decision ledger exists;
absent outcomes are not zero edges or successful rejections.

Eight reference rows, their authenticated node map, cached features and the
native flat/L2 index are preserved externally. The180-second worker deadline was
not hit. Exact worker wall/GPU-peak values were not retained on this failure.
All evidence totals546185 bytes, below the16MiB acceptance bound.

## Diagnostic boundary and next step

Static source inspection confirms the native LightGlue constructor first loads
with strict=False, remaps legacy self_attn/cross_attn keys into transformers,
then performs its final strict=False load. The adapter retains that last result,
but checks missing trainable or unexpected keys and raises before emitting the
key lists. Thus the exact incompatibility set is not in this attempt's evidence.
The guard executes after the native base constructor returns. No model was
reconstructed to recover missing diagnostics and no second attempt occurred.

The next bounded decision is a reviewed key-reporting correction plus CPU-only
checkpoint-key structural inspection against authenticated source/remap rules.
Do not infer defective assets, weaken admission, or claim graph qualification
from this incomplete record. Adaptive/default RAVEL, navigation and physical
STOP remain unqualified. The earlier zero-call readiness refusal is preserved
in [the preflight record](NATIVE_RAVEL_FIXED_GRAPH_PREFLIGHT_V1.md).

Raw evidence: `/home/favl/navfm-runtime-evidence/ravel-fixed-graph-v1-01`.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| attempt.json | 411 | `1dff3b749f424033873dab37d81f999d119c1ebc9fd1fc7b6a3810fa2c1caeea` |
| features.npy | 270464 | `48095770c7ecbf29742dfabbdd1e1b7130cb2b2d3e62562ed73fefd654a07287` |
| index.faiss | 270381 | `aaea739c7dfc5a11aacd825802f524397aad4dddd7eec6d384ed076a9f48309d` |
| index.faiss.meta.json | 67 | `2abb0af4b233aa665a246c9f767cd022ec92d36deabbffd9b94a8320624d795e` |
| node_map.json | 2072 | `c591d691e668a30347a0a71e6898a86539935176e83b4c890dec2d1fecf54e8f` |
| parent_status.json | 135 | `974fa131d554b87cbf698396adf6344404790e733129e4c05e45278b8cf1efed` |
| partial.jsonl | 372 | `1f5e4d3b8abc07e94a1cc9bb03ebce3d2ade265ba8714ed519a38dbbfee66c01` |
| paths.txt | 845 | `7ae306711d49660653ea7b6085a64d560c4a720a58e961c658e11d2f578e402c` |
| worker.log | 1308 | `ed421a02d57c6c0f722c695ba4aa3758b3dc807d7f4eb21efa9c52b5ddb105b4` |
| worker_status.json | 130 | `281e1c9903955cd029c24484d0d353dc36f257b31f4efeb472d8a95a957fdd04` |
