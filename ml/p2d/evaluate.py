"""Run a checkpoint over a synthetic set and score it.

    python -m p2d.evaluate --ckpt runs/v1/best.pt --data data/mpl-val --limit 300 [--viz out/eval-viz]
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os

import cv2
import numpy as np
import torch

from .extract import extract, refine_lines, run_net
from .metrics import score, summarise_split
from .model import PlotNet


def load_net(ckpt: str, device: str = "cuda") -> PlotNet:
    st = torch.load(ckpt, map_location=device)
    net = PlotNet(st.get("encoder", "resnet34"), pretrained=False).to(device)
    net.load_state_dict(st["model"])
    net.eval()
    return net


def draw(img: np.ndarray, ex, meta: dict | None = None) -> np.ndarray:
    """The extraction drawn in a colour unlike the ink, over a faded copy of the source."""
    out = (img.astype(np.float32) * 0.45 + 255 * 0.55).astype(np.uint8)
    if meta is not None:
        for s in meta["series"]:
            p = np.array(s["path_px"])
            if len(p) > 1:
                cv2.polylines(out, [np.round(p * 4).astype(np.int32)], False, (0, 200, 0), 1, cv2.LINE_AA, shift=2)
    pal = [(230, 0, 230), (0, 120, 255), (255, 120, 0), (0, 0, 0), (200, 0, 0), (0, 160, 160), (120, 60, 0)]
    for k, s in enumerate(ex.series):
        c = pal[k % len(pal)]
        if len(s.line_px) > 1:
            cv2.polylines(out, [np.round(s.line_px * 4).astype(np.int32)], False, c, 1, cv2.LINE_AA, shift=2)
        for m in s.markers_px:
            cv2.drawMarker(out, (int(round(m[0])), int(round(m[1]))), c, cv2.MARKER_TILTED_CROSS, 7, 1)
    for t in ex.xticks + ex.yticks:
        a = t["anchor"]
        cv2.drawMarker(out, (int(round(a[0])), int(round(a[1]))), (255, 0, 0), cv2.MARKER_CROSS, 9, 1)
        if t["label_box"]:
            b = np.round(t["label_box"]).astype(int)
            cv2.rectangle(out, (b[0], b[1]), (b[2], b[3]), (0, 0, 255), 1)
    if ex.plot_area:
        b = np.round(ex.plot_area).astype(int)
        cv2.rectangle(out, (b[0], b[1]), (b[2], b[3]), (255, 140, 0), 1)
    return out


def gt_value_to_px(meta: dict, axis: str, v):
    """The chart's own mapping, from the ground truth: data value -> source pixel."""
    pa = meta["plot_area"]
    lim = meta["xlim"] if axis == "x" else meta["ylim"]
    log = meta["xscale" if axis == "x" else "yscale"] == "log"
    v = np.asarray(v, float)
    if axis == "x" and meta.get("xdate") == "%Y" and np.nanmax(np.abs(v)) < 3000:
        # Year labels read as plain numbers give decimal years; the chart's unit is days.
        v = (v - 1970.0) * 365.2425
    with np.errstate(invalid="ignore", divide="ignore"):
        t = np.log10(v) if log else v
    t0, t1 = (np.log10(lim[0]), np.log10(lim[1])) if log else lim
    f = (t - t0) / (t1 - t0)
    return pa[0] + f * (pa[2] - pa[0]) if axis == "x" else pa[3] - f * (pa[3] - pa[1])


def to_gt_pixels(meta: dict, res):
    """Re-express an end-to-end result in the chart's true pixel frame.

    Calibration errors and tracing errors then add up in one number, measured
    in the same unit as the pixel-only score.
    """
    from copy import copy

    ex = copy(res.ex)
    ex.series = []
    from .extract import Series

    def px(v):
        if v is None:
            return np.zeros((0, 2))
        q = np.column_stack([gt_value_to_px(meta, "x", v[:, 0]), gt_value_to_px(meta, "y", v[:, 1])])
        return q[np.all(np.isfinite(q), axis=1)]  # e.g. a negative value on a log axis

    for s, d in zip(res.ex.series, res.series):
        ex.series.append(Series(kind=s.kind, line_px=px(d.get("line")), markers_px=px(d.get("markers"))))
    return ex


def calib_error(meta: dict, res) -> dict:
    """Worst error of the fitted mapping over the plot area, as a fraction of its size."""
    pa = meta["plot_area"]
    out = {}
    for axis, fit, lo, hi in (("x", res.xfit, pa[0], pa[2]), ("y", res.yfit, pa[1], pa[3])):
        if fit is None:
            out[axis] = np.nan
            continue
        px = np.array([lo, hi])
        back = gt_value_to_px(meta, axis, fit.to_value(px))
        e = np.abs(back - px) / (hi - lo)
        out[axis] = float(np.nanmax(e)) if np.any(np.isfinite(e)) else np.nan
        out[axis + "_scale_ok"] = fit.scale == meta[axis + "scale"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--viz", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--ocr", default=None, help="tick reader checkpoint: score end to end in data units")
    ap.add_argument("--refine", action="store_true", help="re-measure lines on the source pixels")
    ap.add_argument("--oracle-ticks", action="store_true", help="end to end, but with the true tick positions and values")
    a = ap.parse_args()
    net = load_net(a.ckpt)
    reader = None
    if a.ocr:
        from .ocr import load_reader

        reader = load_reader(a.ocr)
    e2e = a.ocr is not None or a.oracle_ticks
    cal = []
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    rows = []
    if a.viz:
        os.makedirs(a.viz, exist_ok=True)
    for i, f in enumerate(files):
        meta = json.load(open(f))
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        if e2e:
            from .pipeline import run

            oracle = None
            if a.oracle_ticks:
                oracle = {"x": [(t["pos"], t["value"]) for t in meta["xticks"]],
                          "y": [(t["pos"], t["value"]) for t in meta["yticks"]]}
            res = run(net, reader, img, oracle, refine=a.refine)
            ex = to_gt_pixels(meta, res) if res.xfit and res.yfit else res.ex.__class__(M=res.ex.M, plot_area=None)
            M = res.ex.M
            ce = calib_error(meta, res)
            cal.append(ce)
        else:
            out, M = run_net(net, img)
            ex = extract(out, M, img)
            if a.refine:
                ex = refine_lines(img, ex)
        r = score(meta, ex, canvas_scale=math.hypot(M[0, 0], M[1, 0]))
        rows.append(r)
        if a.viz and i < 40:
            cv2.imwrite(os.path.join(a.viz, f"{meta['seed']}.png"), draw(img, ex, meta)[..., ::-1])
    split = summarise_split(rows)
    s = split["all"]
    if cal:
        for axis in ("x", "y"):
            v = np.array([c[axis] for c in cal], float)
            s[f"calib_{axis}_found"] = float(np.mean(np.isfinite(v)))
            s[f"calib_{axis}_err_median_pct"] = float(np.nanmedian(v) * 100) if np.any(np.isfinite(v)) else np.nan
            s[f"calib_{axis}_within_0.5pct"] = float(np.mean(np.nan_to_num(v, nan=1) < 0.005))
            s[f"calib_{axis}_scale_ok"] = float(np.mean([c.get(axis + "_scale_ok", False) for c in cal]))
    keys = [k for k in s if k != "images"]
    simple = split["simple"]
    print(f"{'metric':28s} {'all':>10s} {'simple':>10s}")
    print(f"{'images':28s} {s['images']:>10d} {simple.get('images', 0):>10d}")
    for k in keys:
        a_, b_ = s.get(k, float('nan')), simple.get(k, float('nan'))
        print(f"{k:28s} {a_:>10.4f} {b_:>10.4f}")
    if a.json:
        json.dump({"summary": s, "rows": rows}, open(a.json, "w"), default=float)


if __name__ == "__main__":
    main()
