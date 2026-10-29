"""Zoomed crops of the worst stretch of median-ranked series: what the gross columns look like.

    python teams/t3-precision/scripts/cases.py out/t3/diag-base.pkl out/t3/cases [--simple] [--n 8] [--pick median|worst]
"""
import argparse
import os
import pickle

import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("pkl")
ap.add_argument("out")
ap.add_argument("--simple", action="store_true")
ap.add_argument("--n", type=int, default=8)
ap.add_argument("--pick", default="median")
ap.add_argument("--zoom", type=int, default=4)
a = ap.parse_args()
charts = pickle.load(open(a.pkl, "rb"))
if a.simple:
    charts = [c for c in charts if c["n_series"] <= 3 and c["density"] <= 0.5]
os.makedirs(a.out, exist_ok=True)
rows = []
for c in charts:
    for ln in c.get("lines", []):
        if not ln.get("matched") or "cols" not in ln or not len(ln["cols"]["x"]):
            continue
        cc = ln["cols"]
        err = cc["ref"] - cc["gt"]
        ok = np.isfinite(err)
        if ok.sum() < 10:
            continue
        rms = 100 * np.sqrt(np.mean((err[ok] / c["ph"]) ** 2))
        rows.append((rms, c, ln))
rows.sort(key=lambda r: r[0])
if a.pick == "median":
    m = len(rows) // 2
    sel = rows[max(0, m - a.n // 2): m + (a.n + 1) // 2]
else:
    sel = rows[-a.n:]
z = a.zoom
for rms, c, ln in sel:
    cc = ln["cols"]
    err = np.abs(cc["ref"] - cc["gt"])
    ok = np.isfinite(err)
    # the window of 60 columns holding the most squared error
    e2 = np.where(ok, err ** 2, 0)
    k = 60
    cs = np.convolve(e2, np.ones(k), "valid")
    i0 = int(np.argmax(cs))
    xs = cc["x"][i0:i0 + k]
    ys = cc["gt"][i0:i0 + k]
    cx, cy = float(np.mean(xs)), float(np.nanmean(ys))
    img = cv2.imread(c["file"] + ".png")[..., ::-1].copy()
    H, W = img.shape[:2]
    x0, y0 = int(cx - 40), int(cy - 40)
    x0, y0 = max(0, min(W - 80, x0)), max(0, min(H - 80, y0))
    crop = cv2.resize(img[y0:y0 + 80, x0:x0 + 80], None, fx=z, fy=z, interpolation=cv2.INTER_NEAREST)

    def poly(xv, yv, col):
        pts = np.column_stack([(xv - x0 + 0.5) * z, (yv - y0 + 0.5) * z])
        good = np.isfinite(pts).all(1)
        if good.sum() > 1:
            cv2.polylines(crop, [np.round(pts[good] * 4).astype(np.int32)], False, col, 1, cv2.LINE_AA, shift=2)

    poly(cc["x"], cc["gt"], (0, 190, 0))
    poly(cc["x"], cc["raw"], (0, 90, 255))
    poly(cc["x"], cc["ref"], (230, 0, 230))
    name = f"{c['id']}-{ln['k']}"
    cv2.imwrite(os.path.join(a.out, name + ".png"), crop[..., ::-1])
    w = slice(i0, i0 + k)
    net = np.abs(cc["ref"][w] - cc["raw"][w]) < 1e-4
    print(f"{name} {c['preset']:>10s} rms {rms:.3f}% lw {ln['lw']:.1f} s {c['scale']:.2f} npts {ln['n_pts']} | worst 60 cols at x {xs[0]:.0f}-{xs[-1]:.0f}: "
          f"share of sq err {cs[i0] / e2.sum():.2f}, p50 |err| {np.nanmedian(err[w]):.2f} px, max {np.nanmax(err[w]):.1f}, "
          f"|slope| p50 {np.nanmedian(np.abs(cc['slope'][w])):.2f}, dvert min {np.min(cc['dvert'][w]):.0f}, net-kept {100 * net.mean():.0f}%, "
          f"raw p50 |err| {np.nanmedian(np.abs(cc['raw'][w] - cc['gt'][w])):.2f}")
