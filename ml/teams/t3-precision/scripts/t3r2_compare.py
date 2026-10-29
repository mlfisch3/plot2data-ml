#!/usr/bin/env python3
"""Side-by-side comparison of a probe-set evaluate.py output against a baseline.

    python teams/t3-precision/scripts/t3r2_compare.py out/t3r2/integ-peaks.txt \
        /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t3-precision/ml/out/t3/base-peaks.txt

Prints a per-metric table with ' (new / base: delta)'. Used to populate the
r2 CASES_R2.md section 3 after the integ probe batch lands.
"""
from __future__ import annotations

import sys


def parse(path: str) -> dict:
    out = {}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            # metric name may contain spaces. the last two columns are 'all' then 'simple'.
            try:
                simple = float(parts[-1])
                all_v = float(parts[-2])
                key = " ".join(parts[:-2])
                out[key] = (all_v, simple)
            except ValueError:
                continue
    return out


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: t3r2_compare.py NEW BASE")
    new_path, base_path = sys.argv[1], sys.argv[2]
    new = parse(new_path)
    base = parse(base_path)
    keys_order = [
        "line_found",
        "line_cov_mean",
        "line_good_cov_mean",
        "line_rms_median_pct",
        "line_rms_mean_pct",
        "line_rms_p90_pct",
        "peak_err_median_pct",
        "peak_err_p90_pct",
        "frame_err_median_px",
        "frame_err_p90_px",
        "xticks_err_median_px",
        "yticks_err_median_px",
    ]
    print(f"{'metric':<24}  {'base (all/simple)':>22}  {'new (all/simple)':>22}  {'delta all':>12}")
    for k in keys_order:
        if k not in new or k not in base:
            continue
        ba, bs = base[k]
        na, ns = new[k]
        delta = na - ba
        print(f"{k:<24}  {ba:>10.4f} / {bs:>8.4f}  {na:>10.4f} / {ns:>8.4f}  {delta:>+12.4f}")


if __name__ == "__main__":
    main()
