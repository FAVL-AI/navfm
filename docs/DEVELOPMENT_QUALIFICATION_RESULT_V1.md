# Development qualification result v1

Compatibility: three PASS, one FAIL. Independent controller probe: FAIL at its fixed 120-second child watchdog, with zero recorded IMU samples. Sensor validity and tracking are NOT ASSESSED. No live navigation, training, illumination, held-out or robot episode ran. Failed attempts are preserved; there were no retries or environmental repairs.

## Exact sources and conditions

Compatibility used a clean detached worktree at 00238cbbf7293e345156819a85c5576200a0fc30. The independent IMU probe used clean 9358263857196652e68aaf342772f0db60dc0cbe after explicit continuation; it does not import a model or consume compatibility outcomes. CI-runner cleanup was verified first: the three guarded directories were absent and proxy/registration units inactive/not-found; the listener retained only a not-found failed status.

Both launchers used /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python and invoked the pinned /home/favl/miniforge3/envs/isaac/bin/python workers. Commands and limits are in DEVELOPMENT_QUALIFICATION_V1.md and IMU_CONTROLLER_QUALIFICATION_V1.md. Compatibility output was /home/favl/navfm-runtime-evidence/development-qualification-v1-compatibility-01; controller output was /home/favl/navfm-runtime-evidence/imu-controller-v1-01. Sources/configurations were unchanged during execution.

## Native compatibility outcomes

| Role | Outcome | Strict checkpoint load | Native finite action shape | Child wall seconds |
|---|---|---|---|---:|
| Released ViNT | PASS | True, CUDA | 1×5×4 | 2.894 |
| Adapted ViNT, seed0 epoch20 | PASS | True, CUDA | 1×5×4 | 2.397 |
| Released GNM | PASS | True, CUDA | 1×5×4 | 2.359 |
| Released NoMaD | FAIL | NOT ESTABLISHED | NOT ESTABLISHED | 1.177 |

The three passing cases used observation shape 1×18×64×85 and goal shape 1×3×64×85, from repeated context copies of one existing development reference image. Their measured runtime was PyTorch 2.7.0+cu128, CUDA 12.8, NVIDIA GeForce RTX 4080 SUPER. Deterministic algorithms, cuDNN benchmarking and cuDNN deterministic flags were all false. These are strict-load/native-output compatibility checks, not representative observations, localization, goal stopping, completion or generalization evidence. No GNM/NoMaD adaptation claim is made.

Pinned checkpoint SHA256 values were: released ViNT 155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f; adapted ViNT c7686983099080649dde0eaf79575149c26239321e23cf96788b3dd25b0d5d7c; GNM 4b03e0255f8a547290d4079f4e7d610ff69987122f17e019bd36684c08b3ee95; NoMaD 70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333. These were admitted input digests; NoMaD's failed process did not reach checkpoint loading.

NoMaD's exact error was `ModuleNotFoundError: No module named 'diffusion_policy'`. Read-only diagnosis found that the worker calls the preserved `_build_nomad` helper directly, omitting its vendored-path setup. The clean frozen checkout and admitted upstream snapshot contain no diffusion_policy package; the authentic package exists under /home/favl/projects/navfm/third_party/diffusion_policy. This is a missing dependency/source-path contract, not demonstrated checkpoint incompatibility. Nothing was installed or added to search paths, and the failed outcome remains unchanged.

## Independent controller attempt

The fixed 120-second watchdog raised TimeoutExpired; the launcher returned exit1 and preserved a FAIL ledger. The bounded runner killed/reaped the worker process group. A targeted process-name check found no remaining qualification worker. No imu_qualification.json or imu_readings.jsonl was produced, so actual simulation-clock advancement, sensor initialization, validity, reading rate and tracking remain unobserved; zero recorded samples does not establish zero physics steps or that sensor initialization never happened.

The log contains seven extension-startup markers, the last recorded being omni.client 1.3.0 at 0.099s, and ten OmniHub launch/reconnect warnings, the last at 2026-10-11T03:34:18Z. No “app ready” or “Simulation App Startup Complete” marker was recorded. These observations bound the available startup evidence; they do not identify the exact blocking phase or establish OmniHub as the sole timeout cause. Cause remains UNKNOWN. No controller threshold or budget was changed. The live-development stage remains blocked.

## External evidence identity

The external inventory /home/favl/navfm-runtime-evidence/pr2-resource-contract-20261010/operator-setup/research-qualification-result-evidence-v1.json lists 12 preserved artifacts and their sizes/digests. Its SHA256 is 9e23a88316934c09f88050d396f30f392773f8acecbee1f8e971d85698f13864. This inventory records current evidence identity, not an earlier independent attestation.

| Artifact | SHA256 |
|---|---|
| compat-vint-release.json | eae1786910d81738556cf0cddf8f7cccd5d61c4ffe7a7333189e206ab4781a78 |
| compat-vint-adapted.json | b846a0e45f0a8ee3e30a95569e4f4956e3eca89f627b73404ce35a49cfe0fac9 |
| compat-gnm-release.json | 9c3c96b2514ad02aa361bc654b483d65a856128d27c319bf152aff693000eadf |
| compat-nomad-release.json | b29191156ab95175346a7f6ac2b19f6fea199d3eafd0b3d8f8f568682b5fbfcc |
| Compatibility ledger.jsonl | 2cfe503f594f06274c5d29593dd8f51637b63ac8af4f1207250d58ced1c29cef |
| IMU ledger.json | 904ec1e1ebab597fdccaff429a9376d37082405519416f91d6f794cc62538e7b |

Prior focused validation remains 32 compatibility guards and 15 controller guards passing, with lint/whitespace checks; 2862 population nodes retain all predecessors. No completed test suite was repeated for this result-only documentation. Next decisions are a separately versioned NoMaD dependency-closure amendment and a narrow startup diagnosis before any revised controller attempt. No unchanged retry or live evaluation is authorized by this report. Raw logs, outputs and weights remain external; only this authored result enters Git.
