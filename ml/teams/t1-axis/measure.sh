#!/bin/bash
# Measure one state of the pipeline on everything calibration touches, sequentially on the GPU.
#   out/t1/measure.sh <tag> [tree]      tree: live (this worktree, default) | base (the frozen contest-start tree)
# Writes out/t1/<tag>/: the five standard commands, the probe-set e2e, and diag.py on mpl-val, plotly and the probe.
set -u
TAG=$1
TREE=${2:-live}
MINE=/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis/ml
if [ "$TREE" = base ]; then ROOT=/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml; else ROOT=$MINE; fi
OUT=$MINE/out/t1/$TAG
mkdir -p "$OUT"
cd "$ROOT" || exit 1
source ../.venv/bin/activate
export OMP_NUM_THREADS=2
export P2D_ROOT=$ROOT
F="UserWarning|warnings.warn"
N="nice -n 19"
PROBE=$MINE/data/t1-probe
echo "tree=$TREE root=$ROOT commit=$(git -C "$ROOT" rev-parse --short HEAD) dirty=$(git -C "$ROOT" status --short -- ml/p2d | wc -l) $(date)" > "$OUT/state.txt"
run() {  # run <name> <command...>: retried twice on failure (the shared GPU runs out of memory at times)
  local name=$1; shift
  for i in 1 2 3; do
    "$@" 2>&1 | grep -vE "$F" > "$OUT/$name.txt" && ! grep -q Traceback "$OUT/$name.txt" && return 0
    sleep 60
  done
}
run mpl-e2e      $N python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt --json "$OUT/mpl-rows.json"
run plotly-e2e   $N python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt --json "$OUT/plotly-rows.json"
run corpus       $N python -m p2d.eval_corpus --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --viz "$OUT/corpus-viz"
run real         $N python -m p2d.eval_real --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --out "$OUT/real"
run mpl-refine   $N python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --refine
run probe-e2e    $N python -m p2d.evaluate --ckpt runs/v3/best.pt --data "$PROBE" --limit 640 --ocr runs/ocr1/best.pt --json "$OUT/probe-rows.json"
run calib-mpl    $N python -m p2d.eval_calib --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --data data/mpl-val --limit 200
cd "$MINE"
run diag-mpl     $N python teams/t1-axis/diag.py --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --data data/mpl-val --limit 200 --out "$OUT/diag-mpl"
$N python teams/t1-axis/reclass.py "$OUT/diag-mpl" data/mpl-val > /dev/null 2>&1
run diag-plotly  $N python teams/t1-axis/diag.py --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --data data/plotly-v1 --limit 150 --out "$OUT/diag-plotly"
$N python teams/t1-axis/reclass.py "$OUT/diag-plotly" data/plotly-v1 > /dev/null 2>&1
run diag-probe   $N python teams/t1-axis/diag.py --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --data "$PROBE" --limit 640 --out "$OUT/diag-probe"
$N python teams/t1-axis/reclass.py "$OUT/diag-probe" "$PROBE" > /dev/null 2>&1
echo DONE >> "$OUT/state.txt"
