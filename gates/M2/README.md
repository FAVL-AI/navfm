# M2 — canonical-environment acceptance package

This archive establishes the **canonical environment**: the instrument every
subsequent gate number is produced by. It is **not** a G0.c readiness marker.
No model metric exists in this directory, no forward pass has been run, and no
pre-registration amendment has yet been filed for G0.c.

The canonical-environment establishment point is **`fb393de`**.

## M2 STATUS block

Verbatim and unedited, as received from the accepted external review. It is the
reviewer's snapshot at review time. Everything that happened afterwards is
recorded *beside* it, in the next section, never inside it.

```text
M2 STATUS: CANONICAL ENVIRONMENT ESTABLISHED

Established:

* canonical Python/GPU environment;
* complete upstream-marked test collection;
* dependency closure;
* ROS/PYTHONPATH contamination detection;
* environment identity includes PYTHONPATH;
* 247 tests passing;
* 26 upstream-marked tests passing.

Not yet established:

* resume identity enforcement;
* evidence-class barriers;
* complete table lineage;
* scheduler lineage separation;
* preregistration-commit enforcement;
* G2 mechanical block;
* G0.c preregistration;
* checkpoint and GO Stanford acquisition;
* baseline evidential classification.
```

The `247 tests passing` line is historical and is preserved exactly as issued.
The later counts are recorded in the annotations below, never by editing the
quote.

## Annotations, beside the block

Where the repository has moved past the snapshot, recorded here with the
discharging commit. The block above is unmodified.

| Block line | What happened since | Commit |
|---|---|---|
| "247 tests passing" | grew to 255, then 267 as the effective-import and population-invariant tests landed. The count in the block was correct when written. | `0c4dfd0`, `c9b1ff5` |
| "checkpoint and GO Stanford acquisition" *(listed as not yet established)* | **discharged.** All three checkpoints and the GO Stanford archive are downloaded and hash-verified; byte sizes match the documented values exactly. Acquisition only, under the sequencing ruling — no forward pass, no metric. | `0c4dfd0` |
| "environment identity includes PYTHONPATH" | extended beyond PYTHONPATH to the full effective-import surface: both prefixes, PYTHONHOME, user-site enablement, and the normalised resolved locations of seven load-bearing modules. | `0c4dfd0` |
| "complete upstream-marked test collection" | now *enforced* rather than observed: the three-condition population invariant is asserted from a machine-readable report against a pinned node-id set. | `c9b1ff5` |

Everything else in the "Not yet established" list remains not established, and
this package makes no claim otherwise.

## Acquired artefacts (acquisition/preflight — not evaluation)

| Artefact | Bytes | Expected | SHA-256 |
|---|---|---|---|
| `checkpoints/vint.pth` | 430,167,114 | exact match | `155fd72de2e98ae0e2fef9404072e1aefa79dae5f7f2411d4bcf7e384b83aa1f` |
| `checkpoints/gnm.pth` | 104,806,886 | exact match | `4b03e0255f8a547290d4079f4e7d610ff69987122f17e019bd36684c08b3ee95` |
| `checkpoints/nomad.pth` | 76,473,631 | exact match | `70f79b8262527e20e56ced64a3e3d7ef91855bc9e7c3fa348d78edcb83c6a333` |
| `~/navfm-data/go_stanford/go_stanford.zip` | 781,698,396 | 781.7 MB | `1fe1411945abd9cd0f335e845fe40d3477aac641aeb5669c961ec9debc4fb8a4` |

The GO Stanford archive was fetched fresh into a navfm-owned path. The
pre-existing copy under `~/vint_dataset/` (owned by an unrelated project, dated
2024-09-15) hashes **identically**, which is recorded as a provenance fact — the
Hugging Face artefact has been stable for ~2 years — and not as a licence to
depend on that copy. Nothing in this repository reads it.

## Contents

| File | What it is |
|---|---|
| `fingerprint.txt` | page one: the execution fingerprint, human-readable |
| `fingerprint.json` | the same, machine-readable, including `sys.path`, raw module `__file__`s, and the user-site path |
| `environment_identity` | `4408691cfeb89860fdf42d3db9efed012650e72dfa8c37fb917131974cbde625` (in both files above) |
| `requirements.lock` | resolved dependency closure, 105 distributions |
| `installer_provenance.txt` | uv version, uv binary path, the managed interpreter it fetched, and `pyvenv.cfg` |
| `package_resolution.log` | the full build transcript, every package resolution and download |
| `gpu_visibility.txt` | `nvidia-smi` and torch's own view of the device |
| `test_population.json` | machine-readable population: every node id, marker, outcome, skip reason |
| `test_population_check.txt` | the three-condition invariant, enforced against the pinned manifest |

## Resolved identity

```
Python              3.11.15   (uv-managed CPython, not a system interpreter)
torch               2.11.0+cu128
torchvision         0.26.0+cu128
CUDA (torch)        12.8
GPU                 NVIDIA GeForce RTX 4080 SUPER, driver 580.159.03, cc 8.9
OS                  Linux-6.8.0-124-generic-x86_64-with-glibc2.35
PYTHONPATH          (unset — see F-M2-2)
repository commit   c9b1ff5
upstream commit     dca79815b704e5aa9c6bdc3082351f9e3b2848c2
```

All seven load-bearing modules — torch, torchvision, navfm,
`vint_train.training.train_utils`, cv2, matplotlib, diffusers — resolve under
`<prefix>` or `<repo>`. None resolves under `/opt/ros`, which is the check that
F-M2-2 exists to make.

## A note on the worktree line in the fingerprint

`fingerprint.txt` declares `modified (1): gates/M2/` rather than `clean`. That
is correct and deliberate: the fingerprint was emitted while this directory was
being written, and `gates/M2/` is the only modification. A fingerprint that
reported `clean` while writing itself would be false, and the helper is built to
declare rather than to flatter. Everything outside `gates/M2/` was clean at
`c9b1ff5`.

## Defects found while establishing this environment

Both were found *because* the environment was built and verified rather than
assumed, and both are recorded in full under `gates/failures/`.

* [F-M2-1](../failures/F-M2-1.md) — the documented prerequisites could not
  import `train_utils`, so the 26-test compatibility proof degraded to 9 passed
  / 6 skipped / 11 uncollected while the suite exited 0 reporting "228 passed".
  An evidence-completeness failure caused by silent test-population
  contraction. Now mechanically impossible: `scripts/check_test_population.py`.
* [F-M2-2](../failures/F-M2-2.md) — a sourced ROS 2 Humble tree exported a
  Python 3.10 `PYTHONPATH` that the 3.11 venv inherited and prepended. The
  environment identity would have reported the contaminated and clean shells as
  **the same instrument**, because no field it then hashed moves when
  `PYTHONPATH` changes. Fixed in the identity, not in the runbook.
