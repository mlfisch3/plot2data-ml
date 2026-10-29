"""Re-classify the label grouping of a diag.json against the label ink, and rewrite the summary.

The true `bbox` of a tick label is matplotlib's text extent, which includes font padding
around the glyphs; a predicted box that hugs the ink is not a cropped label. This pass
measures each predicted box against the bounding box of the TICK_LABEL pixels in the chart's
sem map, and reports how many pixels of ink were cut on which side when they were.

    python teams/t1-axis/reclass.py out/t1/diag-mpl data/mpl-val
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from p2d.synth.mpl_render import TICK_LABEL  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diag import norm_text  # noqa: E402


def ink_box(sem: np.ndarray, bbox, pad: int = 2):
    H, W = sem.shape
    x0, y0 = max(0, int(np.floor(bbox[0])) - pad), max(0, int(np.floor(bbox[1])) - pad)
    x1, y1 = min(W, int(np.ceil(bbox[2])) + pad + 1), min(H, int(np.ceil(bbox[3])) + pad + 1)
    m = sem[y0:y1, x0:x1] == TICK_LABEL
    ys, xs = np.nonzero(m)
    if not len(xs):
        return None
    return [x0 + xs.min(), y0 + ys.min(), x0 + xs.max(), y0 + ys.max()]


def classify(d: dict, sem: np.ndarray, data_dir: str) -> None:
    gt = d["gt"]
    inks = [ink_box(sem, g["bbox"]) for g in gt]
    for g, ib in zip(gt, inks):
        g["ink"] = ib
        b = g["bbox"]
        g["rotated"] = (b[2] - b[0]) < (b[3] - b[1]) * 0.9 and len(g["text"]) > 1
    d["rotated_labels"] = any(g["rotated"] for g in gt)
    for t in d["ticks"]:
        lb = t["label_box"]
        j = t.get("gt_index")
        if lb is None:
            t["group"] = "no_label"
            continue
        if j is None:
            t["group"] = "fp_tick"
            continue
        ib = inks[j]
        if ib is None:
            t["group"] = "ok"
            continue
        cut = {"left": ib[0] - lb[0], "right": lb[2] - ib[2], "top": ib[1] - lb[1], "bottom": lb[3] - ib[3]}
        cut = {k: float(-v) for k, v in cut.items() if v < -1.0}  # pixels of ink outside the box, by side
        t["cut"] = cut
        # Another label's ink inside this box?
        others = []
        for k, ob in enumerate(inks):
            if k == j or ob is None:
                continue
            w = min(lb[2], ob[2]) - max(lb[0], ob[0])
            h = min(lb[3], ob[3]) - max(lb[1], ob[1])
            if w > 0 and h > 0 and w * h / max(1.0, (ob[2] - ob[0]) * (ob[3] - ob[1])) > 0.3:
                others.append(k)
        t["others"] = others
        own_w = ib[2] - ib[0] + 1
        own_h = ib[3] - ib[1] + 1
        own_cov = (min(lb[2], ib[2]) - max(lb[0], ib[0]) + 1) * (min(lb[3], ib[3]) - max(lb[1], ib[1]) + 1) / (own_w * own_h)
        if own_cov < 0.3:
            t["group"] = "misgrouped" if others else "elsewhere"
        elif others:
            t["group"] = "merged"
        elif cut:
            t["group"] = "cropped"
        elif (lb[2] - lb[0]) > 1.5 * own_w + 8 or (lb[3] - lb[1]) > 1.5 * own_h + 8:
            t["group"] = "overgrown"
        else:
            t["group"] = "ok"
    d["n_misread"] = sum(1 for t in d["ticks"] if t.get("group") == "ok" and t.get("read_ok") is False)
    d["n_misgroup"] = sum(1 for t in d["ticks"] if t.get("group") in ("misgrouped", "merged", "elsewhere"))
    d["n_cropped"] = sum(1 for t in d["ticks"] if t.get("group") == "cropped")
    d["n_cropped_misread"] = sum(1 for t in d["ticks"] if t.get("group") == "cropped" and t.get("read_ok") is False)
    d["n_overgrown"] = sum(1 for t in d["ticks"] if t.get("group") == "overgrown")
    d["n_overgrown_misread"] = sum(1 for t in d["ticks"] if t.get("group") == "overgrown" and t.get("read_ok") is False)
    d["n_no_label"] = sum(1 for t in d["ticks"] if t.get("group") == "no_label" and t.get("gt_index") is not None)
    # Causes, in order of precedence.
    cause = []
    if d["offset_text"] and not d["factor"]:
        cause.append("multiplier_missed")
    elif d["offset_text"] and d["factor"]:
        cause.append("multiplier_read")
    if d["date_gt"] and not d["date_used"]:
        cause.append("date_not_used")
    if d["rotated_labels"]:
        cause.append("rotated")
    if d["n_misgroup"]:
        cause.append("misgrouped")
    if d["n_cropped_misread"]:
        cause.append("cropped")
    if d["n_overgrown_misread"]:
        cause.append("overgrown")
    if d["n_misread"]:
        cause.append("misread")
    if d["n_fp_read"]:
        cause.append("fp_tick_read")
    if d["n_unparsed"]:
        cause.append("unparsed")
    if d["n_no_label"] and d["n_no_label"] >= d["n_gt"] / 2:
        cause.append("most_labels_unclaimed")
    elif d["n_no_label"]:
        cause.append("some_labels_unclaimed")
    if d["n_read"] < 2:
        cause.append("fewer_than_2_read")
    elif d["n_read"] == 2:
        cause.append("two_read")
    if len(d["missed_gt"]) and len(d["missed_gt"]) >= d["n_gt"] / 2:
        cause.append("most_ticks_missed")
    if d["verdict"] != "ok" and np.isfinite(d["gt_parse_err"] if d["gt_parse_err"] is not None else np.nan) and \
            (d["gt_parse_err"] > 0.005 or d["gt_parse_scale"] != d["scale_gt"]):
        cause.append("parser_or_fitter")
    if d["verdict"] != "ok" and not cause:
        cause.append("unexplained")
    d["cause"] = cause


def summary(recs: list[dict]) -> str:
    lines = []
    n = len(recs)
    by_style = {}
    for r in recs:
        by_style.setdefault(r.get("preset") or "-", []).append(r)
    for axis in "xy":
        ds = [r[axis] for r in recs]
        ver = Counter(d["verdict"] for d in ds)
        lines.append(f"== {axis} axis over {n} charts: " + ", ".join(f"{k} {v}" for k, v in sorted(ver.items())))
        errs = np.array([np.nan if d["err"] is None else d["err"] for d in ds], float)
        o1 = np.array([np.nan if d["oracle_text_err"] is None else d["oracle_text_err"] for d in ds], float)
        o2 = np.array([np.nan if d["gt_parse_err"] is None else d["gt_parse_err"] for d in ds], float)
        within = lambda v: float(np.mean(np.nan_to_num(v, nan=1) < 0.005))  # noqa: E731
        lines.append(f"   within 0.5%: pipeline {within(errs):.3f}   true text on predicted ticks {within(o1):.3f}   "
                     f"true ticks through parser+fitter {within(o2):.3f}")
        sc_ok = np.mean([d["fit"] is not None and d["fit"]["scale"] == d["scale_gt"] for d in ds])
        sc1 = np.mean([d["oracle_text_scale"] == d["scale_gt"] for d in ds])
        sc2 = np.mean([d["gt_parse_scale"] == d["scale_gt"] for d in ds])
        lines.append(f"   scale right: pipeline {sc_ok:.3f}   true text {sc1:.3f}   true ticks {sc2:.3f}")
        bad = [d for d in ds if d["verdict"] != "ok"]
        cc = Counter(c for d in bad for c in d["cause"])
        lines.append(f"   causes among the {len(bad)} failing axes (several per axis): " + ", ".join(f"{k} {v}" for k, v in cc.most_common()))
        first = Counter(d["cause"][0] if d["cause"] else "none" for d in bad)
        lines.append("   first cause: " + ", ".join(f"{k} {v}" for k, v in first.most_common()))
        fixed = sum(1 for d in bad if np.nan_to_num(d["oracle_text_err"] if d["oracle_text_err"] is not None else np.nan, nan=1) <= 0.005
                    and d["oracle_text_scale"] == d["scale_gt"])
        lines.append(f"   failing axes that the true text on the predicted ticks would fix: {fixed}/{len(bad)}")
        tk = [t for d in ds for t in d["ticks"]]
        grp = Counter(t.get("group", "?") for t in tk)
        lines.append(f"   predicted ticks {len(tk)}: grouping " + ", ".join(f"{k} {v}" for k, v in grp.most_common()))
        for g in ("ok", "cropped", "overgrown"):
            rd = [t for t in tk if t.get("group") == g and "read_ok" in t]
            lines.append(f"   reads on '{g}' ticks: {sum(t['read_ok'] for t in rd)}/{len(rd)} exact")
            mis = Counter((norm_text(t["gt_text"]), norm_text(t["read"])) for t in rd if not t["read_ok"])
            lines.append(f"      misreads (true -> read): " + "; ".join(f"{g_}->{r} x{c}" for (g_, r), c in mis.most_common(40)))
        sides = Counter(s for t in tk if t.get("group") == "cropped" for s in t.get("cut", {}))
        lines.append("   cropped sides: " + ", ".join(f"{k} {v}" for k, v in sides.most_common()))
        mg = Counter((norm_text(t["gt_text"]), norm_text(t.get("read", ""))) for t in tk if t.get("group") in ("misgrouped", "merged", "elsewhere"))
        lines.append("   misgrouped/merged (true -> read): " + "; ".join(f"{g_}->{r} x{c}" for (g_, r), c in mg.most_common(30)))
        nl = [t for t in tk if t.get("group") == "no_label" and t.get("gt_index") is not None]
        nl_rot = sum(1 for d in ds for t in d["ticks"] if t.get("group") == "no_label" and t.get("gt_index") is not None and d["gt"][t["gt_index"]]["rotated"])
        lines.append(f"   true ticks found but given no label box: {len(nl)} (of which rotated labels {nl_rot}); "
                     f"true ticks with no prediction within 3 px: {sum(len(d['missed_gt']) for d in ds)}/{sum(d['n_gt'] for d in ds)}")
        unparsed = Counter(norm_text(t["read"]) for t in tk if "read" in t and t.get("value") is None and t.get("gt_index") is not None)
        lines.append("   unparsed reads: " + "; ".join(f"{k} x{v}" for k, v in unparsed.most_common(30)))
        lines.append("   failing charts: " + " ".join(f"{r['seed']}({r[axis]['verdict']}:{','.join(r[axis]['cause'])})" for r in recs if r[axis]["verdict"] != "ok"))
        if len(by_style) > 1:
            lines.append("   by style (within 0.5% / scale ok / n):")
            for st, rs in sorted(by_style.items()):
                e = np.array([np.nan if r[axis]["err"] is None else r[axis]["err"] for r in rs], float)
                s_ok = np.mean([r[axis]["fit"] is not None and r[axis]["fit"]["scale"] == r[axis]["scale_gt"] for r in rs])
                lines.append(f"      {st:22s} {within(e):.2f} / {s_ok:.2f} / {len(rs)}")
    return "\n".join(lines) + "\n"


def main(diag_dir: str, data_dir: str) -> None:
    recs = json.load(open(os.path.join(diag_dir, "diag.json")))
    for r in recs:
        stem = os.path.join(data_dir, f"{r['seed']:07d}")
        sem = cv2.imread(stem + ".sem.png", cv2.IMREAD_UNCHANGED)
        for axis in "xy":
            classify(r[axis], sem, data_dir)
    json.dump(recs, open(os.path.join(diag_dir, "diag.json"), "w"), default=float)
    s = summary(recs)
    open(os.path.join(diag_dir, "summary.txt"), "w").write(s)
    print(s)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
