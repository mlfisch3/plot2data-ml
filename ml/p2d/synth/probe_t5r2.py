"""Round-2 probe sets for the clutter failure mode.

Two factors beyond the round-1 ``clutter`` of :mod:`probe_t5`:

- ``clutter-max``: every clutter element present at its maximum size (fixed
  toolbar, full-width sidebar and right strip with a second chart, deep bottom
  text, scrollbar, cursor). The chart is still placed on top, so no chart ink
  is lost. The surrounding furniture occupies as many pixels as the chart
  itself, which pushes the sem head towards calling text TICK_LABEL.
- ``clutter-overlap``: a selection of UI chrome placed AFTER the chart, so it
  overwrites chart ink. Variants (random per sample): a modal-dialog box over a
  chart corner, a scrollbar bar overlapping the plot's right edge, a cursor
  dropped inside the plot area, a tooltip rectangle in the top-right. Chart
  pixels inside the overlap rectangles are lost; the JSON records which classes
  were lost and by how many pixels so eval can split error contributions.

Both variants write the standard dataset format (:mod:`build`) with the seed as
the sample id, and record a ``sem_mapping`` dict in the meta so the eval
pipeline can tell probe variants apart.

Pixel coordinates follow :mod:`mpl_render`: the centre of pixel column i is
``x = i``. Seeds for round-2 are >= 15,100,000.

Usage::

    python -m p2d.synth.probe_t5r2 --factor clutter-max --out data/t5r2-clutter-max \\
        --start 15110000 --count 100 --workers 3 --renderer matplotlib
    python -m p2d.synth.probe_t5r2 --factor clutter-overlap --out data/t5r2-clutter-overlap \\
        --start 15120000 --count 100 --workers 3 --renderer matplotlib
"""

from __future__ import annotations

import argparse
import json
import logging
import os as _os

_os.environ.setdefault("OMP_NUM_THREADS", "1")

import os  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from p2d.synth.probe_t5 import _WORDS, _render_base, _shift_meta, _text_block  # noqa: E402

cv2.setNumThreads(1)


# ---------------------------------------------------------------------- helpers

def _bbox_classes(sem: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> dict[str, int]:
    """Count sem pixels per class inside a bbox (clipped to the image)."""
    H, W = sem.shape
    x0 = max(0, min(W, int(x0)))
    x1 = max(0, min(W, int(x1)))
    y0 = max(0, min(H, int(y0)))
    y1 = max(0, min(H, int(y1)))
    if x1 <= x0 or y1 <= y0:
        return {}
    region = sem[y0:y1, x0:x1]
    classes, counts = np.unique(region, return_counts=True)
    return {int(c): int(n) for c, n in zip(classes, counts)}


# ------------------------------------------------------------- clutter variants

def _clutter_max(r, seed: int, renderer: str):
    """Every piece of chrome at its maximum size, around a chart that is still placed last.

    No chart pixels are lost; the clutter area is 70 px top + 260 px left + 260 px right + 160 px bottom.
    """
    from p2d.synth.mpl_render import BG

    rng = np.random.default_rng(seed + 7)
    H, W = r.image.shape[:2]
    paper = r.image[0, 0].tolist()
    page_bg = paper if rng.random() < 0.3 else [int(v) for v in rng.uniform(235, 255, 3)]
    fg = (60, 60, 60) if np.mean(page_bg) > 128 else (200, 200, 200)
    top, left, right, bottom = 70, 260, 260, 160
    PW, PH = W + left + right, H + top + bottom
    page = np.full((PH, PW, 3), page_bg, np.uint8)
    sem = np.full((PH, PW), BG, np.uint8)
    inst = np.zeros((PH, PW), np.uint8)

    # Toolbar: filled bar with window chrome plus a short title.
    bar_color = [int(v) for v in rng.uniform(40, 240, 3)] if rng.random() < 0.5 else [int(v) for v in rng.uniform(220, 240, 3)]
    page[: 40] = bar_color
    txt_color = (240, 240, 240) if np.mean(bar_color) < 128 else (40, 40, 40)
    cv2.putText(page, " ".join(rng.choice(_WORDS, 5)).title(), (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, txt_color, 1, cv2.LINE_AA)
    # Three "window buttons" that look like a browser's close/min/max.
    for i, c in enumerate([(90, 90, 90), (180, 180, 60), (60, 180, 60)]):
        cv2.circle(page, (PW - 20 - 20 * i, 20), 6, c, -1)

    # Left sidebar: dense text block.
    page[top:, : left - 10] = _text_block(rng, left - 10, PH - top, page_bg, fg, scale=0.45)
    cv2.line(page, (left - 8, top), (left - 8, PH), (200, 200, 200), 1)

    # Right strip: a second chart (always), scaled to fit.
    try:
        other = _render_base(seed + 1_000_000, renderer).image
        s = min((right - 14) / other.shape[1], (PH - top - 10) / other.shape[0], 1.0)
        o = cv2.resize(other, (max(8, int(other.shape[1] * s)), max(8, int(other.shape[0] * s))), interpolation=cv2.INTER_AREA)
        page[top + 6: top + 6 + o.shape[0], left + W + 10: left + W + 10 + o.shape[1]] = o
    except Exception:
        page[top:, left + W + 10:] = _text_block(rng, right - 10, PH - top, page_bg, fg)

    # Bottom caption/body text.
    page[top + H + 6:, left: left + W] = _text_block(rng, W, bottom - 6, page_bg, fg, scale=0.5)

    # Scrollbar on the right edge, always present.
    page[:, PW - 14:] = (235, 235, 235)
    y0 = int(rng.integers(top, PH - PH // 3))
    page[y0: y0 + PH // 3, PW - 12: PW - 2] = (170, 170, 170)

    # Mouse cursor somewhere OUTSIDE the plot (upper-left region).
    cx = int(rng.integers(10, max(11, left - 20)))
    cy = int(rng.integers(top + 10, max(top + 11, top + 60)))
    pts = np.array([[cx, cy], [cx, cy + 16], [cx + 4, cy + 12], [cx + 7, cy + 18], [cx + 9, cy + 17], [cx + 6, cy + 11], [cx + 11, cy + 11]], np.int32)
    cv2.fillPoly(page, [pts], (255, 255, 255))
    cv2.polylines(page, [pts], True, (0, 0, 0), 1)

    # Paste the chart last, so chart pixels are preserved.
    page[top: top + H, left: left + W] = r.image
    sem[top: top + H, left: left + W] = r.sem
    inst[top: top + H, left: left + W] = r.inst

    meta = _shift_meta(r.meta, left, top, PW, PH)
    meta["clutter"] = dict(left=left, top=top, right=right, bottom=bottom, kind="max")
    meta["chart_rect"] = [left, top, left + W, top + H]
    meta["sem_mapping"] = dict(
        chart_classes=_bbox_classes(sem, left, top, left + W, top + H),
        clutter_region_px=int((PW * PH) - (W * H)),
        chart_region_px=int(W * H),
        overlap_rects=[],
        chart_pixels_lost={},
    )
    return r.__class__(image=page, sem=sem, inst=inst, meta=meta)


def _clutter_overlap(r, seed: int, renderer: str):
    """Clutter overwrites chart ink: modal dialog, scrollbar, cursor-in-plot, tooltip.

    Painted AFTER the chart. For every overlapping rect the function records the
    bbox and the chart-class pixel counts that were overwritten in
    ``meta['sem_mapping']['chart_pixels_lost']``.
    """
    from p2d.synth.mpl_render import BG

    rng = np.random.default_rng(seed + 7)
    H, W = r.image.shape[:2]
    paper = r.image[0, 0].tolist()
    page_bg = paper if rng.random() < 0.6 else [int(v) for v in rng.uniform(235, 255, 3)]
    fg = (60, 60, 60) if np.mean(page_bg) > 128 else (200, 200, 200)
    top = int(rng.integers(0, 50))
    left = int(rng.integers(0, 220))
    right = int(rng.integers(0, 220))
    bottom = int(rng.integers(0, 120))
    PW, PH = W + left + right, H + top + bottom
    page = np.full((PH, PW, 3), page_bg, np.uint8)
    sem = np.full((PH, PW), BG, np.uint8)
    inst = np.zeros((PH, PW), np.uint8)

    # Light surrounding furniture (no overlap yet).
    if top >= 24:
        bar = [int(v) for v in rng.uniform(220, 245, 3)]
        page[: min(top, 30)] = bar
    if left >= 60:
        page[top:, : left - 8] = _text_block(rng, left - 8, PH - top, page_bg, fg)
    if right >= 60:
        page[top:, left + W + 8:] = _text_block(rng, right - 8, PH - top, page_bg, fg)
    if bottom >= 30:
        page[top + H + 6:, left: left + W] = _text_block(rng, W, bottom - 6, page_bg, fg)

    # Paste the chart (chart ink lives in sem).
    page[top: top + H, left: left + W] = r.image
    sem[top: top + H, left: left + W] = r.sem
    inst[top: top + H, left: left + W] = r.inst

    pa = r.meta["plot_area"]
    plot_x0, plot_y0 = int(pa[0] + left), int(pa[1] + top)
    plot_x1, plot_y1 = int(pa[2] + left), int(pa[3] + top)

    overlap_rects: list[dict] = []
    chart_lost: dict[str, int] = {}

    def _overwrite_rect(x0: int, y0: int, x1: int, y1: int, color_px, label_px: int = BG, inst_px: int = 0) -> None:
        """Record the chart-class pixel counts that will be overwritten, then overwrite."""
        H2, W2 = page.shape[:2]
        x0 = max(0, min(W2, int(x0)))
        x1 = max(0, min(W2, int(x1)))
        y0 = max(0, min(H2, int(y0)))
        y1 = max(0, min(H2, int(y1)))
        if x1 <= x0 or y1 <= y0:
            return
        pre = _bbox_classes(sem, x0, y0, x1, y1)
        # Only count overlap with chart region (sem != BG inside the chart rect).
        for c, n in pre.items():
            if c != int(BG):
                chart_lost[str(c)] = chart_lost.get(str(c), 0) + int(n)
        page[y0:y1, x0:x1] = color_px
        sem[y0:y1, x0:x1] = label_px
        inst[y0:y1, x0:x1] = inst_px
        overlap_rects.append(dict(x0=x0, y0=y0, x1=x1, y1=y1, pre_classes={str(k): v for k, v in pre.items()}))

    # Variant mix: 1-3 overlapping elements per chart.
    kinds = [str(k) for k in rng.choice(["modal", "scroll", "cursor-plot", "tooltip", "hover-overlay"], size=int(rng.integers(1, 4)), replace=False)]
    if "modal" in kinds:
        # A rectangle covering one corner of the chart.
        corner = str(rng.choice(["tl", "tr", "bl", "br"]))
        w = int(rng.integers(80, min(220, max(81, W // 2))))
        h = int(rng.integers(60, min(140, max(61, H // 2))))
        if corner == "tl":
            x0, y0 = plot_x0 + 8, plot_y0 + 8
        elif corner == "tr":
            x0, y0 = plot_x1 - w - 8, plot_y0 + 8
        elif corner == "bl":
            x0, y0 = plot_x0 + 8, plot_y1 - h - 8
        else:
            x0, y0 = plot_x1 - w - 8, plot_y1 - h - 8
        x1, y1 = x0 + w, y0 + h
        box_bg = tuple(int(v) for v in rng.uniform(245, 255, 3))
        _overwrite_rect(x0, y0, x1, y1, box_bg)
        # Border + a title line.
        cv2.rectangle(page, (x0, y0), (x1 - 1, y1 - 1), (120, 120, 120), 1)
        cv2.putText(page, " ".join(rng.choice(_WORDS, 2)).title(), (x0 + 8, y0 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1, cv2.LINE_AA)
        cv2.line(page, (x0, y0 + 28), (x1, y0 + 28), (200, 200, 200), 1)

    if "scroll" in kinds:
        # A scrollbar strip overlapping the right edge of the plot (10 px wide, full plot height).
        bar_w = 10
        x0 = plot_x1 - bar_w
        x1 = plot_x1
        _overwrite_rect(x0, plot_y0, x1, plot_y1, (230, 230, 230))
        thumb_y0 = int(plot_y0 + (plot_y1 - plot_y0) * 0.3)
        thumb_y1 = int(plot_y0 + (plot_y1 - plot_y0) * 0.7)
        _overwrite_rect(x0 + 1, thumb_y0, x1 - 1, thumb_y1, (170, 170, 170))

    if "cursor-plot" in kinds:
        # A mouse cursor landing somewhere inside the plot area.
        cx = int(rng.integers(plot_x0 + 10, max(plot_x0 + 11, plot_x1 - 20)))
        cy = int(rng.integers(plot_y0 + 10, max(plot_y0 + 11, plot_y1 - 20)))
        # Approximate bounding box of the cursor polygon.
        _overwrite_rect(cx, cy, cx + 12, cy + 19, (255, 255, 255))
        pts = np.array([[cx, cy], [cx, cy + 16], [cx + 4, cy + 12], [cx + 7, cy + 18], [cx + 9, cy + 17], [cx + 6, cy + 11], [cx + 11, cy + 11]], np.int32)
        cv2.fillPoly(page, [pts], (255, 255, 255))
        cv2.polylines(page, [pts], True, (0, 0, 0), 1)

    if "tooltip" in kinds:
        # A tooltip box in the top-right of the plot.
        w = int(rng.integers(80, 150))
        h = int(rng.integers(30, 50))
        x1 = min(plot_x1 - 10, plot_x1 - 10)
        x0 = x1 - w
        y0 = plot_y0 + int(rng.integers(10, 40))
        y1 = y0 + h
        _overwrite_rect(x0, y0, x1, y1, (255, 255, 240))
        cv2.rectangle(page, (x0, y0), (x1 - 1, y1 - 1), (90, 90, 90), 1)
        cv2.putText(page, f"x={int(rng.integers(0, 1000))}", (x0 + 6, y0 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1, cv2.LINE_AA)
        cv2.putText(page, f"y={rng.uniform(0, 100):.2f}", (x0 + 6, y0 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1, cv2.LINE_AA)

    if "hover-overlay" in kinds:
        # A horizontal hover guide across the plot (semi-transparent band, approximated as a lightened strip).
        y0 = int(rng.integers(plot_y0 + 20, max(plot_y0 + 21, plot_y1 - 20)))
        y1 = y0 + 2
        _overwrite_rect(plot_x0, y0, plot_x1, y1, (200, 200, 200))

    meta = _shift_meta(r.meta, left, top, PW, PH)
    meta["clutter"] = dict(left=left, top=top, right=right, bottom=bottom, kind="overlap", kinds=sorted(kinds))
    meta["chart_rect"] = [left, top, left + W, top + H]
    meta["sem_mapping"] = dict(
        chart_classes=_bbox_classes(sem, left, top, left + W, top + H),
        clutter_region_px=int((PW * PH) - (W * H)),
        chart_region_px=int(W * H),
        overlap_rects=overlap_rects,
        chart_pixels_lost=chart_lost,
    )
    return r.__class__(image=page, sem=sem, inst=inst, meta=meta)


# ------------------------------------------------------------------- make/main

def make(seed: int, factor: str, renderer: str):
    r = _render_base(seed, renderer)
    if factor == "clutter-max":
        r = _clutter_max(r, seed, renderer)
    elif factor == "clutter-overlap":
        r = _clutter_overlap(r, seed, renderer)
    else:
        raise ValueError(factor)
    r.meta["probe"] = dict(factor=factor, renderer=renderer)
    return r


def _work(args):
    out, seed, factor, renderer = args
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    stem = os.path.join(out, f"{seed:07d}")
    if os.path.exists(stem + ".json"):
        return seed, True
    try:
        r = make(seed, factor, renderer)
    except Exception as e:
        return seed, repr(e)
    cv2.imwrite(stem + ".png", r.image[..., ::-1])
    cv2.imwrite(stem + ".sem.png", r.sem)
    cv2.imwrite(stem + ".inst.png", r.inst)
    with open(stem + ".json.tmp", "w") as f:
        json.dump(r.meta, f)
    os.replace(stem + ".json.tmp", stem + ".json")
    return seed, True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--factor", required=True, choices=["clutter-max", "clutter-overlap"])
    ap.add_argument("--start", type=int, default=15_110_000)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--renderer", choices=["matplotlib", "plotly", "chartjs"], default="matplotlib")
    a = ap.parse_args()
    if a.start < 15_100_000:
        raise SystemExit("seed must be >= 15,100,000")
    os.makedirs(a.out, exist_ok=True)
    jobs = [(a.out, s, a.factor, a.renderer) for s in range(a.start, a.start + a.count)]
    t0 = time.time()
    failed = 0
    with Pool(a.workers, maxtasksperchild=50) as pool:
        for i, (seed, ok) in enumerate(pool.imap_unordered(_work, jobs, chunksize=2)):
            if ok is not True:
                failed += 1
                print(f"seed {seed} failed: {ok}", file=sys.stderr)
            if (i + 1) % 25 == 0:
                print(f"{i + 1}/{len(jobs)}  {time.time() - t0:.0f}s  failed={failed}", flush=True)
    print(f"done {len(jobs)} in {time.time() - t0:.0f}s, failed={failed}")


if __name__ == "__main__":
    main()
