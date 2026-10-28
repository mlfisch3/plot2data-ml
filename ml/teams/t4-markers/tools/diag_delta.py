"""Before/after delta from two `marker_diag.py` summary.json files.

    python teams/t4-markers/tools/diag_delta.py v3 step23 [--sets "dense row ..."]

For each set, prints a dense Markdown row with recall / precision / capped / error / FN by stage / FP by cause
and the deltas. The "before" tag is `v3` (frozen tree, probe sets have the drawn-centre GT so the "-v3d"
baselines were measured on the regenerated images); the "after" tag is whatever name the current branch's
diag was saved under (`step23`, `step1`, ...).
"""

from __future__ import annotations

import argparse
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "out", "t4")
SETS = ("dense", "row", "shapes", "labels", "hollow", "multi", "lines", "val", "plotly")
STAGES = ("taken", "peak_off", "no_heat", "no_peak", "unlabelled", "dropped", "moved")
CAUSES = ("dup", "line_ink", "marker_ink", "text", "legend", "bg", "grid", "axis")


def read(tag, s):
    p = os.path.join(ROOT, f"diag-{s}-{tag}", "summary.json")
    return json.load(open(p)) if os.path.exists(p) else None


def fmt_pct(a, b):
    if a is None or b is None:
        return "-"
    d = b - a
    return f"{b:.3f} ({d:+.3f})"


def fmt_num(a, b):
    if a is None or b is None:
        return "-"
    d = b - a
    return f"{b} ({d:+d})"


def fmt_dict(a, b, keys):
    out = []
    for k in keys:
        va, vb = (a or {}).get(k, 0), (b or {}).get(k, 0)
        if va == 0 and vb == 0:
            continue
        out.append(f"{k} {vb}({vb - va:+d})")
    return " ".join(out) if out else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--sets", default=None)
    a = ap.parse_args()
    sets = a.sets.split() if a.sets else SETS
    print(f"# diag delta: {a.before} -> {a.after}")
    print()
    print("| set | n gt | n pred (delta) | recall (delta) | prec (delta) | capped R / P | err % raw / drawn | FN stages | FP causes | FP line_ink (within 2 px) | TP within 2 px of a line |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for s in sets:
        A, B = read(a.before, s), read(a.after, s)
        if A is None and B is None:
            continue
        if A is None or B is None:
            tag = a.before if A is None else a.after
            print(f"| {s} | | | missing diag for {tag} | | | | | | | |")
            continue
        n_gt = B["n_gt"]
        n_pred = fmt_num(A["n_pred"], B["n_pred"])
        rec = fmt_pct(A["recall"], B["recall"])
        prec = fmt_pct(A["precision"], B["precision"])
        rc, pc = fmt_pct(A.get("recall_capped"), B.get("recall_capped")), fmt_pct(A.get("precision_capped"), B.get("precision_capped"))
        er, ed = fmt_pct(A.get("err_median_pct"), B.get("err_median_pct")), fmt_pct(A.get("err_drawn_median_pct"), B.get("err_drawn_median_pct"))
        fn = fmt_dict(A.get("fn_by_stage"), B.get("fn_by_stage"), STAGES)
        fp = fmt_dict(A.get("fp_by_cause"), B.get("fp_by_cause"), CAUSES)
        la = A.get("near_traced_line") or {}
        lb = B.get("near_traced_line") or {}
        line = f"{lb.get('fp_line_ink', 0)}({lb.get('fp_line_ink', 0) - la.get('fp_line_ink', 0):+d}) / {lb.get('fp_line_ink_within_2px', 0)}({lb.get('fp_line_ink_within_2px', 0) - la.get('fp_line_ink_within_2px', 0):+d})"
        tp_line = f"{lb.get('tp_within_2px', 0)}({lb.get('tp_within_2px', 0) - la.get('tp_within_2px', 0):+d}) / {lb.get('tp', 0)}"
        print(f"| {s} | {n_gt} | {n_pred} | {rec} ({rc}) | {prec} ({pc}) | {rc} / {pc} | {er} / {ed} | {fn} | {fp} | {line} | {tp_line} |")

    # Shape breakdown on the two standard sets, if present.
    print()
    print("## Error by shape (median %, matched markers)")
    for s in ("val", "plotly"):
        A, B = read(a.before, s), read(a.after, s)
        if not A or not B:
            continue
        print(f"\n### {s}: {a.before} -> {a.after}\n")
        print("| shape | n (before/after) | err before | err after | delta |")
        print("| --- | --- | --- | --- | --- |")
        ea = A.get("err_by_shape_median_pct") or {}
        eb = B.get("err_by_shape_median_pct") or {}
        shapes = sorted(set(ea) | set(eb))
        na = {k: v.get("n", 0) for k, v in (A.get("by_shape") or {}).items()}
        nb = {k: v.get("n", 0) for k, v in (B.get("by_shape") or {}).items()}
        for sh in shapes:
            va, vb = ea.get(sh), eb.get(sh)
            d = (vb - va) if (va is not None and vb is not None) else None
            print(f"| {sh} | {na.get(sh, 0)}/{nb.get(sh, 0)} | {va:.3f} | {vb:.3f} | {d:+.3f} |"
                  if va is not None and vb is not None else f"| {sh} | {na.get(sh, 0)}/{nb.get(sh, 0)} | - | - | - |")

    # Bias on the standard sets.
    print()
    print("## Returned-centre bias on isolated symmetric markers (source px)")
    print("| set | tag | n | dx mean / median | dy mean / median | abs median |")
    print("| --- | --- | --- | --- | --- | --- |")
    for s in ("val", "plotly"):
        for t in (a.before, a.after):
            S = read(t, s)
            if not S:
                continue
            b = S.get("bias_px_isolated_symmetric") or {}
            print(f"| {s} | {t} | {b.get('n', 0)} | {b.get('dx_mean', 0):+.3f} / {b.get('dx_median', 0):+.3f} | {b.get('dy_mean', 0):+.3f} / {b.get('dy_median', 0):+.3f} | {b.get('abs_median', 0):.3f} |")


if __name__ == "__main__":
    main()
