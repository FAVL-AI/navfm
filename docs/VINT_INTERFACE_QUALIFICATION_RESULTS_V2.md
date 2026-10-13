# Native ViNT component qualification v2 result

**PASS for the fixed synthetic native-interface procedure; no pair-scoring or navigation result.** Source freeze `d0b724085afcdc3e2247acd79dfda9695269fb79` completed one authorized 150-second attempt. The original v1 qualification FAIL remains unchanged. The only compatibility correction was the exact authenticated persistent ViNT source entry in the versioned manifest; model/checkpoint/input/acceptance rules were unchanged.

Before CUDA, exact-interpreter import-only validation covered 2,214 loaded file records with zero unaccepted sources, using the original verifier. One focused original-verifier test passed its exact-entry control and three negatives (modified bytes, foreign origin, unexpected file); Ruff passed. A manual preflight initially used a mistyped abbreviated SHA and correctly failed before reservation/launch; the actual full-commit preflight passed. No model retry occurred.

All four identities—the official release and fixed prior epoch20 selections for seeds 0/11/22—passed strict native load/reload, exact observed-session reload outputs, eval state/RNG fences and both fixed synthetic cases. Inputs are `[2,18,64,85]` observation and `[2,3,64,85]` goal; outputs `[2,1]` distance and `[2,5,4]` XY/cos/sin. All output values are finite; heading norms satisfy the frozen criterion. Native XY cumsum is preserved and metric conversion multiplies spacing once. No waypoint/distance accuracy metric was calculated. Native preprocessing/units and exact checkpoint hashes remain in [the original protocol](VINT_INTERFACE_QUALIFICATION_V1.md).

Parent observed child return code 0, timeout false and reaped true. Saved `occupied_wall_s=7.78138513956219` precedes final persistence and is not an end-to-end observation. The frozen finalizer passed its later 150-second checks; actual end-to-end duration was not separately measured. SDK or robot lifecycle claims do not apply to this model-only procedure.

Installed dependency record counts are 1,231 before / 1,236 after; native records 2,240 before / 2,254 after / 2,254 final. Upstream pre/post attestation completed. Full artifact hashes, complete marker→ledger binding and registry→marker/ledger bindings were independently rechecked. Four retained raw content hashes were also recomputed with shape/finite/heading validation. Exact equality is a session control, not universal CUDA determinism. Raw JSON arrays retain numerical values and shape; their original tensor dtype is not separately serialized.

External root: `/home/favl/navfm-training-evidence/vint-interface-v2-qualification-01`.

| Artifact | SHA256 |
|---|---|
| report.json (all raw arrays) | `6d67f6ee200fcf0d7ab9ddbb01f8a1d55fa1fd58c1603b2863be869d213ee71e` |
| provenance.json | `79fb8809018e7aa5de3af33035a2563d5bf51277c86d964e457f0a5887a4785e` |
| process.log | `c3fd0212ce6e5f92d881df92fe619766242144e734b000d5239d4ba509a0c776` |
| ledger.json | `66ab1b80609dec03a053b0fca6cb0c4cfa1d5361c061d35066ab9d0a651288c5` |
| qualification_complete.json | `91dfbfa2df9dfaa1ad84af721a438dc870ba9e1a5307b936f6ccd9c84da6e5b3` |

Four raw content digests are retained in report.json. Checkpoint weights, synthetic arrays and all provenance/logs remain external; no generated artifact enters Git. This establishes the tested native ViNT interface/checkpoints, not learning gains or generalization. Next decision: separately freeze and authorize a compatible three-model evaluation, preserving prior selections and closed GNM/NoMaD results. No scoring, training, collection, simulator or robot action was performed.
