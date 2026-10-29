"""Per-axis calibration diagnosis over a synthetic set: what was read, grouped, cropped, fitted.

Run from ml/ with the venv active:

    python teams/t1-axis/diag.py --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --data data/mpl-val \
        --limit 200 --out out/t1/diag-mpl

Writes <out>/diag.json (one record per chart, per axis), <out>/summary.txt (the distribution of
failures and their causes), and <out>/<seed>.png overlays for every chart whose calibration failed,
with the text read beside each predicted label box (blue) and the true label beside its true box
(green) where the two differ.

Two cheap ablations run per axis without the GPU:
  oracle_text: the predicted ticks, with the true text substituted on every tick matched to a true
               tick (unmatched ticks keep their read) -> how much is reading and grouping.
  gt_parse:    the true ticks and true texts through parse_value / as_dates / fit_axis
               -> what the parser and the fitter lose on perfect input.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np

# The code under test: this worktree's ml/ by default, or a frozen copy named by P2D_ROOT (for the baseline).
sys.path.insert(0, os.environ.get("P2D_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from p2d.calibrate import fit_axis  # noqa: E402
from p2d.dates import resolve  # noqa: E402
from p2d.evaluate import calib_error, draw, gt_value_to_px, load_net  # noqa: E402
from p2d import ocr as _ocr  # noqa: E402
from p2d.ocr import crop, load_reader, read_crops  # noqa: E402
from p2d.pipeline import Result, run  # noqa: E402

# The frozen base's parse_value raises OverflowError on readings like 'e+01' or
# '1e+999' where int(exp) is huge; the live tree fixes it. Wrap it so the
# baseline diag can run against P2D_ROOT without patching the frozen tree.
_parse_value_raw = _ocr.parse_value


def _parse_value_safe(text):
    try:
        return _parse_value_raw(text)
    except (OverflowError, ValueError):
        return None


_ocr.parse_value = _parse_value_safe
# pipeline.py in the frozen base imports parse_value by name at module load; patch there too.
try:
    from p2d import pipeline as _pl  # noqa: E402

    if getattr(_pl, "parse_value", None) is _parse_value_raw:
        _pl.parse_value = _parse_value_safe
except Exception:
    pass
parse_value = _parse_value_safe


def norm_text(s: str) -> str:
    return s.replace(" ", "").replace("−", "-").replace("–", "-").strip()


def overlap(a, b) -> float:
    """Fraction of box b covered by box a."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    area_b = max((b[2] - b[0]) * (b[3] - b[1]), 1e-6)
    return w * h / area_b


def axis_error(meta: dict, axis: str, fit) -> float:
    pa = meta["plot_area"]
    lo, hi = (pa[0], pa[2]) if axis == "x" else (pa[1], pa[3])
    if fit is None:
        return float("nan")
    px = np.array([lo, hi])
    back = gt_value_to_px(meta, axis, fit.to_value(px))
    e = np.abs(back - px) / (hi - lo)
    return float(np.nanmax(e)) if np.any(np.isfinite(e)) else float("nan")


def as_dates(reads, axis: str):
    """The baseline's date rule on (pos, text, conf, value) tuples: mostly non-numeric labels that parse as dates."""
    numeric = sum(r[3] is not None for r in reads)
    if len(reads) < 2 or numeric >= len(reads) / 2:
        return reads
    order = sorted(range(len(reads)), key=lambda i: reads[i][0] if axis == "x" else -reads[i][0])
    vals = resolve([reads[i][1] for i in order])
    if sum(v is not None for v in vals) < 2:
        return reads
    out = list(reads)
    for i, v in zip(order, vals):
        p, t, c, _ = reads[i]
        out[i] = (p, t, c, v)
    return out


def fit_reads(reads, axis: str):
    """The plain fitter (calibrate.fit_axis) on tuple reads; an ablation of reading, not of the fitter under test."""
    reads = as_dates(reads, axis)
    return fit_axis([r[0] for r in reads], [np.nan if r[3] is None else r[3] for r in reads], [r[1] for r in reads])


def diagnose_axis(meta: dict, res: Result, axis: str, reader, gray) -> dict:
    gt = meta["xticks" if axis == "x" else "yticks"]
    pred = res.ex.xticks if axis == "x" else res.ex.yticks
    reads = res.tick_reads[axis]
    fit = res.xfit if axis == "x" else res.yfit
    pa = meta["plot_area"]
    span = (pa[2] - pa[0]) if axis == "x" else (pa[3] - pa[1])
    tol = 3.0
    d = {"axis": axis, "scale_gt": meta[axis + "scale"], "n_gt": len(gt), "n_pred": len(pred),
         "date_gt": meta.get("xdate") if axis == "x" else None, "offset_text": meta["offset_text"][0 if axis == "x" else 1],
         "gt": [{"pos": t["pos"], "text": t["text"], "value": t["value"], "bbox": t["bbox"]} for t in gt]}
    d["err"] = axis_error(meta, axis, fit)
    d["fit"] = None if fit is None else {"scale": fit.scale, "inliers": fit.inliers, "used": fit.used,
                                         "resid_px": fit.resid_px, "warnings": fit.warnings}
    d["date_used"] = bool(res.date_axes.get(axis, False))
    d["factor"] = next((w for w in res.warnings if w.startswith(axis + " axis: values scaled")), None)

    # Per predicted tick: the true tick it sits on, and what its label box covers.
    read_by_pos = {round(r[0], 3): r for r in reads}
    ticks = []
    matched_gt = set()
    for p in pred:
        t = {"pos": p["pos"], "label_box": p["label_box"], "score": p["score"]}
        j = int(np.argmin([abs(g["pos"] - p["pos"]) for g in gt])) if gt else None
        if j is not None and abs(gt[j]["pos"] - p["pos"]) <= tol:
            t["gt_index"] = j
            t["gt_text"] = gt[j]["text"]
            matched_gt.add(j)
        else:
            t["gt_index"] = None
        r = read_by_pos.get(round(p["pos"], 3))
        if r is not None:
            t["read"] = r[1]
            t["conf"] = r[2]
            t["value"] = r[3]
        lb = p["label_box"]
        if lb is not None and gt:
            cov = [overlap(lb, g["bbox"]) for g in gt]  # how much of each true label the box covers
            own = cov[j] if t["gt_index"] is not None else 0.0
            others = [(k, c) for k, c in enumerate(cov) if k != t["gt_index"] and c > 0.2]
            lbw = lb[2] - lb[0]
            lbh = lb[3] - lb[1]
            gw = (gt[j]["bbox"][2] - gt[j]["bbox"][0]) if t["gt_index"] is not None else 0
            gh = (gt[j]["bbox"][3] - gt[j]["bbox"][1]) if t["gt_index"] is not None else 0
            t["cover_own"] = own
            t["cover_others"] = others
            if t["gt_index"] is None:
                t["group"] = "fp_tick"
            elif others:
                t["group"] = "merged" if own >= 0.8 else "misgrouped"
            elif own < 0.8:
                t["group"] = "cropped"
            elif lbw > 1.6 * gw + 6 or lbh > 1.6 * gh + 6:
                t["group"] = "overgrown"
            else:
                t["group"] = "ok"
        elif lb is None:
            t["group"] = "no_label"
        if t.get("gt_index") is not None and "read" in t:
            t["read_ok"] = norm_text(t["read"]) == norm_text(t["gt_text"])
            t["parse_ok"] = t["value"] is not None and (t["gt_text"] == "" or abs(t["value"] - gt[j]["value"]) <= 1e-6 * max(1, abs(gt[j]["value"])) + 1e-9) \
                if not d["date_used"] and not d["factor"] else None
        ticks.append(t)
    d["ticks"] = ticks
    d["missed_gt"] = [k for k in range(len(gt)) if k not in matched_gt]
    d["n_read"] = sum(1 for t in ticks if "read" in t)
    d["n_fp"] = sum(1 for t in ticks if t.get("gt_index") is None)
    d["n_misread"] = sum(1 for t in ticks if t.get("group") == "ok" and t.get("read_ok") is False)
    d["n_misgroup"] = sum(1 for t in ticks if t.get("group") in ("misgrouped", "merged"))
    d["n_cropped"] = sum(1 for t in ticks if t.get("group") == "cropped")
    d["n_overgrown"] = sum(1 for t in ticks if t.get("group") == "overgrown")
    d["n_unparsed"] = sum(1 for t in ticks if "read" in t and t.get("value") is None)
    d["n_fp_read"] = sum(1 for t in ticks if t.get("gt_index") is None and "read" in t)

    # Ablation 1: oracle text on the predicted ticks.
    orc = []
    for t in ticks:
        if "read" not in t:
            continue
        txt = t["gt_text"] if t.get("gt_index") is not None else t["read"]
        orc.append((t["pos"], txt, 1.0, parse_value(txt)))
    f1 = fit_reads(orc, axis) if orc else None
    d["oracle_text_err"] = axis_error(meta, axis, f1)
    d["oracle_text_scale"] = f1.scale if f1 else None
    # Ablation 2: true ticks and texts, through the parser and the fitter.
    g2 = [(g["pos"], g["text"], 1.0, parse_value(g["text"])) for g in gt]
    f2 = fit_reads(g2, axis) if g2 else None
    d["gt_parse_err"] = axis_error(meta, axis, f2)
    d["gt_parse_scale"] = f2.scale if f2 else None

    # What the reader makes of the loose labels near this axis (multipliers live there).
    loose = []
    for b in res.ex.loose_labels:
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        near = (cy < pa[1] + 0.2 * (pa[3] - pa[1]) and axis == "y") or (cy > pa[3] - 5 and cx > pa[2] - 0.4 * (pa[2] - pa[0]) and axis == "x")
        if near and reader is not None:
            txt, conf = read_crops(reader, [crop(gray, b)])[0]
            loose.append({"box": [float(v) for v in b], "read": txt, "conf": conf})
    d["loose"] = loose

    # Verdict.
    if fit is None:
        d["verdict"] = "nofit"
    elif fit.scale != meta[axis + "scale"]:
        d["verdict"] = "scale"
    elif not np.isfinite(d["err"]) or d["err"] > 0.005:
        d["verdict"] = "err"
    else:
        d["verdict"] = "ok"
    # Cause, in a fixed order of precedence.
    cause = []
    if d["offset_text"] and not d["factor"]:
        cause.append("multiplier_missed")
    elif d["offset_text"] and d["factor"]:
        cause.append("multiplier_read")
    if d["date_gt"] and not d["date_used"]:
        cause.append("date_not_used")
    if d["n_misgroup"]:
        cause.append("misgrouped")
    if d["n_cropped"]:
        cause.append("cropped")
    if d["n_overgrown"]:
        cause.append("overgrown")
    if d["n_misread"]:
        cause.append("misread")
    if d["n_fp_read"]:
        cause.append("fp_tick_read")
    if d["n_unparsed"]:
        cause.append("unparsed")
    if d["n_read"] < 2:
        cause.append("fewer_than_2_read")
    elif d["n_read"] == 2:
        cause.append("two_read")
    if len(d["missed_gt"]) and len(d["missed_gt"]) >= len(gt) / 2:
        cause.append("most_ticks_missed")
    if d["verdict"] != "ok" and np.isfinite(d["gt_parse_err"]) and (d["gt_parse_err"] > 0.005 or d["gt_parse_scale"] != meta[axis + "scale"]):
        cause.append("parser_or_fitter")
    if d["verdict"] != "ok" and not cause:
        cause.append("unexplained")
    d["cause"] = cause
    return d


def draw_diag(img, meta, res, dx, dy):
    out = draw(img, res.ex, meta)
    H, W = out.shape[:2]
    scale = max(0.35, min(0.6, W / 1200))
    for d in (dx, dy):
        for g in d["gt"]:
            b = np.round(g["bbox"]).astype(int)
            cv2.rectangle(out, (b[0], b[1]), (b[2], b[3]), (0, 170, 0), 1)
        for t in d["ticks"]:
            if "read" not in t or t["label_box"] is None:
                continue
            b = np.round(t["label_box"]).astype(int)
            ok = t.get("read_ok", False) and t.get("group") == "ok"
            col = (0, 0, 255) if not ok else (120, 120, 255)
            txt = t["read"] + ("" if ok else f" [{t.get('group', '?')}" + (f" gt={t['gt_text']}]" if t.get("gt_index") is not None else "]"))
            x = b[0] if d["axis"] == "x" else max(0, b[0] - 2)
            y = b[3] + 12 if d["axis"] == "x" else b[1] - 2
            cv2.putText(out, txt, (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, scale, col, 1, cv2.LINE_AA)
    lines = []
    for d in (dx, dy):
        f = d["fit"]
        lines.append(f"{d['axis']}: {d['verdict']} err={d['err'] * 100:.2f}% scale={f['scale'] if f else '-'}/{d['scale_gt']} "
                     f"inl={f['inliers'] if f else 0}/{f['used'] if f else 0} cause={','.join(d['cause'])}")
    for i, l in enumerate(lines):
        cv2.putText(out, l, (4, 14 + 14 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 0, 0), 1, cv2.LINE_AA)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", required=True)
    ap.add_argument("--viz-all", action="store_true", help="overlays for every chart, not only the failures")
    ap.add_argument("--tta", default=None, help="pipeline tta mode (e.g. 'shift')")
    a = ap.parse_args()
    net, reader = load_net(a.ckpt), load_reader(a.ocr)
    os.makedirs(a.out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    recs = []
    for f in files:
        meta = json.load(open(f))
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        res = run(net, reader, img, tta=a.tta)
        dx = diagnose_axis(meta, res, "x", reader, gray)
        dy = diagnose_axis(meta, res, "y", reader, gray)
        rec = {"seed": meta["seed"], "preset": meta.get("preset"), "generator": meta.get("generator"), "font": meta.get("font"),
               "x": dx, "y": dy, "warnings": res.warnings}
        recs.append(rec)
        if a.viz_all or dx["verdict"] != "ok" or dy["verdict"] != "ok":
            cv2.imwrite(os.path.join(a.out, f"{meta['seed']}.png"), draw_diag(img, meta, res, dx, dy)[..., ::-1])
    json.dump(recs, open(os.path.join(a.out, "diag.json"), "w"), default=float)
    write_summary(recs, os.path.join(a.out, "summary.txt"))
    print(open(os.path.join(a.out, "summary.txt")).read())


def write_summary(recs: list[dict], path: str) -> None:
    from collections import Counter

    lines = []
    n = len(recs)
    for axis in "xy":
        ds = [r[axis] for r in recs]
        ver = Counter(d["verdict"] for d in ds)
        lines.append(f"== {axis} axis over {n} charts: " + ", ".join(f"{k} {v}" for k, v in sorted(ver.items())))
        errs = np.array([d["err"] for d in ds], float)
        o1 = np.array([d["oracle_text_err"] for d in ds], float)
        o2 = np.array([d["gt_parse_err"] for d in ds], float)
        within = lambda v, sc: float(np.mean(np.nan_to_num(v, nan=1) < 0.005))  # noqa: E731
        lines.append(f"   within 0.5%: pipeline {within(errs, 0):.3f}   oracle text on predicted ticks {within(o1, 0):.3f}   "
                     f"true ticks through parser+fitter {within(o2, 0):.3f}")
        sc_ok = np.mean([d["fit"] is not None and d["fit"]["scale"] == d["scale_gt"] for d in ds])
        sc1 = np.mean([d["oracle_text_scale"] == d["scale_gt"] for d in ds])
        sc2 = np.mean([d["gt_parse_scale"] == d["scale_gt"] for d in ds])
        lines.append(f"   scale right: pipeline {sc_ok:.3f}   oracle text {sc1:.3f}   true ticks {sc2:.3f}")
        bad = [d for d in ds if d["verdict"] != "ok"]
        cc = Counter(c for d in bad for c in d["cause"])
        lines.append(f"   causes among the {len(bad)} failing axes (an axis can have several): " +
                     ", ".join(f"{k} {v}" for k, v in cc.most_common()))
        first = Counter(d["cause"][0] if d["cause"] else "none" for d in bad)
        lines.append("   first cause: " + ", ".join(f"{k} {v}" for k, v in first.most_common()))
        # Does fixing the text alone fix it?
        fixed = sum(1 for d in bad if np.nan_to_num(d["oracle_text_err"], nan=1) <= 0.005 and d["oracle_text_scale"] == d["scale_gt"])
        lines.append(f"   failing axes that the true text on the predicted ticks would fix: {fixed}/{len(bad)}")
        # Tick-level counts.
        tk = [t for d in ds for t in d["ticks"]]
        grp = Counter(t.get("group", "?") for t in tk)
        lines.append(f"   predicted ticks {len(tk)}: grouping " + ", ".join(f"{k} {v}" for k, v in grp.most_common()))
        rd = [t for t in tk if t.get("group") == "ok" and "read_ok" in t]
        lines.append(f"   reads on correctly grouped ticks: {sum(t['read_ok'] for t in rd)}/{len(rd)} exact")
        mis = Counter((norm_text(t["gt_text"]), norm_text(t["read"])) for t in rd if not t["read_ok"])
        lines.append("   misreads (true -> read): " + "; ".join(f"{g}->{r} x{c}" for (g, r), c in mis.most_common(40)))
        crp = Counter((norm_text(t["gt_text"]), norm_text(t.get("read", ""))) for t in tk if t.get("group") == "cropped")
        lines.append("   cropped (true -> read): " + "; ".join(f"{g}->{r} x{c}" for (g, r), c in crp.most_common(30)))
        mg = Counter((norm_text(t["gt_text"]), norm_text(t.get("read", ""))) for t in tk if t.get("group") in ("misgrouped", "merged"))
        lines.append("   misgrouped/merged (true -> read): " + "; ".join(f"{g}->{r} x{c}" for (g, r), c in mg.most_common(30)))
        missed = sum(len(d["missed_gt"]) for d in ds)
        ngt = sum(d["n_gt"] for d in ds)
        lines.append(f"   true ticks with no prediction within 3 px: {missed}/{ngt}")
        lines.append("   failing charts: " + " ".join(f"{r['seed']}({r[axis]['verdict']}:{','.join(r[axis]['cause'])})" for r in recs if r[axis]["verdict"] != "ok"))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
