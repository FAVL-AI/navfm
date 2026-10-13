# Native fixed graph continuation preflight failure v2

**FAIL before worker launch.** The single authorised invocation at freeze
`dac62f9ec7721a31ea5bb1bbf7ce734c8131f564` exited1 with FileExistsError.
The launcher first created attempt.json as PREFLIGHT_STARTED, consumed the
qualified constructor proof, then attempted to create the same file again as
STARTED. The shared writer uses exclusive-create mode. The second write refused
before worker.log or the supervisor/worker was reached.

Zero model constructions, forwards and pair checks occurred; no adjacency,
pruned graph, node map or graph result was produced. There was no child process,
so child exit/reaping/timeout are not applicable, not inferred successful.
No retry, repair, directory deletion, parameter change or inference occurred.
The original attempt record remains intact; a separate terminal sidecar preserves
the actual parent exit1 and preflight failure. All qualified CPU proof hashes
remain unchanged; this software bookkeeping failure does not invalidate that
constructor result or qualify a graph.

The exact source path is launcher lines180–187 (first exclusive write),204–213
(second exclusive write),214–219 (unreached supervisor), and shared write_json
line232 (`path.open("x")`). The helper-level proof/hash tests passed, but did not
execute the admitted launcher record-creation path. That is the concrete coverage
gap. A future narrow fix must test the actual admitted entry lifecycle on CPU
with zero models before any separately authorised graph attempt. No fix is
applied now under the explicit no-retry boundary.

This failure is separate from the [earlier native graph guard refusal](NATIVE_RAVEL_FIXED_GRAPH_RESULT_V1.md).
The prior constructor repair/parity remains qualified; graph construction,
adaptive RAVEL and navigation remain unqualified.

Evidence stays external at `/home/favl/navfm-runtime-evidence/ravel-fixed-graph-v2-01`.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| attempt.json | 186 | `e4ca983ce5a29dc55360e0e2ea2ac8ae0b620d04b05480c6abcd3c0433de8563` |
| terminal_preflight_failure.json | 644 | `268bb499c1b93061153a435c77c033eaace7dfb4a69e9d5758ee1a671e02e35c` |
