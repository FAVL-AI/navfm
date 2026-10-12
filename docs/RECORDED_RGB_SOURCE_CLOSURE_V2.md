# Recorded RGB source-closure repair v2

The previous failed encoder attempt remains recorded without alteration. Its
native ULVN MyVPR extraction omitted the authentic VPRModelBase definition.
The production path now uses load_ulvn_rgb_definitions_v2, also called by the
CPU qualification command. It admits the unchanged pinned base, MyVPR,
MegaLocEmbeddings and build_transform plus a strict explicit dependency namespace.
No source, checkpoint, input frame, graph, threshold or normalization pin changes.

CPU qualification owner: the explicit source-closure command, requiring the
external authenticated bass.py and existing native dependency environment.
It is separate from hermetic pytest and historical archive ownership:

```sh
CUDA_VISIBLE_DEVICES='' timeout 30s /home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/qualify_rgb_source_closure_v2.py
```

The actual shared production loader passed native inheritance and resolved
NumPy/Pillow/Torch annotations, eight missing-global refusals, genuine missing
base-class execution refusal and altered-source-byte refusal. CUDA was hidden;
network access was refused by the worker-local Python audit guard. There were
zero model constructions and zero encoder forwards. CPU wall time was1.073s.
External result SHA256 `706b602cd9da22c88c3305d42bf9397611797b48420456d5141425a337e28269` at
`/home/favl/navfm-runtime-evidence/rgb-source-closure-v2-01/result.json`.

Eighteen focused hermetic tests and Ruff passed. An initial ambient-interpreter
pytest command failed during unrelated ROS-plugin collection/source imports;
the declared environment with plugin autoload disabled and local src binding
passed. The two new ordinary nodes preserve all3165 previous nodes and resource
owners, producing3167 expected nodes. This does not claim the full suite passed.

After reviewed clean freeze, one separately authorised replay uses the unchanged
32-forward/120-second worker/300-second parent contract and a fresh external
`recorded-rgb-stop-v2-01` output directory. No runtime replay occurred during
this repair. Native graph generation and physical STOP remain blocked.
