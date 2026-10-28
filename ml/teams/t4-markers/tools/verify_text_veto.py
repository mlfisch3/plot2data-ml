"""On the labels probe, how many TRUE markers would be vetoed by a sem[non-data] > sem[data] rule?

The brainstormer's proposed sem-TEXT veto drops a predicted marker if the semantic class under its
peak is predominantly non-data (TEXT, LEGEND_SYMBOL, TICK_LABEL) rather than DATA. We check the
false-positive rate against the real markers of the labels probe set, measured in a small window.

    python teams/t4-markers/tools/verify_text_veto.py --data data/t4-labels --limit 200 --window 1

Reports: per chart, the fraction of true markers whose sem patch has non-data >= data (would be
vetoed by the rule). Aggregate over the set with and without each veto variant.
"""

from __future__ import annotations

import argparse
import glob
import json
import os

import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--window", type=int, default=1, help="half-radius in source px; patch is (2w+1)^2")
    a = ap.parse_args()
    jsons = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    rows = []
    for jp in jsons:
        meta = json.load(open(jp))
        inst_path = jp.replace(".json", ".inst.png")
        sem_path = jp.replace(".json", ".sem.png")
        if not (os.path.exists(inst_path) and os.path.exists(sem_path)):
            continue
        sem = cv2.imread(sem_path, cv2.IMREAD_UNCHANGED)
        if sem is None:
            continue
        H, W = sem.shape[:2]
        # From p2d/synth/mpl_render.py line 38:
        # 0=bg, 1=data, 2=legend_symbol, 3=axis, 4=grid, 5=tick_label, 6=text.
        total = 0
        vetoed = 0
        vetoed_text = 0  # strict text-only version
        for s in meta["series"]:
            if s["kind"] == "line":
                continue
            for x, y in s["markers_px"]:
                xi, yi = int(round(x)), int(round(y))
                x0, x1 = max(0, xi - a.window), min(W, xi + a.window + 1)
                y0, y1 = max(0, yi - a.window), min(H, yi + a.window + 1)
                patch = sem[y0:y1, x0:x1].reshape(-1)
                data = (patch == 1).sum()
                text = (patch == 6).sum()
                tick = (patch == 5).sum()
                legend = (patch == 2).sum()
                non_data = text + tick + legend
                total += 1
                if non_data >= data:
                    vetoed += 1
                if text >= max(1, data):
                    vetoed_text += 1
        if total:
            rows.append(dict(id=meta["seed"], total=total, vetoed=vetoed, vetoed_text=vetoed_text, mode=meta.get("probe", {}).get("mode")))

    total = sum(r["total"] for r in rows)
    vetoed = sum(r["vetoed"] for r in rows)
    vetoed_text = sum(r["vetoed_text"] for r in rows)
    print(f"Charts: {len(rows)}, total true markers: {total}")
    print(f"False vetoes (non_data >= data): {vetoed}/{total} = {vetoed / total * 100:.2f}%")
    print(f"False vetoes (text >= data):     {vetoed_text}/{total} = {vetoed_text / total * 100:.2f}%")
    print("\nWorst-affected modes:")
    import collections
    by_mode = collections.defaultdict(lambda: [0, 0, 0])
    for r in rows:
        m = r["mode"] or "?"
        by_mode[m][0] += r["total"]
        by_mode[m][1] += r["vetoed"]
        by_mode[m][2] += r["vetoed_text"]
    for m, (t, v, vt) in sorted(by_mode.items(), key=lambda kv: -kv[1][1]):
        print(f"  {m}: {v}/{t} = {v / max(1, t) * 100:.2f}% (text-only: {vt / max(1, t) * 100:.2f}%)")
    print("\nTop charts by veto count:")
    for r in sorted(rows, key=lambda r: -r["vetoed"])[:10]:
        print(f"  {r['id']} mode={r['mode']}: {r['vetoed']}/{r['total']} vetoed ({r['vetoed_text']} text-only)")


if __name__ == "__main__":
    main()
