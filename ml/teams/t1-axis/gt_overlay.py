"""Draw a dataset sample's recorded ground truth over its render, to check a generator.

    python teams/t1-axis/gt_overlay.py data/t1-probe/11000000 out/t1/gtviz

Green: series paths and markers; red: tick anchors with the text; blue: label boxes; orange: plot area;
magenta: offset text boxes. Also writes the sem map colourised next to it.
"""

from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np


def main(stem: str, out_dir: str) -> None:
    meta = json.load(open(stem + ".json"))
    img = cv2.imread(stem + ".png")
    sem = cv2.imread(stem + ".sem.png", cv2.IMREAD_UNCHANGED)
    out = (img.astype(np.float32) * 0.5 + 127).astype(np.uint8)
    for s in meta["series"]:
        p = np.array(s["path_px"])
        if len(p) > 1:
            cv2.polylines(out, [np.round(p * 4).astype(np.int32)], False, (0, 180, 0), 1, cv2.LINE_AA, shift=2)
        for m in s["markers_px"]:
            cv2.drawMarker(out, (int(round(m[0])), int(round(m[1]))), (0, 180, 0), cv2.MARKER_CROSS, 7, 1)
    pa = np.round(meta["plot_area"]).astype(int)
    cv2.rectangle(out, (pa[0], pa[1]), (pa[2], pa[3]), (0, 140, 255), 1)
    for key in ("xticks", "yticks"):
        for t in meta[key]:
            a = t["anchor"]
            cv2.drawMarker(out, (int(round(a[0])), int(round(a[1]))), (0, 0, 255), cv2.MARKER_CROSS, 9, 1)
            b = np.round(t["bbox"]).astype(int)
            cv2.rectangle(out, (b[0], b[1]), (b[2], b[3]), (255, 0, 0), 1)
            cv2.putText(out, t["text"], (b[0], b[1] - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 200), 1, cv2.LINE_AA)
    for b in meta.get("offset_bbox", []) or []:
        if b:
            b = np.round(b).astype(int)
            cv2.rectangle(out, (b[0], b[1]), (b[2], b[3]), (255, 0, 255), 1)
    pal = np.array([[255, 255, 255], [0, 0, 255], [0, 200, 200], [0, 0, 0], [180, 180, 180], [255, 0, 0], [0, 160, 0]], np.uint8)
    semc = pal[np.clip(sem, 0, 6)]
    os.makedirs(out_dir, exist_ok=True)
    name = os.path.basename(stem)
    cv2.imwrite(os.path.join(out_dir, name + ".gt.png"), np.hstack([out, semc]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
