"""Round-2 tick-measurement diagnostic: joint affine vs shift-only vs no refine.

    python -m p2d.eval_ticks_r2 --ckpt runs/t5-chartjs/best.pt --data data/t3-ticks-r2 \
        --limit 500 --tta shift --out out/t3r2/ticks.json

For every probe chart the network is run once and the extraction's per-axis
tick marks are collected via `refine_ticks`. Three policies are then evaluated
offline on those marks, so the per-tick geometry work is paid once:

  - none: the network's position itself (`pos_net`).
  - shift: the current (frozen baseline) median-shift correction, gated by
    `min_shift` and `max_spread`.
  - affine: the joint `mark = a + b * pos_net` fit now in extract.refine_ticks
    (shift-only when N<=4 marks, full affine with slope-identifiability window
    when N>=5).

For each policy the per-tick error against the probe's ground-truth
`pos_canvas` is bucketed by factor (axis N_marks, axis_style, dpi,
label_density, grid, label_rotation, has_offset). The report prints p50 / p90
of |error| for each policy under each factor level.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os

import cv2
import numpy as np

from .extract import _affine_from_marks, extract, refine_lines, refine_ticks, run_net
from .evaluate import load_net
from .tta import run_net_tta


def _shift_only(pos_net: np.ndarray, marks: np.ndarray, min_shift: float, max_spread: float):
    """What the baseline refine_ticks would have applied, as an array to add to pos_all."""
    if len(pos_net) < 3:
        return None
    sh = marks - pos_net
    med = float(np.median(sh))
    if abs(med) < min_shift or float(np.median(np.abs(sh - med))) > max_spread:
        return None
    return med


def _match_to_truth(pred_pos: np.ndarray, truth_pos: np.ndarray, max_dist: float = 6.0):
    """Nearest-neighbour match, each truth tick to the closest predicted tick within max_dist.

    Returns an int array of length len(truth_pos) with the matched index into
    pred_pos, or -1 for a truth tick with no match."""
    out = -np.ones(len(truth_pos), int)
    if len(pred_pos) == 0:
        return out
    for i, tp in enumerate(truth_pos):
        j = int(np.argmin(np.abs(pred_pos - tp)))
        if abs(pred_pos[j] - tp) <= max_dist:
            out[i] = j
    return out


def _axis_errors(ticks_pred: list[dict], truth_axis: dict, axis_name: str,
                 min_shift: float, max_spread: float, resid_tol: float):
    """Per-tick (truth_pos, net_err, shift_err, affine_err) rows for one axis."""
    truth_ticks = truth_axis["ticks"]
    truth_pos = np.array([t["pos_canvas"] for t in truth_ticks if not t.get("is_minor")], float)
    if len(truth_pos) == 0 or len(ticks_pred) == 0:
        return [], 0
    pos_net = np.array([t.get("pos_net", t["pos"]) for t in ticks_pred], float)
    pos_now = np.array([t["pos"] for t in ticks_pred], float)
    marks = np.array([t.get("mark", np.nan) for t in ticks_pred], float)
    strength = np.array([t.get("mark_strength", 1.0) for t in ticks_pred], float)
    have_mark = np.isfinite(marks)
    pn_m, m_m, s_m = pos_net[have_mark], marks[have_mark], strength[have_mark]
    n_marks = int(have_mark.sum())
    # shift-only (baseline) applied to pos_net:
    shift_delta = _shift_only(pn_m, m_m, min_shift, max_spread) if n_marks >= 3 else None
    pos_shift = pos_net + (shift_delta or 0.0)
    # affine fit (what the integrated refine_ticks has already done):
    pos_affine = pos_now
    # Match truth to pred by nearest pos_net (closest to where the network put them).
    match = _match_to_truth(pos_net, truth_pos)
    rows = []
    for i, j in enumerate(match):
        if j < 0:
            rows.append(dict(truth=float(truth_pos[i]), matched=False))
            continue
        rows.append(dict(
            truth=float(truth_pos[i]),
            matched=True,
            net=float(pos_net[j]),
            shift=float(pos_shift[j]),
            affine=float(pos_affine[j]),
            err_net=float(pos_net[j] - truth_pos[i]),
            err_shift=float(pos_shift[j] - truth_pos[i]),
            err_affine=float(pos_affine[j] - truth_pos[i]),
            has_mark=bool(have_mark[j]),
        ))
    return rows, n_marks


def process_chart(net, reader, img, meta, native: bool, tta: str | None,
                  min_shift: float, max_spread: float, resid_tol: float):
    """Returns per-chart rows (one per tick) and chart-level factor dict."""
    device = str(next(net.parameters()).device)
    if tta:
        out, M = run_net_tta(net, img, native=native, tta=tta, device=device)
    else:
        out, M = run_net(net, img, device=device, native=native)
    ex = extract(out, M, img)
    ex = refine_lines(img, ex)
    ex = refine_ticks(img, ex, min_shift=min_shift, max_spread=max_spread, resid_tol=resid_tol)
    probe = meta.get("probe", {})
    out_rows = []
    for axis_key, name in (("xticks", "x"), ("yticks", "y")):
        axis_truth = probe.get("axes", {}).get(name, {})
        if not axis_truth:
            continue
        rows, n_marks = _axis_errors(getattr(ex, axis_key), axis_truth, name,
                                     min_shift, max_spread, resid_tol)
        factors = dict(
            axis=name,
            n_ticks=axis_truth.get("n_ticks", len(axis_truth.get("ticks", []))),
            axis_style=axis_truth.get("axis_style"),
            label_density=axis_truth.get("label_density"),
            grid=axis_truth.get("grid"),
            label_rotation=axis_truth.get("label_rotation"),
            has_offset=bool(probe.get("has_offset", False)) and (name == "y"),
            dpi=probe.get("dpi"),
            n_marks=n_marks,
        )
        for r in rows:
            r.update(factors)
            out_rows.append(r)
    return out_rows


def summary_table(rows: list[dict], factor: str, levels=None):
    """|err| p50/p90 under each level of a factor, for each policy."""
    matched = [r for r in rows if r.get("matched")]
    if not matched:
        return [{"level": "ALL", "n": 0}]
    if levels is None:
        levels = sorted({r.get(factor) for r in matched}, key=lambda v: (v is None, v))
    out = []
    for lv in levels:
        sub = [r for r in matched if r.get(factor) == lv]
        if not sub:
            continue
        row = {"level": lv, "n": len(sub)}
        for p in ("net", "shift", "affine"):
            e = np.array([abs(r[f"err_{p}"]) for r in sub])
            row[f"{p}_p50"] = float(np.median(e))
            row[f"{p}_p90"] = float(np.percentile(e, 90))
            row[f"{p}_mean"] = float(np.mean(e))
        out.append(row)
    return out


def _print_block(name, rows_tbl):
    print(f"\n--- {name} ---")
    header = f"{'level':>10} {'n':>5}  {'net p50':>8} {'net p90':>8}  {'shift p50':>9} {'shift p90':>9}  {'aff p50':>8} {'aff p90':>8}"
    print(header)
    for r in rows_tbl:
        if "net_p50" not in r:
            continue
        print(f"{str(r['level']):>10} {r['n']:>5}  {r['net_p50']:>8.3f} {r['net_p90']:>8.3f}  "
              f"{r['shift_p50']:>9.3f} {r['shift_p90']:>9.3f}  {r['affine_p50']:>8.3f} {r['affine_p90']:>8.3f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=None, help="write per-tick rows as JSON lines")
    ap.add_argument("--tta", default=None)
    ap.add_argument("--native", default="1")
    ap.add_argument("--min-shift", type=float, default=0.45)
    ap.add_argument("--max-spread", type=float, default=0.45)
    ap.add_argument("--resid-tol", type=float, default=0.35)
    args = ap.parse_args(argv)

    net = load_net(args.ckpt)
    paths = sorted(glob.glob(os.path.join(args.data, "*.png")))
    paths = [p for p in paths if not p.endswith(".sem.png") and not p.endswith(".inst.png")]
    if args.limit:
        paths = paths[:args.limit]
    rows: list[dict] = []
    out_fh = open(args.out, "w") if args.out else None
    native = args.native not in ("0", "false", "False")
    for i, p in enumerate(paths):
        with open(p[:-4] + ".json") as fh:
            meta = json.load(fh)
        img = cv2.imread(p, cv2.IMREAD_COLOR)[..., ::-1]
        try:
            r = process_chart(net, None, img, meta, native, args.tta,
                              args.min_shift, args.max_spread, args.resid_tol)
        except Exception as exc:
            r = [dict(seed=meta.get("seed"), error=str(exc))]
        for row in r:
            row["seed"] = meta.get("seed")
            rows.append(row)
            if out_fh:
                out_fh.write(json.dumps(row) + "\n")
        if (i + 1) % 25 == 0:
            print(f"  {i + 1} / {len(paths)}", flush=True)
    if out_fh:
        out_fh.close()
    # Headlines
    matched = [r for r in rows if r.get("matched")]
    print(f"\nCharts: {len(paths)}; matched ticks: {len(matched)}; unmatched: "
          f"{sum(1 for r in rows if r.get('matched') is False)}")
    _print_block("ALL", summary_table(rows, "axis", levels=["x", "y", None]))
    _print_block("by n_marks (axis-level marks found)", summary_table(rows, "n_marks"))
    _print_block("by n_ticks (visible major ticks)", summary_table(rows, "n_ticks"))
    _print_block("by axis_style", summary_table(rows, "axis_style"))
    _print_block("by label_rotation", summary_table(rows, "label_rotation"))
    _print_block("by label_density", summary_table(rows, "label_density"))
    _print_block("by grid", summary_table(rows, "grid"))
    _print_block("by has_offset (y-axis only)", summary_table(rows, "has_offset"))
    _print_block("by dpi", summary_table(rows, "dpi"))


if __name__ == "__main__":
    main()
