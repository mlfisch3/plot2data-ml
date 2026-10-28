"""Real screenshots in ../examples/real: calibration against hand-measured tick anchors.

The anchors are the ones `tools/eval-real.ts` scores the classical engine on:
tick values whose pixel positions were measured by hand. For each, the fitted
mapping's pixel position for that value is compared to the measured one. Every
image also gets an overlay in `out/real/` to look at, which is the real test.

    python -m p2d.eval_real --ckpt runs/v1/best.pt --ocr runs/ocr1/best.pt
"""

from __future__ import annotations

import argparse
import os

import cv2
import numpy as np

from .evaluate import draw, load_net
from .ocr import load_reader
from .pipeline import run

REAL = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "real")

ANCHORS = {
    "01-panel1.png": ([(2020, 69), (2021, 117), (2022, 166), (2023, 215), (2024, 263)],
                      [(42000, 19), (34000, 45), (25000, 71), (17000, 98), (8000, 124)]),
    "01-panel2.png": ([(2020, 79), (2021, 127), (2022, 176), (2023, 225), (2024, 273)],
                      [(22000, 19), (18000, 45), (13000, 71), (9000, 98), (4000, 124)]),
    "01-panel3.png": ([(2020, 74), (2021, 122), (2022, 171), (2023, 220), (2024, 268)],
                      [(88000, 19), (70000, 45), (53000, 71), (35000, 98), (18000, 124)]),
    "02-microprocessor-log-scatter.png": ([], []),
    "03-women-men-percent.png": ([(1970, 29), (1980, 81), (1990, 133), (2000, 184), (2010, 236)],
                                 [(60, 18), (40, 98), (20, 181)]),
    "04-hits-per-visit-redgreen.png": ([], []),
    "05-retail-sales-monthly.png": ([(1996, 235), (2016, 1092)],
                                    [(520, 15), (440, 121), (360, 230), (280, 335), (200, 443), (120, 549)]),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--out", default="out/real")
    ap.add_argument("--fit-canvas", action="store_true", help="scale every chart to the 768 x 512 canvas (no native-resolution pass)")
    a = ap.parse_args()
    net = load_net(a.ckpt)
    reader = load_reader(a.ocr)
    os.makedirs(a.out, exist_ok=True)
    for name, (xa, ya) in ANCHORS.items():
        img = cv2.imread(os.path.join(REAL, name))[..., ::-1].copy()
        res = run(net, reader, img, native=not a.fit_canvas)
        cv2.imwrite(os.path.join(a.out, name), draw(img, res.ex)[..., ::-1])
        errs = []
        for fit, anchors in ((res.xfit, xa), (res.yfit, ya)):
            if not anchors:
                errs.append("-")
            elif fit is None:
                errs.append("no fit")
            else:
                e = [abs(float(fit.to_pos(v)) - p) for v, p in anchors]
                errs.append(f"max {max(e):.2f}px")
        reads = {k: [r[1] for r in v] for k, v in res.tick_reads.items()}
        print(f"{name:36s} series {len(res.series)} ({', '.join(s['kind'] for s in res.series)})  "
              f"x {res.xfit.scale if res.xfit else '-'} {errs[0]}  y {res.yfit.scale if res.yfit else '-'} {errs[1]}")
        print(f"{'':36s} read x {reads['x']}  y {reads['y']}")
        for w in res.warnings:
            print(f"{'':36s} warn: {w}")


if __name__ == "__main__":
    main()
