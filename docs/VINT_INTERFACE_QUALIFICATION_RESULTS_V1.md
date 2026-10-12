# Native ViNT component qualification v1 result

**FAIL; complete interface qualification NOT ESTABLISHED.** The one authorized synthetic component attempt used source freeze `f0274630cc81dc62978c6938311cf58908d55b4a`. All four checkpoint rows passed their component checks, but post-native dependency authentication failed. No pair scoring, dataset access, adaptation, simulator, robot action or retry occurred. GNM/NoMaD pilot results remain closed.

The official release and prior selected epoch20 seeds 0/11/22 are the fixed identities in [the protocol](VINT_INTERFACE_QUALIFICATION_V1.md); no new checkpoint selection occurred. Each role completed strict native load and reload, exact observed-session reload-output agreement, state/RNG fences and two synthetic cases. Retained distance/action shapes are `[2,1]` and `[2,5,4]`; all values are finite and heading pairs satisfy the frozen unit-direction check. Four raw nested-array content hashes were independently rechecked against the saved arrays, together with shape/finite/heading validation. These are component observations, not prediction-quality metrics or general CUDA determinism.

The child raised `ImportError: unauthenticated generated dependency` in `verify_native_dependencies` after all four rows. The same check failed in finalization. Installed/native/upstream before-attestation exists; the combined after-attestation assignment did not complete, and no after/final proof is available. The verifier routes any file outside the manifest or with a mismatched hash through this error path: the wording alone does **not** prove the rejected object was genuinely generated. Its module name, file, content hash and code/export identity were not retained, so its exact identity remains UNKNOWN. No namespace exception or repair was selected.

The parent preserved FAIL and no `qualification_complete.json` marker exists. Saved `occupied_wall_s=8.1145173702389` is measured before final persistence, not end-to-end duration. The 150-second watchdog was not the reported failure; actual child exit code and reap flags were not serialized on this parent failure path, so they are not separately attested by the ledger. The process command ended with exit 1; no process retry occurred.

External evidence root: `/home/favl/navfm-training-evidence/vint-interface-v1-qualification-01`.

| Evidence | SHA256 |
|---|---|
| report.json, including retained raw arrays | `226bd883366439f21841100fc42118dd5e7b12fb8924ac4a617746f79672ac93` |
| provenance.json | `57d3a8f6b70806889340a891d3bd86998cab84be1c140b8079f1beb8a2916c75` |
| process.log | `4b1e9b42201d055f38580656970bedb3ae58638c382473c680fa20a5ed343c48` |
| failed ledger.json | `897b2828d261ca3f84bd9cacd5d2014164fbe238d6852534735569b9f5305bdb` |

All three artifact bindings in the failed ledger match actual bytes. The four raw content hashes are recorded in the report. Raw weights, synthetic outputs and logs remain external. Ten focused CPU tests passed before the run; no software suite or model attempt was repeated afterward. A metadata-validation command initially named a nonexistent helper module and failed before reading evidence; correcting that import enabled the checks above without a runtime retry.

CAD remains blocked on an available trusted Parasolid decoder/license and validated STEP assembly output; the existing conversion packet is the handoff. Next decision is a narrowly versioned source-authentication diagnostic that preserves the rejected object's actual identity before any justified rule correction and fresh component attempt. ViNT remains excluded from scoring until complete qualification and a separately frozen scoring protocol; no repair or additional runtime was performed here.
