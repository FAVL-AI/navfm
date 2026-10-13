# Saved graph to native ULVN component replay

This qualification targets the already admitted fixed-mode pruned weighted graph, eight cached reference descriptors and eight cached query descriptors. The versioned configuration binds the graph result, parent exit record, complete 28-pair ledger, node map, graph configuration, canonical transport policy, RGB encoder proof/cache and authenticated native source. No neural model, encoder, matcher, fitting, graph construction, simulation or actuator runs are authorized.

Before observing outputs, goal frame28/node7 and queries1,5,…,29 are fixed. Two fresh episodes perform16 native BPL updates, including explicit initialize then match of the same first query. One separately saved all-zero disconnected fixture performs one update; two additional BPL objects expose weighted versus binary transition matrices without match updates. Thus five BPL and three BASS instances are constructed. Production graph weights/order are preserved. Native BPL uses its float64 transition arithmetic; BASS casts references/graph to float32 and uses the released unweighted route cost. The cached goal retains its prior native query/goal normalization seam and BASS adds only its own native normalization.

Each update records the full posterior, MAP/confidence, inferred goal/start, path, subgoal, replanning, sticky arrival state, publication and mock motion state externally. Before sticky arrival, native publication is absent (`null`); a missing subgoal also suppresses publication even after the latch. Only a valid-subgoal sticky arrival produces `true`. The mock STOP cancels queued/current motion, latches and blocks resumed motion until reset; it establishes no physical or native actuator performance. Virtual timestamps i/4 describe adapter order, not camera capture or ROS cadence.

The derived disconnected/binary controls never replace the production graph. Unreachable-goal, stale-episode, weighted/binary transition and cancellation/reset controls must pass; unsuccessful controls fail the attempt without alternative frame/goal selection. Hermetic tests reject invalid maps, dtype/weights/order and altered fixed selection/budgets before native decisions.

The CPU-only worker uses the existing Python socket/DNS audit refusal guard, not an OS network sandbox. The worker has30 seconds; parent envelope60 seconds. There are zero neural/GPU calls. Raw output acceptance is capped at16MiB; full traces and derived arrays remain external. Run only after clean reviewed freeze:

```sh
timeout 60s env CUDA_VISIBLE_DEVICES='' /home/favl/navfm-source-evidence/ravel-fixed-assets-20261012-01/venv/bin/python scripts/replay_saved_graph_ulvn_v1.py --freeze <exact-sha> --out /home/favl/navfm-runtime-evidence/graph-comparator-v1-01/result.json
```

The result records observed True-publication and mock STOP-command counts. If no True publication occurs, the production native-to-STOP path is explicitly unexercised; the separate synthetic mock cancellation control is not substituted as evidence. The dispatch command enforces the60-second outer envelope; the parent supervises the30-second worker. One attempt only; retain partial/error/exit evidence without retry. A PASS qualifies this saved fixed-mode graph/native component/mock integration, not adaptive RAVEL, localization accuracy, goal completion, navigation or physical stopping.
