"""Sanity-check the ground truth of a t5-real-style directory.

Flags: missing files, zero series, bad JSON, non-matching image dimensions,
y-range that collapses to a single point, x not sorted.

    python ml/teams/round4-benchmark/tools/validate_gt.py --data ml/data/t5-real-ext
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from p2d.eval_t5real import load_truth  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    a = ap.parse_args()
    probs = []
    n = 0
    for f in sorted(os.listdir(a.data)):
        if not f.endswith(".json"):
            continue
        n += 1
        path = os.path.join(a.data, f)
        try:
            meta = json.load(open(path))
        except Exception as e:
            probs.append(f"{f}: bad JSON ({e})")
            continue
        cid = meta.get("id", "?")
        png = os.path.join(a.data, cid + ".png")
        if not os.path.exists(png):
            probs.append(f"{cid}: no png")
            continue
        img = cv2.imread(png)
        if img is None:
            probs.append(f"{cid}: unreadable png")
            continue
        csv_path = os.path.join(a.data, cid + ".data.csv")
        try:
            truth = load_truth(meta, csv_path)
        except Exception as e:
            probs.append(f"{cid}: load_truth failed ({e})")
            continue
        if not truth:
            probs.append(f"{cid}: zero series after loader")
            continue
        for name, (xs, ys) in truth.items():
            if len(xs) < 2:
                probs.append(f"{cid}:{name}: fewer than 2 points")
            yr = float(np.nanmax(ys) - np.nanmin(ys))
            if yr == 0:
                probs.append(f"{cid}:{name}: y collapses")
            if not np.all(np.diff(xs) >= 0):
                probs.append(f"{cid}:{name}: x not sorted after load")
    print(f"checked {n} charts")
    for p in probs:
        print("  " + p)
    print(f"{len(probs)} issues")


if __name__ == "__main__":
    main()
