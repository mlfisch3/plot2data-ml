"""Per-chart TP/FP/FN delta from a before diag and an after diag (or a partial after from the diag's log).

    python teams/t4-markers/tools/perchart_delta.py <set> <before-tag> <after-tag> [--log]
                                                     [--worst-fn N] [--worst-fp N] [--best-fn N] [--best-fp N]

With `--log`, the after side is read from `out/t4/diag-<set>-<after>.log` (each line is one chart printed as the
run goes), which lets us peek before `summary.json` is written. Otherwise both sides come from `rows.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "out", "t4")

LINE = re.compile(r"^\s*(\d+)\s+gt\s+(\d+)\s+pred\s+(\d+)\s+tp\s+(\d+)\s+FN\s+(\d+)\s+FP\s+(\d+)")


def from_rows(path):
    rows = json.load(open(path))
    return {r["id"]: (r["n_gt"], r["n_pred"], r["tp"]) for r in rows}


def from_log(path):
    out = {}
    for line in open(path):
        m = LINE.match(line)
        if m:
            seed, gt, pred, tp, fn, fp = map(int, m.groups())
            out[seed] = (gt, pred, tp)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set")
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--worst-fn", type=int, default=10)
    ap.add_argument("--worst-fp", type=int, default=10)
    ap.add_argument("--best-fn", type=int, default=10)
    ap.add_argument("--best-fp", type=int, default=10)
    a = ap.parse_args()
    before = from_rows(os.path.join(ROOT, f"diag-{a.set}-{a.before}", "rows.json"))
    if a.log:
        after = from_log(os.path.join(ROOT, f"diag-{a.set}-{a.after}.log"))
    else:
        after = from_rows(os.path.join(ROOT, f"diag-{a.set}-{a.after}", "rows.json"))
    rows = []
    for seed, (gt, pb, tpb) in before.items():
        if seed not in after:
            continue
        _, pa, tpa = after[seed]
        rows.append(dict(seed=seed, gt=gt, pb=pb, tpb=tpb, pa=pa, tpa=tpa,
                         d_tp=tpa - tpb, d_fp=(pa - tpa) - (pb - tpb), d_fn=(gt - tpa) - (gt - tpb)))
    n = len(rows)
    tot_tp = sum(r["d_tp"] for r in rows)
    tot_fp = sum(r["d_fp"] for r in rows)
    tot_fn = sum(r["d_fn"] for r in rows)
    gt_total = sum(r["gt"] for r in rows)
    pb_total = sum(r["pb"] for r in rows)
    pa_total = sum(r["pa"] for r in rows)
    tpb_total = sum(r["tpb"] for r in rows)
    tpa_total = sum(r["tpa"] for r in rows)

    def pct(num, den):
        return f"{(num / den * 100 if den else 0):+.2f}%"

    print(f"{a.set}: {n} charts common, gt {gt_total}, pred before {pb_total} after {pa_total} (delta {pa_total - pb_total:+d}), tp before {tpb_total} after {tpa_total} (delta {tot_tp:+d})")
    print(f"recall before {tpb_total / gt_total:.4f} -> after {tpa_total / gt_total:.4f}; precision before {tpb_total / max(1, pb_total):.4f} -> after {tpa_total / max(1, pa_total):.4f}")
    print(f"sum of per-chart deltas: TP {tot_tp:+d}, FP {tot_fp:+d}, FN {tot_fn:+d}")

    def show(title, rows, key, n):
        print(f"\n{title} (top {n}):")
        for r in sorted(rows, key=key)[:n]:
            print(f"  {r['seed']}: gt={r['gt']} pred {r['pb']}->{r['pa']} tp {r['tpb']}->{r['tpa']}  dTP={r['d_tp']:+d} dFP={r['d_fp']:+d} dFN={r['d_fn']:+d}")

    show("worst recall loss (dTP most negative)", rows, lambda r: r["d_tp"], a.worst_fn)
    show("best recall gain (dTP most positive)", rows, lambda r: -r["d_tp"], a.best_fn)
    show("best FP reduction (dFP most negative)", rows, lambda r: r["d_fp"], a.worst_fp)
    show("worst FP gain (dFP most positive)", rows, lambda r: -r["d_fp"], a.best_fp)


if __name__ == "__main__":
    main()
