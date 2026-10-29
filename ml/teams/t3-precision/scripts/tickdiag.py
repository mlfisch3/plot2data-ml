"""Tick positions before and after `refine_ticks`, against the truth, per tick.

    python teams/t3-precision/scripts/tickdiag.py --ckpt runs/v3/best.pt --data data/mpl-val --limit 60

Prints, per axis and overall: the median and p90 of |error| from the network alone
and after snapping, how many ticks moved, how many moved the wrong way (error grew
by more than 0.3 px), and lists the worst snaps with the chart's style.
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from p2d.evaluate import load_net  # noqa: E402
from p2d.extract import extract, refine_ticks, run_net  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    net = load_net(a.ckpt)
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    recs = []
    for f in files:
        meta = json.load(open(f))
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        out, M = run_net(net, img)
        ex = extract(out, M, img)
        s = float(np.hypot(M[0, 0], M[1, 0]))
        net_ticks = {k: copy.deepcopy(getattr(ex, k)) for k in ("xticks", "yticks")}
        ex = refine_ticks(img, ex)
        tol = max(3.0, 2.5 / s)
        for key in ("xticks", "yticks"):
            gt = meta[key]
            pn = net_ticks[key]
            pr = getattr(ex, key)
            used = set()
            for t in gt:
                best, bd = None, 1e9
                for j, p in enumerate(pn):
                    d = np.hypot(p["anchor"][0] - t["anchor"][0], p["anchor"][1] - t["anchor"][1])
                    if d < bd and j not in used:
                        best, bd = j, d
                if best is None or bd > tol:
                    continue
                used.add(best)
                e_net = pn[best]["pos"] - t["pos"]
                e_ref = pr[best]["pos"] - t["pos"]
                recs.append(dict(seed=meta["seed"], axis=key[0], e_net=e_net, e_ref=e_ref, moved="pos_net" in pr[best],
                                 s=s, preset=meta.get("preset"), style=meta.get("style"), value=t["value"],
                                 frame=ex.plot_area, pa=meta["plot_area"]))
    if a.out:
        json.dump(recs, open(a.out, "w"), default=float)
    for axis in ("x", "y", "xy"):
        r = [q for q in recs if axis == "xy" or q["axis"] == axis]
        en = np.array([abs(q["e_net"]) for q in r])
        er = np.array([abs(q["e_ref"]) for q in r])
        mv = np.array([q["moved"] for q in r])
        sg_net = np.array([q["e_net"] for q in r])
        sg_ref = np.array([q["e_ref"] for q in r])
        print(f"\n== axis {axis}: {len(r)} ticks  moved {mv.mean():.0%}")
        print(f"  net : med|e| {np.median(en):.3f}  p90 {np.quantile(en, .9):.3f}  mean e {sg_net.mean():+.3f}  rms {np.sqrt(np.mean(sg_net**2)):.3f}")
        print(f"  ref : med|e| {np.median(er):.3f}  p90 {np.quantile(er, .9):.3f}  mean e {sg_ref.mean():+.3f}  rms {np.sqrt(np.mean(sg_ref**2)):.3f}")
        if mv.any():
            print(f"  moved ticks: net med|e| {np.median(en[mv]):.3f} -> ref {np.median(er[mv]):.3f};  worse by >0.3 px: {(er[mv] > en[mv] + 0.3).mean():.1%}  better by >0.3: {(er[mv] < en[mv] - 0.3).mean():.1%}")
        if (~mv).any():
            print(f"  unmoved ticks: med|e| {np.median(en[~mv]):.3f}  p90 {np.quantile(en[~mv], .9):.3f}  mean e {sg_net[~mv].mean():+.3f}")
        # Per preset.
        for pre in sorted(set(q["preset"] for q in r)):
            rr = [q for q in r if q["preset"] == pre]
            e1 = np.array([abs(q["e_net"]) for q in rr])
            e2 = np.array([abs(q["e_ref"]) for q in rr])
            m2 = np.array([q["moved"] for q in rr])
            print(f"    {pre:16s} n {len(rr):4d}  moved {m2.mean():4.0%}  net med {np.median(e1):.3f} p90 {np.quantile(e1,.9):.2f}  ref med {np.median(e2):.3f} p90 {np.quantile(e2,.9):.2f}")
    worst = sorted(recs, key=lambda q: -(abs(q["e_ref"]) - abs(q["e_net"])))[:15]
    print("\nworst snaps (error grew):")
    for q in worst:
        print(f"  seed {q['seed']} {q['axis']} value {q['value']:g}  net {q['e_net']:+.2f} -> ref {q['e_ref']:+.2f}  s {q['s']:.2f}  {q['preset']}/{q['style']}")
    worst = sorted(recs, key=lambda q: -abs(q["e_ref"]))[:15]
    print("\nworst after refine:")
    for q in worst:
        print(f"  seed {q['seed']} {q['axis']} value {q['value']:g}  net {q['e_net']:+.2f} -> ref {q['e_ref']:+.2f}  moved {q['moved']}  s {q['s']:.2f}  {q['preset']}/{q['style']}")


if __name__ == "__main__":
    main()
