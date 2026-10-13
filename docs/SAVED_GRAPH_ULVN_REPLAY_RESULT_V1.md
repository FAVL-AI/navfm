# Saved graph to native ULVN component replay result

The single CPU-only attempt at freeze `5f2fe30126760d8440f81dd1142326d3fbd1ba26` passed the saved-graph/native-component/mock contract. Parent exit0, no timeout, child reaped; worker0.057115116 seconds,14,902 bytes retained. No neural model, encoder, matcher, GPU, fitting, graph reconstruction, simulation, navigation or actuator execution occurred.

Two fresh episodes each consumed the same eight cached queries in frozen order. All16 production posterior/path/publication/mock rows were identical across resets. Native goal/start localization returned7/0; initial released unweighted BASS path was0→1→2→3→4→5→6→7. MAP progression was1,1,2,3,4,5,6,7, with subgoals3,3,4,5,6,7,7,7. Each final query29 generated one native True publication and one mock STOP command: two of each overall. Each command latched the mock and canceled queued/current motion with zero target. Earlier publications were absent, not False messages.

The separately derived disconnected fixture performed one update, retained inferred goal7/start0 and returned empty path, absent subgoal and absent publication. Weighted-versus-binary native transition matrices differed while each remained valid and row-normalized. Stale-episode rejection and synthetic mock cancellation/reset controls passed. Five BPL and three BASS instances were constructed; the extra two BPL objects inspected transitions without match updates. Production graph/node/descriptor identities were not changed.

This qualifies integration of this authenticated fixed-mode weighted graph, cached descriptors, native BPL/BASS components and mock STOP adaptation. It does not establish localization accuracy, physical stopping, native ULVN actuator STOP, navigation success or adaptive/default RAVEL qualification. The query timestamps remain virtual adapter cadence. No frame/goal reselection or retry occurred.

Evidence remains external at `/home/favl/navfm-runtime-evidence/graph-comparator-v1-01`: full posterior/path/localization/publication/mock records are in `partial.jsonl`; the derived disconnected and binary matrices are explicitly control artifacts.

| Artifact | SHA256 |
|---|---|
| result.json | `0d86ad7bb6ca1019cdbe6d4397336a47e3c15abdf46395581351b6547f7b0560` |
| parent_status.json | `19e51cc421ba7c94c95f5317f2a3e1d0126f1de833d8acf4f4f0cd1e34263b8a` |
| partial.jsonl | `481fb179a9586e9ce5f99e225464eb86bd125b9df3fa95406a9d7e5ddbd84fae` |
| weighted_transition.npy | `f964ea266a51b5fdf3a0a0dfcfbb5815b1980c1155bb759c82bd4ed20f93052f` |
| derived_binary_transition.npy | `d9e51105df2dfebe0a3997d209a623b34ad4096457140634ba744a435d0ba479` |
| derived_disconnected_fixture.npy | `705afa81b533bc5e349ff5e1f1b5f116fbe5161a9cfca2eeb8a4f92074b9aec6` |

The source freeze passed12 hermetic guards and Ruff; all3,201 prior test nodes and resource owners were retained (3,213 total). Raw arrays, traces, assets and images remain outside Git. The next decision is whether to authorize another separately scoped integration milestone; no navigation or feasibility launch is implied.
