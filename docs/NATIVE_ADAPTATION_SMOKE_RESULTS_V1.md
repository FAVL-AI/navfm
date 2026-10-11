# Native adaptation smoke results v1

Source freeze: `d921602166e6bb2b8257367c06b098ae4d25a3f1`. The committed two-process protocol remains unchanged. GNM **FAIL**; NoMaD **NOTRUN** because shared import integrity was not established. No training adaptation or checkpoint compatibility conclusion follows from this attempt.

The GNM worker failed while importing the admitted native dataset module: `ModuleNotFoundError: No module named 'lmdb'` at `train/vint_train/data/vint_dataset.py:8`. This preceded fixed-batch construction, model construction, released checkpoint loading and optimizer updates. The child exited normally and was reaped; the launcher preserved report, provenance and process log. Source/input/dependency-file preflight and postflight returned, but complete loaded-source attestation did not complete: the ledger correctly records shared integrity FAIL. No retry or installation occurred.

The exact configured interpreter is `/home/favl/miniforge3/envs/isaac/bin/python` (Python 3.11.15). Targeted import-only diagnosis found neither an `lmdb` import spec nor installed distribution. The existing installed dependency manifest contains zero lmdb file entries. The admitted upstream `train/train_environment.yml:27` explicitly requires `lmdb`, without a version pin. Thus this is an incomplete native-training dependency closure, not evidence that the released GNM checkpoint failed. The fixed-batch subclass avoids native LMDB cache creation, but importing its authentic parent still requires that package. No substitute module or ambient-path workaround was used.

| External evidence | SHA256 |
|---|---|
| `ledger.json` | `7b041438cb20cdceecbd98640af54ff0dcc01bde6f789d9a52116b451fcd35e2` |
| `gnm/report.json` | `40d10e9f32e97286c148adc3669255378e28468a95cbc3f9bdf5089bb752ada3` |
| `gnm/provenance.json` | `814cc5393358509526b89972248e9e494a835bbb09e7a5337108c213eb815829` |
| `gnm/process.log` | `e3548c9a63148506244bf6bbad9641a2b49c152af19d6acc50361a839dbc9a5d` |

Evidence root: `/home/favl/navfm-training-evidence/native-adaptation-smoke-v1-01`. All three consumed artifact hashes were independently recomputed after exit. Outputs and model weights remain external; no runtime artifacts are committed.

Validation before freeze: 16 focused CPU tests passed, including actual optimizer/scheduler/EMA/all-available-RNG restoration and next-draw identity, development nonmutation, split leakage rejection, normalization roundtrip and independent staging. CUDA restoration was covered by implementation and reserved runtime readbacks; the CPU test run hid CUDA. Ruff and diff checks passed. The runtime did not reach six-update, changed-parameter, finite-gradient, strict-reload or deployment-EMA checks; those remain NOT ASSESSED.

The historical ViNT reconciliation in [the source protocol](NATIVE_ADAPTATION_SMOKE_V1.md) is separate: three preserved reports contain 20 epochs of 236 updates each (4720), with 15/15 saved learning-curve checkpoint hashes and 34/34 source hashes per seed matched. Stale top-level six-step/default metadata does not override those epoch records. This supports historical training-engineering records, not independent reproduction or held-out navigation performance.

Next decision: prepare a versioned, explicitly pinned LMDB native-training dependency closure in a declared environment, with authentic package identity, upstream requirement provenance and import-only validation before another training attempt. Preserve this failure and the NoMaD NOTRUN disposition; no new attempt has been made.
