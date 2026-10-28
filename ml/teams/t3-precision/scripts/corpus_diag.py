"""Where the corpus error comes from: calibration (an affine error in value space) versus the trace itself.

    python teams/t3-precision/scripts/corpus_diag.py --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt [--no-refine]

For each line series the error e(x) = pred(x) - truth(x) on the 200-point grid
of eval_corpus is fitted with e = a + b * truth + c * truth'(x): a and b are a
y-calibration error, c an x-calibration shift. The RMS before and after
removing that fit splits the published number into a calibration part and a
trace part. The signed shortfall at the turning points of the truth is printed
too (+ = clipped, inward), as ACCURACY.md does for the classical engine.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import cv2
import numpy as np

# P2D_ROOT selects which tree's p2d is imported: the frozen baseline worktree for "before" numbers,
# this worktree (the default) for "after" numbers.
ML = os.environ.get("P2D_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ML)

from p2d.eval_corpus import CORPUS, _t  # noqa: E402
from p2d.evaluate import load_net  # noqa: E402
from p2d.ocr import load_reader  # noqa: E402
from p2d.pipeline import run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--no-refine", action="store_true")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    net = load_net(a.ckpt)
    reader = load_reader(a.ocr)
    index = json.load(open(os.path.join(CORPUS, "index.json")))
    print(f"{'case':22s} {'series':10s} {'rms%':>7s} {'calib%':>7s} {'trace%':>7s} {'yoff%':>7s} {'ygain%':>7s} {'xshift%':>8s} {'peaks':>5s} {'in_mean%':>8s} {'in_p50%':>7s} {'cover':>5s}")
    for case in index:
        if a.only and case["id"] != a.only:
            continue
        spec = json.load(open(os.path.join(CORPUS, case["id"] + ".json")))
        if spec.get("scatter"):
            continue
        img = cv2.imread(os.path.join(CORPUS, spec["image"]))[..., ::-1].copy()
        csv = np.genfromtxt(os.path.join(CORPUS, spec["truth"]), delimiter=",", names=True)
        names = csv.dtype.names
        xs = csv[names[0]]
        xlog, ylog = spec["xScale"] == "log", spec["yScale"] == "log"
        yspan = _t(spec["yMax"], ylog) - _t(spec["yMin"], ylog)
        xspan = _t(spec["xMax"], xlog) - _t(spec["xMin"], xlog)
        res = run(net, reader, img, refine=not a.no_refine)
        preds = [s["line"] for s in res.series if "line" in s and len(s["line"]) > 2]
        tx = _t(xs, xlog)
        for name in names[1:]:
            ty = _t(csv[name], ylog)
            best = None
            for p in preds:
                px, py = _t(p[:, 0], xlog), _t(p[:, 1], ylog)
                o = np.argsort(px)
                px, py = px[o], py[o]
                lo, hi = max(px.min(), tx.min()), min(px.max(), tx.max())
                if hi <= lo:
                    continue
                g = np.linspace(tx.min(), tx.max(), 200)
                inside = (g >= lo) & (g <= hi)
                gt = np.interp(g[inside], tx, ty)
                e = np.interp(g[inside], px, py) - gt
                rms = float(np.sqrt(np.mean(e ** 2)) / yspan)
                if best is None or rms < best[0]:
                    best = (rms, e, gt, g[inside], inside.mean(), px, py)
            if best is None:
                print(f"{case['id']:22s} {name:10s} not found")
                continue
            rms, e, gt, g, cover, px, py = best
            slope = np.gradient(gt, g)
            A = np.column_stack([np.ones(len(g)), gt - gt.mean(), slope])
            coef, *_ = np.linalg.lstsq(A, e, rcond=None)
            resid = e - A @ coef
            trace = float(np.sqrt(np.mean(resid ** 2)) / yspan)
            calib = float(np.sqrt(max(0.0, np.mean(e ** 2) - np.mean(resid ** 2))) / yspan)
            # Turning points of the truth, prominence >= 5% of the y span.
            inn = []
            for i in range(1, len(ty) - 1):
                if (ty[i] > ty[i - 1] and ty[i] >= ty[i + 1]) or (ty[i] < ty[i - 1] and ty[i] <= ty[i + 1]):
                    lo_, hi_ = max(0, i - 15), min(len(ty), i + 16)
                    if ty[i] > ty[i - 1]:
                        prom = min(ty[i] - ty[lo_:i].min(), ty[i] - ty[i + 1:hi_].min())
                        sign = 1.0
                    else:
                        prom = min(ty[lo_:i].max() - ty[i], ty[i + 1:hi_].max() - ty[i])
                        sign = -1.0
                    if prom >= 0.05 * yspan and px.min() <= tx[i] <= px.max():
                        yp = np.interp(tx[i], px, py)
                        inn.append((ty[i] - yp) * sign / yspan)  # + = prediction short of the tip
            inn = np.array(inn)
            print(f"{case['id']:22s} {name:10s} {100 * rms:7.3f} {100 * calib:7.3f} {100 * trace:7.3f} {100 * coef[0] / yspan:+7.3f} {100 * coef[1]:+7.3f} "
                  f"{100 * -coef[2] / xspan if xspan else 0:+8.3f} {len(inn):5d} {100 * np.mean(inn) if len(inn) else np.nan:+8.3f} {100 * np.median(inn) if len(inn) else np.nan:+7.3f} {cover:5.2f}")


if __name__ == "__main__":
    main()
