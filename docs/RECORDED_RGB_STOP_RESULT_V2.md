# Recorded RGB encoder/reference qualification result v2

**PASS for recorded encoder/reference and mock STOP components only.**
The single authorised attempt used clean freeze
`b466f026286e04e350dfc89bb743ed3c550ce69d`. Parent exit0, no timeout,
child reaped, and worker/source status verified. The earlier preflight refusal
and failed source-loading attempt remain separately recorded without alteration.

Both authentic released encoders completed the fixed32 forwards: eight
references and eight queries each. Full checkpoint state coverage, decoded RGB
agreement, native preprocessing/normalization and descriptor shape/finite/unit
checks passed. No fitting, frame reselection or encoder retry occurred.

Each comparator processed eight cached queries in two fresh-state replays:
16 belief updates per comparator,32 total; reset parity passed for both. This
qualifies cached-descriptor state isolation, not repeat-encoding determinism.
Native ULVN arrival publication remains distinct from the mock STOP conversion.
The mock latch/cancel/reset guards were covered by18 focused hermetic tests;
no physical controller or actuator executed.

GPU-reserved worker phase:3.223420s; total worker wall:3.304621s;
peak allocated GPU memory:966,652,928 bytes. Device: NVIDIA GeForce RTX4080 SUPER.
Runtime: Python3.11.15, torch2.7.0+cu128, torchvision0.22.0+cu128,
OpenCV4.10.0, Pillow11.3.0, safetensors0.7.0, NumPy1.26.4, CUDA build12.8.
Both the120-second whole-worker and300-second parent limits were respected.

The fixed reference-order chain is an explicit graph adaptation. Native RAVEL
graph construction remains BLOCKED; no threshold calibration was performed.
This replay does not qualify navigation efficacy, actual acquisition cadence,
physical STOP, contact observability or a loaded motion plant. No simulator,
collection, calibration or held-out test access occurred.

Raw evidence stays external at
`/home/favl/navfm-runtime-evidence/recorded-rgb-stop-v2-01`:
626981 bytes, below the16MiB output acceptance bound.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| attempt.json | 205 | `0b1ef75b06fe627b638a67a65b749c9b97d0327ce72807e1941e7ce5a21452af` |
| descriptors.npz | 607992 | `e93c50d1a952882cc2444d9d48df536db7876aed9025d6e67c3e97c6389ae16a` |
| parent_status.json | 176 | `8b642391f03b93a562d8e0e5cb3cc728bcd0e8518805e8175a5ee8c948919aa8` |
| partial.jsonl | 17608 | `5e9f10e2a534b77237156e6674922c83eccb1adb17b784ae9371b4b196ecea9f` |
| result.json | 869 | `e78b4bd84173ca90da76d13c02d3925d94ec64f177341b28b0e4629d165ac293` |
| worker.log | 52 | `ade03486c308815a295708fb6069bca95212dceb216014bfdd0ada267119308c` |
| worker_status.json | 79 | `7b483c79ec1827314ed5eab2648bb9d6b2cbfdddfc5bd264d29025afdb30589f` |

Next decision: separately review native graph qualification and controller/motion
prerequisites before any navigation study; this result grants no runtime study
or resource-budget approval.
