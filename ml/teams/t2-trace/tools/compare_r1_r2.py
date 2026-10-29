"""Compare integrated-model probe numbers to round-1 numbers.

Reads line_found all/simple (or any other metric) from:
  r1 frozen:   /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml/out/t2c/v3-<probe>-refine.txt
  r1 overlap:  /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml/out/t2c/live-overlap-merge-v3/<probe>-refine.txt
  r2 integ:    /tmp/claude-1000/.../scratchpad/t2-baseline/ml/out/t2r2-base/int-<probe>-refine.txt
  r2 fix:      /home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t2-trace/ml/out/t2r2/int-<probe>-refine.txt (if present)

Prints a markdown table that fills the probe-set section in CASES_R2.md / REPORT_R2_sections.md.

Usage:
  python ml/teams/t2-trace/tools/compare_r1_r2.py [metric]
  metric defaults to line_found; try line_cov_mean, line_rms_median_pct, peak_err_median_pct ...
"""
from __future__ import annotations
import os
import re
import sys

PROBES = ["ghostpair", "parallel", "shallowx", "legend", "legocclude", "multi", "wide", "area",
          "cross", "samecolour", "dotted", "steep", "thin", "small", "dense", "step", "clipped", "markers"]
R1_FROZEN = "/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml/out/t2c"
R1_OVERLAP = "/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml/out/t2c/live-overlap-merge-v3"
R2_BASE = "/tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/t2-baseline/ml/out/t2r2-base"
R2_FIX = "/home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t2-trace/ml/out/t2r2"


def _read(path: str, metric: str = "line_found") -> tuple[float | None, float | None]:
    if not os.path.exists(path):
        return None, None
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return None, None
    for line in text.splitlines():
        m = re.match(rf"^{re.escape(metric)}\s+([\d.na-]+)\s+([\d.na-]+)\s*$", line)
        if m:
            def _as_float(s: str) -> float | None:
                try:
                    return float(s)
                except ValueError:
                    return None
            return _as_float(m.group(1)), _as_float(m.group(2))
    return None, None


def _fmt(x: float | None) -> str:
    return "-" if x is None else f"{x:.4f}"


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "-"
    d = a - b
    return f"{'+' if d >= 0 else ''}{d:.4f}"


def main() -> None:
    metric = sys.argv[1] if len(sys.argv) > 1 else "line_found"
    print(f"\n### {metric}\n")
    cols = ["probe", "frozen v3", "r1 overlap", "integ 121ed4d", "r2 fix b5f1a32", "d_int-vs-r1", "d_fix-vs-int"]
    print("| " + " | ".join(cols) + " |")
    print("| " + " | ".join(["---"] * len(cols)) + " |")
    for p in PROBES:
        f_all, _ = _read(f"{R1_FROZEN}/v3-{p}-refine.txt", metric)
        o_all, _ = _read(f"{R1_OVERLAP}/{p}-refine.txt", metric)
        if o_all is None:
            o_all, _ = _read(f"{R1_OVERLAP}/{p}.txt", metric)
        i_all, _ = _read(f"{R2_BASE}/int-{p}-refine.txt", metric)
        x_all, _ = _read(f"{R2_FIX}/int-{p}-refine.txt", metric)
        print(f"| {p} | {_fmt(f_all)} | {_fmt(o_all)} | {_fmt(i_all)} | {_fmt(x_all)} | {_delta(i_all, o_all)} | {_delta(x_all, i_all)} |")


if __name__ == "__main__":
    main()
