#!/bin/bash
set -u
cd /home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t2-trace/ml
source ../../../PLOT2DATA/.venv/bin/activate
export OMP_NUM_THREADS=1
LOCK=/home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock
CKPT=runs/t5-chartjs/best.pt
OUT=out/t2r2
mkdir -p "$OUT"
PROBES="cross samecolour parallel shallowx legocclude legend dotted steep thin small dense area step clipped multi markers wide"
for p in $PROBES; do
    OUTFILE="$OUT/int-$p-refine.txt"
    ERRFILE="$OUT/int-$p-refine.err"
    if [ -s "$OUTFILE" ]; then
        echo "SKIP $p (already measured)"
        continue
    fi
    echo "RUN $p at $(date '+%H:%M:%S')"
    flock "$LOCK" nice -n 19 python -m p2d.evaluate --ckpt "$CKPT" --data "data/t2-$p" --refine --tta shift > "$OUTFILE" 2> "$ERRFILE"
    tail -2 "$OUTFILE" 2>/dev/null | head -1
done
echo "DONE t2-trace probes at $(date '+%H:%M:%S')"
