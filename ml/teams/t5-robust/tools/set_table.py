"""A markdown table of evaluate outputs over probe sets, before and after.

    python teams/t5-robust/tools/set_table.py --tags v3 23a5b7d --mode pixel --sets dpr1 dpr2 dpr3 chartjs-val half up2x jpeg50 jpeg30 blur dark clutter skew1

Reads out/t5/<set>-<tag>-<mode>.txt (the stdout of `p2d.evaluate`) and prints,
per set and tag, the headline metrics of the "all" column.
"""

from __future__ import annotations

import argparse
import os

KEYS = ["line_found", "line_good_cov_mean", "line_rms_median_pct", "peak_err_median_pct", "marker_recall", "marker_precision",
        "frame_err_median_px", "xticks_recall", "yticks_recall", "calib_x_within_0.5pct", "calib_y_within_0.5pct"]
SHORT = ["found", "good_cov", "rms_med%", "peak_med%", "mk_rec", "mk_prec", "frame_med_px", "xt_rec", "yt_rec", "calx<.5%", "caly<.5%"]


def parse(path: str, col: int = 1) -> dict[str, float]:
    out = {}
    if not os.path.exists(path):
        return out
    for ln in open(path):
        parts = ln.split()
        if len(parts) >= 3 and parts[0] != "metric":
            try:
                out[parts[0]] = float(parts[col])
            except ValueError:
                pass
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", nargs="+", required=True)
    ap.add_argument("--mode", default="pixel", choices=["pixel", "e2e"])
    ap.add_argument("--sets", nargs="+", required=True)
    ap.add_argument("--dir", default="out/t5")
    ap.add_argument("--simple", action="store_true", help="the simple split instead of all")
    a = ap.parse_args()
    col = 2 if a.simple else 1
    keys = [k for k in KEYS if a.mode == "e2e" or not k.startswith("calib")]
    short = [s for k, s in zip(KEYS, SHORT) if a.mode == "e2e" or not k.startswith("calib")]
    print("| set | tag | " + " | ".join(short) + " |")
    print("| --- | --- | " + " | ".join("---" for _ in short) + " |")
    for s in a.sets:
        for t in a.tags:
            d = parse(os.path.join(a.dir, f"{s}-{t}-{a.mode}.txt"), col)
            if not d:
                print(f"| {s} | {t} | " + " | ".join("-" for _ in short) + " |")
                continue
            print(f"| {s} | {t} | " + " | ".join(f"{d.get(k, float('nan')):.3f}" for k in keys) + " |")


if __name__ == "__main__":
    main()
