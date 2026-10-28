"""Per-chart evaluation rows (evaluate --json) split by canvas scale and by preset.

    python teams/t5-robust/tools/rows_by.py out/t5/v3-mplval-rows.json data/mpl-val [--bins 0.5,0.72,1.0,2.0]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))

from p2d.metrics import summarise  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("data")
    ap.add_argument("--bins", default="0.45,0.6,0.75,1.0,2.01")
    a = ap.parse_args()
    rows = json.load(open(a.rows))["rows"]
    edges = [float(v) for v in a.bins.split(",")]
    for r in rows:
        m = json.load(open(os.path.join(a.data, f"{r['id']:07d}.json")))
        r["scale"] = min(768 / m["width"], 512 / m["height"], 2.0)
        r["preset"] = m.get("preset", "none")
        r["style"] = m.get("style", "")
        r["w"], r["h"] = m["width"], m["height"]
        r["simple"] = r["n_series"] <= 3 and r["density"] <= 0.5

    keys = ["images", "line_found", "line_good_cov_mean", "line_rms_median_pct", "peak_err_median_pct", "marker_recall",
            "marker_precision", "frame_found", "frame_err_median_px", "frame_err_p90_px", "xticks_recall", "yticks_recall",
            "xticks_err_median_px", "yticks_err_median_px"]

    def table(groups: list[tuple[str, list[dict]]]) -> None:
        print(f"{'group':26s}" + "".join(f"{k[:14]:>15s}" for k in keys))
        for name, rs in groups:
            if not rs:
                continue
            s = summarise(rs)
            print(f"{name:26s}" + "".join(f"{s[k]:>15.3f}" if isinstance(s[k], float) else f"{s[k]:>15d}" for k in keys))

    print("== by canvas scale (all charts)")
    groups = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        groups.append((f"scale [{lo:.2f},{hi:.2f})", [r for r in rows if lo <= r["scale"] < hi]))
    table(groups)
    print("== by canvas scale (simple charts)")
    table([(n, [r for r in rs if r["simple"]]) for n, rs in groups])
    print("== by preset (all charts)")
    presets = sorted({r["preset"] for r in rows})
    table([(p, [r for r in rows if r["preset"] == p]) for p in presets])
    print("== frame: fraction None, fraction > 5 px, by preset")
    for p in presets:
        rs = [r for r in rows if r["preset"] == p]
        fe = np.array([r["frame_err_px"] for r in rs], float)
        print(f"{p:16s} n {len(rs):4d}  none {np.mean(np.isnan(fe)):.2f}  >5px {np.mean(np.nan_to_num(fe, nan=1e9) > 5):.2f}  "
              f"median {np.nanmedian(fe) if np.any(~np.isnan(fe)) else float('nan'):.2f}")
    print("== worst 15 by line_good_cov (simple charts)")
    simple = [r for r in rows if r["simple"] and r["line_cov"]]
    simple.sort(key=lambda r: np.mean(r["line_good"]))
    for r in simple[:15]:
        print(f"{r['id']:07d} preset {r['preset']:10s} style {r['style'][:18]:18s} {r['w']}x{r['h']} scale {r['scale']:.2f} "
              f"good {np.mean(r['line_good']):.2f} cov {np.mean(r['line_cov']):.2f} frame {r['frame_err_px']:.1f} "
              f"xt {r['xticks_recall']:.2f} yt {r['yticks_recall']:.2f}")


if __name__ == "__main__":
    main()
