"""Probe sets for the precision diagnosis (team t3): matplotlib charts that isolate one error source each.

    python -m p2d.synth.probe_t3 --family peaks --out data/t3-peaks --start 13000000 --count 96 --workers 3

Same dataset format as `build.py` (PNG, .sem.png, .inst.png, JSON with exact
geometry), same pixel convention (the centre of pixel column i is x = i). The
seed selects one point of a family's parameter grid, so a sweep is a contiguous
range of seeds and every chart can be regenerated from its id. The chosen
parameters are recorded under `meta["probe"]`.

Families:
- peaks: one polyline with sharp turning points of known prominence, width and
  angle; round, mitred or bevelled joins; 1 to 5 px lines; 400 to 1800 px wide.
- scale: the same smooth curve at 500, 900, 1400 and 1800 px, thin and normal
  lines, either everything scaled (a retina screenshot) or only the canvas.
- ticks: label-only axes, marks without grid, grid without marks, in/out,
  labels on the right, in a few house looks: the label-to-tick offset.
- width: a smooth curve drawn 0.5 to 6 px wide, light and dark ink, over a grid.
- log: log y and log-log axes with steep slopes.
- grid: many evenly spaced gridlines and dense ticks, minor grid.
- frame: spines hidden in every combination, offset spines, tinted paper.
- spikes: dense series (300 to 2,500 points) with one-sample spikes, so the
  flanks are narrower than a column; round, mitred and bevelled joins.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from multiprocessing import Pool

os.environ.setdefault("OMP_NUM_THREADS", "1")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.collections import Collection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from .mpl_render import (AXIS, DATA, GRID, LEGEND_SYMBOL, TEXT, TICK_LABEL, BG, Rendered, _clean_label, _leaves,  # noqa: E402
                         _render_alpha, _to_px)

SEED_BASE = 13_000_000
# Each family has its own seed range, so an id names one chart across all probe sets.
FAMILY_BASE = {"peaks": 13_000_000, "scale": 13_100_000, "ticks": 13_200_000, "width": 13_300_000, "log": 13_400_000,
               "grid": 13_500_000, "frame": 13_600_000, "spikes": 13_700_000}


def _grid(seed: int, family: str, *sizes: int) -> list[int]:
    """Mixed-radix digits of the seed offset: one index per parameter, cycling fastest first."""
    k = seed - FAMILY_BASE[family]
    out = []
    for n in sizes:
        out.append(k % n)
        k //= n
    return out


def _pick(seed: int, *sizes: int) -> list[int]:
    """One random point of the grid per seed, so any contiguous range of seeds samples it evenly."""
    rng = np.random.default_rng(seed + 7)
    return [int(rng.integers(n)) for n in sizes]


def finish(fig, ax, canvas, series_meta: list[dict], data_artists: list, seed: int, probe: dict,
           grid_extra: list | None = None) -> Rendered:
    """Render, build the label maps by re-rendering per group, and record the geometry (as mpl_render does)."""
    canvas.draw()
    ax.set_xlim(ax.get_xlim())
    ax.set_ylim(ax.get_ylim())
    fig.set_layout_engine("none")
    canvas.draw()
    rgba = np.asarray(canvas.buffer_rgba()).copy()
    H, W = rgba.shape[:2]
    image = rgba[..., :3].copy()

    leaves = _leaves(fig)
    xt_labels = [t for t in ax.get_xticklabels() if t.get_visible() and t.get_text()]
    yt_labels = [t for t in ax.get_yticklabels() if t.get_visible() and t.get_text()]
    offset_texts = [ax.xaxis.get_offset_text(), ax.yaxis.get_offset_text()]
    tick_label_ids = {id(t) for t in xt_labels + yt_labels + [o for o in offset_texts if o.get_text()]}
    axis_ids = {id(s) for s in ax.spines.values()}
    for axis in (ax.xaxis, ax.yaxis):
        for tl in axis.get_ticklines() + axis.get_ticklines(minor=True):
            axis_ids.add(id(tl))
    grid_ids = {id(g) for g in ax.xaxis.get_gridlines() + ax.yaxis.get_gridlines()}
    for axis in (ax.xaxis, ax.yaxis):
        for t in axis.get_minor_ticks():
            grid_ids.add(id(t.gridline))
    grid_ids |= {id(a) for a in (grid_extra or [])}
    from matplotlib.text import Text

    text_ids = {id(a) for a in leaves if isinstance(a, Text) and a.get_text() and id(a) not in tick_label_ids}
    alphas = {}
    for cls, ids in ((GRID, grid_ids), (AXIS, axis_ids), (LEGEND_SYMBOL, set()), (TICK_LABEL, tick_label_ids), (TEXT, text_ids)):
        alphas[cls] = _render_alpha(fig, canvas, leaves, ids) if ids else np.zeros((H, W), np.uint8)
    series_alpha = [_render_alpha(fig, canvas, leaves, {id(a)}) for a in data_artists]
    thr = 60
    stack = [alphas[GRID], alphas[AXIS]] + series_alpha + [alphas[LEGEND_SYMBOL], alphas[TICK_LABEL], alphas[TEXT]]
    cls_of = [GRID, AXIS] + [DATA] * len(series_alpha) + [LEGEND_SYMBOL, TICK_LABEL, TEXT]
    st = np.stack(stack, 0).astype(np.int16) + np.arange(len(stack), dtype=np.int16)[:, None, None]
    idx = st.argmax(0)
    peak = st.max(0) - idx
    sem = np.where(peak >= thr, np.array(cls_of, np.uint8)[idx], BG).astype(np.uint8)
    inst = np.zeros((H, W), np.uint8)
    if series_alpha:
        sa = np.stack(series_alpha, 0).astype(np.int16) + np.arange(len(series_alpha), dtype=np.int16)[:, None, None]
        inst = np.where(sem == DATA, sa.argmax(0) + 1, 0).astype(np.uint8)

    bb = ax.get_window_extent(renderer=canvas.get_renderer())
    plot_area = [bb.x0 - 0.5, H - bb.y1 - 0.5, bb.x1 - 0.5, H - bb.y0 - 0.5]
    renderer = canvas.get_renderer()
    xlim, ylim = ax.get_xlim(), ax.get_ylim()

    def ticks_for(axis_name: str):
        axis = ax.xaxis if axis_name == "x" else ax.yaxis
        lim = xlim if axis_name == "x" else ylim
        out = []
        for tick, v in zip(axis.get_major_ticks(), axis.get_majorticklocs()):
            lo, hi = min(lim), max(lim)
            eps = (hi - lo) * 1e-9
            if not (lo - eps <= v <= hi + eps):
                continue
            label = tick.label1 if tick.label1.get_visible() and tick.label1.get_text() else tick.label2
            if not (label.get_visible() and label.get_text()):
                continue
            side = "low" if label is tick.label1 else "high"
            e = label.get_window_extent(renderer)
            if axis_name == "x":
                pos = float(_to_px(ax, H, [v], [ylim[0]])[0][0])
                anchor = [pos, plot_area[3] if side == "low" else plot_area[1]]
            else:
                pos = float(_to_px(ax, H, [xlim[0]], [v])[0][1])
                anchor = [plot_area[0] if side == "low" else plot_area[2], pos]
            out.append(dict(value=float(v), pos=pos, anchor=anchor, side=side, text=_clean_label(label.get_text()),
                            raw=label.get_text(), bbox=[e.x0 - 0.5, H - e.y1 - 0.5, e.x1 - 0.5, H - e.y0 - 0.5]))
        return out

    out_series = []
    for m, art in zip(series_meta, data_artists):
        x, y = m["x"], m["y"]
        path = _to_px(ax, H, x, y) if m["kind"] != "scatter" else np.zeros((0, 2))
        markers = _to_px(ax, H, x, y) if m["kind"] in ("scatter", "line+markers") else np.zeros((0, 2))
        color = matplotlib.colors.to_hex(art.get_color())
        out_series.append(dict(kind=m["kind"], label=m["label"], color=color, linestyle=m["ls"],
                               linewidth_px=m["lw"] * fig.dpi / 72.0, marker=m.get("marker"),
                               markersize_px=m.get("ms", 6.0) * fig.dpi / 72.0, x=np.asarray(x).tolist(), y=np.asarray(y).tolist(),
                               path_px=path.round(3).tolist(), markers_px=markers.round(3).tolist()))
    meta = dict(
        seed=seed, generator="matplotlib", style="probe", preset="t3-" + probe["family"], font=plt.rcParams["font.family"][0],
        width=W, height=H, plot_area=plot_area, xscale=ax.get_xscale(), xdate=None, yscale=ax.get_yscale(),
        xlim=list(map(float, xlim)), ylim=list(map(float, ylim)), xticks=ticks_for("x"), yticks=ticks_for("y"),
        series=out_series, legend_bbox=None, offset_text=[_clean_label(o.get_text()) for o in offset_texts], probe=probe,
    )
    plt.close(fig)
    return Rendered(image=image, sem=sem, inst=inst, meta=meta)


def _figure(wpx: float, hpx: float, dpi: float, font_pt: float, font: str = "DejaVu Sans"):
    rc = {"font.family": font, "font.size": font_pt, "axes.unicode_minus": False, "path.simplify": False}
    ctx = plt.rc_context(rc)
    ctx.__enter__()
    fig = plt.figure(figsize=(wpx / dpi, hpx / dpi), dpi=dpi)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    return fig, ax, canvas, ctx


def _plot(ax, x, y, lw_px: float, dpi: float, color: str, ls: str = "-", join: str = "round", cap: str = "projecting"):
    (art,) = ax.plot(x, y, lw=lw_px * 72.0 / dpi, ls=ls, color=color, label="Series 1", solid_joinstyle=join,
                     solid_capstyle=cap)
    art.set_snap(False)
    return art


def _smooth(rng: np.random.Generator, n: int) -> np.ndarray:
    """A damped oscillation plus a slow trend, unit scale, on n points."""
    t = np.linspace(0, 1, n)
    y = np.exp(-rng.uniform(0.5, 3) * t) * np.cos(2 * np.pi * rng.uniform(1.5, 5) * t + rng.uniform(0, 6)) + rng.uniform(-0.5, 0.5) * t
    return (y - y.mean()) / (y.max() - y.min())


# --------------------------------------------------------------------------- families

def peaks(seed: int) -> Rendered:
    """A triangle wave (or narrow Gaussian peaks, or one-sample spikes) with known vertices."""
    rng = np.random.default_rng(seed)
    i_shape, i_prom, i_width, i_lw, i_join, i_size = _pick(seed, 3, 4, 4, 4, 3, 3)
    shape = ["triangle", "gauss", "spike"][i_shape]
    prom = [0.05, 0.12, 0.25, 0.5][i_prom]  # fraction of the plot height
    half_cols = [2, 4, 8, 16][i_width]  # half-width of a tooth, in pixel columns (sets the angle)
    lw_px = [1.0, 2.0, 3.0, 5.0][i_lw]
    join = ["round", "miter", "bevel"][i_join]
    wpx = [450, 900, 1800][i_size]
    hpx = wpx * 0.62
    dpi = 100.0
    fig, ax, canvas, ctx = _figure(wpx, hpx, dpi, max(7.0, 10 * wpx / 900))
    try:
        # Plot area is roughly 78% of the width: columns per data unit follow from that.
        n_cols_est = 0.78 * wpx
        if shape == "triangle":
            n_teeth = max(3, int(n_cols_est / (2 * half_cols)))
            k = np.arange(2 * n_teeth + 1)
            x = k / (2 * n_teeth)
            base = rng.uniform(0.2, 0.5)
            y = np.where(k % 2 == 1, base + prom, base)
            # a gentle slope so the teeth are not all identical
            y = y + rng.uniform(-0.1, 0.1) * x
        elif shape == "gauss":
            n = 2000
            x = np.linspace(0, 1, n)
            y = np.full(n, rng.uniform(0.2, 0.4))
            n_pk = int(rng.integers(4, 9))
            centres = np.linspace(0.08, 0.92, n_pk) + rng.uniform(-0.02, 0.02, n_pk)
            for c in centres:
                y += prom * np.exp(-0.5 * ((x - c) / (half_cols / n_cols_est)) ** 2)
        else:
            n = max(12, int(n_cols_est / max(1, half_cols)))
            x = np.linspace(0, 1, n)
            y = np.full(n, rng.uniform(0.2, 0.4)) + 0.02 * rng.normal(size=n)
            idx = np.arange(2, n - 2, max(3, n // 12))
            y[idx] += prom
        ax.set_ylim(0, 1)
        ax.set_xlim(0, 1)
        ax.yaxis.set_major_locator(mticker.MultipleLocator(0.2))
        ax.xaxis.set_major_locator(mticker.MultipleLocator(0.2))
        if rng.random() < 0.5:
            ax.grid(True, color="#dddddd", lw=0.8)
        art = _plot(ax, x, y, lw_px, dpi, ["#0072B2", "#D55E00", "#009E73", "#222222"][int(rng.integers(4))], join=join)
        fig.tight_layout(pad=0.6)
        probe = dict(family="peaks", shape=shape, prom=prom, half_cols=half_cols, lw_px=lw_px, join=join, width=wpx)
        return finish(fig, ax, canvas, [dict(kind="line", label="Series 1", x=x, y=y, lw=lw_px * 72 / dpi, ls="-")], [art], seed, probe)
    finally:
        ctx.__exit__(None, None, None)


def scale(seed: int) -> Rendered:
    """One curve at four widths and two line weights; `mode` scales everything (dpi) or only the canvas (size)."""
    i_w, i_lw, i_mode = _grid(seed, "scale", 4, 2, 2)
    curve_id = (seed - FAMILY_BASE["scale"]) // 16
    rng = np.random.default_rng(1_000_000 + curve_id)
    wpx = [500, 900, 1400, 1800][i_w]
    hpx = wpx * 0.62
    mode = ["dpi", "size"][i_mode]
    f = wpx / 900.0
    dpi = 100.0 * f if mode == "dpi" else 100.0
    lw_px = [1.0, 2.0][i_lw] * (f if mode == "dpi" else 1.0)
    font_pt = 10.0
    fig, ax, canvas, ctx = _figure(wpx, hpx, dpi, font_pt)
    try:
        n = 400
        x = np.linspace(0, 10, n)
        y = 50 + 40 * _smooth(rng, n)
        ax.grid(True, color="#dddddd", lw=0.8)
        art = _plot(ax, x, y, lw_px, dpi, "#0072B2")
        fig.tight_layout(pad=0.6)
        probe = dict(family="scale", width=wpx, lw_px=lw_px, mode=mode, curve=curve_id)
        return finish(fig, ax, canvas, [dict(kind="line", label="Series 1", x=x, y=y, lw=lw_px * 72 / dpi, ls="-")], [art], seed, probe)
    finally:
        ctx.__exit__(None, None, None)


def ticks(seed: int) -> Rendered:
    """Axes that differ only in what is drawn at a tick: nothing, a mark, a gridline; in/out; right/top labels."""
    rng = np.random.default_rng(seed)
    i_marks, i_grid, i_side, i_look, i_size = _pick(seed, 4, 2, 2, 3, 3)
    marks = ["none", "out", "in", "inout"][i_marks]
    grid = [False, True][i_grid]
    side = ["low", "high"][i_side]
    look = ["plain", "excel", "plotly"][i_look]
    wpx = [500, 900, 1600][i_size]
    hpx = wpx * 0.6
    dpi = 100.0
    font = {"plain": "DejaVu Sans", "excel": "Liberation Sans", "plotly": "Open Sans"}[look]
    fig, ax, canvas, ctx = _figure(wpx, hpx, dpi, float(rng.uniform(8, 13)), font)
    try:
        n = 300
        x = np.linspace(0, 100, n)
        y = 1000 + 800 * _smooth(rng, n)
        if look == "plotly":
            ax.set_facecolor("#E5ECF6")
            for s in ax.spines.values():
                s.set_visible(False)
            if grid:
                ax.grid(True, color="white", lw=1.0)
            ax.tick_params(colors="#2a3f5f")
        elif look == "excel":
            for k in ("left", "right", "top"):
                ax.spines[k].set_visible(False)
            ax.spines["bottom"].set_color("#BFBFBF")
            if grid:
                ax.grid(True, axis="y", color="#D9D9D9", lw=0.8)
            ax.tick_params(colors="#595959")
        else:
            if grid:
                ax.grid(True, color="#cccccc", lw=0.8, ls=str(rng.choice(["-", ":", "--"])))
        ax.set_axisbelow(True)
        length = 0.0 if marks == "none" else float(rng.choice([2, 3.5, 5, 7]))
        ax.tick_params(direction="out" if marks in ("none", "out") else marks, length=length, width=float(rng.uniform(0.6, 1.4)))
        if side == "high":
            ax.yaxis.tick_right()
            if rng.random() < 0.5:
                ax.xaxis.tick_top()
        ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(4, 11)), steps=[1, 2, 2.5, 5, 10]))
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(4, 11)), steps=[1, 2, 2.5, 5, 10]))
        art = _plot(ax, x, y, 2.0, dpi, "#0072B2")
        fig.tight_layout(pad=float(rng.uniform(0.4, 1.2)))
        probe = dict(family="ticks", marks=marks, grid=grid, side=side, look=look, width=wpx, length=length)
        return finish(fig, ax, canvas, [dict(kind="line", label="Series 1", x=x, y=y, lw=2.0 * 72 / dpi, ls="-")], [art], seed, probe)
    finally:
        ctx.__exit__(None, None, None)


def width(seed: int) -> Rendered:
    """A smooth curve drawn at a known width, in light or dark ink, with or without gridlines across it."""
    rng = np.random.default_rng(seed)
    i_lw, i_col, i_grid, i_size = _pick(seed, 8, 3, 2, 2)
    lw_px = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0][i_lw]
    color = ["#222222", "#0072B2", "#9ecae1"][i_col]  # dark, mid, light
    grid = [False, True][i_grid]
    wpx = [700, 1200][i_size]
    hpx = wpx * 0.62
    dpi = 100.0
    fig, ax, canvas, ctx = _figure(wpx, hpx, dpi, 10.0)
    try:
        n = 600
        x = np.linspace(0, 10, n)
        y = 50 + 40 * _smooth(rng, n)
        if grid:
            ax.grid(True, which="major", color="#bbbbbb", lw=1.0)
            ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=10))
        art = _plot(ax, x, y, lw_px, dpi, color)
        fig.tight_layout(pad=0.6)
        probe = dict(family="width", lw_px=lw_px, color=color, grid=grid, width=wpx)
        return finish(fig, ax, canvas, [dict(kind="line", label="Series 1", x=x, y=y, lw=lw_px * 72 / dpi, ls="-")], [art], seed, probe)
    finally:
        ctx.__exit__(None, None, None)


def log(seed: int) -> Rendered:
    """Log y (exponential growth, several decades) and log-log (power laws) with steep slopes."""
    rng = np.random.default_rng(seed)
    i_kind, i_dec, i_lw, i_size = _pick(seed, 2, 3, 2, 2)
    kind = ["logy", "loglog"][i_kind]
    decades = [2, 4, 6][i_dec]
    lw_px = [1.0, 2.0][i_lw]
    wpx = [600, 1200][i_size]
    hpx = wpx * 0.62
    dpi = 100.0
    fig, ax, canvas, ctx = _figure(wpx, hpx, dpi, 10.0)
    try:
        n = 400
        if kind == "logy":
            x = np.linspace(0, 10, n)
            y = 10 ** (rng.uniform(-2, 2) + decades * (x / 10) ** rng.uniform(0.7, 1.5) + 0.15 * _smooth(rng, n))
            ax.set_yscale("log")
        else:
            x = 10 ** np.linspace(0, decades, n)
            y = 10 ** (rng.uniform(-1, 1) + rng.uniform(-2.5, 2.5) * np.log10(x) + 0.2 * _smooth(rng, n))
            ax.set_xscale("log")
            ax.set_yscale("log")
        ax.grid(True, which="major", color="#cccccc", lw=0.8)
        if rng.random() < 0.5:
            ax.grid(True, which="minor", color="#eeeeee", lw=0.5)
        art = _plot(ax, x, y, lw_px, dpi, "#CC79A7")
        fig.tight_layout(pad=0.6)
        probe = dict(family="log", kind=kind, decades=decades, lw_px=lw_px, width=wpx)
        return finish(fig, ax, canvas, [dict(kind="line", label="Series 1", x=x, y=y, lw=lw_px * 72 / dpi, ls="-")], [art], seed, probe)
    finally:
        ctx.__exit__(None, None, None)


def grid(seed: int) -> Rendered:
    """Many evenly spaced gridlines and dense ticks: minor grid, 10 to 25 ticks per axis."""
    rng = np.random.default_rng(seed)
    i_n, i_minor, i_size = _pick(seed, 3, 2, 2)
    nb = [8, 15, 25][i_n]
    minor = [False, True][i_minor]
    wpx = [700, 1400][i_size]
    hpx = wpx * 0.62
    dpi = 100.0
    fig, ax, canvas, ctx = _figure(wpx, hpx, dpi, 8.0 if nb > 10 else 10.0)
    try:
        n = 500
        x = np.linspace(0, 100, n)
        y = 50 + 40 * _smooth(rng, n)
        ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=nb, steps=[1, 2, 2.5, 5, 10]))
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=nb, steps=[1, 2, 2.5, 5, 10]))
        ax.grid(True, which="major", color=str(rng.choice(["#bbbbbb", "#888888", "#dddddd"])), lw=float(rng.uniform(0.5, 1.2)))
        if minor:
            ax.minorticks_on()
            ax.grid(True, which="minor", color="#e8e8e8", lw=0.5)
        art = _plot(ax, x, y, 2.0, dpi, "#0072B2")
        fig.tight_layout(pad=0.6)
        probe = dict(family="grid", nbins=nb, minor=minor, width=wpx)
        return finish(fig, ax, canvas, [dict(kind="line", label="Series 1", x=x, y=y, lw=2.0 * 72 / dpi, ls="-")], [art], seed, probe)
    finally:
        ctx.__exit__(None, None, None)


def frame(seed: int) -> Rendered:
    """Spines in every combination, offset spines, tinted paper, grid on or off."""
    rng = np.random.default_rng(seed)
    i_sp, i_grid, i_tint, i_size = _pick(seed, 5, 2, 2, 2)
    spines = ["all", "lb", "b", "none", "offset"][i_sp]
    grid_on = [False, True][i_grid]
    tint = [False, True][i_tint]
    wpx = [600, 1300][i_size]
    hpx = wpx * 0.62
    dpi = 100.0
    fig, ax, canvas, ctx = _figure(wpx, hpx, dpi, 10.0)
    try:
        n = 300
        x = np.linspace(0, 10, n)
        y = 50 + 40 * _smooth(rng, n)
        sp = ax.spines
        if spines == "lb":
            sp["top"].set_visible(False)
            sp["right"].set_visible(False)
        elif spines == "b":
            for k in ("top", "right", "left"):
                sp[k].set_visible(False)
        elif spines == "none":
            for s in sp.values():
                s.set_visible(False)
        elif spines == "offset":
            sp["top"].set_visible(False)
            sp["right"].set_visible(False)
            off = float(rng.uniform(4, 12))
            sp["left"].set_position(("outward", off))
            sp["bottom"].set_position(("outward", off))
        if tint:
            ax.set_facecolor("#E5ECF6" if rng.random() < 0.5 else "#f7f3ea")
        if grid_on:
            ax.grid(True, color="white" if tint else "#dddddd", lw=1.0)
        ax.set_axisbelow(True)
        ax.tick_params(length=float(rng.choice([0, 3.5])))
        art = _plot(ax, x, y, 2.0, dpi, "#0072B2")
        fig.tight_layout(pad=float(rng.uniform(0.4, 1.5)))
        probe = dict(family="frame", spines=spines, grid=grid_on, tint=tint, width=wpx)
        return finish(fig, ax, canvas, [dict(kind="line", label="Series 1", x=x, y=y, lw=2.0 * 72 / dpi, ls="-")], [art], seed, probe)
    finally:
        ctx.__exit__(None, None, None)


def spikes(seed: int) -> Rendered:
    """Dense series (more points than columns) with one-sample spikes: flanks narrower than a pixel column."""
    rng = np.random.default_rng(seed)
    i_n, i_prom, i_sp, i_lw, i_join, i_size = _pick(seed, 4, 4, 4, 4, 3, 3)
    n = [300, 800, 1500, 2500][i_n]
    prom = [0.05, 0.12, 0.25, 0.5][i_prom]
    spacing = [4, 8, 16, 32][i_sp]  # columns between spikes
    lw_px = [1.0, 2.0, 3.0, 5.0][i_lw]
    join = ["round", "miter", "bevel"][i_join]
    wpx = [450, 900, 1800][i_size]
    hpx = wpx * 0.62
    dpi = 100.0
    fig, ax, canvas, ctx = _figure(wpx, hpx, dpi, max(7.0, 10 * wpx / 900))
    try:
        n_cols_est = 0.78 * wpx
        x = np.linspace(0, 1, n)
        y = rng.uniform(0.2, 0.4) + 0.08 * _smooth(rng, n)
        step = max(2, int(round(n * spacing / n_cols_est)))
        idx = np.arange(step, n - step, step)
        y[idx] += prom * rng.uniform(1.0, 1.4, len(idx))
        ax.set_ylim(0, 1)
        ax.set_xlim(0, 1)
        ax.yaxis.set_major_locator(mticker.MultipleLocator(0.2))
        ax.xaxis.set_major_locator(mticker.MultipleLocator(0.2))
        if rng.random() < 0.5:
            ax.grid(True, color="#dddddd", lw=0.8)
        art = _plot(ax, x, y, lw_px, dpi, ["#0072B2", "#D55E00", "#009E73", "#222222"][int(rng.integers(4))], join=join)
        fig.tight_layout(pad=0.6)
        probe = dict(family="spikes", n=n, prom=prom, spacing=spacing, lw_px=lw_px, join=join, width=wpx,
                     flank_cols=float(n_cols_est / n))
        return finish(fig, ax, canvas, [dict(kind="line", label="Series 1", x=x, y=y, lw=lw_px * 72 / dpi, ls="-")], [art], seed, probe)
    finally:
        ctx.__exit__(None, None, None)


FAMILIES = {"peaks": peaks, "scale": scale, "ticks": ticks, "width": width, "log": log, "grid": grid, "frame": frame,
            "spikes": spikes}


def generate(family: str, seed: int) -> Rendered:
    return FAMILIES[family](seed)


def _work(args):
    out, family, seed = args
    import json
    import logging

    import cv2

    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    stem = os.path.join(out, f"{seed:07d}")
    if os.path.exists(stem + ".json"):
        return seed, True
    try:
        r = generate(family, seed)
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
    ap.add_argument("--family", required=True, choices=sorted(FAMILIES))
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, default=None, help="default: the family's own seed base")
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    if a.start is None:
        a.start = FAMILY_BASE[a.family]
    if a.start < SEED_BASE:
        sys.exit(f"seeds for team t3 start at {SEED_BASE}")
    os.makedirs(a.out, exist_ok=True)
    jobs = [(a.out, a.family, s) for s in range(a.start, a.start + a.count)]
    t0 = time.time()
    failed = 0
    with Pool(min(a.workers, 3), maxtasksperchild=100) as pool:
        for seed, ok in pool.imap_unordered(_work, jobs, chunksize=4):
            if ok is not True:
                failed += 1
                print(f"seed {seed} failed: {ok}", file=sys.stderr)
    print(f"done {len(jobs)} in {time.time() - t0:.0f}s, failed={failed}")


if __name__ == "__main__":
    main()
