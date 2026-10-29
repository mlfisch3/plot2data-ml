"""Compare integrated-model probe numbers to round-1 numbers.

Reads a chosen metric (default line_found) all/simple from:
  r1 frozen:   /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml/out/t2c/v3-<probe>-refine.txt
  r1 overlap:  /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml/out/t2c/live-overlap-merge-v3/<probe>-refine.txt
  r2 integ:    ml/out/t2r2/int-<probe>-refine.txt

Prints a markdown table that fills section 3 of CASES_R2.md.

Usage:
  python -m teams.t2-trace.tools.compare_r1_r2 [metric]
"""
from __future__ import annotations
import os
import re
import sys

PROBES = ["cross", "samecolour", "parallel", "shallowx", "legocclude", "legend", "dotted", "steep",
          "thin", "small", "dense", "area", "step", "clipped", "multi", "markers", "wide", "ghostpair"]
R1_FROZEN = "/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml/out/t2c"
R1_OVERLAP = "/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml/out/t2c/live-overlap-merge-v3"
R2_INT = "/home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t2-trace/ml/out/t2r2"


def _read(path: str, metric: str = "line_found") -> tuple[float | None, float | None]:
    """Return (all, simple) for `metric` from an evaluate-style output file."""
    if not os.path.exists(path):
        return None, None
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return None, None
    for line in text.splitlines():
        m = re.match(rf"^{re.escape(metric)}\s+([\d.nan-]+)\s+([\d.nan-]+)\s*$", line)
        if m:
            def _as_float(s: str) -> float | None:
                try:
                    return float(s)
                except ValueError:
                    return None
            return _as_float(m.group(1)), _as_float(m.group(2))
    return None, None


def _fmt(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x:.4f}"


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return "-"
    d = a - b
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.4f}"


def main() -> None:
    metric = sys.argv[1] if len(sys.argv) > 1 else "line_found"
    print(f"\n### {metric}\n")
    print(f"| probe | frozen v3 all | r1 overlap all | integrated all | d_int-vs-r1 | d_int-vs-frozen |")
    print("| --- | --- | --- | --- | --- | --- |")
    for p in PROBES:
        f_all, _ = _read(f"{R1_FROZEN}/v3-{p}-refine.txt", metric)
        o_all, _ = _read(f"{R1_OVERLAP}/{p}-refine.txt", metric)
        if o_all is None:
            o_all, _ = _read(f"{R1_OVERLAP}/{p}.txt", metric)
        i_all, _ = _read(f"{R2_INT}/int-{p}-refine.txt", metric)
        print(f"| {p} | {_fmt(f_all)} | {_fmt(o_all)} | {_fmt(i_all)} | {_delta(i_all, o_all)} | {_delta(i_all, f_all)} |")


if __name__ == "__main__":
    main()
