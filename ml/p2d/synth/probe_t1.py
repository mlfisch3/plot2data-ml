"""Probe charts for calibration from the tick labels (team t1-axis).

Each seed draws one matplotlib chart in one named style, and every style is
built to provoke one failure of the tick reader, the label grouping, the
multiplier handling or the axis fit, reliably, with the same exact ground truth
as `mpl_render` (plot area, ticks with value / position / text / bbox, series
in pixels, per-pixel class and instance maps). The style is chosen from the seed
so that a run of consecutive seeds covers every style evenly.

    python -m p2d.synth.probe_t1 --out data/t1-probe --start 11000000 --count 560 --workers 3
    python -m p2d.synth.probe_t1 --out data/t1-rot --start 11100000 --count 60 --style rot45

Styles:
  rot30, rot45, rot90   x labels rotated (the reader never saw a rotated crop).
  two_lin               an axis with exactly two labelled ticks, linear.
  two_log               an axis with exactly two labelled decades, log, labels plain or 10^k.
  crowded_y             9 to 12 long y labels in a small font at a low dpi.
  mult_sci              a scientific multiplier printed at the axis end ("1e6", "x10^6").
  offset                an additive offset printed at the axis end ("+1.2e3").
  pow10_edge            log axis with 10^k labels in a narrow font, the figure cropped so the
                        "1" is cut by the image edge (the microprocessor screenshot).
  dates                 month names, "Jan '21", "Q1 2020", "2020-03", "Mar 12".
  neg_small             negative decimals with unicode or ascii minus (-0.004 ... 0.002).
  units                 "$1.2M", "45%", "1.5k", "12,000", with and without a space.
  sci_e                 "2.5e+08", "1e-5" labels.
  nogrid_noticks        no tick marks, no gridlines, no spines (labels only).
  tiny                  a small low-resolution figure with 7 pt labels.
  right_axis            y labels on the right.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from multiprocessing import Pool

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.text import Text  # noqa: E402

from . import series as S  # noqa: E402
from .mpl_render import (AXIS, BG, DATA, GRID, LEGEND_SYMBOL, TEXT, TICK_LABEL, Rendered, StyledFormatter,  # noqa: E402
                         _clean_label, _leaves, _render_alpha, _to_px)

STYLES = ["rot30", "rot45", "rot90", "two_lin", "two_log", "crowded_y", "mult_sci", "offset", "pow10_edge", "dates",
          "neg_small", "units", "sci_e", "nogrid_noticks", "tiny", "right_axis"]

FONTS = ["DejaVu Sans", "Liberation Sans", "Liberation Serif", "Lato", "Ubuntu", "FreeSans", "Nimbus Sans",
         "TeX Gyre Heros", "Liberation Sans Narrow", "Noto Sans Mono", "DejaVu Serif", "C059", "P052"]
THIN_FONTS = ["Liberation Sans Narrow", "Lato Light", "Ubuntu Light", "DejaVu Sans Light", "Nimbus Sans Narrow",
              "TeX Gyre Heros Cn", "Ubuntu Condensed", "DejaVu Sans Condensed"]


def style_of(seed: int) -> str:
    return STYLES[seed % len(STYLES)]


def generate(seed: int, style: str | None = None) -> Rendered:
    rng = np.random.default_rng(seed)
    style = style or style_of(seed)
    fonts = THIN_FONTS if style == "pow10_edge" else FONTS
    rc = {
        "font.family": str(rng.choice(fonts)),
        "font.size": float(rng.uniform(7, 9)) if style in ("crowded_y", "tiny", "pow10_edge") else float(rng.uniform(8, 13)),
        "axes.unicode_minus": bool(rng.random() < 0.5),
        "path.simplify": False,
    }
    with plt.rc_context(rc):
        return _generate(rng, seed, style, rc)


def _data(rng: np.random.Generator, n_series: int, n: int, xlog: bool, ylog: bool, x: np.ndarray, ylo: float, yhi: float):
    """Series whose y span is [ylo, yhi] in data units (log10 units on a log axis)."""
    out = []
    t = (np.log10(x) - np.log10(x[0])) / (np.log10(x[-1]) - np.log10(x[0])) if xlog else (x - x[0]) / (x[-1] - x[0] + 1e-300)
    for k in range(n_series):
        _, cur = S.shape(rng, t, kind=str(rng.choice(["sines", "walk", "trend_noise", "poly", "logistic"])))
        cur = (cur - cur.min()) / (cur.max() - cur.min() + 1e-9)
        lo = ylo + (yhi - ylo) * rng.uniform(0.0, 0.3)
        hi = yhi - (yhi - ylo) * rng.uniform(0.0, 0.3)
        y = lo + (hi - lo) * cur
        if ylog:
            y = 10 ** y
        out.append((x, y))
    return out


def _generate(rng: np.random.Generator, seed: int, style: str, rc: dict) -> Rendered:
    # --- figure ---
    if style == "tiny":
        dpi = float(rng.choice([60, 72, 80]))
        wpx = rng.uniform(320, 460)
    elif style == "crowded_y":
        dpi = float(rng.choice([60, 72, 80, 96]))
        wpx = rng.uniform(420, 900)
    else:
        dpi = float(rng.choice([72, 96, 100, 120, 144]))
        wpx = rng.uniform(450, 1400)
    hpx = max(220, wpx * rng.uniform(0.45, 0.8))
    fig = plt.figure(figsize=(wpx / dpi, hpx / dpi), dpi=dpi)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)

    xlog = style == "two_log" and rng.random() < 0.4 or style == "pow10_edge" and rng.random() < 0.3
    ylog = style in ("pow10_edge",) or style == "two_log" and not xlog
    date_axis = None
    n = int(rng.integers(12, 110))
    n_series = int(rng.choice([1, 1, 2]))

    # --- x values ---
    if style == "dates":
        date_axis = _date_axis(rng, n)
        x = date_axis[0]
    elif xlog:
        lo = rng.uniform(-2, 3)
        x = 10 ** np.linspace(lo, lo + (rng.uniform(1.0, 1.6) if style == "two_log" else rng.uniform(2, 5)), n)
    else:
        _, x = S.x_values(rng, n, False)
        if style in ("rot30", "rot45", "rot90"):
            # Long labels: years with decimals, thousands, or small decimals.
            kind = str(rng.choice(["year", "thousands", "decimal"]))
            if kind == "year":
                x = np.linspace(rng.integers(1950, 2010), rng.integers(2015, 2030), n)
            elif kind == "thousands":
                x = np.linspace(0, 10 ** rng.uniform(3.5, 6), n)
            else:
                x = np.linspace(0, 10 ** rng.uniform(-3, 0), n)

    # --- y range ---
    if ylog:
        # Limits chosen so that exactly two (two_log) or 3 to 6 (pow10_edge) labelled decades lie inside.
        k = int(rng.integers(-3, 5))
        ndec = 2 if style == "two_log" else int(rng.integers(3, 7))
        ylo = k - rng.uniform(0.05, 0.6)
        yhi = k + ndec - 1 + rng.uniform(0.05, 0.6)
    elif style == "mult_sci":
        m = 10.0 ** float(rng.choice([-6, -5, -4, 4, 5, 6, 7, 8, 9]))
        ylo, yhi = m * rng.uniform(0, 3), m * rng.uniform(4, 9)
    elif style == "offset":
        # Matplotlib prints an offset only when every tick shares at least four leading digits.
        k = int(rng.integers(-1, 5))
        base = int(rng.integers(1000, 9999)) * 10.0 ** k
        span = 10.0 ** k * rng.uniform(0.3, 0.9)
        ylo, yhi = base + 0.03 * span, base + span
    elif style == "neg_small":
        m = 10.0 ** rng.uniform(-4, -1)
        ylo, yhi = -m * rng.uniform(1, 8), m * rng.uniform(0.5, 4)
    elif style == "units":
        unit = str(rng.choice(["M", "k", "pct", "dollar", "thousands", "space"]))
        top = {"M": 10.0 ** rng.uniform(6.3, 8.5), "k": 10.0 ** rng.uniform(4.3, 5.8), "pct": rng.uniform(30, 100),
               "dollar": 10.0 ** rng.uniform(1, 6), "thousands": 10.0 ** rng.uniform(3.3, 7), "space": 10.0 ** rng.uniform(3.3, 6)}[unit]
        ylo, yhi = (0.0 if rng.random() < 0.5 else top * rng.uniform(0.1, 0.5)), top
    elif style == "sci_e":
        m = 10.0 ** float(rng.choice([-7, -5, 5, 7, 8]))
        ylo, yhi = m * rng.uniform(0, 2), m * rng.uniform(3, 9)
    elif style == "two_lin":
        ylo, yhi = (0.0, 10.0 ** rng.uniform(0, 4) * rng.uniform(1, 9)) if rng.random() < 0.5 else (rng.uniform(-50, 50), rng.uniform(60, 400))
    elif style == "crowded_y":
        n_lab = int(rng.integers(9, 13))
        step = float(rng.choice([1, 2, 2.5, 5])) * 10.0 ** int(rng.integers(-3, 5))
        first = step * int(rng.integers(-5, 40))
        ylo, yhi = first - 0.3 * step, first + (n_lab - 1) * step + 0.3 * step
    else:
        c, s = S.y_scale(rng, False)
        ylo, yhi = c - s / 2, c + s / 2
    series = _data(rng, n_series, n, xlog, ylog, x, ylo, yhi)

    data_artists, series_meta = [], []
    pal = [f"C{k}" for k in range(10)]
    for k, (sx, sy) in enumerate(series):
        lw = float(rng.uniform(1, 2.5))
        kind = "line+markers" if rng.random() < 0.15 and n <= 60 else "line"
        mk = dict(marker=str(rng.choice(["o", "s", "D", "^"])), markersize=float(rng.uniform(3, 7))) if kind == "line+markers" else {}
        (art,) = ax.plot(sx, sy, lw=lw, color=pal[k], label=f"Series {k + 1}", zorder=2 + k * 0.01, **mk)
        art.set_snap(False)
        data_artists.append(art)
        series_meta.append(dict(kind=kind, label=f"Series {k + 1}", x=sx, y=sy, lw=lw, ls="-", where=None,
                                marker=mk.get("marker"), ms=mk.get("markersize", 0.0)))

    # --- axes ---
    if xlog:
        ax.set_xscale("log")
        if style == "two_log":
            k = int(np.floor(np.log10(x[0]) + 0.5))
            ax.set_xlim(10.0 ** (k - rng.uniform(0.05, 0.6)), 10.0 ** (k + 1 + rng.uniform(0.05, 0.6)))
    if ylog:
        ax.set_yscale("log")
        ax.set_ylim(10.0 ** ylo, 10.0 ** yhi)
    if style in ("offset", "crowded_y"):
        ax.set_ylim(ylo, yhi)
    minus = "−" if rc["axes.unicode_minus"] else "-"
    offset_expected = False
    tested = "x" if style in ("rot30", "rot45", "rot90", "dates") or xlog else "y"  # the axis the probe is about
    if style in ("rot30", "rot45", "rot90"):
        ax.tick_params(axis="x", labelrotation=float(style[3:]))
        ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(6, 12)), steps=[1, 2, 2.5, 5, 10]))
        f = str(rng.choice(["thousands", "plain", "default"]))
        if f != "default":
            ax.xaxis.set_major_formatter(StyledFormatter(f, minus=minus))
        else:
            ax.xaxis.get_major_formatter().set_scientific(False)
            ax.xaxis.get_major_formatter().set_useOffset(False)
    elif style == "two_lin":
        which = ax.yaxis if rng.random() < 0.6 else ax.xaxis
        tested = "y" if which is ax.yaxis else "x"
        lo, hi = ax.get_ylim() if which is ax.yaxis else ax.get_xlim()  # the autoscaled view, margins included
        for nb in (2, 3, 4):
            v = mticker.MaxNLocator(nbins=nb, steps=[1, 2, 2.5, 5, 10]).tick_values(lo, hi)
            v = v[(v >= lo) & (v <= hi)]
            if len(v) >= 2:
                break
        if len(v) > 2:
            v = v[[0, -1]] if rng.random() < 0.5 else v[:2]
        which.set_major_locator(mticker.FixedLocator(list(v)))
        if rng.random() < 0.3:
            which.set_major_formatter(StyledFormatter("thousands", minus=minus))
    elif style == "two_log":
        which = ax.yaxis if ylog else ax.xaxis
        lo, hi = np.log10(which.get_view_interval())
        decades = 10.0 ** np.arange(math.ceil(lo - 1e-9), math.floor(hi + 1e-9) + 1)
        if len(decades) > 2:
            decades = decades[:2]
        which.set_major_locator(mticker.FixedLocator(list(decades)))
        c = str(rng.choice(["mathtext", "plain", "plain", "e"]))
        if c == "plain":
            which.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:,.10g}" if v >= 1 else f"{v:g}"))
        elif c == "e":
            which.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:.0e}".replace("e+0", "e").replace("e-0", "e-")))
        which.set_minor_formatter(mticker.NullFormatter())
        if rng.random() < 0.5:
            which.set_minor_locator(mticker.NullLocator())
    elif style == "crowded_y":
        ax.yaxis.set_major_locator(mticker.FixedLocator(list(first + step * np.arange(n_lab))))
        f = str(rng.choice(["thousands", "plain", "dollar", "pct" if yhi <= 100 else "plain"]))
        extra = 1 if rng.random() < 0.3 else 0
        ax.yaxis.set_major_formatter(StyledFormatter(f, minus=minus, extra=extra))
    elif style == "mult_sci":
        fmt = mticker.ScalarFormatter(useMathText=bool(rng.random() < 0.4))
        fmt.set_scientific(True)
        fmt.set_powerlimits((-3, 3))
        fmt.set_useOffset(False)
        ax.yaxis.set_major_formatter(fmt)
        offset_expected = True
    elif style == "offset":
        fmt = mticker.ScalarFormatter(useMathText=bool(rng.random() < 0.3))
        fmt.set_useOffset(True)
        ax.yaxis.set_major_formatter(fmt)
        offset_expected = True
    elif style == "pow10_edge":
        ax.yaxis.set_minor_formatter(mticker.NullFormatter())
        if rng.random() < 0.5:
            ax.yaxis.set_minor_locator(mticker.NullLocator())
    elif style == "dates":
        ax.xaxis.set_major_locator(date_axis[1])
        ax.xaxis.set_major_formatter(date_axis[2])
        if rng.random() < 0.3:
            ax.tick_params(axis="x", labelrotation=float(rng.choice([30, 45])))
    elif style == "neg_small":
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(4, 9)), steps=[1, 2, 2.5, 5, 10]))
        ax.yaxis.set_major_formatter(StyledFormatter("plain", minus=minus))
    elif style == "units":
        if unit in ("M", "k"):
            div, suf = (1e6, "M") if unit == "M" else (1e3, str(rng.choice(["k", "K"])))
            ax.yaxis.set_major_formatter(StyledFormatter("plain", div, (" " if rng.random() < 0.3 else "") + suf, minus))
        elif unit == "space":
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:,.0f}".replace(",", " ")))
        else:
            ax.yaxis.set_major_formatter(StyledFormatter(unit, minus=minus))
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(4, 9)), steps=[1, 2, 2.5, 5, 10]))
    elif style == "sci_e":
        ax.yaxis.set_major_formatter(StyledFormatter("sci", minus=minus))
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(4, 8)), steps=[1, 2, 2.5, 5, 10]))
    elif style == "nogrid_noticks":
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.grid(False)
    elif style == "tiny":
        ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(4, 8)), steps=[1, 2, 2.5, 5, 10]))
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(4, 8)), steps=[1, 2, 2.5, 5, 10]))
    elif style == "right_axis":
        ax.yaxis.tick_right()
        ax.yaxis.set_major_formatter(StyledFormatter(str(rng.choice(["plain", "thousands"])), minus=minus))

    # Plain formatting of the axis not under test, so the probe isolates one thing.
    for name, axis, is_log in (("x", ax.xaxis, xlog), ("y", ax.yaxis, ylog)):
        if name == tested or is_log or style in ("nogrid_noticks", "tiny"):
            continue
        f = axis.get_major_formatter()
        if isinstance(f, mticker.ScalarFormatter):
            f.set_scientific(False)
            f.set_useOffset(False)
    if style not in ("nogrid_noticks",):
        if rng.random() < 0.5:
            ax.spines["top"].set_visible(False)
            ax.spines["right" if style != "right_axis" else "left"].set_visible(False)
        ax.tick_params(direction=str(rng.choice(["out", "in"], p=[0.8, 0.2])),
                       length=float(rng.choice([0, 2, 3.5, 5], p=[0.15, 0.25, 0.4, 0.2])), width=float(rng.uniform(0.5, 1.2)))
        if rng.random() < 0.4:
            ax.grid(True, alpha=float(rng.uniform(0.3, 0.8)), lw=float(rng.uniform(0.4, 1.0)))
    if rng.random() < 0.5:
        ax.set_title(str(rng.choice(["Results", "Population growth", "Performance over time", "Figure 2"])))
    if rng.random() < 0.5:
        ax.set_xlabel(str(rng.choice(["Year", "Time (s)", "x", "Date"])))
    if rng.random() < 0.5:
        ax.set_ylabel(str(rng.choice(["Value", "Sales ($M)", "Count", "y"])))
    legend = None
    if n_series > 1 and rng.random() < 0.6:
        legend = ax.legend(loc=str(rng.choice(["upper left", "upper right", "lower right"])), frameon=bool(rng.random() < 0.6))

    pad = 0.05 if style == "pow10_edge" else float(rng.uniform(0.2, 1.2))
    try:
        fig.tight_layout(pad=pad)
    except Exception:
        pass
    canvas.draw()
    ax.set_xlim(ax.get_xlim())
    ax.set_ylim(ax.get_ylim())
    fig.set_layout_engine("none")
    canvas.draw()
    rgba = np.asarray(canvas.buffer_rgba()).copy()
    H, W = rgba.shape[:2]
    image = rgba[..., :3].copy()

    # --- label maps ---
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
    legend_symbol_ids: set[int] = set()
    legend_text_ids: set[int] = set()
    if legend is not None:
        legend_text_ids = {id(t) for t in legend.get_texts()}
        for a in legend.findobj():
            if a is legend.get_frame() or id(a) in legend_text_ids or a is legend:
                continue
            if isinstance(a, Line2D):
                legend_symbol_ids.add(id(a))
    text_ids = {id(a) for a in leaves if isinstance(a, Text) and a.get_text() and id(a) not in tick_label_ids}
    alphas = {}
    for cls, ids in ((GRID, grid_ids), (AXIS, axis_ids), (LEGEND_SYMBOL, legend_symbol_ids), (TICK_LABEL, tick_label_ids), (TEXT, text_ids)):
        alphas[cls] = _render_alpha(fig, canvas, leaves, ids) if ids else np.zeros((H, W), np.uint8)
    series_alpha = [_render_alpha(fig, canvas, leaves, {id(a)}) for a in data_artists]
    thr = 60
    stack = [alphas[GRID], alphas[AXIS]] + series_alpha + [alphas[LEGEND_SYMBOL], alphas[TICK_LABEL], alphas[TEXT]]
    cls_of = [GRID, AXIS] + [DATA] * len(series_alpha) + [LEGEND_SYMBOL, TICK_LABEL, TEXT]
    st = np.stack(stack, 0).astype(np.int16) + np.arange(len(stack), dtype=np.int16)[:, None, None]
    idx = st.argmax(0)
    peak = st.max(0) - idx
    sem = np.where(peak >= thr, np.array(cls_of, np.uint8)[idx], BG).astype(np.uint8)
    sa = np.stack(series_alpha, 0).astype(np.int16) + np.arange(len(series_alpha), dtype=np.int16)[:, None, None]
    inst = np.where(sem == DATA, sa.argmax(0) + 1, 0).astype(np.uint8)

    # --- geometry ---
    renderer = canvas.get_renderer()
    bb = ax.get_window_extent(renderer=renderer)
    plot_area = [bb.x0 - 0.5, H - bb.y1 - 0.5, bb.x1 - 0.5, H - bb.y0 - 0.5]
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

    xticks, yticks = ticks_for("x"), ticks_for("y")
    out_series = []
    for m, art in zip(series_meta, data_artists):
        path = _to_px(ax, H, m["x"], m["y"])
        markers = _to_px(ax, H, m["x"], m["y"]) if m["kind"] == "line+markers" else np.zeros((0, 2))
        out_series.append(dict(kind=m["kind"], label=m["label"], color=matplotlib.colors.to_hex(art.get_color()),
                               linestyle=m["ls"], linewidth_px=m["lw"] * fig.dpi / 72.0, marker=m["marker"],
                               markersize_px=m["ms"] * fig.dpi / 72.0, x=m["x"].tolist(), y=m["y"].tolist(),
                               path_px=path.round(3).tolist(), markers_px=markers.round(3).tolist()))
    leg_bbox = None
    if legend is not None:
        e = legend.get_window_extent(renderer)
        leg_bbox = [e.x0 - 0.5, H - e.y1 - 0.5, e.x1 - 0.5, H - e.y0 - 0.5]
    offset_bbox = []
    for o in offset_texts:
        if o.get_text():
            e = o.get_window_extent(renderer)
            offset_bbox.append([e.x0 - 0.5, H - e.y1 - 0.5, e.x1 - 0.5, H - e.y0 - 0.5])
        else:
            offset_bbox.append(None)
    meta = dict(
        seed=seed, generator="matplotlib", style="probe", preset="t1-" + style, probe=style, font=rc["font.family"],
        width=W, height=H, plot_area=plot_area, xscale="log" if xlog else "linear",
        xdate=date_axis[3] if date_axis else None, yscale="log" if ylog else "linear", probe_axis=tested,
        xlim=list(map(float, xlim)), ylim=list(map(float, ylim)), xticks=xticks, yticks=yticks, series=out_series,
        legend_bbox=leg_bbox, offset_text=[_clean_label(o.get_text()) for o in offset_texts], offset_bbox=offset_bbox,
        offset_expected=offset_expected,
    )
    plt.close(fig)
    r = Rendered(image=image, sem=sem, inst=inst, meta=meta)
    if style == "pow10_edge":
        r = _crop_left(r, rng)
    return r


def _crop_left(r: Rendered, rng: np.random.Generator) -> Rendered:
    """Cut the image at the left so the "1" of the leftmost y label is partly lost, as a tight screenshot does."""
    yt = r.meta["yticks"]
    if not yt:
        return r
    left = min(t["bbox"][0] for t in yt)
    # The "1" of "10^k" is the first glyph: cut between a third and all of its width (about 0.5 em).
    em = float(np.median([t["bbox"][3] - t["bbox"][1] for t in yt]))
    cut = int(round(left + rng.uniform(0.15, 0.5) * em))
    if cut <= 0:
        return r

    def shift_box(b):
        return None if b is None else [b[0] - cut, b[1], b[2] - cut, b[3]]

    m = r.meta
    m["plot_area"] = shift_box(m["plot_area"])
    m["legend_bbox"] = shift_box(m.get("legend_bbox"))
    m["offset_bbox"] = [shift_box(b) for b in m.get("offset_bbox", [])]
    for key in ("xticks", "yticks"):
        for t in m[key]:
            t["bbox"] = shift_box(t["bbox"])
            t["anchor"] = [t["anchor"][0] - cut, t["anchor"][1]]
            if key == "xticks":
                t["pos"] -= cut
    for s in m["series"]:
        s["path_px"] = [[p[0] - cut, p[1]] for p in s["path_px"]]
        s["markers_px"] = [[p[0] - cut, p[1]] for p in s["markers_px"]]
    m["width"] = r.image.shape[1] - cut
    m["cropped_left_px"] = cut
    return Rendered(image=np.ascontiguousarray(r.image[:, cut:]), sem=np.ascontiguousarray(r.sem[:, cut:]),
                    inst=np.ascontiguousarray(r.inst[:, cut:]), meta=m)


def _date_axis(rng: np.random.Generator, n: int):
    """Like dates.date_axis, plus quarters and bare month names, all formats equally likely."""
    from ..dates import days

    start = days(int(rng.integers(1995, 2024)), int(rng.integers(1, 13)), int(rng.integers(1, 28)))
    fmt = str(rng.choice(["%b", "%b '%y", "%b %Y", "%Y-%m", "%b %d", "%d %b", "%m/%Y", "Q", "%Y-%m-%d"]))
    if fmt in ("%b %d", "%d %b", "%Y-%m-%d"):
        span = rng.uniform(25, 110)
        loc = mdates.DayLocator(interval=int(max(1, round(span / rng.integers(4, 8)))))
    elif fmt == "Q":
        span = rng.uniform(500, 1500)
        loc = mdates.MonthLocator(bymonth=[1, 4, 7, 10])
    elif fmt in ("%b", "%b '%y", "%b %Y", "%Y-%m", "%m/%Y"):
        span = rng.uniform(150, 900)
        loc = mdates.MonthLocator(interval=int(max(1, round(span / 30 / rng.integers(4, 8)))))
    else:
        span = rng.uniform(1100, 9000)
        loc = mdates.YearLocator(base=int(max(1, round(span / 365 / rng.integers(4, 8)))))
    x = start + np.linspace(0, span, n)
    if fmt == "Q":
        f = mticker.FuncFormatter(lambda v, _p: (lambda d: f"Q{(d.month - 1) // 3 + 1} {d.year}")(mdates.num2date(v)))
    else:
        f = mdates.DateFormatter(fmt)
    return x, loc, f, fmt


def _work(args):
    out, seed, style = args
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import cv2

    stem = os.path.join(out, f"{seed:07d}")
    if os.path.exists(stem + ".json"):
        return seed, True
    try:
        r = generate(seed, style)
    except Exception as e:  # noqa: BLE001
        return seed, repr(e)
    cv2.imwrite(stem + ".png", r.image[..., ::-1])
    cv2.imwrite(stem + ".sem.png", r.sem)
    cv2.imwrite(stem + ".inst.png", r.inst)
    with open(stem + ".json.tmp", "w") as f:
        json.dump(r.meta, f)
    os.replace(stem + ".json.tmp", stem + ".json")
    return seed, True


def main() -> None:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, default=11000000)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--style", default=None, choices=STYLES, help="one style for every seed (default: by seed)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    jobs = [(a.out, s, a.style) for s in range(a.start, a.start + a.count)]
    t0 = time.time()
    failed = 0
    with Pool(a.workers, maxtasksperchild=100) as pool:
        for i, (seed, ok) in enumerate(pool.imap_unordered(_work, jobs, chunksize=4)):
            if ok is not True:
                failed += 1
                print(f"seed {seed} failed: {ok}", file=sys.stderr)
            if (i + 1) % 100 == 0:
                print(f"{i + 1}/{len(jobs)}  {time.time() - t0:.0f}s  failed={failed}", flush=True)
    print(f"done {len(jobs)} in {time.time() - t0:.0f}s, failed={failed}")


if __name__ == "__main__":
    main()
