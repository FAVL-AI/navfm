#!/usr/bin/env bash
# M1 definition-of-done: the runs-to-tables path, end to end, on CPU.
#
# Reproduces every log in this directory from a clean checkout. Needs the
# reference clone (NAVFM_UPSTREAM or third_party/visualnav-transformer) and a
# CPU-only PyTorch; no GPU, no vint.pth, no downloaded corpus. It therefore
# proves the *plumbing* and nothing else -- the model trains on synthetic noise
# from a random initialisation, and every artefact it writes says so.
#
#   bash gates/M1/reproduce.sh [workdir]
#
# The real numbers arrive at gate G0.c in Session 2 (docs/WORKFLOW.md Phase 0),
# when this same command runs against vint.pth and GO Stanford.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="${1:-${TMPDIR:-/tmp}/navfm-m1}"
PY="${PYTHON:-python}"
export NAVFM_UPSTREAM="${NAVFM_UPSTREAM:-$REPO/third_party/visualnav-transformer}"
export MPLBACKEND=Agg WANDB_MODE=disabled
MARKER=".navfm-m1-workdir"

# --- preflight, because a gate that fails halfway is worse than one that
# --- refuses to start. Each check names the fix rather than the symptom.

if ! "$PY" -c "import navfm" 2>/dev/null; then
    cat >&2 <<MSG
$PY cannot import navfm.

This script does not guess an interpreter: picking the wrong environment
silently would produce numbers from the wrong torch. Point PYTHON at one that
has this package installed, e.g.

  PYTHON=~/.venv-train/bin/python bash gates/M1/reproduce.sh

or install it into the current one:

  $PY -m pip install -e "$REPO" lmdb
MSG
    exit 1
fi

if ! "$PY" -c "import navfm.upstream as u; u.upstream_root()" 2>/dev/null; then
    echo "reference clone not found. Set NAVFM_UPSTREAM, or:" >&2
    echo "  git clone https://github.com/robodhruv/visualnav-transformer.git \\" >&2
    echo "      $REPO/third_party/visualnav-transformer" >&2
    exit 1
fi

# The workdir is deleted, so refuse any path that is not either absent or a
# previous run of this script. `bash gates/M1/reproduce.sh ~/projects` must not
# be a way to lose ~/projects.
if [ -e "$WORK" ] && [ ! -e "$WORK/$MARKER" ]; then
    echo "refusing to delete $WORK: it exists and was not created by this script." >&2
    echo "Pass a path that does not exist yet, or remove it yourself first." >&2
    exit 1
fi

rm -rf "$WORK"
mkdir -p "$WORK"
touch "$WORK/$MARKER"
cd "$WORK"
echo "workdir: $WORK"
echo "python : $("$PY" -V 2>&1), torch $("$PY" -c 'import torch;print(torch.__version__)')"
echo "upstream: $(git -C "$NAVFM_UPSTREAM" rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo

echo "### 1. synthetic GNM-format corpus, written through navfm.writer"
"$PY" "$REPO/scripts/make_synthetic_dataset.py" "$WORK/data/recon" --trajectories 6 --length 60

echo
echo "### 2. deterministic scene-grouped split"
"$PY" -m navfm.splits "$WORK/data/recon" --name recon --out "$WORK/splits" --group-by scene

echo
echo "### 3. validator -- the format claim, on our own output"
"$PY" -m navfm.validate "$WORK/data/recon" --model vint --decode-images -v

echo
echo "### 4. offline eval, random init (plumbing only, NOT a result)"
"$PY" -m navfm.eval.offline --model vint --dataset recon --split test --batch-size 32 \
    --data-folder "$WORK/data/recon" --split-folder "$WORK/splits/recon/test" \
    --device cpu --no-progress --run-name e0.2_randominit_control

echo
echo "### 5. fine-tune: 3 seeds of one matrix cell, 2 epochs each"
for seed in 0 1 2; do
    sed "s/^seed: 0/seed: $seed/" "$REPO/configs/train/smoke_cpu.yaml" > "$WORK/seed$seed.yaml"
    "$PY" -m navfm.train.run --config "$WORK/seed$seed.yaml" \
        --data-root "$WORK/data" --splits-root "$WORK/splits" \
        --run-name "e2_nonholo_diff_seed$seed" --overfit-n 2 --epochs 2 \
        --eval-batch-size 32 --no-progress
done

echo
echo "### 6. the round trip: a fine-tuned epoch checkpoint back through eval,"
echo "###    with NO --trust-checkpoint (finding F5 does not apply to our files)"
"$PY" -m navfm.eval.offline --model vint \
    --checkpoint "$WORK/runs/e2_nonholo_diff_seed0/epoch_1.pth" \
    --dataset recon --split test --batch-size 32 \
    --data-folder "$WORK/data/recon" --split-folder "$WORK/splits/recon/test" \
    --device cpu --no-progress --run-name e0.2_finetuned_roundtrip

echo
echo "### 7. the synthetic-number stamping, asserted rather than claimed"
"$PY" - "$WORK" <<'PY'
import json, sys
from pathlib import Path

work = Path(sys.argv[1])
control = json.loads((work / "runs/e0.2_randominit_control/metrics.json").read_text())
loaded = json.loads((work / "runs/e0.2_finetuned_roundtrip/metrics.json").read_text())

assert control["random_init"] is True, "an uncheckpointed eval must be marked random_init"
assert control["checkpoint"] is None
assert loaded["random_init"] is False, "a checkpointed eval must NOT be marked random_init"
assert loaded["checkpoint"].endswith("epoch_1.pth")
assert loaded["checkpoint_sha256"], "every checkpointed run records the bytes it scored"
print('e0.2_randominit_control  "random_init": true,  "checkpoint": null')
print(f'e0.2_finetuned_roundtrip "random_init": false, sha256 {loaded["checkpoint_sha256"][:16]}...')
PY
cp "$WORK/runs/e0.2_randominit_control/metrics.json" "$WORK/metrics_randominit_control.json"
cp "$WORK/runs/e0.2_finetuned_roundtrip/metrics.json" "$WORK/metrics_finetuned_roundtrip.json"
echo "(both copied next to the workdir root; gates/M1/ archives them)"

echo
echo "### 8. tables -- the missing-seed guard first"
mv "$WORK/runs/e2_nonholo_diff_seed2" "$WORK/parked_seed2"
if "$PY" "$REPO/scripts/make_tables.py" --runs "$WORK/runs" --out "$WORK/tables"; then
    echo "FAIL: make_tables accepted a cell with a missing seed"
    exit 1
fi
echo "(exit 2 as required; no tables written)"
mv "$WORK/parked_seed2" "$WORK/runs/e2_nonholo_diff_seed2"

echo
echo "### 9. tables, complete matrix"
"$PY" "$REPO/scripts/make_tables.py" --runs "$WORK/runs" --out "$WORK/tables"
echo
cat "$WORK/tables/table4.md"

echo
echo "### M1 DoD: the path from a run directory to a paper table is closed."
