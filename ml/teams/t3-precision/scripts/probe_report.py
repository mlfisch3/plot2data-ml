"""Per-factor tables for a probe set: a diag.py pickle of charts made by p2d.synth.probe_t3.

    python teams/t3-precision/scripts/probe_report.py out/t3/diag-peaks.pkl [--which ref|raw]

For every probe parameter, charts are grouped by its value and each group gets:
line RMS (median over series, % of plot height), per-column bias and RMS on
flat columns (px), peak inward error (median px, % clipped by > 1 px), tick
error raw and snapped (median px), frame max-corner error (median px).
"""

from __future__ import annotations

import argparse
import pickle
from collections import defaultdict

import numpy as np


def chart_stats(c: dict, which: str) -> dict:
    out = {"rms": [], "col": [], "flat": [], "peak": [], "peak_raw": [], "tick_raw": [], "tick_snap": [], "frame": np.nan, "cov": []}
    for ln in c.get("lines", []):
        if not ln.get("matched") or "cols" not in ln or not len(ln["cols"]["x"]):
            out["cov"].append(ln.get("cov", 0.0))
            continue
        cc = ln["cols"]
        err = cc[which] - cc["gt"]
        ok = np.isfinite(err)
        out["cov"].append(ln["cov"])
        if ok.any():
            out["rms"].append(100 * np.sqrt(np.mean((err[ok] / c["ph"]) ** 2)))
            out["col"].append(err[ok])
            flat = ok & (np.abs(cc["slope"]) < 0.5) & (cc["dvert"] > 3)
            out["flat"].append(err[flat])
        for p in ln.get("peaks", []):
            if np.isfinite(p[which]):
                out["peak"].append((p[which] - p["y"]) * p["sign"])
            if np.isfinite(p["raw"]):
                out["peak_raw"].append((p["raw"] - p["y"]) * p["sign"])
    for t in c["ticks"]:
        if t["found"]:
            out["tick_raw"].append(t["raw"] - t["gt"])
            out["tick_snap"].append(t["snap"] - t["gt"])
    if c["frame_err"] is not None:
        out["frame"] = float(np.max(np.abs(c["frame_err"])))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pkl")
    ap.add_argument("--which", default="ref", choices=["ref", "raw"])
    a = ap.parse_args()
    charts = pickle.load(open(a.pkl, "rb"))
    charts = [c for c in charts if c.get("probe")]
    if not charts:
        print("no probe charts")
        return
    stats = [chart_stats(c, a.which) for c in charts]
    factors = [k for k in charts[0]["probe"] if k != "family"]
    print(f"{len(charts)} charts of family {charts[0]['probe']['family']}, scoring the {a.which} trace")

    def summarise(idx: list[int]) -> str:
        rms = [v for i in idx for v in stats[i]["rms"]]
        cols = np.concatenate([v for i in idx for v in stats[i]["col"]]) if any(stats[i]["col"] for i in idx) else np.zeros(0)
        flat = np.concatenate([v for i in idx for v in stats[i]["flat"]]) if any(stats[i]["flat"] for i in idx) else np.zeros(0)
        pk = np.array([v for i in idx for v in stats[i]["peak"]])
        pkr = np.array([v for i in idx for v in stats[i]["peak_raw"]])
        tr = np.array([v for i in idx for v in stats[i]["tick_raw"]])
        ts = np.array([v for i in idx for v in stats[i]["tick_snap"]])
        fr = np.array([stats[i]["frame"] for i in idx], float)
        cov = np.array([v for i in idx for v in stats[i]["cov"]])
        s = f"{len(idx):4d} | found {np.mean(cov > 0.5) if len(cov) else np.nan:5.2f} rms {np.median(rms) if rms else np.nan:6.3f}% "
        s += f"| cols bias {np.mean(cols) if len(cols) else np.nan:+6.3f} rms {np.sqrt(np.mean(cols ** 2)) if len(cols) else np.nan:6.3f} p50 {np.median(np.abs(cols)) if len(cols) else np.nan:5.3f} "
        s += f"| flat bias {np.mean(flat) if len(flat) else np.nan:+6.3f} p50 {np.median(np.abs(flat)) if len(flat) else np.nan:5.3f} "
        s += f"| peaks n {len(pk):4d} in p50 {np.median(pk) if len(pk) else np.nan:+6.2f} >1px {100 * np.mean(pk > 1) if len(pk) else np.nan:5.1f}% raw p50 {np.median(pkr) if len(pkr) else np.nan:+6.2f} "
        s += f"| ticks n {len(tr):4d} raw bias {np.mean(tr) if len(tr) else np.nan:+6.3f} p50 {np.median(np.abs(tr)) if len(tr) else np.nan:5.3f} snap p50 {np.median(np.abs(ts)) if len(ts) else np.nan:5.3f} "
        s += f"| frame p50 {np.nanmedian(fr) if np.any(np.isfinite(fr)) else np.nan:5.2f} p90 {np.nanquantile(fr, 0.9) if np.any(np.isfinite(fr)) else np.nan:5.2f} found {np.mean(np.isfinite(fr)):4.2f}"
        return s

    print("  all: " + summarise(list(range(len(charts)))))
    for f in factors:
        groups = defaultdict(list)
        for i, c in enumerate(charts):
            groups[c["probe"][f]].append(i)
        print(f"\n  by {f}:")
        for v in sorted(groups, key=lambda v: (str(type(v)), v)):
            print(f"  {str(v):>10s}: " + summarise(groups[v]))
    # Two-way tables that matter most.
    fam = charts[0]["probe"]["family"]
    pairs = {"peaks": [("shape", "half_cols"), ("join", "lw_px"), ("prom", "half_cols"), ("width", "lw_px")],
             "scale": [("mode", "width"), ("width", "lw_px")], "ticks": [("look", "marks"), ("marks", "grid")],
             "width": [("color", "lw_px"), ("grid", "lw_px")], "log": [("kind", "decades")], "grid": [("nbins", "minor")],
             "frame": [("spines", "grid")]}
    for f1, f2 in pairs.get(fam, []):
        groups = defaultdict(list)
        for i, c in enumerate(charts):
            groups[(c["probe"][f1], c["probe"][f2])].append(i)
        print(f"\n  by {f1} x {f2}:")
        for v in sorted(groups, key=lambda v: (str(v[0]), str(v[1]))):
            print(f"  {str(v[0]):>8s} {str(v[1]):>6s}: " + summarise(groups[v]))


if __name__ == "__main__":
    main()
