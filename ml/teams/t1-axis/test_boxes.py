"""Score a label-box finder against the label ink, from the TRUE tick positions, without the network.

    python teams/t1-axis/test_boxes.py data/mpl-val 200
    python teams/t1-axis/test_boxes.py data/t1-probe 640

For every true tick, `extract.label_from_source` (the live tree's) is asked for the label box from the true
tick position and anchor; the box is scored against the bounding box of the TICK_LABEL pixels of the true
label in the sem map: ok (every side within 1.5 px, no other label's ink inside), cropped (which side, how
many px), merged (another label's ink inside), elsewhere (does not cover the label), none. Rotated labels are
scored too but listed apart. Prints the counts per set and, for the probe set, per style.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter, defaultdict

import cv2
import numpy as np

sys.path.insert(0, os.environ.get("P2D_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from p2d.extract import label_from_source  # noqa: E402
from reclass import ink_box  # noqa: E402


def score_box(box, ink, others):
    if box is None:
        return "none", {}
    if ink is None:
        return "ok", {}
    cov = (min(box[2], ink[2]) - max(box[0], ink[0]) + 1) * (min(box[3], ink[3]) - max(box[1], ink[1]) + 1)
    own = cov / ((ink[2] - ink[0] + 1) * (ink[3] - ink[1] + 1)) if cov > 0 else 0.0
    if own < 0.3:
        return "elsewhere", {}
    for ob in others:
        if ob is None:
            continue
        w = min(box[2], ob[2]) - max(box[0], ob[0])
        h = min(box[3], ob[3]) - max(box[1], ob[1])
        if w > 0 and h > 0 and w * h / max(1.0, (ob[2] - ob[0]) * (ob[3] - ob[1])) > 0.3:
            return "merged", {}
    cut = {"left": ink[0] - box[0], "right": box[2] - ink[2], "top": ink[1] - box[1], "bottom": box[3] - ink[3]}
    cut = {k: round(float(-v), 1) for k, v in cut.items() if v < -1.5}
    if cut:
        return "cropped", cut
    return "ok", {}


def main(data: str, limit: int) -> None:
    files = sorted(glob.glob(os.path.join(data, "*.json")))[:limit]
    counts = defaultdict(Counter)
    sides = Counter()
    examples = defaultdict(list)
    for f in files:
        m = json.load(open(f))
        img = cv2.imread(f[:-5] + ".png")
        sem = cv2.imread(f[:-5] + ".sem.png", cv2.IMREAD_UNCHANGED)
        g = img.astype(np.float32).mean(-1)
        H, W = g.shape
        pa = m["plot_area"]
        style = m.get("probe", "all")
        for key in ("xticks", "yticks"):
            ticks = m[key]
            if not ticks:
                continue
            horizontal = key == "xticks"
            inks = [ink_box(sem, t["bbox"]) for t in ticks]
            p = np.sort(np.array([t["pos"] for t in ticks]))
            spacing = float(np.median(np.diff(p))) if len(p) > 1 else 60.0
            half = max(6.0, 0.48 * spacing)
            for i, t in enumerate(ticks):
                ax_, ay = t["anchor"]
                if horizontal:
                    outward = 1 if ay >= (pa[1] + pa[3]) / 2 else -1
                    box = label_from_source(g, t["pos"], ay, outward, True, half)
                else:
                    outward = -1 if ax_ <= (pa[0] + pa[2]) / 2 else 1
                    box = label_from_source(g, t["pos"], ax_, outward, False, half)
                verdict, cut = score_box(box, inks[i], [b for j, b in enumerate(inks) if j != i])
                b = t["bbox"]
                rotated = (b[2] - b[0]) < (b[3] - b[1]) * 0.9 and len(t["text"]) > 1
                group = f"{style}/{key[0]}" + ("/rot" if rotated else "")
                counts[group][verdict] += 1
                counts["TOTAL" + ("/rot" if rotated else "")][verdict] += 1
                for s in cut:
                    sides[s] += 1
                if verdict != "ok" and len(examples[verdict]) < 25:
                    examples[verdict].append((m["seed"], key[0], t["text"], cut, None if box is None else [round(v) for v in box], inks[i]))
    for grp in sorted(counts):
        c = counts[grp]
        n = sum(c.values())
        print(f"{grp:28s} n={n:4d}  ok {c['ok'] / n:.3f}  cropped {c['cropped']}  merged {c['merged']}  elsewhere {c['elsewhere']}  none {c['none']}")
    print("cropped sides:", dict(sides))
    for v, ex in examples.items():
        print(f"--- {v} examples (seed, axis, text, cut, box, ink):")
        for e in ex:
            print("   ", e)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
