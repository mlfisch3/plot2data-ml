"""End-to-end score on the Chart.js corpus in ../corpus, the classical engine's home ground.

Same definition as ACCURACY.md: RMS over 200 points spaced uniformly across
the x range, as a percentage of the axis full-scale range, log axes compared in
log space. Markers are scored point to point. Chart.js is a renderer the model
never saw in training, so this is an out-of-distribution test.

    python -m p2d.eval_corpus --ckpt runs/v1/best.pt --ocr runs/ocr1/best.pt
"""

from __future__ import annotations

import argparse
import json
import os

import cv2
import numpy as np

from .evaluate import load_net
from .ocr import load_reader
from .pipeline import run

CORPUS = os.path.join(os.path.dirname(__file__), "..", "..", "corpus")


def _t(v, log):
    v = np.asarray(v, float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.log10(v) if log else v


def score_case(spec: dict, truth: dict[str, np.ndarray], xs_truth: np.ndarray, res) -> list[dict]:
    xlog, ylog = spec["xScale"] == "log", spec["yScale"] == "log"
    yspan = _t(spec["yMax"], ylog) - _t(spec["yMin"], ylog)
    xspan = _t(spec["xMax"], xlog) - _t(spec["xMin"], xlog)
    preds = []
    for s in res.series:
        if "line" in s and not spec.get("scatter"):
            preds.append(("line", s["line"]))
        elif "markers" in s and len(s["markers"]):
            preds.append(("markers", s["markers"]))
        elif "line" in s:
            preds.append(("line", s["line"]))
    out = []
    used = set()
    for name, ys in truth.items():
        best = None
        for j, (kind, p) in enumerate(preds):
            if j in used or len(p) < 2:
                continue
            px, py = _t(p[:, 0], xlog), _t(p[:, 1], ylog)
            tx, ty = _t(xs_truth, xlog), _t(ys, ylog)
            if spec.get("scatter"):
                # Point to point: each true marker against the nearest extracted one.
                d = np.hypot((px[None] - tx[:, None]) / xspan, (py[None] - ty[:, None]) / yspan)
                nn = d.min(1)
                hit = nn < 0.02
                rms = float(np.sqrt(np.mean(nn[hit] ** 2))) if hit.any() else np.inf
                cov = float(hit.mean())
            else:
                o = np.argsort(px)
                px, py = px[o], py[o]
                lo, hi = max(px.min(), tx.min()), min(px.max(), tx.max())
                if hi <= lo:
                    continue
                g = np.linspace(tx.min(), tx.max(), 200)
                inside = (g >= lo) & (g <= hi)
                e = np.interp(g[inside], px, py) - np.interp(g[inside], tx, ty)
                rms = float(np.sqrt(np.mean(e ** 2)) / yspan)
                cov = float(inside.mean())
            if best is None or rms < best[1]:
                best = (j, rms, cov)
        if best is None:
            out.append({"series": name, "rms_pct": np.nan, "cover": 0.0})
        else:
            used.add(best[0])
            out.append({"series": name, "rms_pct": best[1] * 100, "cover": best[2]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--viz", default=None)
    ap.add_argument("--fit-canvas", action="store_true", help="scale every chart to the 768 x 512 canvas (no native-resolution pass)")
    a = ap.parse_args()
    net = load_net(a.ckpt)
    reader = load_reader(a.ocr)
    index = json.load(open(os.path.join(CORPUS, "index.json")))
    allr = []
    if a.viz:
        os.makedirs(a.viz, exist_ok=True)
    for case in index:
        spec = json.load(open(os.path.join(CORPUS, case["id"] + ".json")))
        img = cv2.imread(os.path.join(CORPUS, spec["image"]))[..., ::-1].copy()
        csv = np.genfromtxt(os.path.join(CORPUS, spec["truth"]), delimiter=",", names=True)
        names = csv.dtype.names
        xs = csv[names[0]]
        truth = {n: csv[n] for n in names[1:]}
        res = run(net, reader, img, native=not a.fit_canvas)
        rows = score_case(spec, truth, xs, res)
        xs_ = res.xfit.scale if res.xfit else "-"
        ys_ = res.yfit.scale if res.yfit else "-"
        print(f"{case['id']:24s} found {len(res.series)}/{len(truth)}  scales {xs_}/{ys_}  " +
              "  ".join(f"{r['rms_pct']:.3f}% cov {r['cover']:.0%}" for r in rows) +
              ("  WARN " + "; ".join(res.warnings) if res.warnings else ""))
        allr += rows
        if a.viz:
            from .evaluate import draw

            cv2.imwrite(os.path.join(a.viz, case["id"] + ".png"), draw(img, res.ex)[..., ::-1])
    v = np.array([r["rms_pct"] for r in allr], float)
    print(f"series {len(v)}  median {np.nanmedian(v):.3f}%  worst {np.nanmax(v):.3f}%  failed {np.isnan(v).sum()}")


if __name__ == "__main__":
    main()
