"""Dump what PlotNet sees and says on one image, stage by stage.

    python teams/t5-robust/tools/probe_net.py IMAGE [IMAGE ...] --out out/t5/probe [--ckpt runs/v3/best.pt]

For each image writes <out>/<stem>.png: a montage of the canvas the network
sees, the sem argmax, and the six heat maps, with the decoded frame, ticks and
label boxes drawn on; and prints what each stage produced (corner peaks, tick
peaks, label boxes, tick reads, calibration, series).
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# P2D_ROOT selects which copy of the p2d package is measured (the frozen baseline in out/t5/base-code, or the live tree).
sys.path.insert(0, os.environ.get("P2D_ROOT") or os.path.abspath(os.path.join(HERE, "..", "..", "..")))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from p2d.data import H_CORNER, H_LINE, H_MARKER, H_VERTEX, H_XTICK, H_YTICK, apply  # noqa: E402
from p2d.evaluate import draw, load_net  # noqa: E402
from p2d.extract import label_boxes, peaks, prepare, run_net  # noqa: E402
from p2d.ocr import load_reader  # noqa: E402
from p2d.pipeline import run  # noqa: E402
from p2d.synth.mpl_render import CLASS_NAMES  # noqa: E402

SEM_COLOURS = np.array([
    [255, 255, 255],  # bg
    [220, 0, 0],      # data
    [255, 140, 0],    # legend symbol
    [0, 0, 0],        # axis
    [160, 160, 255],  # grid
    [0, 150, 0],      # tick label
    [150, 0, 150],    # text
], np.uint8)


def heat_img(h: np.ndarray) -> np.ndarray:
    return cv2.applyColorMap((np.clip(h, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)[..., ::-1]


def label(img: np.ndarray, text: str) -> np.ndarray:
    out = img.copy()
    cv2.rectangle(out, (0, 0), (len(text) * 9 + 6, 18), (0, 0, 0), -1)
    cv2.putText(out, text, (3, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return out


def probe(net, reader, path: str, out_dir: str) -> None:
    img = cv2.imread(path)[..., ::-1].copy()
    h, w = img.shape[:2]
    x, M = prepare(img)
    out, _ = run_net(net, img)
    sem, heat = out["sem"], out["heat"]
    canvas = ((x[0].numpy().transpose(1, 2, 0) * np.array([0.229, 0.224, 0.225]) + np.array([0.485, 0.456, 0.406])) * 255)
    canvas = np.clip(canvas, 0, 255).astype(np.uint8)
    s = float(M[0, 0])
    stem = os.path.splitext(os.path.basename(path))[0]
    print(f"=== {path}  {w}x{h}  canvas scale {s:.3f}")

    # Stage 1: frame.
    pk = peaks(heat[H_CORNER], 0.25, nms=5)[:12]
    print(f"corner peaks >=0.25: {len(pk)}  " + "  ".join(f"({p[0]:.0f},{p[1]:.0f}:{p[2]:.2f})" for p in pk[:8]))
    print(f"corner heat max {heat[H_CORNER].max():.3f}")
    # Stage 2: ticks.
    for ch, name in ((H_XTICK, "xtick"), (H_YTICK, "ytick")):
        tp = peaks(heat[ch], 0.3, nms=3)
        print(f"{name} peaks >=0.3: {len(tp)}  max {heat[ch].max():.3f}  " +
              "  ".join(f"({p[0]:.0f},{p[1]:.0f}:{p[2]:.2f})" for p in tp[:12]))
    boxes = label_boxes(sem)
    print(f"tick-label boxes: {len(boxes)}")
    sa = sem.argmax(0)
    frac = {CLASS_NAMES[i]: float((sa == i).mean()) for i in range(len(CLASS_NAMES))}
    print("sem fractions: " + "  ".join(f"{k} {v:.4f}" for k, v in frac.items()))
    print(f"line heat max {heat[H_LINE].max():.3f}  pixels>0.25 {(heat[H_LINE] > 0.25).sum()}  "
          f"marker max {heat[H_MARKER].max():.3f}  pixels>0.3 {(heat[H_MARKER] > 0.3).sum()}  "
          f"vertex max {heat[H_VERTEX].max():.3f}")

    # Full pipeline.
    res = run(net, reader, img)
    ex = res.ex
    print(f"plot_area (src px): {None if ex.plot_area is None else [round(v, 1) for v in ex.plot_area]}")
    for key in ("xticks", "yticks"):
        ts = getattr(ex, key)
        print(f"{key}: {len(ts)}  with label {sum(t['label_box'] is not None for t in ts)}  " +
              "  ".join(f"{t['pos']:.1f}" + (f"<-{t['pos_net']:.1f}" if 'pos_net' in t else "") for t in ts[:12]))
    for ax in ("x", "y"):
        reads = res.tick_reads.get(ax, [])
        print(f"reads {ax}: " + "  ".join(f"{r[0]:.0f}:'{r[1]}'={r[3]}" for r in sorted(reads, key=lambda r: r[0])))
        f = res.xfit if ax == "x" else res.yfit
        print(f"fit {ax}: " + (f"{f.scale} a={f.a:.6g} b={f.b:.6g} inliers {f.inliers}/{f.used} resid {f.resid_px:.2f}px"
                              if f else "none"))
    print(f"loose labels: {len(ex.loose_labels)}  " + "  ".join(f"[{b[0]:.0f},{b[1]:.0f},{b[2]:.0f},{b[3]:.0f}]" for b in ex.loose_labels[:6]))
    print(f"series: {len(ex.series)}  " + "  ".join(f"{se.kind}/{len(se.line_px)}pts/{len(se.markers_px)}mk/col{se.color}" for se in ex.series))
    for wmsg in res.warnings:
        print(f"warn: {wmsg}")

    # Montage.
    semimg = SEM_COLOURS[sa]
    panels = [label(canvas, "canvas"), label(semimg, "sem argmax"),
              label(heat_img(heat[H_LINE]), "line"), label(heat_img(heat[H_MARKER]), "marker"),
              label(heat_img(np.maximum(heat[H_XTICK], heat[H_YTICK])), "x/y tick"), label(heat_img(heat[H_CORNER]), "corner")]
    # Decoded geometry on the canvas panel.
    cv = panels[0]
    for p in pk:
        cv2.drawMarker(cv, (int(round(p[0])), int(round(p[1]))), (255, 140, 0), cv2.MARKER_SQUARE, 9, 1)
    for b in boxes:
        cv2.rectangle(cv, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (0, 0, 255), 1)
    for key in ("xticks", "yticks"):
        for t in getattr(ex, key):
            a = apply(M, [t["anchor"]])[0]
            cv2.drawMarker(cv, (int(round(a[0])), int(round(a[1]))), (255, 0, 0), cv2.MARKER_CROSS, 9, 1)
    rows = [np.hstack(panels[:3]), np.hstack(panels[3:])]
    os.makedirs(out_dir, exist_ok=True)
    cv2.imwrite(os.path.join(out_dir, stem + ".png"), np.vstack(rows)[..., ::-1])
    cv2.imwrite(os.path.join(out_dir, stem + ".overlay.png"), draw(img, ex)[..., ::-1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--ckpt", default="runs/v3/best.pt")
    ap.add_argument("--ocr", default="runs/ocr1/best.pt")
    ap.add_argument("--out", default="out/t5/probe")
    a = ap.parse_args()
    net = load_net(a.ckpt)
    reader = load_reader(a.ocr)
    for p in a.images:
        probe(net, reader, p, a.out)


if __name__ == "__main__":
    main()
