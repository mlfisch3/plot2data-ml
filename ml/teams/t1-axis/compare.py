"""Before/after of two diag runs: what moved, what did not, which charts flipped.

    python teams/t1-axis/compare.py out/t1/diag-mpl out/t1/s1/diag-mpl
    python teams/t1-axis/compare.py out/t1/diag-probe-base out/t1/s1/diag-probe --by-style

Prints, per axis: within 0.5% and scale right before/after; the failing-axis counts by first cause before/after;
per style (probe sets) within 0.5% before/after on the axis under test; and the charts that were fixed or broken,
with their causes, so a regression is never hidden in an average.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter

import numpy as np


def load(d):
    recs = json.load(open(os.path.join(d, "diag.json")))
    return {r["seed"]: r for r in recs}


def within(d):
    e = d["err"]
    return e is not None and np.isfinite(e) and e <= 0.005 and d["fit"] is not None and d["fit"]["scale"] == d["scale_gt"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--by-style", action="store_true")
    ap.add_argument("--max-list", type=int, default=40)
    a = ap.parse_args()
    B, A = load(a.before), load(a.after)
    seeds = sorted(set(B) & set(A))
    print(f"charts in both: {len(seeds)} (before {len(B)}, after {len(A)})")
    for axis in "xy":
        wb = np.array([within(B[s][axis]) for s in seeds])
        wa = np.array([within(A[s][axis]) for s in seeds])
        sb = np.array([B[s][axis]["fit"] is not None and B[s][axis]["fit"]["scale"] == B[s][axis]["scale_gt"] for s in seeds])
        sa = np.array([A[s][axis]["fit"] is not None and A[s][axis]["fit"]["scale"] == A[s][axis]["scale_gt"] for s in seeds])
        fb = np.array([B[s][axis]["fit"] is not None for s in seeds])
        fa = np.array([A[s][axis]["fit"] is not None for s in seeds])
        print(f"\n== {axis}: within 0.5% and scale right {wb.mean():.3f} -> {wa.mean():.3f}   scale right {sb.mean():.3f} -> {sa.mean():.3f}   "
              f"fitted {fb.mean():.3f} -> {fa.mean():.3f}   fixed {int((~wb & wa).sum())}  broken {int((wb & ~wa).sum())}")
        cb = Counter(B[s][axis]["cause"][0] if B[s][axis]["cause"] else "none" for s in seeds if not within(B[s][axis]))
        ca = Counter(A[s][axis]["cause"][0] if A[s][axis]["cause"] else "none" for s in seeds if not within(A[s][axis]))
        keys = sorted(set(cb) | set(ca), key=lambda k: -(cb[k] + ca[k]))
        print("   first cause of the failing axes, before -> after: " + ", ".join(f"{k} {cb[k]}->{ca[k]}" for k in keys))
        fixed = [s for s in seeds if not within(B[s][axis]) and within(A[s][axis])]
        broken = [s for s in seeds if within(B[s][axis]) and not within(A[s][axis])]
        if fixed:
            print(f"   fixed ({len(fixed)}): " + " ".join(f"{s}[{','.join(B[s][axis]['cause'])}]" for s in fixed[: a.max_list]))
        if broken:
            print(f"   BROKEN ({len(broken)}): " + " ".join(f"{s}[{','.join(A[s][axis]['cause'])} err={100 * (A[s][axis]['err'] or float('nan')):.2f}%]" for s in broken[: a.max_list]))
        if a.by_style:
            styles = sorted({B[s].get("preset") for s in seeds})
            print("   by style (within 0.5% and scale right, before -> after, n):")
            for st in styles:
                ss = [s for s in seeds if B[s].get("preset") == st]
                b = np.mean([within(B[s][axis]) for s in ss])
                aa = np.mean([within(A[s][axis]) for s in ss])
                flag = "  <-- worse" if aa < b - 1e-9 else ""
                print(f"      {st:24s} {b:.3f} -> {aa:.3f}  n={len(ss)}{flag}")
    # Tick-level: reads on the probe axis.
    for axis in "xy":
        rb = [t for s in seeds for t in B[s][axis]["ticks"] if "read_ok" in t]
        ra = [t for s in seeds for t in A[s][axis]["ticks"] if "read_ok" in t]
        nb = sum(1 for s in seeds for t in B[s][axis]["ticks"] if t.get("group") == "no_label" and t.get("gt_index") is not None)
        na = sum(1 for s in seeds for t in A[s][axis]["ticks"] if t.get("group") == "no_label" and t.get("gt_index") is not None)
        print(f"\n{axis} ticks: read exactly {sum(t['read_ok'] for t in rb)}/{len(rb)} -> {sum(t['read_ok'] for t in ra)}/{len(ra)}; "
              f"true ticks found but without a box {nb} -> {na}")


if __name__ == "__main__":
    main()
