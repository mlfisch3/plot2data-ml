"""Round-2 scoreboard tables.

Reads `out/t5r2/<name>.txt` (p2d.evaluate output) and prints the integrated
model's probe numbers alongside the round-1 base / V1-sub / V2-sub numbers
copied from CASES.md section 9.5 and 9.10.2.

Also reads the sem_mapping JSON fields from `data/t5r2-clutter-overlap/*.json`
to summarise chart_pixels_lost.

Usage:
    python teams/t5-robust/tools/r2_tables.py \\
        --out out/t5r2 --metric line_rms_median_pct --split simple

    python teams/t5-robust/tools/r2_tables.py --sem-mapping data/t5r2-clutter-overlap
"""

from __future__ import annotations

import argparse
import glob
import json
import os

# Baseline numbers copied from round-1 CASES.md section 9.5 and 9.10.2.
# Rows: (probe set, metric key) -> {source: value}.
# Metrics: 'line_rms_median_pct' (simple), 'peak_err_median_pct' (simple),
# 'marker_recall' (all), 'frame_err_median_px' (all), 'calib_y_err_median_pct' (all).
BASELINE = {
    "line_rms_median_pct": {  # simple split
        "blur":    {"base": 0.232, "v1": 0.163, "v2": 0.201},
        "dark":    {"base": 0.278, "v1": 0.222, "v2": 0.217},
        "clutter": {"base": 0.241, "v1": 0.168, "v2": 0.226},
        "half":    {"base": 0.213, "v1": 0.223, "v2": 0.191},
        "up2x":    {"base": 0.271, "v1": 0.099, "v2": 0.097},
        "jpeg50":  {"base": 0.212, "v1": 0.193, "v2": 0.206},
        "jpeg30":  {"base": 0.240, "v1": 0.215, "v2": 0.225},
        "skew1":   {"base": 2.803, "v1": 2.349, "v2": 2.310},
        "dpr1":    {"base": 0.223, "v1": 0.185, "v2": 0.173},
        "dpr2":    {"base": 0.249, "v1": 0.088, "v2": 0.109},
        "dpr3":    {"base": 0.373, "v1": 0.097, "v2": 0.106},
    },
    "marker_recall": {  # simple split
        "blur":    {"base": 0.499, "v1": 0.572, "v2": None},
        "dark":    {"base": 0.465, "v1": 0.582, "v2": None},
        "clutter": {"base": 0.387, "v1": 0.469, "v2": None},
        "dpr1":    {"base": 0.502, "v1": 0.533, "v2": 0.536},
        "dpr2":    {"base": 0.349, "v1": 0.326, "v2": 0.337},
        "dpr3":    {"base": 0.287, "v1": 0.286, "v2": 0.295},
    },
    "frame_err_median_px": {  # simple split
        "blur":    {"base": None, "v1": None, "v2": None},
        "dpr1":    {"base": 1.12, "v1": 0.81, "v2": 0.96},
        "dpr2":    {"base": 2.56, "v1": 1.26, "v2": 1.20},
        "dpr3":    {"base": 2.92, "v1": 1.45, "v2": 1.59},
    },
}

# Column index: 1 = "all", 2 = "simple".
SPLIT = {"all": 1, "simple": 2}


def parse(path: str, col: int) -> dict[str, float]:
    out: dict[str, float] = {}
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for ln in f:
            parts = ln.split()
            if len(parts) >= 3 and parts[0] != "metric":
                try:
                    out[parts[0]] = float(parts[col])
                except (ValueError, IndexError):
                    pass
    return out


def _get(d: dict | None, k: str) -> str:
    if d is None or k not in d or d[k] is None:
        return "-"
    v = d[k]
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def table(out_dir: str, metric: str, split: str) -> str:
    col = SPLIT[split]
    rows = BASELINE.get(metric, {})
    lines = [
        f"### {metric} ({split} split)",
        "",
        "| set | base | V1 sub | V2 sub | integrated | int - V2 | int - base |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, b in rows.items():
        file = os.path.join(out_dir, f"{name}.txt")
        parsed = parse(file, col)
        v_int = parsed.get(metric)
        v_v2 = b.get("v2")
        v_base = b.get("base")
        d_v2 = f"{v_int - v_v2:+.3f}" if v_int is not None and v_v2 is not None else "-"
        d_base = f"{v_int - v_base:+.3f}" if v_int is not None and v_base is not None else "-"
        lines.append(
            f"| {name} | {_get(b, 'base')} | {_get(b, 'v1')} | {_get(b, 'v2')} | "
            f"{_get({'i': v_int}, 'i')} | {d_v2} | {d_base} |"
        )

    # Round-2 clutter probes (no round-1 baseline).
    for name in ("r2-clutter-max", "r2-clutter-overlap"):
        file = os.path.join(out_dir, f"{name}.txt")
        parsed = parse(file, col)
        v_int = parsed.get(metric)
        lines.append(
            f"| {name} | - | - | - | {_get({'i': v_int}, 'i')} | - | - |"
        )
    return "\n".join(lines)


def sem_mapping(data_dir: str) -> str:
    """Summarise chart_pixels_lost across the clutter-overlap probe set."""
    from p2d.synth.mpl_render import AXIS, DATA, GRID, LEGEND_SYMBOL, TEXT, TICK_LABEL
    class_name = {int(DATA): "DATA", int(GRID): "GRID", int(TICK_LABEL): "TICK_LABEL",
                  int(AXIS): "AXIS", int(TEXT): "TEXT", int(LEGEND_SYMBOL): "LEGEND_SYMBOL"}

    per_class: dict[int, list[int]] = {c: [] for c in class_name}
    n_samples = 0
    overlap_counts: dict[str, int] = {}
    for jp in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        with open(jp) as f:
            m = json.load(f)
        n_samples += 1
        lost = m.get("sem_mapping", {}).get("chart_pixels_lost") or {}
        for k, v in lost.items():
            c = int(k)
            if c in per_class:
                per_class[c].append(int(v))
        for kind in m.get("clutter", {}).get("kinds", []):
            overlap_counts[kind] = overlap_counts.get(kind, 0) + 1

    import statistics
    lines = [
        "### Clutter overlap: pixel loss statistics",
        "",
        f"Samples: {n_samples} (from `{data_dir}`)",
        "",
        "| class | median loss (nonzero) | p90 loss (nonzero) | samples with loss |",
        "| --- | --- | --- | --- |",
    ]
    for c, name in class_name.items():
        vals = [v for v in per_class[c] if v > 0]
        if not vals:
            lines.append(f"| {name} | 0 | 0 | 0 |")
            continue
        med = statistics.median(vals)
        p90 = sorted(vals)[int(0.9 * (len(vals) - 1))]
        lines.append(f"| {name} | {med:.0f} | {p90} | {len(vals)} / {n_samples} |")

    lines.append("")
    lines.append("Overlay-kind frequency (one chart may have 1-3 kinds):")
    lines.append("")
    for k, v in sorted(overlap_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{k}`: {v} charts")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/t5r2")
    ap.add_argument("--metric", default="line_rms_median_pct",
                    choices=list(BASELINE.keys()))
    ap.add_argument("--split", default="simple", choices=["all", "simple"])
    ap.add_argument("--sem-mapping", default=None, help="data dir of clutter-overlap probe to summarise")
    a = ap.parse_args()
    if a.sem_mapping:
        print(sem_mapping(a.sem_mapping))
    else:
        print(table(a.out, a.metric, a.split))


if __name__ == "__main__":
    main()
