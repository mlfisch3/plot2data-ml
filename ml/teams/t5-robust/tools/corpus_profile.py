"""Error profile of the extraction against the corpus truth, per chart: where along x the error sits.

    python teams/t5-robust/tools/corpus_profile.py retina-2x log-log linear-single-nogrid [--ckpt runs/v3/best.pt]

Prints, for the best-matching extracted series of each truth series, the signed
error (extracted minus truth, % of the y axis span, in log space on a log axis)
in 10 bins along x, plus the mean (a calibration offset shows up as a constant)
and the RMS; and the extracted line's x extent against the truth's.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# P2D_ROOT selects which copy of the p2d package is measured (the frozen baseline in out/t5/base-code, or the live tree).
sys.path.insert(0, os.environ.get("P2D_ROOT") or os.path.abspath(os.path.join(HERE, "..", "..", "..")))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from p2d.eval_corpus import CORPUS, _t  # noqa: E402
from p2d.evaluate import load_net  # noqa: E402
from p2d.ocr import load_reader  # noqa: E402
from p2d.pipeline import run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="+")
    ap.add_argument("--ckpt", default="runs/v3/best.pt")
    ap.add_argument("--ocr", default="runs/ocr1/best.pt")
    a = ap.parse_args()
    net, reader = load_net(a.ckpt), load_reader(a.ocr)
    for cid in a.cases:
        spec = json.load(open(os.path.join(CORPUS, cid + ".json")))
        img = cv2.imread(os.path.join(CORPUS, spec["image"]))[..., ::-1].copy()
        csv = np.genfromtxt(os.path.join(CORPUS, spec["truth"]), delimiter=",", names=True)
        names = csv.dtype.names
        xs = csv[names[0]]
        xlog, ylog = spec["xScale"] == "log", spec["yScale"] == "log"
        yspan = _t(spec["yMax"], ylog) - _t(spec["yMin"], ylog)
        res = run(net, reader, img)
        print(f"=== {cid}  x {res.xfit.scale if res.xfit else '-'}  y {res.yfit.scale if res.yfit else '-'}  series {len(res.series)}")
        tx = _t(xs, xlog)
        for name in names[1:]:
            ty = _t(csv[name], ylog)
            vis = (csv[name] >= spec["yMin"]) & (csv[name] <= spec["yMax"])
            best = None
            for s in res.series:
                if "line" not in s or len(s["line"]) < 2:
                    continue
                p = s["line"]
                px, py = _t(p[:, 0], xlog), _t(p[:, 1], ylog)
                o = np.argsort(px)
                px, py = px[o], py[o]
                inside = (tx >= px.min()) & (tx <= px.max()) & vis
                if inside.sum() < 3:
                    continue
                e = (np.interp(tx[inside], px, py) - ty[inside]) / yspan * 100
                rms = float(np.sqrt(np.mean(e ** 2)))
                if best is None or rms < best[0]:
                    best = (rms, e, inside, px, s)
            if best is None:
                print(f"  {name}: no match")
                continue
            rms, e, inside, px, s = best
            print(f"  {name}: rms {rms:.3f}%  mean {e.mean():+.3f}%  |e|>0.1% at {np.mean(np.abs(e) > 0.1):.0%} of points  "
                  f"x extent extracted [{px.min():.4g}, {px.max():.4g}]  truth visible [{tx[vis].min():.4g}, {tx[vis].max():.4g}]  "
                  f"inside {inside.sum()}/{vis.sum()}  colour {s['color']}")
            bins = np.linspace(tx[inside].min(), tx[inside].max(), 11)
            idx = np.clip(np.searchsorted(bins, tx[inside]) - 1, 0, 9)
            prof = [f"{e[idx == k].mean():+.2f}" if (idx == k).any() else "  -  " for k in range(10)]
            print("    signed error by x decile (%): " + " ".join(prof))
            # The same residual in pixels, through the pipeline's own fits: a tracing error shows here too,
            # a calibration error does not (the fit maps the truth and the trace alike).
            if res.xfit and res.yfit and "line" in s:
                lp = s["line"]
                src = np.column_stack([res.xfit.to_pos(lp[:, 0]), res.yfit.to_pos(lp[:, 1])])
                o = np.argsort(src[:, 0])
                tpx = res.xfit.to_pos(xs[inside] if not xlog else 10 ** tx[inside]) if True else None
                tpy = res.yfit.to_pos(csv[name][inside])
                ok = np.isfinite(tpx) & np.isfinite(tpy)
                ep = np.interp(tpx[ok], src[o, 0], src[o, 1]) - tpy[ok]
                ip = idx[ok]
                profp = [f"{ep[ip == k].mean():+.2f}" if (ip == k).any() else "  -  " for k in range(10)]
                print("    pixel residual of the trace by x decile (px, through the fits): " + " ".join(profp))


if __name__ == "__main__":
    main()
