"""Counts from an inspect_stages JSON: verdicts, split and hop statistics, why junctions were refused.

    python teams/t2-trace/tools/summarize_inspect.py out/t2c/inspect-val.json [--rows out/t2c/rows-val.json]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--rows", default=None, help="evaluate rows, to split simple from all")
    a = ap.parse_args()
    reps = json.load(open(a.json))
    simple_ids = None
    if a.rows:
        rows = json.load(open(a.rows))["rows"]
        simple_ids = {r["id"] for r in rows if r["n_series"] <= 3 and r["density"] <= 0.5}
    reps = [r for r in reps if r.get("verdict") not in (None, "n/a")]
    pools = [("all", reps)] + ([("simple", [r for r in reps if r["seed"] in simple_ids])] if simple_ids is not None else [])
    for name, pool in pools:
        print(f"== {name}: {len(pool)} series")
        v = Counter(r["verdict"] for r in pool)
        lost = [r for r in pool if r["cov"] <= 0.5]
        vl = Counter(r["verdict"] for r in lost)
        part = [r for r in pool if r["cov"] > 0.5 and r["good"] < 0.9]
        vp = Counter(r["verdict"] for r in part)
        print(f"   {'verdict':18s} {'series':>7s} {'lost':>6s} {'partial':>8s}")
        for k, n in v.most_common():
            print(f"   {k:18s} {n:7d} {vl.get(k, 0):6d} {vp.get(k, 0):8d}")
        # Splits and hops.
        nclu = np.array([sum(1 for _, f in r["clusters"] if f >= 0.15) for r in pool])
        print(f"   series whose ridge pixels fall in >= 2 clusters (each >= 15%): {int((nclu >= 2).sum())} ({100 * (nclu >= 2).mean():.0f}%), >= 3: {int((nclu >= 3).sum())}")
        print(f"   series with a hopping chain: {sum(1 for r in pool if r['hops'] > 0)}; with >= 2 kept pieces: {sum(1 for r in pool if sum(1 for p in r['pieces'] if p[3] == 'kept') >= 2)}")
        heat_lo = [r for r in pool if r["heat_cov"] < 0.9]
        print(f"   heat coverage < 0.9: {len(heat_lo)} series; < 0.6: {sum(1 for r in pool if r['heat_cov'] < 0.6)}")
        fates = Counter(p[3] for r in pool for p in r["pieces"])
        print(f"   fates of covering pieces: {dict(fates)}")
        # Junction refusals.
        refs = [x for r in pool for x in r.get("refusals", [])]
        if refs:
            de = np.array([x["de"] for x in refs]); dx = np.array([x["dx"] for x in refs])
            yg = np.array([x["ygap"] for x in refs]); ex = np.array([x["extrap"] for x in refs])
            print(f"   refused junctions between kept pieces of one series: {len(refs)}")
            print(f"     embedding distance de: p10 {np.quantile(de, .1):.2f} p50 {np.median(de):.2f} p90 {np.quantile(de, .9):.2f}; de > 3.0 (emb_tol): {100 * (de > 3).mean():.0f}%")
            print(f"     dx (B start - A end, columns): < -8 (overlap rule): {100 * (dx < -8).mean():.0f}%; -8..0: {100 * ((dx >= -8) & (dx <= 0)).mean():.0f}%; 1..60: {100 * ((dx > 0) & (dx <= 60)).mean():.0f}%; > 60: {100 * (dx > 60).mean():.0f}%")
            ok_gap = yg <= 3 + 2 * np.maximum(dx, 0)
            print(f"     y gap within the merge rule (gap <= 3 + 2 dx): {100 * ok_gap.mean():.0f}%; y gap p50 {np.median(yg):.1f} px")
            print(f"     slope-extrapolated miss at the junction: p50 {np.median(ex):.1f} px, p90 {np.quantile(ex, .9):.1f} px; within 4 px: {100 * (ex <= 4).mean():.0f}%")
            only_de = (de > 3) & (dx >= -8) & (dx <= 60) & ok_gap
            print(f"     refused on the embedding alone (geometry would pass): {100 * only_de.mean():.0f}%")
            joinable = (ex <= 4) & (dx >= -8) & (dx <= 60)
            print(f"     joinable by extrapolated slope within 4 px and dx in [-8, 60]: {100 * joinable.mean():.0f}%")
            lostj = [r for r in lost if r.get("refusals")]
            print(f"     lost series with such a refused junction: {len(lostj)} of {len(lost)}")


if __name__ == "__main__":
    main()
