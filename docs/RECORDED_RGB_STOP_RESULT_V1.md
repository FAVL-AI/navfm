# Recorded RGB qualification result v1

**FAIL before encoder inference.** The first actual worker attempt used freeze
`968b9d3aaffef71f81ec71e79fa28c3af0465e98`. Parent exit code was1,
timeout was false, and the child was reaped. Worker status records
`NameError: name 'VPRModelBase' is not defined` during authenticated source
setup, before the RGB loop. This is an implementation source-loading defect.

Zero encoder forwards completed; no descriptors or belief/mock replay results
were produced. The proposed32-forward qualification remains unachieved.
No automatic retry, checkpoint substitution, data reselection or fitting occurred.
Native graph generation, navigation and physical STOP remain BLOCKED.

The earlier clean-tree preflight refusal is recorded separately in
[the preflight record](RECORDED_RGB_STOP_PREFLIGHT_V1.md). It is not counted as
an encoder execution or relabeled as a pass.

Durable evidence stays outside Git at
`/home/favl/navfm-runtime-evidence/recorded-rgb-stop-v1-01`.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| attempt.json | 205 | `373ac8387f8c1358eb8b30abd6c973a26175c1286711119d338dd24a21e45196` |
| parent_status.json | 177 | `9a7d95c83c8bc5f3097692697a71ab92b86a809c9fbc2893a2e312d40bdb5338` |
| worker.log | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| worker_status.json | 162 | `bd670e5dad6d888cc6b8a96ad4bd702e56b9017d76fa65bfa5948603de5b2026` |

Read-only diagnosis identifies the omitted native base class: pinned ULVN
`BPL & BASS/bass.py` defines `VPRModelBase` at line78 and
`MyVPR(VPRModelBase)` at line82. The extraction allowlist selected MyVPR,
MegaLocEmbeddings and build_transform but omitted VPRModelBase and its NumPy
annotation dependency. The underlying source bytes remain authenticated.

Next decision: in a new reviewed version, include the native base class and
explicit annotation dependencies, then exercise the complete source-definition
construction on CPU before any CUDA allocation or checkpoint/model execution.
No repair or second runtime attempt was performed in this milestone.
