# Targeted qualification repairs v2

REVIEWED SOURCE FREEZE, NOT RUN. Nine focused pure tests passed; static review corrections are resolved. Preserves original 00238cb compatibility outcomes and 9358263 IMU timeout without reclassification. No training, upgrade, other-model repetition or live navigation. Confirm CI-cleanup guards again before launch. Two independently gated processes only: IMU first, 120 seconds/1200 unchanged ticks; then only NoMaD 150 seconds under separate explicit continuation if the IMU contract fails. STOP after each outcome, no retry.

## NoMaD dependency closure

Authentic diffusion_policy source is /home/favl/projects/navfm/third_party/diffusion_policy, clean Git HEAD 5ba07ac6661db573af695b419a7947ecb704690f, origin https://github.com/real-stanford/diffusion_policy.git. ConditionalUnet1D and its two local diffusion components match actual GitHEAD blobs; their digests are pinned in configs/eval/nomad_compatibility_v2.json. This namespace package has no initializer files. A closed import finder admits exactly those three source files and three namespace directories, rejects preloaded/undeclared diffusion modules, and compiles hash-verified source without trusting bytecode caches. It adds no global dependency path or ambient PYTHONPATH.

Existing torch2.7.0+cu128, torchvision0.22.0+cu128, einops0.8.2, diffusers0.29.2 and efficientnet-pytorch0.7.1 source/extension files are snapshotted in an external 2757-file hash manifest; its digest is pinned, all bytes checked before/after, and versions checked before import. Actual loaded module origins and hashes are checked against that manifest before and after the native check, including failure paths; the ledger binds the provenance report digest. Source-free runtime-generated torch.ops/torch.classes are explicitly recorded separately. Embedded torch._C descendants require exact nested object identity under the authenticated torch._C binary; its source and digest are recorded. No package is installed or upgraded. This describes selected native dependency packages, not universal operating-system/native-driver reproducibility. Native upstream source, goal image and original NoMaD checkpoint remain pinned. Before model construction the worker executes an actual import-resolution check and writes its source origins externally. The original native model/strict-load/geometry/one-sample10-step diffusion check is reused unchanged. No download/training operation is requested by the worker.

## IMU lifecycle and one-factor launch amendment

Existing hospital-runtime-smoke-20261007-09/runtime_manifest.json records PASS, AFTER_WARMUP and OMNICLIENT_HUB_MODE=disabled; its SHA256 ecbb93599c808aaa77a0b687367bfe757a9d5de0b1a120b3a8c9af5974ae3bf3 is pinned. This different successful smoke is a launch precedent, not proof that Hub alone caused the previous timeout. The amended launcher sets exactly this environment variable. Timeout, physics ticks, startup settling, commands, controller/sensor implementation, gains, stop behavior and tracking thresholds remain unchanged.

A new wrapper instruments the unchanged probe, appending/flushing/fsyncing lifecycle.jsonl around SimulationApp creation, stage creation, sensor initialization and first requested/successful reading. It records sequence, wall/monotonic clocks, exact Hub-mode readback, sensor metadata and simulation/sensor clocks; failures record their class. Unknown phase/cause remains UNKNOWN, and missing samples cannot qualify tracking. Instrumentation may affect wall timing and is disclosed; it does not add physics steps or warmup. Raw records and all failures remain external.

## Freeze and commands

After bounded executable review and a named clean source/config commit, each command requires a new external output. No edits while running. IMU commands are the original ten-second schedule; no autonomous navigation entry is connected.

```bash
/home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/run_imu_controller_v2.py --freeze "$(git rev-parse HEAD)" --out /home/favl/navfm-runtime-evidence/imu-controller-v2-01
/home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/run_nomad_compatibility_v2.py --freeze "$(git rev-parse HEAD)" --out /home/favl/navfm-runtime-evidence/nomad-compatibility-v2-01
```

The dependency manifest is /home/favl/navfm-runtime-evidence/pr2-resource-contract-20261010/operator-setup/nomad-installed-dependency-manifest-v2.json, SHA256 f2f010e75e547a4f5eb32a6b601a7fa4061eb8986f03fec27c72f8d67aba1eeb. Pure tests cover source drift, undeclared/preloaded namespaces, ambient module-origin rejection, fsync/worker-entry/import/phase order and preserved fixed physics boundaries. Neither repaired runtime outcome is established yet.
