#!/bin/bash
set -u
cd /home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t2-trace/ml
source ../../../PLOT2DATA/.venv/bin/activate
export OMP_NUM_THREADS=1
LOCK=/home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock
CKPT=runs/t5-chartjs/best.pt
OUT=out/t2r2
mkdir -p "$OUT"
echo "ghostpair geometry at $(date '+%H:%M:%S')"
flock "$LOCK" nice -n 19 python -m p2d.evaluate --ckpt "$CKPT" --data data/t2-ghostpair --refine --tta shift > "$OUT/int-ghostpair-refine.txt" 2> "$OUT/int-ghostpair-refine.err"
tail -3 "$OUT/int-ghostpair-refine.txt" | head -1
echo "ghostpair done at $(date '+%H:%M:%S')"
