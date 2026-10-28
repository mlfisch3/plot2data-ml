#!/bin/bash
# After the brainstormer commits a new fix, run this with a tag to re-measure
# diag on mpl-val and t1-probe, compare to the frozen base, and run box tests.
#
# Usage:  teams/t1-axis/remeasure.sh <tag>
# Reads commit from the current HEAD; `<tag>` is just an output folder suffix,
# e.g. teams/t1-axis/remeasure.sh v2-fixedbox
#
# All numbers go under out/t1/<tag>-*; compares go to out/t1/compare-<tag>-*.txt.
set -eo pipefail
cd "$(dirname "$0")/../.."
source ../.venv/bin/activate
TAG="${1:?usage: remeasure.sh <tag>}"
export OMP_NUM_THREADS=2
unset P2D_ROOT  # worktree is the live tree

# Diag on mpl-val
rm -rf out/t1/diag-mpl-$TAG; mkdir -p out/t1/diag-mpl-$TAG
nice -n 19 python teams/t1-axis/diag.py --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt \
    --data data/mpl-val --limit 200 --out out/t1/diag-mpl-$TAG > out/t1/diag-mpl-$TAG.log 2>&1
nice -n 19 python teams/t1-axis/reclass.py out/t1/diag-mpl-$TAG data/mpl-val >> out/t1/diag-mpl-$TAG.log 2>&1

# Diag on t1-probe
rm -rf out/t1/diag-probe-$TAG; mkdir -p out/t1/diag-probe-$TAG
nice -n 19 python teams/t1-axis/diag.py --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt \
    --data data/t1-probe --limit 640 --out out/t1/diag-probe-$TAG > out/t1/diag-probe-$TAG.log 2>&1
nice -n 19 python teams/t1-axis/reclass.py out/t1/diag-probe-$TAG data/t1-probe >> out/t1/diag-probe-$TAG.log 2>&1

# Compare vs frozen base
nice -n 19 python teams/t1-axis/compare.py \
    out/t1/diag-mpl out/t1/diag-mpl-$TAG > out/t1/compare-mpl-$TAG.txt 2>&1
nice -n 19 python teams/t1-axis/compare.py --by-style \
    out/t1/diag-probe-base out/t1/diag-probe-$TAG > out/t1/compare-probe-$TAG.txt 2>&1

# CPU-only box finder quality
nice -n 19 python teams/t1-axis/test_boxes.py data/mpl-val 200 > out/t1/boxes-mpl-$TAG.txt 2>&1
nice -n 19 python teams/t1-axis/test_boxes.py data/t1-probe 640 > out/t1/boxes-probe-$TAG.txt 2>&1

echo DONE
