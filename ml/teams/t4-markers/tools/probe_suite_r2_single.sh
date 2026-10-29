#!/bin/bash
# Round-2 probe suite: evaluate against the INTEGRATED model, under a single lock
# acquisition. All sets run back to back once we have the lock.
#
#   teams/t4-markers/tools/probe_suite_r2_single.sh <tag> [--sets "..."]
#
# Writes out/t4r2/eval-<set>-<tag>.txt and rows-<set>-<tag>.json for every set.
set -u
T4=/home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t4-markers/ml
LOCK=/home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock
TAG=${1:?tag}
shift || true
SETS="dense row labels shapes hollow multi lines val plotly"
while [ $# -gt 0 ]; do
  case "$1" in
    --sets) SETS="$2"; shift 2 ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
done
source /home/drd/PROJECT/CLAUDE/PLOT2DATA/.venv/bin/activate
export OMP_NUM_THREADS=2
cd $T4
mkdir -p out/t4r2
echo "r2 single-lock $TAG @ $(git -C $T4 rev-parse --short HEAD) sets: $SETS" > out/t4r2/suite-$TAG.log
flock -w 10800 $LOCK bash -c '
set -u
cd '"$T4"'
for k in '"$SETS"'; do
  case $k in
    val) DATA=data/mpl-val; LIMIT=200 ;;
    plotly) DATA=data/plotly-v1; LIMIT=150 ;;
    linemk) DATA=data/t4r2-linemk; LIMIT=216 ;;
    *) DATA=data/t4-$k; LIMIT=200 ;;
  esac
  nice -n 19 python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data $DATA --limit $LIMIT --refine --tta shift --json out/t4r2/rows-$k-'"$TAG"'.json > out/t4r2/eval-$k-'"$TAG"'.txt 2>&1
  echo "$k done $(date +%H:%M:%S)" >> out/t4r2/suite-'"$TAG"'.log
done
'
echo done > out/t4r2/suite-$TAG.done
