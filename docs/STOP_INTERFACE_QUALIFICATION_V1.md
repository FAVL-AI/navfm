# Pinned stopping interface qualification v1

**SYNTHETIC COMPONENTS ONLY; measured probe NOT RUN before reviewed source
freeze. Navigation, encoder/VPR, controller STOP and feasibility remain BLOCKED.**
Branch `agent/research-three-model-plan`, baseline
`9ea28bdf7adbf19bde70ed5e30a1eb81afbec122`.

The [contract](../configs/eval/stop_interface_qualification_v1.json),
[interfaces](../scripts/pinned_stop_interfaces_v1.py) and
[bounded probe](../scripts/qualify_pinned_stop_interfaces_v1.py) bind immutable
official source commits/file SHA-256 and Git blob identities. Source and both
MIT notices remain external; no upstream code, image or weight is vendored.
The [independent source review](STOPPING_COMPARATOR_FIDELITY_REVIEW_V1.md)
records exact primary sources and their limitations.

## Implemented boundary

The loader authenticates bytes before extracting an explicit class/function
AST allowlist. It executes those definitions with NumPy/stdlib dependencies,
not imports, ROS nodes or a full native program. Method bodies stay unchanged.
PlaceNav database/extractor I/O is replaced by an explicitly synthetic
in-memory descriptor seam; this does not qualify its VPR pipeline.

PlaceNav uses released CLI constants delta 10/window [-1,2), initializes and
matches the SAME first frame, and exposes its actual MAP-equals-goal rule.
Its native code lacks equal-quantile and dot-product clipping guards. The
adapter refuses nonfinite native beliefs; it never inserts a stabilizing floor
or uniform fallback and does not claim equivalence outside the finite domain.

ULVN targets the released ROS `BPL & BASS/bass.py` BPL/BASS definitions,
not the numerically different `ulvn_core` library. It retains weighted
`I+A+A²+A³` transition construction, source clipping/quantile fallback,
entropy-dependent fusion and native planner/localization. Its native observable
is the sticky conjunction of MAP-at-goal AND valid subgoal-at-goal. A None
subgoal preserves stored latch state but suppresses native publication and any
STOP proposal, including after a previously true latch. The released local planner does not
consume that flag, so native actuator STOP is not established. `STOP_proposal`
is explicitly a blocked downstream adaptation, never a controller command.
Native goal localization remains descriptor-based; an identity it cannot
represent is rejected, not hard-assigned to a convenient map node.

Native float32/float64 descriptor dtypes are preserved and query/reference
dtypes must match. Posterior validation permits declared dtype roundoff
(maximum of 1e-12 and eight dtype epsilons per node), without renormalizing;
adapter/oracle state comparison remains exact within each dtype.

Reference identities, 64-hex hashes, normalized descriptors and weighted graph/order
are shared permitted prior information. No live ground truth/depth input is
accepted. Unknown/mismatched/ambiguous goal identity is rejected. Frames require
explicit episode identity, consecutive sequence and fresh .25-s simulation-time
spacing. Reset builds fresh native state; there is no state sharing between
instances. Native rates are PlaceNav 5 Hz and ULVN 30 Hz; common fresh 4-Hz
scheduling is an adaptation, not cadence-invariant equivalence.

The selected NoMaD EMA checkpoint metadata fixes all seeds 0/11/22 from the
prior admitted contract. Each 76,487,854-byte file matches its declared digest
in a single hash-only stream check (0.11535 seconds total). No checkpoint is
deserialized and no encoder, navigator or GPU inference runs. Integrity does
not qualify VPR/NoMaD integration or change prior pilot results.

## Verification and freeze boundary

Twenty-four hermetic controls PASS, covering goal identity, graph/descriptor input
refusals, clock/order/reset identity, finite call budget, source substitution
before execution, native-constant drift and supervisor nonzero/timeout/launch
failure outcomes with actual exit/reaping records. Targeted Ruff PASS. These tests
need no external comparator cache or new historical-archive owner. The exact
new nodes join the ordinary-hermetic population; old nodes/resources stay intact.

The positive native component probe is separate and requires exact clean
reviewed source HEAD plus authenticated external source cache. Fixed synthetic
one-hot/weighted-chain inputs compare wrapper posterior, MAP and confidence
with independent native objects, including first-frame initialization/update;
check reset/isolation, sticky conjunction, None-subgoal, weighted-vs-binary
counterexample, unsupported goals, equal quantiles and invalid zero likelihood.
The probe also independently executes BASS localization/path/subgoal state
and compares initialized beliefs/lambda and both floating dtypes, including
actual duplicate-descriptor goal rejection. No random seed selection, labels,
threshold fitting or recorded pilot outcomes
are used. Its worker cap is 30 wall/CPU seconds, parent cap 35 wall seconds,
192 native match calls, zero GPU
calls and 128 KiB external output. A first failure halts; no automatic retry or
outcome-based adaptation follows.

After independent review, commit/push this source freeze before executing:

```sh
timeout 40s env PYTHONPATH=/home/favl/projects/navfm-research-planning/src /home/favl/navfm-runtime-evidence/pr2-ci-hermetic-20261010-02/venv/bin/python scripts/qualify_pinned_stop_interfaces_v1.py --freeze COMMITTED_REVIEWED_SHA --out /home/favl/navfm-runtime-evidence/stop-interface-v1-synthetic-01/result.json
```

The script refuses dirty/wrong HEAD and existing or in-repository output.
It persists an attempt record before spawning, appends/fsyncs partial events
before assertions, retains terminal worker failures, and records parent exit,
timeout and reaping separately. A missing final result cannot erase an attempt. Raw
probe output remains external; report a measured result only after execution.
The existing 29 prerequisite failures are not reclassified or rerun unchanged.

## Apparatus and study safety

The single bounded CAD metadata check found the known 189,763,420-byte source
present, no STEP in its known source directory and no inspected installed CAD
Exchanger executable/path. Converter/version/license/export remain unavailable.
No geometry contents were read, converter installed or manufacturer contacted.
CAD/motion/contact qualification remains BLOCKED; no simulator runs or actuation
follow. Held-out geometry stays untouched, illumination paused and the 216-task
DEV feasibility/108 passive controls and larger benchmark remain unauthorized.
