# Native fixed-mode RAVEL graph qualification result v3

**PASS for the fixed eight-reference native construction component.** The single
production attempt used freeze `7869df824a78e64e19927e60330927fcb5f09616`.
Parent exit0, no timeout, child started and reaped. Worker wall4.632440s;
peak allocated GPU680,023,040 bytes on RTX4080 SUPER. Raw evidence1,732,417 bytes
is below16MiB;180-second worker/360-second parent bounds were respected.

Existing authenticated constructor proof was consumed without repeating the
six-case CPU validation. Normal production admitted2 models and executed exactly
56 SuperPoint/28 LightGlue forwards (the fixed caps),0 global encoder forwards
and0 technical failures. Every reference/descriptor/node binding remained intact.
The recorded node-map SHA matches the earlier8-node mapping.

| Recorded construction outcome | Before pruning | After native pruning |
| --- | ---: | ---: |
| Nodes | 8 | 8 |
| Weighted edges | 28 | 7 |
| Connected components | 1 | 1 |
| Isolated nodes | 0 | 0 |
| Edge-weight range | 9–127 | 64–127 |
| Matrix | 8×8 uint16 | 8×8 int32 |

All8 native range rows and all28 unordered pair outcomes are preserved:
28 accepted with positive geometric-inlier counts,0 radius exclusions,
0 zero-count rejections. Native maximum-spanning pruning removed21 edges;
no edge exceeded the>300 add-back threshold. Both matrices remain symmetric
with zero diagonals and retain all8 node identities. No synthetic connectivity
was inserted. The complete pair ledger, mappings, matrices, plots and model/load/
error records stay external.

These facts qualify faithful execution of the declared nondefault native
num_clusters1/tau0/radius2/flat-L2/weighted-RANSAC/pruning mode on the fixed DEV
reference subset. They do not establish that every matched edge is navigable,
map topology is correct, adaptive/default HNSW RAVEL is reproduced, or navigation
and physical STOP work. No fitting, frame reselection, source/asset download,
six-case constructor validation/global-encoder replay, simulation, navigation or actuator operation
occurred. Nineteen hermetic guards and the six actual CPU-only launcher cases
passed before freeze. Prior [graph guard refusal](NATIVE_RAVEL_FIXED_GRAPH_RESULT_V1.md)
and [launcher preflight failure](NATIVE_RAVEL_GRAPH_CONTINUATION_RESULT_V2.md)
remain preserved; no retry or retrospective pass was applied.

Evidence: `/home/favl/navfm-runtime-evidence/ravel-fixed-graph-v3-01`.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| adjacency_matrix.npy | 256 | `3cd169a999d7ad0b57c7e90a3fe1d86ff837c11ea1af413494e951bcf820c6e0` |
| attempt.json | 186 | `984a15ef445f3ca4a32b377e34cf2293a0400f51bca96a13ec14753be8ee18f7` |
| features.npy | 270464 | `48095770c7ecbf29742dfabbdd1e1b7130cb2b2d3e62562ed73fefd654a07287` |
| index.faiss | 270381 | `aaea739c7dfc5a11aacd825802f524397aad4dddd7eec6d384ed076a9f48309d` |
| index.faiss.meta.json | 67 | `2abb0af4b233aa665a246c9f767cd022ec92d36deabbffd9b94a8320624d795e` |
| node_map.json | 2072 | `c591d691e668a30347a0a71e6898a86539935176e83b4c890dec2d1fecf54e8f` |
| pair_decisions.json | 2665 | `a402fc4c09e1a12107922f7a1dce3d9389cbb8adf2244d61dfd56047b977d6cf` |
| parent_status.json | 161 | `14bd184773622d9071249920998a3ff8074998111e18d9dc5ec04b59791a1323` |
| partial.jsonl | 124422 | `0452606e656708d140f88551aa91240260d3f6cca08bc46db28d75539cc594ef` |
| paths.txt | 845 | `7ae306711d49660653ea7b6085a64d560c4a720a58e961c658e11d2f578e402c` |
| pruned.npy | 384 | `fc14ff6266dfa5870ee105aa8d18eb1b33ca58165c113552d913baab4a5a03bb` |
| pruned.png | 263796 | `26733956fe0d3c0be80909afe9d5ea25f370f37786ffe688e14802cb6c1a465a` |
| result.json | 505 | `b9b47f87288dda138e430d06cac0ac04927b806035b16d2a4c061120aa18816c` |
| topological_map_visualization.png | 791987 | `e638dbcf2ebb854d937423d5e7f9b06c1d194fd86111e2dadfe0cd1a50733597` |
| worker.log | 3736 | `2f3c1c5a1616bd882862e16d715ebb49c67bb47142ee445c0c9a2f76967d7162` |
| worker_start.json | 411 | `be6d3a77b6280db2be081372b1e173c6b304b01bee534e3543c85d5e0d9acd29` |
| worker_status.json | 79 | `88a706f1b5b3560186a87d226aaeae07f3c2c858ee1b19c49567d5079e0b5d6d` |

Next decision: separately scope any use of this graph by the comparator interfaces;
no navigation/robot study is authorised by this component result.
