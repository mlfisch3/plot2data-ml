#!/bin/bash
# Round-2 probe suite: evaluate against the INTEGRATED model
# (t5-chartjs/best.pt + --tta shift + --refine) on t4 probe sets.
#
#   teams/t4-markers/tools/probe_suite_r2.sh <tag> [--sets "dense row ..."] [--no-diag]
#
# Writes out/t4r2/eval-<set>-<tag>.txt, rows-<set>-<tag>.json, diag-<set>-<tag>/
set -u
T4=/home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t4-markers/ml
LOCK=/home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock
TAG=${1:?tag}
shift
DIAG=1
SETS="dense row labels shapes hollow multi lines val plotly"
while [ $# -gt 0 ]; do
  case "$1" in
    --no-diag) DIAG=0; shift ;;
    --sets) SETS="$2"; shift 2 ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
done
source /home/drd/PROJECT/CLAUDE/PLOT2DATA/.venv/bin/activate
export OMP_NUM_THREADS=2
cd $T4
mkdir -p out/t4r2
echo "r2 suite $TAG @ $(git -C $T4 rev-parse --short HEAD) sets: $SETS" > out/t4r2/suite-$TAG.log
for k in $SETS; do
  case $k in
    val) DATA=data/mpl-val; LIMIT=200 ;;
    plotly) DATA=data/plotly-v1; LIMIT=150 ;;
    *) DATA=data/t4-$k; LIMIT=200 ;;
  esac
  flock -w 7200 $LOCK nice -n 19 python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data $DATA --limit $LIMIT --refine --tta shift --json out/t4r2/rows-$k-$TAG.json > out/t4r2/eval-$k-$TAG.txt 2>&1
  echo "$k eval done $(date '+%H:%M')" >> out/t4r2/suite-$TAG.log
  if [ $DIAG = 1 ]; then
    flock -w 7200 $LOCK P2D_ROOT=$T4 nice -n 19 python teams/t4-markers/tools/marker_diag.py --ckpt runs/t5-chartjs/best.pt --data $DATA --limit $LIMIT --out out/t4r2/diag-$k-$TAG --worst 12 > out/t4r2/diag-$k-$TAG.log 2>&1
    echo "$k diag done $(date '+%H:%M')" >> out/t4r2/suite-$TAG.log
  fi
done
echo done > out/t4r2/suite-$TAG.done
