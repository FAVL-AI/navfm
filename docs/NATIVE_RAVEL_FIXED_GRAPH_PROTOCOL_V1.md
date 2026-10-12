# Native RAVEL fixed-mode graph qualification v1

Branch `agent/research-three-model-plan`; baseline
`a7f11e902ac6b93af6c94434607c8464f87dae18`. This milestone targets qualification of a
nondefault native fixed-mode graph on eight already admitted DEV reference
images. It does not reproduce the paper's adaptive graph calibration or default
HNSW index. No KMeans, threshold fitting, global encoder repeat, new collection,
simulator, navigation or actuator execution is authorised.

The exact [source-bound adapter](../scripts/ravel_fixed_graph_v1.py) and
[manifest](../configs/eval/ravel_fixed_graph_v1.json) invoke authenticated native
build_index.main, build_matrix.main/analyzer.run_parameter_analysis and
prune_topomap_nx.main. The independent [source review](NATIVE_RAVEL_GRAPH_FIDELITY_REVIEW_V1.md)
describes fidelity boundaries. Sources match immutable ULVN commit
`e2f47fe3e2757a1ebdc041f4364dddd26a19f9f5` Git blobs, verified against the
[official repository](https://github.com/hren20/ulvn/tree/e2f47fe3e2757a1ebdc041f4364dddd26a19f9f5/RAVEL/scripts).
No upstream source is vendored; its notices stay external.

## Native fixed mode and fixed inputs

The native analyzer has a fitting-free num_clusters<=1 branch after matcher
construction. Prospectively choose num_clusters1, giving native tau0/radius2;
choose native flat/L2 instead of HNSW before any graph output. Radius2 is a
squared-L2 strict range boundary, not all-pairs for unit vectors (range0–4).
Binary conversion and RANSAC disabling are false, threads1, native pruning
retains maximum spanning forest plus nonforest weights strictly greater than300.
These are declared fixed native modes, not outcome-selected parameter changes.
The full adaptive/default pipeline remains unqualified.

Use exactly the eight authenticated reference frames0,4,8,12,16,20,24,28 from
prospective_v1_layout0_route0, unchanged from the successful recorded RGB replay.
Reuse its first eight MegaLoc descriptor rows and bind the prior result/freeze,
array archive SHA and admission/finalization transaction. No global encoder runs.
Explicit numeric node order is shared with the reference interface; it is an
ordering adaptation relative to the mapping image-discovery lexicographic default.
Native index inputs remain float32; the native analyzer's additional normalization
of query features remains unchanged. Raw reference hash/path-to-row mapping is
written externally and no image can be silently substituted or dropped.

## Source/dependency closure and native matching

Six packages were added only to an external isolated overlay: faiss-cpu1.8.0.post1,
scikit-learn1.5.2, kornia0.7.3, kornia_rs0.1.9, joblib1.4.2, threadpoolctl3.5.0.
Existing Torch2.7.0+cu128, NumPy1.26.4 and SciPy1.15.3 were left unchanged.
The shared production loader imports the actual authenticated native modules.
Its narrow package export exposes native LightGlue/SuperPoint/utils without
importing unused detector families; this is an explicit import-closure adaptation.

Official [LightGlue v0.1_arxiv assets](https://github.com/cvg/LightGlue/releases/tag/v0.1_arxiv)
were retrieved once under the600-second CPU-only/4GiB external preparation bound:
SuperPoint5,206,086 bytes, SHA
`52b6708629640ca883673b5d5c097c4ddad37d8048b33f09c8ca0d69db12c40e`;
SuperPoint-LightGlue47,500,279 bytes, SHA
`6ff7040d0a497fc6639337946d7538dae07428c18f77a067a0b5a960e7cc551a`.
Official API digests were null: these are observed first-retrieval hashes,
not independently publisher-certified checksums. Acquisition evidence/bytes
stay at `/home/favl/navfm-source-evidence/ravel-fixed-assets-20261012-01`.

Only the native matcher modules' local Torch download transport is redirected
to these verified bytes; no ambient Torch monkeypatch or implicit download.
SuperPoint strict loading and LightGlue's native legacy key remap/strict=False
loading remain unchanged. Final missing trainable or unexpected state fails;
missing buffers are recorded. Source-native SuperPoint resize1024, detector
settings, LightGlue thresholds and RANSAC3px/.999 are retained. Indoor/outdoor
labels select the same native superpoint_lightglue release at this source pin.

Observation wrappers record candidate distances/order and every attempted pair,
model forward and outcome. Raised decode, model, FAISS or RANSAC errors remain
technical failures despite native broad catches returning0. A successful RANSAC
call yielding no mask/inliers remains a legitimate zero count, not a failure.
A per-call trace observes exception events only in the authenticated unwrapped
native counter code, covering swallowed preprocessing and result-indexing failures
without altering its returned count. The actual native CPU control confirms a
swallowed preprocessing exception still returns0 while being marked technical
failure. No native numeric rule is replaced. Store all28 candidate/exclusion/rejection
statuses, weighted adjacency, pruned adjacency and node map externally.

## CPU verification and one frozen runtime boundary

The actual shared production loader passed with CUDA hidden and Python network
refused. Missing-kornia and altered-source controls refused; the actual native
flat index excluded squared-distance2/4 while admitting smaller distances; native
pruning removed a redundant300 edge, retained301, and preserved an isolated node.
These synthetic component checks do not qualify a graph from RGB.
There were zero matcher constructions and zero encoder/matching forwards.
Final CPU wall1.824s; result SHA `cb5f3536d377b8cde972df321cc2ee3e4b284e6d945cfd68923cc1ebb203735a` at
`/home/favl/navfm-runtime-evidence/ravel-fixed-cpu-closure-v1-04/result.json`;
its synthetic matrices/index/node paths and rejection evidence remain external.
Initial CPU source closure exposed a missing inherited Torch site path; the
isolated overlay binding was corrected before model construction. No asset fetch
was repeated. Nine hermetic guards/Ruff pass; all3167 old nodes and owners remain,
3176 expected nodes total. The separate external CPU qualification has explicit
command ownership, not immutable archive ownership.

```sh
CUDA_VISIBLE_DEVICES='' timeout 30s /home/favl/navfm-source-evidence/ravel-fixed-assets-20261012-01/venv/bin/python scripts/check_ravel_source_closure_v1.py EXTERNAL_RESULT.json
```

After source review and clean freeze, exactly one measured graph attempt may
process these8 nodes and at most28 native unordered candidate pairs, at most56
SuperPoint and28 LightGlue forwards, zero global encoder forwards. The whole
worker is killed/reaped at180s (a conservative GPU-reserved ceiling); total parent
wall is bounded360s by its outer launcher. Raw output16MiB is an acceptance bound,
not a filesystem quota. No retry, parameter change or frame reselection follows a
failure. Attempt/partial/worker/parent status survive errors and timeout.
Fresh external destination: `/home/favl/navfm-runtime-evidence/ravel-fixed-graph-v1-01`.
This is not authorisation for navigation or physical STOP.
