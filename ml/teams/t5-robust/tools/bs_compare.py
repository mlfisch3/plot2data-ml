"""Compare two per-chart row files from `evaluate --json`, overall and by fit scale, preset and split.

    python teams/t5-robust/tools/bs_compare.py out/t5/base-refine.json out/t5/native-refine.json [--data data/mpl-val]
"""

from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np

CANVAS_W, CANVAS_H = 768, 512


def summ(rs: list[dict]) -> dict:
    cov = np.array([v for r in rs for v in r["line_cov"]], float)
    good = np.array([v for r in rs for v in r["line_good"]], float)
    rms = np.array([v for r in rs for v in r["line_rms"]], float)
    pk = np.array([v for r in rs for v in r["peak_err"]], float)
    tp = sum(r["marker_tp"] for r in rs)
    ngt = sum(r["n_markers_gt"] for r in rs)
    npr = sum(r["n_markers_pred"] for r in rs)
    fe = np.array([r["frame_err_px"] for r in rs], float)
    out = {
        "n": len(rs), "series": len(cov),
        "found": float(np.mean(cov > 0.5)) if len(cov) else np.nan,
        "good": float(good.mean()) if len(good) else np.nan,
        "rms_med%": float(np.median(rms) * 100) if len(rms) else np.nan,
        "rms_p90%": float(np.quantile(rms, 0.9) * 100) if len(rms) else np.nan,
        "peak_med%": float(np.median(pk) * 100) if len(pk) else np.nan,
        "mk_rec": tp / max(ngt, 1), "mk_prec": tp / max(npr, 1),
        "frame_med": float(np.nanmedian(fe)) if np.any(np.isfinite(fe)) else np.nan,
        "frame_p90": float(np.nanquantile(fe, 0.9)) if np.any(np.isfinite(fe)) else np.nan,
        "xt_rec": float(np.mean([r["xticks_recall"] for r in rs])),
        "yt_rec": float(np.mean([r["yticks_recall"] for r in rs])),
        "xt_err": float(np.nanmedian([r["xticks_err_px"] for r in rs])),
        "yt_err": float(np.nanmedian([r["yticks_err_px"] for r in rs])),
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--data", default="data/mpl-val")
    a = ap.parse_args()
    A = {r["id"]: r for r in json.load(open(a.a))["rows"]}
    B = {r["id"]: r for r in json.load(open(a.b))["rows"]}
    ids = [i for i in A if i in B]
    meta = {}
    for f in glob.glob(os.path.join(a.data, "*.json")):
        m = json.load(open(f))
        if m["seed"] in A:
            meta[m["seed"]] = m
    for i in ids:
        m = meta[i]
        for r in (A[i], B[i]):
            r["scale"] = min(CANVAS_W / m["width"], CANVAS_H / m["height"], 2.0)
            r["preset"] = m.get("preset", "none")
    keys = ["n", "series", "found", "good", "rms_med%", "rms_p90%", "peak_med%", "mk_rec", "mk_prec", "frame_med", "frame_p90",
            "xt_rec", "yt_rec", "xt_err", "yt_err"]

    def show(name, sel):
        ra = [A[i] for i in ids if sel(A[i])]
        rb = [B[i] for i in ids if sel(B[i])]
        sa, sb = summ(ra), summ(rb)
        print(f"{name}")
        print("  " + " ".join(f"{k:>9s}" for k in keys))
        print("  " + " ".join(f"{sa[k]:9.3f}" for k in keys) + "   A")
        print("  " + " ".join(f"{sb[k]:9.3f}" for k in keys) + "   B")

    simple = lambda r: r["n_series"] <= 3 and r["density"] <= 0.5
    show("all", lambda r: True)
    show("simple", simple)
    for lo, hi in [(0, 0.5), (0.5, 0.7), (0.7, 1.0), (1.0, 3.0)]:
        show(f"scale [{lo},{hi}) all", lambda r, lo=lo, hi=hi: lo <= r["scale"] < hi)
    for lo, hi in [(0, 0.5), (0.5, 0.7), (0.7, 1.0), (1.0, 3.0)]:
        show(f"scale [{lo},{hi}) simple", lambda r, lo=lo, hi=hi: lo <= r["scale"] < hi and simple(r))
    show("preset none", lambda r: r["preset"] == "none")
    show("presets", lambda r: r["preset"] != "none")
    # The charts that changed most.
    deltas = []
    for i in ids:
        ga, gb = np.mean(A[i]["line_good"] or [0]), np.mean(B[i]["line_good"] or [0])
        deltas.append((gb - ga, i, A[i]["preset"], round(A[i]["scale"], 2)))
    deltas.sort()
    print("worst changes (good cov B - A):", deltas[:6])
    print("best changes:", deltas[-6:])


if __name__ == "__main__":
    main()
