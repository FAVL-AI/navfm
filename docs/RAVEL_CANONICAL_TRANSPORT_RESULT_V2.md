# Exact LightGlue transport CPU validation result v2

**PASS for CPU constructor transport/state parity only.** One authorised attempt
used freeze `63b482203f24cbd6cfda707073e2763ee6851b4a`; parent exit0,
no timeout, child reaped. Worker wall2.115919s; zero forwards/GPU calls.
Six constructor attempts: raw-native oracle, canonical guarded candidate and
four refused negative cases. The canonical candidate passed the unchanged
trained-parameter/unexpected-key admission guard.

All251 parameters and1 computed buffer matched the native raw-checkpoint oracle
in names, dtype, shape, values and tensor bytes. Only the exact nine authenticated
source-unused float32/finite/shape[1] entries were removed from the copied local
transport mapping. Every remaining tensor object was preserved. The checkpoint
file/checksum, native source/constructor/remap and admission guard stayed intact.
The raw-native oracle bypasses only the project guard for this CPU comparison;
it is not an admitted inference path.

| Control | Actual refusal boundary |
| --- | --- |
| Missing posenc.Wr.weight | Existing final trained-parameter guard |
| Unknown diagnostic_unexpected | Existing final unexpected-key guard |
| Wrong trained tensor shape | Native load RuntimeError, metadata persisted first |
| Native remap collision | Refused before canonical copying/load |

Eight pre-constructor controls also refused: missing/tampered asset, altered
source/asset/effective-config bindings and wrong legacy shape/dtype/nonfinite
state. Derived negative mappings were explicitly CPU-validation-only after
original byte authentication; they never became replacement checkpoint files.
All expected positive/negative outcomes were retained, with no retry.

Raw evidence stays external at
`/home/favl/navfm-runtime-evidence/ravel-checkpoint-validation-v2-01`:
393,909 bytes below the16MiB acceptance bound. Both60-second worker and120-second
parent bounds were respected. Twenty-five focused hermetic tests/Ruff passed
before freeze; all previous population/resource ownership remains preserved.
Independent readback accepted these counts and this limited claim.

The [original guard refusal](RAVEL_CHECKPOINT_DIAGNOSTIC_RESULT_V1.md) and
[failed graph attempt](NATIVE_RAVEL_FIXED_GRAPH_RESULT_V1.md) remain unchanged.
No encoder replay, image access, matching, graph, fitting, simulation, navigation
or actuator operation occurred. This result does not qualify RAVEL graph
construction or authorise another graph/navigation attempt; the next decision
is a separately scoped use of the now-qualified guarded constructor preflight.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| attempt.json | 344 | `41e3a882387c5640e452e88d5d6e8137b23331c6cb060beed8c83eacc37f10b4` |
| parent_status.json | 135 | `2296f43f68ed3d167dab1e747d347f0fc70da473d0fcb1c538f0691c2e9fde6b` |
| partial.jsonl | 392632 | `08bd89b95b7dd87a5867b7612287951a0d96260af2cc50dade6a997592d88b3e` |
| result.json | 393 | `1bbf596f07ca3e6d85be47eececbd2a8f39b9b042c2974d3795350c4786b5426` |
| tampered_asset.pth | 1 | `6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d` |
| worker.log | 325 | `cb4a90df7d76040396825d7dc185f5906f6d8e67af9b1d308971534fa14bfdb2` |
| worker_status.json | 79 | `1f68c073875c4a00d4576aeefa314a98cca0e9bd7cbd92096c43680693af1e37` |
