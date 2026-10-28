"""How often end-to-end calibration lands within 0.5% of the truth, per axis.

    python -m p2d.eval_calib --ckpt runs/v1/best.pt --ocr runs/ocr1/best.pt --data data/mpl-val --limit 100

With `--json`, every axis of every chart is written out in detail (the true
ticks, the ticks found, what was read off each label, the fit, the error), which
is what a diagnosis of calibration failures works from.
"""

from __future__ import annotations

import argparse
import glob
import json
import os

import cv2
import numpy as np

from .evaluate import calib_error, load_net
from .ocr import load_reader
from .pipeline import run


def axis_record(meta: dict, res, axis: str) -> dict:
    """Everything about one axis of one chart: truth, detection, reading, fit."""
    ex = res.ex
    fit = res.xfit if axis == "x" else res.yfit
    gt = meta["xticks"] if axis == "x" else meta["yticks"]
    pred = ex.xticks if axis == "x" else ex.yticks
    reads = {round(r[0], 3): r for r in res.tick_reads.get(axis, [])}
    out = {
        "scale": meta[axis + "scale"],
        "date": meta.get("xdate") if axis == "x" else None,
        "offset_text": meta.get("offset_text", ["", ""])[0 if axis == "x" else 1],
        "true": [{"pos": t["pos"], "value": t["value"], "text": t["text"], "bbox": t["bbox"]} for t in gt],
        "pred": [],
        "fit": None,
        "read_as_dates": bool(res.date_axes.get(axis, False)),
        "warnings": [w for w in res.warnings if w.startswith(axis + " axis")],
    }
    for t in pred:
        r = reads.get(round(t["pos"], 3))
        out["pred"].append({"pos": t["pos"], "pos_net": t.get("pos_net"), "score": t["score"], "label_box": t["label_box"],
                            "text": None if r is None else r[1], "conf": None if r is None else r[2],
                            "value": None if r is None else r[3]})
    if fit is not None:
        out["fit"] = {"scale": fit.scale, "a": fit.a, "b": fit.b, "inliers": fit.inliers, "used": fit.used,
                      "resid_px": fit.resid_px}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--json", default=None, help="write every axis's truth, reads and fit here")
    a = ap.parse_args()
    net, reader = load_net(a.ckpt), load_reader(a.ocr)
    bad = {"x": 0, "y": 0}
    errs = {"x": [], "y": []}
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    records = []
    for f in files:
        m = json.load(open(f))
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        res = run(net, reader, img)
        ce = calib_error(m, res)
        for ax in "xy":
            e = ce[ax]
            errs[ax].append(e)
            if not np.isfinite(e) or e > 0.005:
                bad[ax] += 1
        if a.json:
            rec = {"id": m["seed"], "file": f, "plot_area": m["plot_area"], "preset": m.get("preset"),
                   "loose_labels": res.ex.loose_labels}
            for ax in "xy":
                rec[ax] = axis_record(m, res, ax)
                rec[ax]["err"] = None if not np.isfinite(ce[ax]) else float(ce[ax])
                rec[ax]["scale_ok"] = bool(ce.get(ax + "_scale_ok", False))
            records.append(rec)
    for ax in "xy":
        v = np.array(errs[ax], float)
        print(f"{ax}: within 0.5% {1 - bad[ax] / len(files):.0%}  median error {np.nanmedian(v) * 100:.3f}%  "
              f"no fit {np.isnan(v).sum()}")
    if a.json:
        json.dump(records, open(a.json, "w"), default=float)


if __name__ == "__main__":
    main()
