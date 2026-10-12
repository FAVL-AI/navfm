# ViNT provenance rejection diagnostic v1

Status: REVIEWED / CPU import-only rejection identified / synthetic GPU replay NOT RUN. Baseline `00e46be6c830c9d6aec39d197949b3b541a72fe0`. Original qualification FAIL remains immutable. No acceptance rule, trust exception, model, checkpoint, synthetic input, output criterion or 150-second limit changes.

The versioned worker binds a diagnostic verifier in place of the original native verifier. It walks the same loaded-file records and calls the same generated authentication function. Before propagating its first rejection it atomically preserves module name, resolved origin, actual SHA, manifest expected SHA or null, and UNLISTED_ORIGIN versus FILE_HASH_MISMATCH. Generated generator/export identity is UNKNOWN when not authenticated; the generic error is never proof of generation. A diagnostic write failure also rejects admission. No namespace or temporary-path exemption is introduced.

The parent preserves actual child return code, observed timeout, kill-request status and reap outcome even on worker failure. Successful Popen immediately enters unconditional cleanup ownership; signal errors cannot bypass wait. Unknown unlaunched/unobserved outcomes remain null. No signal request is described as proven termination. Existing fail-closed 150-second finalization and complete-marker rules are reused.

Seven focused CPU controls cover both rejection categories/atomic evidence, write failure, actual failed-child exit, timeout/reaping, and cleanup signal-error reaping. They import no models or checkpoint contents. The prior four-row failure did not retain the rejected identity, so static source alone cannot identify its actual rejected object. One source-frozen replay of the unchanged two-case/four-checkpoint synthetic procedure is conditionally authorized to obtain that identity; no dataset/pilot scoring, training, simulator or CAD work is included. A future acceptance correction is outside this diagnostic.

```sh
PYTHONPATH=src NAVFM_UPSTREAM=/home/favl/navfm-runtime-evidence/option1-expanded-admitted-20261007-01/upstream /home/favl/navfm-training-evidence/native-dependency-closure-v2/venv/bin/python scripts/run_vint_provenance_diagnostic_v1.py --freeze FULL_REVIEWED_COMMIT --out /home/favl/navfm-training-evidence/vint-provenance-diagnostic-v1-01
```

One fresh external directory/registry, at most one 150-second process (145 child plus five cleanup), no retry. Raw evidence remains external; publication is compact identity/category findings only. The closure preserves all prior records and adds only the three diagnostic sources. All old checkpoints/freezes/failures and GNM/NoMaD outcomes remain unchanged.

## CPU import-only finding

Exact worker interpreter with CUDA hidden imported native ViNT, native image helpers and checkpoint loader without constructing a model or reading weights. First two harness attempts failed on `<stdin>` file hashing (the second retained its `__mp_main__` alias); both are preserved. The corrected mapping excludes only aliases of the same transient harness object, not any native module and not a production acceptance rule. It reproduced UNLISTED_ORIGIN for `vint_train.models.vint.vint`, resolved to pinned upstream `train/vint_train/models/vint/vint.py`, actual SHA `1af3afb275f6f52d643df792cf39d8bb77e0fe00f06d7ceb9c152a408554ad37`, manifest expected null. That SHA exactly matches the existing frozen upstream_files record. This authentic persistent native source is absent from the separate native manifest; no generation is established.

Evidence is external at `vint-provenance-cpu-import-v1-01`, `-02`, `-03` under the training-evidence root. These diagnostics used reviewed-in-progress source rather than a committed runtime freeze. No GPU replay is needed or performed. The diagnostic now preserves the first rejected record across finalization and rejects an output/rejection-path mismatch before launch. Seven focused controls PASS, including those two corrections. The narrowly supported next proposal is adding this exact authenticated native source to a future versioned manifest, retaining all acceptance rules; that compatibility correction is not implemented here.

| CPU evidence | SHA256 |
|---|---|
| CPU 01 report.json | `20b4e0fdbc1d98367d3b20445d7fb722ea99bcd745ee648aa88cec0374818b43` |
| CPU 02 report.json | `32447f7a3e5beb9ae075bb1331c22571063c7bf8c3bf8350bf26bc63dfb7db01` |
| CPU 03 report.json | `2288692df518dbdd05d46a634c0fdfcf1600a3f5e10cdc7c9d0b3172794794d2` |
| CPU 03 rejection.json | `5a198bd37abb37d36dcea4fc62a3681568ad1a607e7880ae35ee5bc879d76e02` |
