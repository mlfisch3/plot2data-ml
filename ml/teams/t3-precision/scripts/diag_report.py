"""Tables from a diag.py pickle: where the error comes from.

    python teams/t3-precision/scripts/diag_report.py out/t3/diag-base.pkl [--simple] [--worst 25]
"""

from __future__ import annotations

import argparse
import pickle

import numpy as np


def fmt(v, d=3):
    return "nan" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{d}f}"


def bins_table(name, key, edges, labels, d, mask_extra=None):
    print(f"\n  by {name}:")
    print(f"  {'bin':>14s} {'cols':>8s} {'share%':>7s} {'bias':>7s} {'rms':>7s} {'p50':>7s} {'p90':>7s} {'net%':>6s}  (px; share of total squared error)")
    tot = float(np.sum(d["err"] ** 2))
    for lo, hi, lab in zip(edges[:-1], edges[1:], labels):
        m = (d[key] >= lo) & (d[key] < hi)
        if mask_extra is not None:
            m &= mask_extra
        if not m.any():
            continue
        e = d["err"][m]
        print(f"  {lab:>14s} {m.sum():8d} {100 * np.sum(e ** 2) / tot:7.1f} {np.mean(e):7.3f} {np.sqrt(np.mean(e ** 2)):7.3f} "
              f"{np.median(np.abs(e)):7.3f} {np.quantile(np.abs(e), 0.9):7.3f} {100 * np.mean(d['net'][m]):6.1f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pkl")
    ap.add_argument("--simple", action="store_true", help="only charts with <= 3 series and density <= 0.5")
    ap.add_argument("--worst", type=int, default=20)
    ap.add_argument("--which", default="ref", choices=["ref", "raw"], help="score the refined or the raw trace")
    a = ap.parse_args()
    charts = pickle.load(open(a.pkl, "rb"))
    if a.simple:
        charts = [c for c in charts if c["n_series"] <= 3 and c["density"] <= 0.5]
    print(f"{len(charts)} charts, {'simple' if a.simple else 'all'}, scoring the {a.which} trace")

    # ---------------- lines, per column ----------------
    cols = {k: [] for k in ("err", "err_raw", "slope", "lw", "scale", "grid", "axis", "other", "dvert", "ink", "net", "ph", "log")}
    per_series = []
    for c in charts:
        for ln in c.get("lines", []):
            if not ln.get("matched") or "cols" not in ln:
                continue
            cc = ln["cols"]
            n = len(cc["x"])
            if n == 0:
                continue
            pred = cc[a.which]
            err = pred - cc["gt"]
            ok = np.isfinite(err)
            cols["err"].append(err[ok])
            cols["err_raw"].append((cc["raw"] - cc["gt"])[ok])
            cols["slope"].append(np.abs(cc["slope"][ok]))
            cols["lw"].append(np.full(ok.sum(), ln["lw"]))
            cols["scale"].append(np.full(ok.sum(), c["scale"]))
            cols["grid"].append(cc["grid"][ok])
            cols["axis"].append(cc["axis"][ok])
            cols["other"].append(cc["other"][ok])
            cols["dvert"].append(cc["dvert"][ok])
            cols["ink"].append(cc["ink"][ok])
            cols["net"].append(np.abs(cc["ref"][ok] - cc["raw"][ok]) < 1e-4)
            cols["ph"].append(np.full(ok.sum(), c["ph"]))
            cols["log"].append(np.full(ok.sum(), c["yscale"] == "log"))
            d = err[ok] / c["ph"]
            big = np.abs(err[ok]) > max(3.0, 2.0 * ln["lw"])
            sq = float(np.sum(d ** 2))
            per_series.append({"id": c["id"], "preset": c["preset"], "k": ln["k"], "cov": ln["cov"], "lw": ln["lw"],
                               "rms_pct": 100 * float(np.sqrt(np.mean(d ** 2))) if len(d) else np.nan,
                               "rms_small_pct": 100 * float(np.sqrt(np.mean(d[~big] ** 2))) if (~big).any() else np.nan,
                               "big_share": float(np.sum(d[big] ** 2) / sq) if sq > 0 else 0.0, "big_frac": float(big.mean()),
                               "scale": c["scale"], "n": int(ok.sum()), "n_pts": ln["n_pts"], "ls": ln["ls"],
                               "peaks": ln.get("peaks", [])})
    d = {k: np.concatenate(v) if v else np.zeros(0) for k, v in cols.items()}
    n = len(d["err"])
    print(f"\n== LINES: {len(per_series)} matched series, {n} columns (source px, + means prediction below the truth on screen) ==")
    e = d["err"]
    print(f"  all columns: bias {np.mean(e):+.3f}  rms {np.sqrt(np.mean(e ** 2)):.3f}  p50 {np.median(np.abs(e)):.3f}  "
          f"p90 {np.quantile(np.abs(e), 0.9):.3f}  p99 {np.quantile(np.abs(e), 0.99):.3f}  net-kept {100 * np.mean(d['net']):.1f}%")
    small = np.abs(e) < 3
    print(f"  |err|<3 px: {100 * small.mean():.1f}% of columns, bias {np.mean(e[small]):+.3f} rms {np.sqrt(np.mean(e[small] ** 2)):.3f} "
          f"p50 {np.median(np.abs(e[small])):.3f}; they hold {100 * np.sum(e[small] ** 2) / np.sum(e ** 2):.1f}% of the squared error")
    r = per_series
    rms = np.array([s["rms_pct"] for s in r])
    rms_small = np.array([s["rms_small_pct"] for s in r])
    print(f"  per-series RMS (% ph): median {np.nanmedian(rms):.3f}  mean {np.nanmean(rms):.3f}  p90 {np.nanquantile(rms, 0.9):.3f}")
    print(f"  per-series RMS without the gross columns (|err| > max(3, 2 lw)): median {np.nanmedian(rms_small):.3f}  mean {np.nanmean(rms_small):.3f}")
    # Signed error against slope sign: does the trace lag the slope?
    sl_signed = np.concatenate([np.sign(ln["cols"]["slope"]) for c in charts for ln in c.get("lines", []) if ln.get("matched") and "cols" in ln and len(ln["cols"]["x"])])
    sl_signed = sl_signed[np.isfinite(np.concatenate([ln["cols"][a.which] - ln["cols"]["gt"] for c in charts for ln in c.get("lines", []) if ln.get("matched") and "cols" in ln and len(ln["cols"]["x"])]))]
    for sgn, lab in ((1, "slope > 0 (falling on screen)"), (-1, "slope < 0 (rising on screen)")):
        m = (sl_signed == sgn) & small & (d["slope"] > 0.5)
        if m.any():
            print(f"  {lab}, |slope|>0.5, |err|<3: n {m.sum()} bias {np.mean(e[m]):+.3f}")
    bins_table("|slope| (px/px)", "slope", [0, 0.25, 0.5, 1, 2, 4, 1e9], ["0-0.25", "0.25-0.5", "0.5-1", "1-2", "2-4", ">4"], d)
    bins_table("line width (px)", "lw", [0, 1.2, 2, 3, 4, 1e9], ["<1.2", "1.2-2", "2-3", "3-4", ">4"], d)
    bins_table("canvas scale", "scale", [0, 0.5, 0.7, 0.999, 1.5, 9], ["<0.5", "0.5-0.7", "0.7-1", "1.0", ">1"], d)
    bins_table("dist to gridline", "grid", [0, 1.5, 3, 6, 1e9], ["<1.5", "1.5-3", "3-6", ">6"], d)
    bins_table("dist to axis/ref", "axis", [0, 1.5, 3, 6, 1e9], ["<1.5", "1.5-3", "3-6", ">6"], d)
    bins_table("dist to other series", "other", [0, 2, 4, 8, 1e9], ["<2", "2-4", "4-8", ">8"], d)
    bins_table("dist to vertex (cols)", "dvert", [0, 1.01, 3.01, 8.01, 1e9], ["<=1", "1-3", "3-8", ">8"], d)
    bins_table("ink run height (px)", "ink", [0, 2, 3, 4, 6, 1e9], ["<2", "2-3", "3-4", "4-6", ">6"], d)
    flat = (d["slope"] < 0.5) & (d["dvert"] > 3) & small
    bins_table("line width, flat columns only (|slope|<0.5, dvert>3, |err|<3)", "lw", [0, 1.2, 2, 3, 4, 1e9], ["<1.2", "1.2-2", "2-3", "3-4", ">4"], d, flat)
    bins_table("canvas scale, flat columns only", "scale", [0, 0.5, 0.7, 0.999, 1.5, 9], ["<0.5", "0.5-0.7", "0.7-1", "1.0", ">1"], d, flat)
    bins_table("gridline distance, flat columns only", "grid", [0, 1.5, 3, 6, 1e9], ["<1.5", "1.5-3", "3-6", ">6"], d, flat)
    # refined vs raw on the same columns
    er = d["err_raw"]
    okr = np.isfinite(er)
    print(f"\n  raw net trace on the same columns: bias {np.mean(er[okr]):+.3f} rms {np.sqrt(np.mean(er[okr] ** 2)):.3f} p50 {np.median(np.abs(er[okr])):.3f}")
    m = okr & flat
    print(f"  flat columns: raw p50 {np.median(np.abs(er[m])):.3f} rms {np.sqrt(np.mean(er[m] ** 2)):.3f}  vs refined p50 {np.median(np.abs(e[m])):.3f} rms {np.sqrt(np.mean(e[m] ** 2)):.3f}")
    m = okr & flat & ~d["net"]
    if m.any():
        print(f"  flat columns the refinement moved: n {m.sum()} raw p50 {np.median(np.abs(er[m])):.3f} -> refined p50 {np.median(np.abs(e[m])):.3f}")
    m = okr & flat & d["net"]
    if m.any():
        print(f"  flat columns kept from the net: n {m.sum()} p50 {np.median(np.abs(e[m])):.3f} rms {np.sqrt(np.mean(e[m] ** 2)):.3f}")

    # ---------------- peaks ----------------
    pk = [dict(p, lw=s["lw"], scale=s["scale"], ph=s["id"] and None) for s in r for p in s["peaks"]]
    for p, s in [(p, s) for s in r for p in s["peaks"]]:
        p["ph_"] = None
    phs = {c["id"]: c["ph"] for c in charts}
    pk = []
    for s in r:
        for p in s["peaks"]:
            q = dict(p)
            q["lw"], q["scale"], q["ph"] = s["lw"], s["scale"], phs[s["id"]]
            q["in"] = (q[a.which] - q["y"]) * q["sign"]  # + = inward (clipped), in px
            q["in_raw"] = (q["raw"] - q["y"]) * q["sign"]
            pk.append(q)
    if pk:
        ok = np.array([np.isfinite(q["in"]) for q in pk])
        print(f"\n== PEAKS: {len(pk)} turning points (prominence >= 5% ph), {ok.sum()} with a prediction; + = clipped (inward), px ==")
        inn = np.array([q["in"] for q in pk])[ok]
        inr = np.array([q["in_raw"] for q in pk])[ok]
        ph_ = np.array([q["ph"] for q in pk])[ok]
        print(f"  signed inward: mean {np.mean(inn):+.3f} median {np.median(inn):+.3f}  |err| p50 {np.median(np.abs(inn)):.3f} p90 {np.quantile(np.abs(inn), 0.9):.3f}")
        print(f"  as % ph: |err| median {100 * np.median(np.abs(inn) / ph_):.3f}  mean {100 * np.mean(np.abs(inn) / ph_):.3f}")
        print(f"  raw net at the same peaks: mean {np.mean(inr[np.isfinite(inr)]):+.3f} median {np.median(inr[np.isfinite(inr)]):+.3f} |err| p50 {np.median(np.abs(inr[np.isfinite(inr)])):.3f}")
        print(f"  clipped by > 1 px: {100 * np.mean(inn > 1):.1f}%   by > 3 px: {100 * np.mean(inn > 3):.1f}%   overshoot < -1 px: {100 * np.mean(inn < -1):.1f}%")

        def pk_table(name, key, edges, labels):
            vals = np.array([q[key] for q in pk])[ok]
            print(f"\n  peaks by {name}:")
            print(f"  {'bin':>12s} {'n':>5s} {'mean_in':>8s} {'p50_in':>8s} {'p50|e|':>8s} {'p90|e|':>8s} {'>1px%':>6s} {'%ph p50':>8s}")
            for lo, hi, lab in zip(edges[:-1], edges[1:], labels):
                m = (vals >= lo) & (vals < hi)
                if not m.any():
                    continue
                print(f"  {lab:>12s} {m.sum():5d} {np.mean(inn[m]):+8.3f} {np.median(inn[m]):+8.3f} {np.median(np.abs(inn[m])):8.3f} "
                      f"{np.quantile(np.abs(inn[m]), 0.9):8.3f} {100 * np.mean(inn[m] > 1):6.1f} {100 * np.median(np.abs(inn[m]) / ph_[m]):8.3f}")

        pk_table("angle at the vertex (deg; 180 = straight)", "angle", [0, 30, 60, 90, 120, 150, 181], ["<30", "30-60", "60-90", "90-120", "120-150", ">150"])
        pk_table("width 2 px below the tip (cols)", "w_2px", [0, 2, 4, 8, 16, 1e9], ["<2", "2-4", "4-8", "8-16", ">16"])
        pk_table("line width (px)", "lw", [0, 1.2, 2, 3, 4, 1e9], ["<1.2", "1.2-2", "2-3", "3-4", ">4"])
        pk_table("canvas scale", "scale", [0, 0.5, 0.7, 0.999, 1.5, 9], ["<0.5", "0.5-0.7", "0.7-1", "1.0", ">1"])
        pk_table("vertex heat at the tip", "vheat", [0, 0.3, 0.6, 1.01], ["<0.3", "0.3-0.6", ">0.6"])
        pk_table("nearest vertex peak (px)", "dvert", [0, 1, 2, 4, 1e9], ["<1", "1-2", "2-4", ">4"])
        pk_table("ink run at the tip (px)", "ink", [0, 3, 5, 8, 1e9], ["<3", "3-5", "5-8", ">8"])

    # ---------------- ticks ----------------
    ticks = [dict(t, generator=c["generator"], preset=c["preset"], scale=c["scale"]) for c in charts for t in c["ticks"]]
    print(f"\n== TICKS: {len(ticks)} labelled ticks ==")
    for axis in ("x", "y"):
        tt = [t for t in ticks if t["axis"] == axis]
        found = [t for t in tt if t["found"]]
        if not found:
            continue
        raw = np.array([t["raw"] - t["gt"] for t in found])
        snap = np.array([t["snap"] - t["gt"] for t in found])
        snapped = np.array([t["snapped"] for t in found])
        print(f"  {axis}: recall {len(found) / max(1, len(tt)):.3f}  raw: bias {np.mean(raw):+.3f} std {np.std(raw):.3f} p50|e| {np.median(np.abs(raw)):.3f} p90 {np.quantile(np.abs(raw), 0.9):.3f}"
              f"   snapped ({100 * snapped.mean():.0f}% of ticks): bias {np.mean(snap):+.3f} p50|e| {np.median(np.abs(snap)):.3f} p90 {np.quantile(np.abs(snap), 0.9):.3f}")
        if snapped.any():
            print(f"     on the snapped ticks: raw p50 {np.median(np.abs(raw[snapped])):.3f} -> snap p50 {np.median(np.abs(snap[snapped])):.3f}; "
                  f"unsnapped ticks raw p50 {np.median(np.abs(raw[~snapped])):.3f}")

        def tick_table(name, keyf, groups):
            print(f"\n  {axis} ticks by {name}:")
            print(f"  {'group':>22s} {'n':>5s} {'bias':>7s} {'std':>6s} {'p50|e|':>7s} {'p90':>6s} {'snap%':>6s} {'p50 snap':>8s}")
            for lab, fn in groups:
                m = np.array([fn(t) for t in found])
                if not m.any():
                    continue
                print(f"  {lab:>22s} {m.sum():5d} {np.mean(raw[m]):+7.3f} {np.std(raw[m]):6.3f} {np.median(np.abs(raw[m])):7.3f} "
                      f"{np.quantile(np.abs(raw[m]), 0.9):6.3f} {100 * np.mean(snapped[m]):6.1f} {np.median(np.abs(snap[m])):8.3f}")

        tick_table("what is drawn at the tick", None, [
            ("mark out, grid", lambda t: t["mark_out"] > 0 and t["grid"] > 0.5),
            ("mark out, no grid", lambda t: t["mark_out"] > 0 and t["grid"] <= 0.5),
            ("mark in only", lambda t: t["mark_out"] == 0 and t["mark_in"] > 0),
            ("grid only", lambda t: t["mark_out"] == 0 and t["mark_in"] == 0 and t["grid"] > 0.5),
            ("label only", lambda t: t["mark_out"] == 0 and t["mark_in"] == 0 and t["grid"] <= 0.5),
        ])
        tick_table("side", None, [("low (left/bottom)", lambda t: t["side"] == "low"), ("high (right/top)", lambda t: t["side"] == "high")])
        tick_table("generator / preset", None, [("matplotlib none", lambda t: t["generator"] == "matplotlib" and t["preset"] == "none"),
                                                ("matplotlib house", lambda t: t["generator"] == "matplotlib" and t["preset"] != "none"),
                                                ("plotly", lambda t: t["generator"] == "plotly")])
        tick_table("canvas scale", None, [("<0.5", lambda t: t["scale"] < 0.5), ("0.5-0.7", lambda t: 0.5 <= t["scale"] < 0.7),
                                          ("0.7-1", lambda t: 0.7 <= t["scale"] < 0.999), ("1.0", lambda t: 0.999 <= t["scale"] < 1.5), (">1", lambda t: t["scale"] >= 1.5)])
        tick_table("label height (px)", None, [("<9", lambda t: t["label_h"] < 9), ("9-12", lambda t: 9 <= t["label_h"] < 12), ("12-16", lambda t: 12 <= t["label_h"] < 16), (">=16", lambda t: t["label_h"] >= 16)])
        # Does the raw error follow the label offset (label centre minus tick) ?
        off = np.array([t["label_off"] for t in found])
        okk = np.isfinite(off)
        if okk.sum() > 10:
            cc = np.corrcoef(off[okk], raw[okk])[0, 1]
            print(f"  corr(raw error, label-centre offset from the tick) = {cc:+.3f}; label offset mean {np.mean(off[okk]):+.2f} std {np.std(off[okk]):.2f}")
        fp = sum(c["tick_fp"][axis + "ticks"] for c in charts)
        print(f"  false positives per chart: {fp / len(charts):.2f}")

    # ---------------- frame ----------------
    print(f"\n== FRAME ==")
    fe = [c for c in charts if c["frame_err"] is not None]
    print(f"  found {len(fe)}/{len(charts)}")
    if fe:
        E = np.array([c["frame_err"] for c in fe])  # x0 y0 x1 y1 signed
        V = np.array([c["edge_vis"] for c in fe])  # left top right bottom
        mx = np.abs(E).max(1)
        print(f"  max-corner error: p50 {np.median(mx):.2f} p90 {np.quantile(mx, 0.9):.2f}  >3 px on {100 * np.mean(mx > 3):.1f}% of charts")
        for i, (lab, vi) in enumerate(zip(("x0 (left)", "y0 (top)", "x1 (right)", "y1 (bottom)"), (0, 1, 2, 3))):
            e = E[:, i]
            vis = V[:, vi] > 0.5
            print(f"  {lab:12s}: visible spine n {vis.sum():3d} bias {np.mean(e[vis]) if vis.any() else np.nan:+.2f} p50|e| {np.median(np.abs(e[vis])) if vis.any() else np.nan:.2f} p90 {np.quantile(np.abs(e[vis]), 0.9) if vis.any() else np.nan:.2f}"
                  f"   hidden n {(~vis).sum():3d} bias {np.mean(e[~vis]) if (~vis).any() else np.nan:+.2f} p50|e| {np.median(np.abs(e[~vis])) if (~vis).any() else np.nan:.2f} p90 {np.quantile(np.abs(e[~vis]), 0.9) if (~vis).any() else np.nan:.2f}")
        allvis = (V > 0.5).all(1)
        print(f"  all four spines visible: n {allvis.sum()} max-err p50 {np.median(mx[allvis]):.2f} p90 {np.quantile(mx[allvis], 0.9):.2f};"
              f"  some hidden: n {(~allvis).sum()} p50 {np.median(mx[~allvis]) if (~allvis).any() else np.nan:.2f} p90 {np.quantile(mx[~allvis], 0.9) if (~allvis).any() else np.nan:.2f}")
        order = np.argsort(-mx)[: a.worst]
        print("  worst frames: id preset err(x0,y0,x1,y1) vis(l,t,r,b) scale")
        for i in order:
            c = fe[i]
            print(f"    {c['id']} {c['preset']:16s} " + " ".join(f"{v:+6.1f}" for v in E[i]) + "   " + " ".join(f"{v:.2f}" for v in V[i]) + f"  s={c['scale']:.2f}")
    miss = [c for c in charts if c["frame_err"] is None]
    if miss:
        print("  not found: " + ", ".join(f"{c['id']}({c['preset']}, vis {' '.join(f'{v:.1f}' for v in c['edge_vis'])}, {len(c['corner_peaks'])} pk)" for c in miss[:20]))

    # ---------------- worst series ----------------
    print(f"\n== WORST {a.worst} matched series by RMS (% ph): precision = gross columns (|err| > max(3, 2 lw)) hold < 50% of the squared error ==")
    print(f"  {'id':>8s} {'k':>2s} {'preset':>12s} {'cov':>5s} {'rms%':>7s} {'rms_small%':>10s} {'gross_share':>11s} {'gross_cols%':>11s} {'lw':>4s} {'s':>5s} {'npts':>5s} class")
    for s in sorted(r, key=lambda s: -np.nan_to_num(s["rms_pct"]))[: a.worst]:
        cls = "tracing" if s["big_share"] >= 0.5 else "precision"
        print(f"  {s['id']:>8d} {s['k']:2d} {s['preset']:>12s} {s['cov']:5.2f} {s['rms_pct']:7.3f} {s['rms_small_pct']:10.3f} {s['big_share']:11.2f} {100 * s['big_frac']:11.1f} {s['lw']:4.1f} {s['scale']:5.2f} {s['n_pts']:5d} {cls}")
    n_tr = sum(1 for s in r if s["big_share"] >= 0.5)
    print(f"  over all matched series: {n_tr} tracing-dominated, {len(r) - n_tr} precision-dominated; "
          f"median RMS of the precision-dominated {np.nanmedian([s['rms_pct'] for s in r if s['big_share'] < 0.5]):.3f}%")


if __name__ == "__main__":
    main()
