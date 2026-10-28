"""Calibration without the GPU in the loop: cache PlotNet's tick detections once, then iterate the reader
and the decoder on the CPU.

    python teams/t1-axis/offline.py cache --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --out out/t1/cache-mpl.json
    python teams/t1-axis/offline.py eval --cache out/t1/cache-mpl.json --ocr runs/ocr1/best.pt [--json out.json] [--plain]

`eval` prints the same three numbers per axis as p2d.eval_calib and, with --json, the same per-axis records.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

import cv2
import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from p2d.eval_calib import axis_record  # noqa: E402
from p2d.evaluate import calib_error, load_net  # noqa: E402
from p2d.extract import Extraction, extract, refine_labels, refine_ticks, run_net  # noqa: E402
from p2d.ocr import load_reader  # noqa: E402
from p2d import pipeline  # noqa: E402


def cache(a) -> None:
    net = load_net(a.ckpt)
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    out = []
    t0 = time.time()
    for i, f in enumerate(files):
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        o, M = run_net(net, img)
        ex = extract(o, M, img)
        ex = refine_ticks(img, ex)
        out.append({"file": f, "M": ex.M.tolist(), "plot_area": ex.plot_area, "xticks": ex.xticks, "yticks": ex.yticks,
                    "loose_labels": ex.loose_labels})
        if (i + 1) % 25 == 0:
            print(f"{i + 1}/{len(files)} {time.time() - t0:.0f}s", flush=True)
    json.dump(out, open(a.out, "w"), default=float)


def evaluate(a) -> None:
    device = "cuda" if a.gpu else "cpu"
    reader = load_reader(a.ocr, device=device)
    recs = json.load(open(a.cache))
    if a.limit:
        recs = recs[: a.limit]
    bad = {"x": 0, "y": 0}
    errs = {"x": [], "y": []}
    records = []
    t0 = time.time()
    for rec in recs:
        meta = json.load(open(rec["file"]))
        img = cv2.imread(rec["file"][:-5] + ".png")[..., ::-1].copy()
        ex = Extraction(M=np.array(rec["M"]), plot_area=rec["plot_area"], xticks=rec["xticks"], yticks=rec["yticks"],
                        loose_labels=rec["loose_labels"])
        res = calibrate_cached(reader, img, ex, plain=a.plain, net_boxes=a.net_boxes)
        ce = calib_error(meta, res)
        for ax in "xy":
            e = ce[ax]
            errs[ax].append(e)
            if not np.isfinite(e) or e > 0.005:
                bad[ax] += 1
        if a.json:
            r = {"id": meta["seed"], "file": rec["file"], "plot_area": meta["plot_area"], "preset": meta.get("preset"),
                 "loose_labels": ex.loose_labels}
            for ax in "xy":
                r[ax] = axis_record(meta, res, ax)
                r[ax]["err"] = None if not np.isfinite(ce[ax]) else float(ce[ax])
                r[ax]["scale_ok"] = bool(ce.get(ax + "_scale_ok", False))
            records.append(r)
    n = len(recs)
    for ax in "xy":
        v = np.array(errs[ax], float)
        print(f"{ax}: within 0.5% {1 - bad[ax] / n:.1%}  median error {np.nanmedian(v) * 100:.3f}%  no fit {np.isnan(v).sum()}"
              f"  scale ok {np.mean([r[ax]['scale_ok'] for r in records]) if records else float('nan'):.1%}")
    both = sum(1 for ex_, ey in zip(errs["x"], errs["y"]) if np.isfinite(ex_) and np.isfinite(ey) and ex_ <= 0.005 and ey <= 0.005)
    print(f"both axes within 0.5%: {both / n:.1%}   ({time.time() - t0:.0f}s)")
    if a.json:
        json.dump(records, open(a.json, "w"), default=float)


def calibrate_cached(reader, img, ex: Extraction, plain: bool = False, net_boxes: bool = False):
    """The calibration half of pipeline.run on a cached extraction."""
    if not net_boxes:
        ex = refine_labels(img, ex)
    rx, ry = pipeline.read_ticks(reader, img, ex.xticks), pipeline.read_ticks(reader, img, ex.yticks)
    xdate, ydate = pipeline.as_dates(rx, "x"), pipeline.as_dates(ry, "y")
    if plain:
        for r in rx + ry:
            r.logits = None
    xfit, yfit = pipeline.fit_reads(rx, xdate), pipeline.fit_reads(ry, ydate)
    factors = {}
    for name, reads in (("x", rx), ("y", ry)):
        scale, shift, text = pipeline.axis_factor(reader, img, ex, name)
        if text is not None:
            factors[name] = text
            if name == "x":
                xfit = pipeline.apply_factor(xfit, reads, scale, shift)
            else:
                yfit = pipeline.apply_factor(yfit, reads, scale, shift)
    res = pipeline.Result(ex=ex, xfit=xfit, yfit=yfit,
                          tick_reads={"x": [r.as_tuple() for r in rx], "y": [r.as_tuple() for r in ry]},
                          reads={"x": rx, "y": ry})
    res.date_axes = {"x": xdate, "y": ydate}
    for name, text in factors.items():
        res.warnings.append(f"{name} axis: values scaled by the printed '{text}'")
    for name, f in (("x", xfit), ("y", yfit)):
        if f is None:
            res.warnings.append(f"{name} axis: could not calibrate from the tick labels")
        else:
            res.warnings += [f"{name} axis: {w}" for w in f.warnings]
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cache")
    c.add_argument("--ckpt", required=True)
    c.add_argument("--data", required=True)
    c.add_argument("--limit", type=int, default=200)
    c.add_argument("--out", required=True)
    e = sub.add_parser("eval")
    e.add_argument("--cache", required=True)
    e.add_argument("--ocr", required=True)
    e.add_argument("--json", default=None)
    e.add_argument("--limit", type=int, default=None)
    e.add_argument("--plain", action="store_true", help="greedy reads and the plain fit, as before")
    e.add_argument("--net-boxes", action="store_true", help="the network's label boxes, not the source-measured ones")
    e.add_argument("--gpu", action="store_true")
    a = ap.parse_args()
    torch.set_num_threads(2)
    if a.cmd == "cache":
        cache(a)
    else:
        evaluate(a)


if __name__ == "__main__":
    main()
