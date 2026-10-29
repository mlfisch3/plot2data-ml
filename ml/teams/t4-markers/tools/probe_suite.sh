#!/bin/bash
# The whole probe suite plus the two standard sets, geometry only with --refine, from a given p2d tree.
#
#   teams/t4-markers/tools/probe_suite.sh <tag> [<tree>/ml] [--no-diag] [--sets "dense row ..."]
#
# Writes out/t4/eval-<set>-<tag>.txt, rows-<set>-<tag>.json and (unless --no-diag) diag-<set>-<tag>/ for every set.
# <tree>/ml defaults to this worktree's ml; pass /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml for a frozen "before".
set -u
T4=/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t4-markers/ml
TAG=${1:?tag}
TREE=${2:-$T4}
shift; [ $# -gt 0 ] && shift
DIAG=1
SETS="dense row labels shapes hollow multi lines val plotly"
while [ $# -gt 0 ]; do
  case "$1" in
    --no-diag) DIAG=0; shift ;;
    --sets) SETS="$2"; shift 2 ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
done
source $T4/../.venv/bin/activate
export OMP_NUM_THREADS=2
cd $TREE
echo "suite $TAG from $TREE ($(git -C $TREE rev-parse --short HEAD)) sets: $SETS" > $T4/out/t4/suite-$TAG.log
for k in $SETS; do
  case $k in
    val) DATA=data/mpl-val; LIMIT=200 ;;
    plotly) DATA=data/plotly-v1; LIMIT=150 ;;
    *) DATA=data/t4-$k; LIMIT=200 ;;
  esac
  nice -n 19 python -m p2d.evaluate --ckpt runs/v3/best.pt --data $DATA --limit $LIMIT --refine --json $T4/out/t4/rows-$k-$TAG.json > $T4/out/t4/eval-$k-$TAG.txt 2>&1
  echo "$k eval done $(date '+%H:%M')" >> $T4/out/t4/suite-$TAG.log
  if [ $DIAG = 1 ]; then
    P2D_ROOT=$TREE nice -n 19 python $T4/teams/t4-markers/tools/marker_diag.py --ckpt runs/v3/best.pt --data $DATA --limit $LIMIT --out $T4/out/t4/diag-$k-$TAG --worst 12 > $T4/out/t4/diag-$k-$TAG.log 2>&1
    echo "$k diag done $(date '+%H:%M')" >> $T4/out/t4/suite-$TAG.log
  fi
done
echo done > $T4/out/t4/suite-$TAG.done
