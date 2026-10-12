# LightGlue CPU checkpoint fidelity review v1

Owner: Frank Asante Van Laarhoven <frankleroyvan@gmail.com>

Review date: 2026-10-12. Branch: `agent/research-three-model-plan`; inspected baseline: `e67c23902c60f8513e3b4d08bc9b7a044485b5ca`.

## Diagnostic boundary

The [retained graph attempt](NATIVE_RAVEL_FIXED_GRAPH_RESULT_V1.md) stopped at the adapter's final LightGlue checkpoint-coverage guard before any matching or encoder forward. It did not retain the refused key lists. That evidence establishes a guard refusal, not defective weights, an incompatible model or an incorrect remap. This CPU diagnostic preserves that failure and the authenticated source, weight and configuration identities. It performs no matching, graph construction, image/descriptor replay, fitting, simulation or robot operation. No new asset or source search is needed. Skill-retrieval remains unavailable; the criteria come from the existing project contracts and pinned source.

The [native constructor](https://github.com/hren20/ulvn/blob/e2f47fe3e2757a1ebdc041f4364dddd26a19f9f5/RAVEL/scripts/lightglue/lightglue.py) applies the SuperPoint feature configuration, performs an initial non-strict state load, remaps legacy attention names, then performs a final non-strict load. The first stage's incompatibility list cannot substitute for the final stage's result. The adapter's initial rule remains unchanged: any missing trainable parameter or unexpected final key refuses admission. Native non-strict loading is not, by itself, justification to remove this guard.

| Competing explanation | Evidence needed to distinguish it |
| --- | --- |
| Source/version or configuration mismatch | Effective native configuration and source/asset identities, model parameter/buffer keys and shapes, supplied checkpoint shapes, and actual final-load discrepancies. |
| Legacy remap error or collision | Both actual load stages plus the authenticated native key-string mapping and any distinct original keys mapping to one final key. |
| Extra checkpoint state unused by this source | Complete learned-parameter coverage and matching shapes, with each unexpected key separately traced against the pinned model state and code. Its irrelevance cannot be inferred merely from non-strict loading. |
| Adapter guard rejects otherwise compatible native state | The preceding evidence must show why a precise exception is safe for these pinned inputs; no broad relaxation, dropped learned parameter or silently substituted configuration is acceptable. |

Detailed key/shape records remain external. No tensor values, weights, image bytes or learned descriptors enter this review or Git. A supported correction must retain exact identities, explicitly account for any approved key exception and preserve failure behavior for missing, altered or incompatible inputs. CPU construction alone cannot establish numerical matching correctness or graph quality.

## Initial implementation review

The [diagnostic protocol](RAVEL_CHECKPOINT_DIAGNOSTIC_PROTOCOL_V1.md) uses the shared production constructor instrumentation and the exact authenticated native analyzer constructor statements with a CPU device. It retains SuperPoint's strict load and both LightGlue load stages, effective configuration, parameter/buffer/checkpoint shapes and final admission diagnostics. Reports are flushed before native loading or the unchanged guard can raise. The remap report executes only the authenticated key-string loop; it does not alter the actual checkpoint or native constructor sequence.

The bounded corrective readback resolved a diagnostic namespace error: the native remap comprehension now executes with one explicit restricted globals/locals namespace. The actual helper passed a legacy-key/collision check with zero tensor access, constructor calls or forwards; retained result SHA-256 is `1b4c4f46a3ef2d7599043d0c828ab491469cfad76ea33c97001414f29921f327`. The missing/tampered-file negatives target the LightGlue asset through the production authenticity helper. Diagnostic completion requires the actual LightGlue constructor attempt, both load diagnostic/result stages and its final admission report; a SuperPoint-only or incomplete record cannot be labelled the completed target diagnosis. Seven new diagnostic controls and ten existing graph guards, plus Ruff, are reported passing. These software checks do not execute a model constructor.

The initial diagnostic implementation is accepted for a clean freeze and one CPU attempt under the fixed envelope: at most two constructors, zero forwards/GPU calls, a 30-second supervised worker, a 60-second outer launcher and a 16 MiB output acceptance limit. CUDA must be hidden and the existing Python network restriction enabled. The two file-authenticity negatives precede construction and do not add model attempts. Preserve attempt, partial, worker and parent evidence. A completed guard-refusal diagnosis is distinct from successful constructor admission.

No cause or correction is asserted before the actual CPU evidence. Any justified repair requires a separately reviewed revision and fresh bounded CPU validation. The reusable preflight requirement is limited to these actual matcher constructors before a subsequent expensive adapter attempt; it does not authorize a general framework, encoder replay or graph retry. Initial review edits are complete before the diagnostic freeze.
