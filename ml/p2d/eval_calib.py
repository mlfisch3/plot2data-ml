"""How often end-to-end calibration lands within 0.5% of the truth, per axis.

    python -m p2d.eval_calib --ckpt runs/v1/best.pt --ocr runs/ocr1/best.pt --data data/mpl-val --limit 100
"""

from __future__ import annotations

import argparse
import glob
import json
import os

import cv2
import numpy as np

from .evaluate import calib_error, load_net
from .ocr import load_reader
from .pipeline import run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=100)
    a = ap.parse_args()
    net, reader = load_net(a.ckpt), load_reader(a.ocr)
    bad = {"x": 0, "y": 0}
    errs = {"x": [], "y": []}
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    for f in files:
        m = json.load(open(f))
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        ce = calib_error(m, run(net, reader, img))
        for ax in "xy":
            e = ce[ax]
            errs[ax].append(e)
            if not np.isfinite(e) or e > 0.005:
                bad[ax] += 1
    for ax in "xy":
        v = np.array(errs[ax], float)
        print(f"{ax}: within 0.5% {1 - bad[ax] / len(files):.0%}  median error {np.nanmedian(v) * 100:.3f}%  "
              f"no fit {np.isnan(v).sum()}")


if __name__ == "__main__":
    main()
