"""Slice a marker_diag rows.json by the probe parameters recorded in each chart's meta.

    python teams/t4-markers/tools/probe_report.py out/t4/diag-dense/rows.json [--by spacing_rel]

Prints, per level of the chosen parameter (default: every parameter with few distinct values): charts,
true markers, recall, precision, median error, and the stage/cause breakdown.
"""

from __future__ import annotations

import argparse
import collections
import json

import numpy as np


def slice_rows(rows, key, bins=None):
    groups = collections.defaultdict(list)
    for r in rows:
        p = r.get("probe") or {}
        if key == "nn_rel":
            v = p.get("nn_rel_median")
            if v is None:
                continue
            b = next((f"{bins[i]}-{bins[i + 1]}" for i in range(len(bins) - 1) if bins[i] <= v < bins[i + 1]), None)
            if b is None:
                continue
            groups[b].append(r)
        elif key == "simple":
            groups["simple" if r["n_series"] <= 3 and r.get("density", 0) <= 0.5 else "hard"].append(r)
        else:
            v = p.get(key)
            if v is None:
                continue
            groups[str(v)].append(r)
    return groups


def report(groups, title):
    print(f"\n== by {title}")
    print(f"{'level':>18s} {'charts':>6s} {'gt':>6s} {'pred':>6s} {'recall':>7s} {'prec':>7s} {'err%':>6s}  FN stages | FP causes")

    def keyf(k):
        try:
            return float(k.split("-")[0])
        except ValueError:
            return k

    for lvl in sorted(groups, key=keyf):
        rs = groups[lvl]
        gt = sum(r["n_gt"] for r in rs)
        pr = sum(r["n_pred"] for r in rs)
        tp = sum(r["tp"] for r in rs)
        errs = [g["err_pct"] for r in rs for g in r["gt"] if g["stage"] == "ok"]
        fn = collections.Counter(g["stage"] for r in rs for g in r["gt"] if g["stage"] != "ok")
        fp = collections.Counter(p["cause"] for r in rs for p in r["pred"] if p["cause"] != "ok")
        fn_s = " ".join(f"{k}:{v}" for k, v in fn.most_common(4))
        fp_s = " ".join(f"{k}:{v}" for k, v in fp.most_common(4))
        print(f"{lvl:>18s} {len(rs):6d} {gt:6d} {pr:6d} {tp / max(gt, 1):7.3f} {tp / max(pr, 1):7.3f} "
              f"{np.median(errs) if errs else float('nan'):6.3f}  {fn_s} | {fp_s}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--by", nargs="*", default=None)
    a = ap.parse_args()
    rows = json.load(open(a.rows))
    gt = sum(r["n_gt"] for r in rows)
    pr = sum(r["n_pred"] for r in rows)
    tp = sum(r["tp"] for r in rows)
    print(f"{a.rows}: charts {len(rows)}  gt {gt}  pred {pr}  recall {tp / max(gt, 1):.3f}  precision {tp / max(pr, 1):.3f}")
    keys = a.by
    if keys is None:
        cand = collections.Counter()
        for r in rows:
            for k, v in (r.get("probe") or {}).items():
                if not isinstance(v, (list, dict)) and k not in ("kind", "nn_px_median", "nn_rel_median", "n_markers", "n", "ms_px"):
                    cand[k] += 1
        keys = [k for k in cand if len({str((r.get("probe") or {}).get(k)) for r in rows}) <= 12]
        keys = ["simple"] + keys + ["nn_rel", "ms_bin"]
    for k in keys:
        if k == "nn_rel":
            report(slice_rows(rows, "nn_rel", [0, 0.7, 0.9, 1.1, 1.4, 2.0, 3.0, 100]), "nearest-neighbour distance / marker diameter (measured)")
        elif k == "ms_bin":
            groups = collections.defaultdict(list)
            for r in rows:
                v = (r.get("probe") or {}).get("ms_px")
                if v is None:
                    continue
                bins = [0, 3, 4, 5, 6, 8, 10, 14, 100]
                b = next(f"{bins[i]}-{bins[i + 1]}" for i in range(len(bins) - 1) if bins[i] <= v < bins[i + 1])
                groups[b].append(r)
            if groups:
                report(groups, "marker size px")
        else:
            g = slice_rows(rows, k)
            if g:
                report(g, k)


if __name__ == "__main__":
    main()
