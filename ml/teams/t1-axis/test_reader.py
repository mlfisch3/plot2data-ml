"""The tick reader alone, on the TRUE label boxes, on the CPU: how much is the reader and how much the boxes.

    P2D_ROOT=/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml python teams/t1-axis/test_reader.py data/mpl-val 200 runs/ocr1/best.pt
    python teams/t1-axis/test_reader.py data/t1-probe 640 runs/ocr1/best.pt

Every true tick label (box inside the image) is cut with `ocr.crop` from its true bbox, read, and compared with
the true text (exact, after normalising spaces and the minus sign) and with the true value through `parse_value`.
Per set and per probe style, rotated labels apart; the commonest confusions are listed.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter, defaultdict

import cv2
import numpy as np
import torch

sys.path.insert(0, os.environ.get("P2D_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from p2d.ocr import TickReader, crop, parse_value, read_crops  # noqa: E402


def norm(s: str) -> str:
    return s.replace(" ", "").replace("−", "-").replace("–", "-").strip()


def main(data: str, limit: int, ckpt: str) -> None:
    torch.set_num_threads(2)
    m = TickReader()
    m.load_state_dict(torch.load(ckpt, map_location="cpu")["model"])
    m.eval()
    files = sorted(glob.glob(os.path.join(data, "*.json")))[:limit]
    stats = defaultdict(Counter)
    conf = defaultdict(Counter)
    for f in files:
        meta = json.load(open(f))
        gray = cv2.imread(f[:-5] + ".png", cv2.IMREAD_GRAYSCALE)
        H, W = gray.shape
        style = meta.get("probe", "all")
        items = []
        for key in ("xticks", "yticks"):
            for t in meta[key]:
                b = t["bbox"]
                if b[0] < 0 or b[1] < 0 or b[2] > W - 1 or b[3] > H - 1 or b[2] - b[0] < 2 or b[3] - b[1] < 2:
                    stats[f"{style}/{key[0]}"]["cut_by_image"] += 1
                    continue
                rot = (b[2] - b[0]) < (b[3] - b[1]) * 0.9 and len(t["text"]) > 1
                items.append((f"{style}/{key[0]}" + ("/rot" if rot else ""), t, crop(gray, b)))
        if not items:
            continue
        reads = read_crops(m, [c for _, _, c in items], device="cpu")
        for (grp, t, _), (text, c) in zip(items, reads):
            ok = norm(text) == norm(t["text"])
            v = parse_value(text)
            vok = v is not None and abs(v - t["value"]) <= 1e-6 * max(1.0, abs(t["value"])) + 1e-12
            for g in (grp, "TOTAL" + ("/rot" if grp.endswith("/rot") else "")):
                stats[g]["n"] += 1
                stats[g]["exact"] += ok
                stats[g]["value_ok"] += vok
            if not ok:
                conf[grp.split("/")[0]][(norm(t["text"]), norm(text))] += 1
    for g in sorted(stats):
        s = stats[g]
        n = s["n"]
        if n == 0:
            print(f"{g:26s} cut_by_image {s['cut_by_image']}")
            continue
        print(f"{g:26s} n={n:5d}  exact {s['exact'] / n:.3f}  value ok {s['value_ok'] / n:.3f}  cut_by_image {s['cut_by_image']}")
    for st, c in conf.items():
        print(f"--- {st} confusions (true -> read): " + "; ".join(f"{a}->{b} x{k}" for (a, b), k in c.most_common(20)))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
