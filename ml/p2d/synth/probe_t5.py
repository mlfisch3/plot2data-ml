"""Probe sets for robustness: the same synthetic charts with one factor changed, truth kept exact.

Every set is written in the standard dataset format (see `build.py`), with the
seed as the sample id, so the same chart can be compared across sets:

    python -m p2d.synth.probe_t5 --factor dpr --k 2 --out data/t5-dpr2 --start 15000000 --count 100 --workers 3

Factors:

- `dpr K`: the chart re-rendered at K times the device pixel ratio. matplotlib:
  the figure keeps its size in inches and gets K times the dpi, so fonts, line
  widths, markers and layout scale together, exactly like a retina screenshot.
  Plotly: kaleido renders at scale K (the layout is in CSS pixels; the truth is
  mapped through the same scale).
- `resize K`: the rendered image resampled by K (area for K < 1, cubic above),
  the way a screenshot is when it is pasted into a document.
- `jpeg Q`: JPEG at quality Q.
- `blur S`: Gaussian blur of sigma S pixels, plus a down-and-up resample at 0.7
  (screen capture softness).
- `dark`: paper inverted with hues kept (a dark theme made from a light one).
- `clutter`: the chart pasted into a larger page with text blocks, a toolbar,
  a sidebar, a scrollbar and a second chart, at a random offset.
- `skew D`: the whole image rotated by D degrees (a photographed page). The
  plot area in the truth becomes the bounding box of the rotated frame, and a
  tick's `pos` its rotated anchor's coordinate along its axis; only the pixel
  geometry metrics mean much on this set.

Pixel coordinates keep the convention of `mpl_render`: the centre of pixel
column i is x = i. A coordinate c under a resample by K becomes (c + 0.5) K - 0.5.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os as _os

_os.environ.setdefault("OMP_NUM_THREADS", "1")
import os  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from multiprocessing import Pool  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

cv2.setNumThreads(1)


# ----------------------------------------------------------------------------- truth transforms

def _scale_meta(meta: dict, k: float) -> dict:
    """The truth of a chart resampled by K: every pixel coordinate mapped through (c + 0.5) K - 0.5."""
    f = lambda c: (c + 0.5) * k - 0.5  # noqa: E731
    m = json.loads(json.dumps(meta))
    m["width"] = int(round(meta["width"] * k))
    m["height"] = int(round(meta["height"] * k))
    m["plot_area"] = [f(v) for v in meta["plot_area"]]
    for key in ("xticks", "yticks"):
        for t in m[key]:
            t["pos"] = f(t["pos"])
            t["anchor"] = [f(t["anchor"][0]), f(t["anchor"][1])]
            if t.get("bbox"):
                b = t["bbox"]
                t["bbox"] = [f(b[0]), f(b[1]), f(b[2]), f(b[3])]
    for s in m["series"]:
        s["path_px"] = [[f(x), f(y)] for x, y in s["path_px"]]
        s["markers_px"] = [[f(x), f(y)] for x, y in s["markers_px"]]
        s["linewidth_px"] = s["linewidth_px"] * k
        s["markersize_px"] = s["markersize_px"] * k
    if m.get("legend_bbox"):
        m["legend_bbox"] = [f(v) for v in meta["legend_bbox"]]
    return m


def _shift_meta(meta: dict, dx: float, dy: float, width: int, height: int) -> dict:
    m = json.loads(json.dumps(meta))
    m["width"], m["height"] = width, height
    m["plot_area"] = [meta["plot_area"][0] + dx, meta["plot_area"][1] + dy, meta["plot_area"][2] + dx, meta["plot_area"][3] + dy]
    for key, d in (("xticks", dx), ("yticks", dy)):
        for t in m[key]:
            t["pos"] = t["pos"] + d
            t["anchor"] = [t["anchor"][0] + dx, t["anchor"][1] + dy]
            if t.get("bbox"):
                b = t["bbox"]
                t["bbox"] = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy]
    for s in m["series"]:
        s["path_px"] = [[x + dx, y + dy] for x, y in s["path_px"]]
        s["markers_px"] = [[x + dx, y + dy] for x, y in s["markers_px"]]
    if m.get("legend_bbox"):
        b = meta["legend_bbox"]
        m["legend_bbox"] = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy]
    return m


def _affine_meta(meta: dict, M: np.ndarray, width: int, height: int) -> dict:
    """The truth under a 2x3 affine map (pixel centres to pixel centres)."""

    def ap(pts):
        p = np.asarray(pts, float).reshape(-1, 2)
        return (p @ M[:, :2].T + M[:, 2]).tolist()

    def box(b):
        q = np.array(ap([[b[0], b[1]], [b[2], b[1]], [b[0], b[3]], [b[2], b[3]]]))
        return [float(q[:, 0].min()), float(q[:, 1].min()), float(q[:, 0].max()), float(q[:, 1].max())]

    m = json.loads(json.dumps(meta))
    m["width"], m["height"] = width, height
    m["plot_area"] = box(meta["plot_area"])
    for key in ("xticks", "yticks"):
        for t in m[key]:
            a = ap([t["anchor"]])[0]
            t["anchor"] = a
            t["pos"] = a[0] if key == "xticks" else a[1]
            if t.get("bbox"):
                t["bbox"] = box(t["bbox"])
    for s in m["series"]:
        s["path_px"] = ap(s["path_px"]) if s["path_px"] else []
        s["markers_px"] = ap(s["markers_px"]) if s["markers_px"] else []
    if m.get("legend_bbox"):
        m["legend_bbox"] = box(meta["legend_bbox"])
    return m


# ----------------------------------------------------------------------------- renderers

def _render_base(seed: int, renderer: str):
    if renderer == "plotly":
        from .plotly_render import generate
    else:
        from .mpl_render import generate
    return generate(seed)


def _render_dpr(seed: int, renderer: str, k: float):
    """The chart at K times the device pixel ratio, truth included."""
    if renderer == "plotly":
        from . import plotly_render as PR

        base = PR.generate(seed)  # truth in CSS pixels
        orig = PR._render

        def scaled(fig, w, h):
            import kaleido

            if not PR._server:
                kaleido.start_sync_server(silence_warnings=True)
                PR._server = True
            png = kaleido.calc_fig_sync(fig, opts=dict(format="png", width=w, height=h, scale=k))
            from PIL import Image
            import io

            return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))

        PR._render = scaled
        try:
            r = PR.generate(seed)  # same seed, same layout, K times the pixels
        finally:
            PR._render = orig
        meta = _scale_meta(base.meta, k)
        meta["width"], meta["height"] = r.image.shape[1], r.image.shape[0]
        # The label boxes the scaled pass found (at CSS positions) are unreliable: take the scaled base ones.
        return PR.Rendered(image=r.image, sem=r.sem, inst=r.inst, meta=meta)
    import matplotlib.pyplot as plt

    from . import mpl_render as MR

    orig = plt.figure

    def figure(*a, **kw):
        kw["dpi"] = kw.get("dpi", 100.0) * k
        return orig(*a, **kw)

    plt.figure = figure
    try:
        r = MR.generate(seed)
    finally:
        plt.figure = orig
    return r


# ----------------------------------------------------------------------------- image factors

def _resize(r, k: float):
    H, W = r.image.shape[:2]
    nw, nh = max(8, int(round(W * k))), max(8, int(round(H * k)))
    interp = cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC
    img = cv2.resize(r.image, (nw, nh), interpolation=interp)
    sem = cv2.resize(r.sem, (nw, nh), interpolation=cv2.INTER_NEAREST)
    inst = cv2.resize(r.inst, (nw, nh), interpolation=cv2.INTER_NEAREST)
    meta = _scale_meta(r.meta, nw / W)
    meta["width"], meta["height"] = nw, nh
    return r.__class__(image=img, sem=sem, inst=inst, meta=meta)


def _jpeg(r, q: int):
    ok, enc = cv2.imencode(".jpg", r.image[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, int(q)])
    img = cv2.imdecode(enc, cv2.IMREAD_COLOR)[..., ::-1].copy()
    return r.__class__(image=img, sem=r.sem, inst=r.inst, meta=r.meta)


def _blur(r, sigma: float, rng: np.random.Generator):
    H, W = r.image.shape[:2]
    f = 0.7
    small = cv2.resize(r.image, (max(8, int(W * f)), max(8, int(H * f))), interpolation=cv2.INTER_AREA)
    img = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
    if sigma > 0:
        img = cv2.GaussianBlur(img, (0, 0), sigma)
    return r.__class__(image=img, sem=r.sem, inst=r.inst, meta=r.meta)


def _dark(r):
    """Invert lightness, keep hue: white paper to black, black text to white, a blue line stays blue."""
    inv = 255 - r.image
    hsv = cv2.cvtColor(np.ascontiguousarray(inv), cv2.COLOR_RGB2HSV)
    hsv[..., 0] = (hsv[..., 0].astype(int) + 90) % 180
    img = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    return r.__class__(image=img, sem=r.sem, inst=r.inst, meta=r.meta)


_WORDS = ("revenue growth quarter report total users index value change rate average median share market "
          "forecast actual baseline region north south east west product channel segment summary notes").split()


def _text_block(rng: np.random.Generator, w: int, h: int, bg, fg, scale: float = 0.45) -> np.ndarray:
    out = np.full((h, w, 3), bg, np.uint8)
    y = int(18 * scale / 0.45)
    lh = int(16 * scale / 0.45)
    while y < h - 4:
        line = " ".join(rng.choice(_WORDS, int(rng.integers(3, 12))))
        cv2.putText(out, line, (6, y), cv2.FONT_HERSHEY_SIMPLEX, scale, fg, 1, cv2.LINE_AA)
        y += lh
        if rng.random() < 0.15:
            y += lh // 2
    return out


def _clutter(r, seed: int, renderer: str):
    """The chart inside a page: toolbar, sidebar, text, a second chart, a scrollbar."""
    from .mpl_render import BG

    rng = np.random.default_rng(seed + 7)
    H, W = r.image.shape[:2]
    paper = r.image[0, 0].tolist()
    page_bg = paper if rng.random() < 0.6 else [int(v) for v in rng.uniform(235, 255, 3)]
    fg = (60, 60, 60) if np.mean(page_bg) > 128 else (200, 200, 200)
    top = int(rng.integers(0, 70))
    left = int(rng.integers(0, 260))
    right = int(rng.integers(0, 260))
    bottom = int(rng.integers(0, 160))
    PW, PH = W + left + right, H + top + bottom
    page = np.full((PH, PW, 3), page_bg, np.uint8)
    sem = np.full((PH, PW), BG, np.uint8)
    inst = np.zeros((PH, PW), np.uint8)
    if top >= 24:
        # A toolbar or title bar.
        bar = [int(v) for v in rng.uniform(40, 240, 3)] if rng.random() < 0.5 else [int(v) for v in rng.uniform(225, 245, 3)]
        page[: min(top, int(rng.integers(24, 48)))] = bar
        cv2.putText(page, " ".join(rng.choice(_WORDS, 3)).title(), (12, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (240, 240, 240) if np.mean(bar) < 128 else (40, 40, 40), 1, cv2.LINE_AA)
    if left >= 60:
        page[top:, : left - 8] = _text_block(rng, left - 8, PH - top, page_bg, fg)
        if rng.random() < 0.5:
            cv2.line(page, (left - 6, top), (left - 6, PH), (200, 200, 200), 1)
    if right >= 60:
        if rng.random() < 0.5:
            # A second chart beside this one, scaled to the strip.
            try:
                other = _render_base(seed + 1_000_000, renderer).image
                s = min((right - 12) / other.shape[1], (PH - top - 8) / other.shape[0], 1.0)
                o = cv2.resize(other, (max(8, int(other.shape[1] * s)), max(8, int(other.shape[0] * s))), interpolation=cv2.INTER_AREA)
                page[top + 4: top + 4 + o.shape[0], left + W + 8: left + W + 8 + o.shape[1]] = o
            except Exception:
                page[top:, left + W + 8:] = _text_block(rng, right - 8, PH - top, page_bg, fg)
        else:
            page[top:, left + W + 8:] = _text_block(rng, right - 8, PH - top, page_bg, fg)
    if bottom >= 30:
        page[top + H + 6:, left: left + W] = _text_block(rng, W, bottom - 6, page_bg, fg)
    if rng.random() < 0.5:
        # A scrollbar on the right edge.
        page[:, PW - 12:] = (235, 235, 235)
        y0 = int(rng.integers(0, PH // 2))
        page[y0: y0 + PH // 3, PW - 10: PW - 2] = (180, 180, 180)
    if rng.random() < 0.4:
        # A mouse cursor somewhere on the page.
        cx, cy = int(rng.integers(0, PW - 20)), int(rng.integers(0, PH - 20))
        pts = np.array([[cx, cy], [cx, cy + 16], [cx + 4, cy + 12], [cx + 7, cy + 18], [cx + 9, cy + 17], [cx + 6, cy + 11], [cx + 11, cy + 11]], np.int32)
        cv2.fillPoly(page, [pts], (255, 255, 255))
        cv2.polylines(page, [pts], True, (0, 0, 0), 1)
    page[top: top + H, left: left + W] = r.image
    sem[top: top + H, left: left + W] = r.sem
    inst[top: top + H, left: left + W] = r.inst
    meta = _shift_meta(r.meta, left, top, PW, PH)
    meta["clutter"] = dict(left=left, top=top, right=right, bottom=bottom)
    return r.__class__(image=page, sem=sem, inst=inst, meta=meta)


def _skew(r, deg: float):
    H, W = r.image.shape[:2]
    c = (W / 2 - 0.5, H / 2 - 0.5)
    R = cv2.getRotationMatrix2D(c, deg, 1.0)
    cos, sin = abs(R[0, 0]), abs(R[0, 1])
    nw, nh = int(math.ceil(W * cos + H * sin)), int(math.ceil(W * sin + H * cos))
    R[0, 2] += (nw - W) / 2
    R[1, 2] += (nh - H) / 2
    paper = [int(v) for v in r.image[0, 0]]
    img = cv2.warpAffine(r.image, R, (nw, nh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=paper)
    sem = cv2.warpAffine(r.sem, R, (nw, nh), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    inst = cv2.warpAffine(r.inst, R, (nw, nh), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    meta = _affine_meta(r.meta, R, nw, nh)
    meta["skew_deg"] = deg
    return r.__class__(image=img, sem=sem, inst=inst, meta=meta)


# ----------------------------------------------------------------------------- driver

def make(seed: int, factor: str, value: float, renderer: str):
    rng = np.random.default_rng(seed + 11)
    if factor == "dpr":
        r = _render_dpr(seed, renderer, value) if value != 1 else _render_base(seed, renderer)
    else:
        r = _render_base(seed, renderer)
        if factor == "resize":
            r = _resize(r, value)
        elif factor == "jpeg":
            r = _jpeg(r, int(value))
        elif factor == "blur":
            r = _blur(r, value, rng)
        elif factor == "dark":
            r = _dark(r)
        elif factor == "clutter":
            r = _clutter(r, seed, renderer)
        elif factor == "skew":
            r = _skew(r, value)
        elif factor != "none":
            raise ValueError(factor)
    r.meta["probe"] = dict(factor=factor, value=value, renderer=renderer)
    return r


def _work(args):
    out, seed, factor, value, renderer = args
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    stem = os.path.join(out, f"{seed:07d}")
    if os.path.exists(stem + ".json"):
        return seed, True
    try:
        r = make(seed, factor, value, renderer)
    except Exception as e:  # a bad random combination is skipped, not fatal
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
    ap.add_argument("--factor", required=True, choices=["none", "dpr", "resize", "jpeg", "blur", "dark", "clutter", "skew"])
    ap.add_argument("--value", type=float, default=1.0, help="K for dpr/resize, Q for jpeg, sigma for blur, degrees for skew")
    ap.add_argument("--start", type=int, default=15_000_000)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--renderer", choices=["matplotlib", "plotly"], default="matplotlib")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    jobs = [(a.out, s, a.factor, a.value, a.renderer) for s in range(a.start, a.start + a.count)]
    t0 = time.time()
    failed = 0
    with Pool(a.workers, maxtasksperchild=50) as pool:
        for i, (seed, ok) in enumerate(pool.imap_unordered(_work, jobs, chunksize=2)):
            if ok is not True:
                failed += 1
                print(f"seed {seed} failed: {ok}", file=sys.stderr)
            if (i + 1) % 50 == 0:
                print(f"{i + 1}/{len(jobs)}  {time.time() - t0:.0f}s  failed={failed}", flush=True)
    print(f"done {len(jobs)} in {time.time() - t0:.0f}s, failed={failed}")


if __name__ == "__main__":
    main()
