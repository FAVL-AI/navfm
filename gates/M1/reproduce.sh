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

rm -rf "$WORK"
mkdir -p "$WORK"
cd "$WORK"

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
echo "### 7. tables -- the missing-seed guard first"
mv "$WORK/runs/e2_nonholo_diff_seed2" "$WORK/parked_seed2"
if "$PY" "$REPO/scripts/make_tables.py" --runs "$WORK/runs" --out "$WORK/tables"; then
    echo "FAIL: make_tables accepted a cell with a missing seed"
    exit 1
fi
echo "(exit 2 as required; no tables written)"
mv "$WORK/parked_seed2" "$WORK/runs/e2_nonholo_diff_seed2"

echo
echo "### 8. tables, complete matrix"
"$PY" "$REPO/scripts/make_tables.py" --runs "$WORK/runs" --out "$WORK/tables"
echo
cat "$WORK/tables/table4.md"

echo
echo "### M1 DoD: the path from a run directory to a paper table is closed."
