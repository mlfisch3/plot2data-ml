"""Per-series failure table from an `evaluate --json` rows file.

    python teams/t2-trace/tools/analyze_rows.py out/t2c/rows-val.json data/mpl-val --out out/t2c/series-val.csv

Each ground-truth line series becomes one record with the score it got
(coverage, good coverage, RMS) and tags describing the chart's structure:
how many series, whether another series shares its colour, dashes, line width,
density, how often it crosses or runs close to another series, whether the
legend sits in the plot, whether it is a step or area series. The summary at
the end counts the failures by tag.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter

import numpy as np

LINE_KINDS = ("line", "step", "line+markers", "area")


def curve_on(path, xs):
    p = np.asarray(path, float)
    if len(p) < 2:
        return np.full(len(xs), np.nan)
    o = np.argsort(p[:, 0], kind="stable")
    return np.interp(xs, p[o, 0], p[o, 1], left=np.nan, right=np.nan)


def series_records(meta: dict, row: dict) -> list[dict]:
    pa = meta["plot_area"]
    ph, pw = pa[3] - pa[1], pa[2] - pa[0]
    xs = np.arange(int(np.ceil(pa[0])), int(np.floor(pa[2])) + 1, dtype=float)
    gts = [s for s in meta["series"] if s["kind"] in LINE_KINDS]
    curves = []
    for s in gts:
        y = curve_on(s["path_px"], xs)
        y[(y < pa[1]) | (y > pa[3])] = np.nan
        curves.append(y)
    cov, good = row["line_cov"], row["line_good"]
    rms_list = list(row["line_rms"])
    legend_in = False
    lb = meta.get("legend_bbox")
    if lb:
        ix = max(0, min(lb[2], pa[2]) - max(lb[0], pa[0]))
        iy = max(0, min(lb[3], pa[3]) - max(lb[1], pa[1]))
        legend_in = ix * iy > 0.25 * (lb[2] - lb[0]) * (lb[3] - lb[1])
    out = []
    ri = 0
    for i, s in enumerate(gts):
        c = cov[i]
        matched = c > 0
        rms = rms_list[ri] if matched and ri < len(rms_list) else np.nan
        if matched:
            ri += 1
        y = curves[i]
        valid = ~np.isnan(y)
        n_valid = int(valid.sum())
        # Interaction with the other line series, over the columns both are drawn in.
        crossings, near3, near8, min_med = 0, 0.0, 0.0, np.inf
        for j, y2 in enumerate(curves):
            if j == i:
                continue
            both = valid & ~np.isnan(y2)
            if both.sum() < 3:
                continue
            d = y[both] - y2[both]
            sgn = np.sign(d)
            sgn = sgn[sgn != 0]
            crossings += int((np.diff(sgn) != 0).sum())
            near3 = max(near3, float((np.abs(d) < 3).mean() * both.sum() / max(n_valid, 1)))
            near8 = max(near8, float((np.abs(d) < 8).mean() * both.sum() / max(n_valid, 1)))
            min_med = min(min_med, float(np.median(np.abs(d))))
        same_colour = any(o["color"].lower() == s["color"].lower() for k, o in enumerate(gts) if k != i)
        same_colour_any = any(o["color"].lower() == s["color"].lower() for k, o in enumerate(meta["series"]) if meta["series"][k] is not s)
        dy = np.abs(np.diff(y[valid])) if n_valid > 2 else np.array([0.0])
        clipped = int(((~valid) & (curve_on(s["path_px"], xs) == curve_on(s["path_px"], xs))).sum())
        out.append(dict(
            seed=meta["seed"], idx=i, kind=s["kind"], ls=s["linestyle"], lw=round(s["linewidth_px"], 2),
            color=s["color"], marker=s["marker"] or "", n_pts=len(s["x"]), dens=round(len(s["x"]) / max(pw, 1), 3),
            cov=round(c, 3), good=round(good[i], 3), rms_pct=round(rms * 100, 3) if matched else "",
            n_series=len(meta["series"]), n_line=len(gts), preset=meta.get("preset", ""), style=meta.get("style", ""),
            generator=meta.get("generator", ""), ylog=meta["yscale"] == "log", legend_in=legend_in,
            same_colour=same_colour or same_colour_any, crossings=crossings, near3=round(near3, 3), near8=round(near8, 3),
            min_med_dist=round(min_med, 1) if np.isfinite(min_med) else "", steep_p90=round(float(np.quantile(dy, 0.9)), 1),
            cols=n_valid, frac_x=round(n_valid / max(len(xs), 1), 3), clipped_cols=clipped, ph=round(ph, 1), pw=round(pw, 1),
        ))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("data")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rows = json.load(open(a.rows))["rows"]
    recs = []
    for r in rows:
        f = os.path.join(a.data, f"{r['id']:07d}.json")
        if not os.path.exists(f):
            f = os.path.join(a.data, f"{r['id']}.json")
        meta = json.load(open(f))
        recs += series_records(meta, r)
    if a.out:
        with open(a.out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(recs[0].keys()))
            w.writeheader()
            w.writerows(recs)
    n = len(recs)
    lost = [r for r in recs if r["cov"] <= 0.5]
    partial = [r for r in recs if r["cov"] > 0.5 and r["good"] < 0.9]
    bad = [r for r in recs if r["cov"] > 0.5 and r["rms_pct"] != "" and r["rms_pct"] > 1.0]
    simple = [r for r in recs if r["n_series"] <= 3 and r["dens"] <= 0.5]

    def pct(k, pool):
        return f"{len(k)}/{len(pool)} ({100 * len(k) / max(len(pool), 1):.0f}%)"

    print(f"series {n}; not found (cov<=0.5) {pct(lost, recs)}; found but good<0.9 {pct(partial, recs)}; found with rms>1% {pct(bad, recs)}")
    print(f"simple: {len(simple)}; not found {pct([r for r in lost if r in simple], simple)}; partial {pct([r for r in partial if r in simple], simple)}")

    def breakdown(name, key):
        print(f"\n{name}")
        tot = Counter(key(r) for r in recs)
        lo = Counter(key(r) for r in lost)
        pa = Counter(key(r) for r in partial)
        for k in sorted(tot, key=lambda v: str(v)):
            print(f"  {str(k):>18s}  n={tot[k]:4d}  lost={lo[k]:3d} ({100 * lo[k] / tot[k]:3.0f}%)  partial={pa[k]:3d} ({100 * pa[k] / tot[k]:3.0f}%)")

    breakdown("by kind", lambda r: r["kind"])
    breakdown("by linestyle", lambda r: r["ls"])
    breakdown("by n_line (line series in chart)", lambda r: r["n_line"])
    breakdown("by density (pts per column)", lambda r: "<0.25" if r["dens"] < 0.25 else "<0.5" if r["dens"] < 0.5 else "<1" if r["dens"] < 1 else "<2" if r["dens"] < 2 else ">=2")
    breakdown("by line width px", lambda r: "<1.2" if r["lw"] < 1.2 else "<2" if r["lw"] < 2 else "<3" if r["lw"] < 3 else ">=3")
    breakdown("by same colour as another series", lambda r: r["same_colour"])
    breakdown("by crossings with other series", lambda r: "0" if r["crossings"] == 0 else "1-2" if r["crossings"] <= 2 else "3-9" if r["crossings"] < 10 else ">=10")
    breakdown("by fraction of columns within 3 px of another series", lambda r: "0" if r["near3"] == 0 else "<0.1" if r["near3"] < 0.1 else "<0.3" if r["near3"] < 0.3 else ">=0.3")
    breakdown("by legend inside plot", lambda r: r["legend_in"])
    breakdown("by preset", lambda r: r["preset"])
    breakdown("by x extent (fraction of plot width)", lambda r: "<0.5" if r["frac_x"] < 0.5 else "<0.9" if r["frac_x"] < 0.9 else ">=0.9")
    breakdown("by steepness p90 (px per column)", lambda r: "<1" if r["steep_p90"] < 1 else "<3" if r["steep_p90"] < 3 else "<8" if r["steep_p90"] < 8 else ">=8")
    breakdown("by plot height px", lambda r: "<250" if r["ph"] < 250 else "<400" if r["ph"] < 400 else ">=400")

    print("\nworst not-found (cov<=0.5), simple first:")
    for r in sorted(lost, key=lambda r: (r["n_series"] > 3 or r["dens"] > 0.5, -r["cols"]))[:40]:
        print(f"  seed {r['seed']} s{r['idx']} {r['kind']:13s} ls={r['ls']:2s} lw={r['lw']:4.1f} n={r['n_pts']:4d} dens={r['dens']:5.2f} nline={r['n_line']} "
              f"cov={r['cov']:.2f} good={r['good']:.2f} same={int(r['same_colour'])} cross={r['crossings']:2d} near3={r['near3']:.2f} legend_in={int(r['legend_in'])} {r['preset']}")
    print("\nworst partial (found, good<0.9):")
    for r in sorted(partial, key=lambda r: r["good"])[:40]:
        print(f"  seed {r['seed']} s{r['idx']} {r['kind']:13s} ls={r['ls']:2s} lw={r['lw']:4.1f} n={r['n_pts']:4d} dens={r['dens']:5.2f} nline={r['n_line']} "
              f"cov={r['cov']:.2f} good={r['good']:.2f} rms={r['rms_pct']} same={int(r['same_colour'])} cross={r['crossings']:2d} near3={r['near3']:.2f} legend_in={int(r['legend_in'])} {r['preset']}")
    print("\nworst RMS among found:")
    for r in sorted(bad, key=lambda r: -r["rms_pct"])[:30]:
        print(f"  seed {r['seed']} s{r['idx']} {r['kind']:13s} ls={r['ls']:2s} lw={r['lw']:4.1f} n={r['n_pts']:4d} dens={r['dens']:5.2f} nline={r['n_line']} "
              f"cov={r['cov']:.2f} good={r['good']:.2f} rms={r['rms_pct']} same={int(r['same_colour'])} cross={r['crossings']:2d} near3={r['near3']:.2f} steep={r['steep_p90']}")


if __name__ == "__main__":
    main()
