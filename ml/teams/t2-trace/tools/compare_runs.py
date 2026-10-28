"""Side-by-side comparison of two evaluate runs. Prints before/after for the key metrics.

    python teams/t2-trace/tools/compare_runs.py --a out/t2c/v3-val-refine.txt --b out/t2c/live-overlap-merge/val-refine.txt
    python teams/t2-trace/tools/compare_runs.py --dir-a out/t2c --dir-b out/t2c/live-overlap-merge --pattern 'v3-{name}-refine.txt' 'val-refine.txt' --probes cross samecolour parallel shallowx legocclude val plotly

The second form compares every probe set at once; .txt files are matched by name. Column deltas use the standard metrics.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys


METRICS = ["line_found", "line_cov_mean", "line_good_cov_mean",
           "line_rms_median_pct", "line_rms_p90_pct", "peak_err_median_pct", "peak_err_p90_pct",
           "marker_recall", "marker_precision"]


def read_metrics(path: str) -> dict:
    """Parse an evaluate text report: 'metric  all  simple' lines."""
    if not os.path.exists(path):
        return {}
    out = {}
    for ln in open(path):
        parts = ln.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        if name not in METRICS:
            continue
        try:
            all_val = float(parts[1])
            simple_val = float(parts[2]) if len(parts) > 2 else float("nan")
        except ValueError:
            continue
        out[name] = (all_val, simple_val)
    return out


def fmt_delta(a: float, b: float) -> str:
    if a != a or b != b:
        return "   nan"
    d = b - a
    sign = "+" if d >= 0 else "-"
    return f"{sign}{abs(d):.4f}"


def pretty_pair(name: str, a_vals: dict, b_vals: dict) -> list[str]:
    rows = []
    rows.append(f"-- {name}")
    rows.append(f"  {'metric':<30}  {'A all':>8}  {'B all':>8}  {'d_all':>8}   {'A simp':>8}  {'B simp':>8}  {'d_simp':>8}")
    for m in METRICS:
        a = a_vals.get(m, (float("nan"), float("nan")))
        b = b_vals.get(m, (float("nan"), float("nan")))
        rows.append(f"  {m:<30}  {a[0]:>8.4f}  {b[0]:>8.4f}  {fmt_delta(a[0], b[0]):>8}   {a[1]:>8.4f}  {b[1]:>8.4f}  {fmt_delta(a[1], b[1]):>8}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", help="single A file")
    ap.add_argument("--b", help="single B file")
    ap.add_argument("--dir-a", help="A directory")
    ap.add_argument("--dir-b", help="B directory")
    ap.add_argument("--probes", nargs="+", help="probe set names (expands pattern)")
    ap.add_argument("--pattern-a", default="v3-{name}-refine.txt", help="file-name pattern inside dir-a")
    ap.add_argument("--pattern-b", default="{name}-refine.txt", help="file-name pattern inside dir-b")
    a = ap.parse_args()
    lines = []
    if a.a and a.b:
        lines += pretty_pair(f"{a.a} vs {a.b}", read_metrics(a.a), read_metrics(a.b))
    elif a.dir_a and a.dir_b and a.probes:
        for name in a.probes:
            pa = os.path.join(a.dir_a, a.pattern_a.replace("{name}", name))
            pb = os.path.join(a.dir_b, a.pattern_b.replace("{name}", name))
            lines += pretty_pair(name, read_metrics(pa), read_metrics(pb))
    else:
        ap.error("provide --a/--b, or --dir-a/--dir-b/--probes")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
