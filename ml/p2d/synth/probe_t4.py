"""Probe charts for the marker work (team t4): controlled scatter and marker charts with exact ground truth.

    python -m p2d.synth.probe_t4 --out data/t4-dense --kind dense --start 14000000 --count 150 --workers 3

Each kind provokes one failure on purpose, with the provoking quantity drawn from a short list of levels
and recorded in `meta["probe"]`, so results can be sliced by it:

    dense    scatter clouds at a set spacing between markers (median nearest-neighbour distance over
             marker diameter): overlapping and touching markers, several series in one cloud
    row      markers in a row along a curve at a set spacing, with or without the line drawn
    shapes   every marker shape at one size per chart (2 to 20 px), well separated, filled or hollow
    hollow   hollow, haloed (paper-coloured edge), translucent and small markers, on gridlines and lines
    labels   value labels printed next to every marker, end labels, annotations, an in-plot legend
    multi    several series sharing one cloud: close colours, or one colour and different shapes
    lines    dense, noisy, dashed and thick lines without any marker: nothing here is a marker
    mix      one of the above at random (for training data)

Same output as `mpl_render.generate`: a `Rendered` with image, class map, instance map and meta; written
in the dataset format of `build.py`. Pixel convention: the centre of pixel column i is x = i.
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
import cv2  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.collections import Collection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.text import Text  # noqa: E402

from . import presets as P  # noqa: E402
from . import series as S  # noqa: E402
from .mpl_render import (AXIS, BG, DATA, FONTS, GRID, LEGEND_SYMBOL, MARKERS, TEXT, TICK_LABEL, Rendered,  # noqa: E402
                         _clean_label, _leaves, _render_alpha, _to_px, _pick)

KINDS = ["dense", "row", "shapes", "hollow", "labels", "multi", "lines"]
# Shapes that are symmetric under a half turn: the centre is the centroid of the ink.
SYMMETRIC = {"o", "s", "D", "d", "h", "H", "8", "x", "+", "P", "X", ".", "*"}
NAMES = ["Revenue", "Women", "Men", "Control", "Model A", "Model B", "Baseline", "Measured", "Predicted", "Total",
         "Sales", "Temperature", "GDP", "Price", "Signal", "Noise", "Fit", "Theory", "Experiment", "North", "South"]


def _levels(rng, levels):
    return levels[int(rng.integers(len(levels)))]


def generate(seed: int, kind: str | None = None) -> Rendered:
    rng = np.random.default_rng(seed)
    if kind is None or kind == "mix":
        kind = KINDS[int(rng.integers(len(KINDS)))]
    preset = P.choose(rng) if rng.random() < 0.4 else "none"
    style = "default"
    if preset == "none" and rng.random() < 0.3:
        style = str(rng.choice(["seaborn-v0_8-whitegrid", "ggplot", "bmh", "seaborn-v0_8-darkgrid", "fivethirtyeight",
                                "dark_background", "classic", "seaborn-v0_8-white"]))
    rc = {"font.family": str(rng.choice(FONTS)), "font.size": float(rng.uniform(7, 14)),
          "axes.unicode_minus": bool(rng.random() < 0.5), "path.simplify": False}
    rc.update(P.rc(preset, rng))
    with plt.style.context(style), plt.rc_context(rc):
        return _generate(rng, seed, kind, style, rc, preset)


def _generate(rng, seed, kind, style, rc, preset) -> Rendered:
    pal = P.palette(preset)
    dpi = float(rng.choice([72, 96, 100, 100, 120, 144]))
    wpx = rng.uniform(480, 1400)
    hpx = wpx * rng.uniform(0.45, 0.8)
    fig = plt.figure(figsize=(wpx / dpi, hpx / dpi), dpi=dpi)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    px_per_pt = dpi / 72.0
    # The plot area is about this much of the figure once laid out; used only to choose counts.
    area_px = 0.72 * wpx * hpx
    plot_w_px = 0.85 * wpx

    probe = {"kind": kind}
    series_meta, data_artists, text_extra, grid_extra = [], [], [], []
    colours = list(pal) if pal else [f"C{i}" for i in range(10)]
    rng.shuffle(colours)

    def xy_cloud(n):
        """A cloud in the unit square: a band around a curve, or a few gaussian blobs."""
        if rng.random() < 0.5:
            x = np.sort(rng.uniform(0, 1, n))
            y = 0.5 + 0.35 * S.shape(rng, x)[1] + rng.normal(0, rng.uniform(0.02, 0.12), n)
        else:
            k = int(rng.integers(1, 4))
            cx, cy = rng.uniform(0.15, 0.85, (2, k))
            sx, sy = rng.uniform(0.05, 0.25, (2, k))
            which = rng.integers(0, k, n)
            x = cx[which] + rng.normal(0, 1, n) * sx[which]
            y = cy[which] + rng.normal(0, 1, n) * sy[which]
        return np.clip(x, 0, 1), np.clip(y, 0, 1)

    def add_scatter(x, y, ms_pt, shape, colour, label, hollow=False, halo=False, alpha=None, lw=None, zorder=2.0):
        kw = dict(s=ms_pt ** 2, marker=shape, label=label, zorder=zorder)
        edge_only = shape in ("x", "+", "1", "2", "3", "4", "|", "_")
        if hollow and not edge_only:
            kw.update(facecolors="none", edgecolors=colour, linewidths=lw if lw else float(rng.uniform(0.6, 2.0)))
        elif halo and not edge_only:
            kw.update(color=colour, edgecolors=rc.get("axes.facecolor", "white") if rng.random() < 0.7 else "white",
                      linewidths=lw if lw else float(rng.uniform(0.8, 2.0)))
        else:
            kw.update(color=colour, linewidths=lw if (lw and edge_only) else None)
        if alpha is not None:
            kw["alpha"] = alpha
        art = ax.scatter(x, y, **kw)
        art.set_snap(False)
        data_artists.append(art)
        series_meta.append(dict(kind="scatter", label=label, x=x, y=y, lw=1.0, ls="-", where=None, marker=shape,
                                ms=ms_pt, hollow=hollow, halo=halo))
        return art

    def add_line_markers(x, y, ms_pt, shape, colour, label, lw, hollow=False, halo=False, ls="-", zorder=2.0,
                         draw_line=True):
        kw = dict(marker=shape, markersize=ms_pt, color=colour, label=label, zorder=zorder, lw=lw if draw_line else 0,
                  ls=ls)
        if hollow and shape not in ("x", "+", "."):
            kw["markerfacecolor"] = "none"
        if halo and shape not in ("x", "+", "."):
            kw["markeredgecolor"] = rc.get("axes.facecolor", "white")
            kw["markeredgewidth"] = float(rng.uniform(0.8, 2.0))
        (art,) = ax.plot(x, y, **kw)
        art.set_snap(False)
        data_artists.append(art)
        series_meta.append(dict(kind="line+markers" if draw_line else "scatter", label=label, x=x, y=y, lw=lw, ls=ls,
                                where=None, marker=shape, ms=ms_pt, hollow=hollow, halo=halo))
        return art

    xr = (0.0, float(rng.choice([1, 10, 100, 2020, 50])))
    yr = (float(rng.choice([0, 0, -20, 100])), None)
    yspan = float(rng.choice([1, 10, 60, 1000]))
    yr = (yr[0], yr[0] + yspan)

    def to_data(x01, y01):
        return xr[0] + x01 * (xr[1] - xr[0]), yr[0] + y01 * (yr[1] - yr[0])

    if kind == "dense":
        spacing = _levels(rng, [0.6, 0.8, 1.0, 1.3, 1.7, 2.5, 4.0])
        ms_pt = float(rng.uniform(3, 9))
        diam = ms_pt * px_per_pt
        n_series = int(rng.choice([1, 1, 2, 3, 4]))
        n_total = int(rng.integers(60, 400))
        # Uniform points in a region whose area gives the wanted mean nearest-neighbour distance
        # (0.5 / sqrt(density) for a Poisson field); the region is a window of the plot.
        frac = min(1.0, n_total * (2 * spacing * diam) ** 2 / area_px)
        side = math.sqrt(frac)
        ox, oy = rng.uniform(0, 1 - side, 2)
        shape = _levels(rng, ["o", "o", "o", "s", "D", "^", "v", "*", "x", "p", "h"])
        probe.update(spacing_rel=spacing, ms_px=diam, n_series=n_series, shape=shape, n=n_total)
        for k in range(n_series):
            n = max(5, n_total // n_series)
            x = ox + side * rng.uniform(0, 1, n)
            y = oy + side * rng.uniform(0, 1, n)
            sh = shape if rng.random() < 0.6 else _levels(rng, MARKERS)
            add_scatter(*to_data(x, y), ms_pt, sh, colours[k % len(colours)], NAMES[k], alpha=float(rng.uniform(0.5, 0.9)) if rng.random() < 0.2 else None,
                        zorder=2 + 0.01 * k)
        # The limits stay at the full range, or autoscaling would spread the window over the plot.
        mx, my = 0.02 * (xr[1] - xr[0]), 0.02 * (yr[1] - yr[0])
        ax.set_xlim(xr[0] - mx, xr[1] + mx)
        ax.set_ylim(yr[0] - my, yr[1] + my)
    elif kind == "row":
        spacing = _levels(rng, [0.7, 0.9, 1.1, 1.4, 2.0, 3.0, 5.0])
        ms_pt = float(rng.uniform(2.5, 8))
        diam = ms_pt * px_per_pt
        n_series = int(rng.choice([1, 1, 2, 3]))
        draw_line = rng.random() < 0.6
        n = int(np.clip(plot_w_px / (spacing * diam), 4, 900))
        shape = _levels(rng, ["o", "o", "s", "D", "^", "v", "*", "x", "+", ".", "d", "P"])
        probe.update(spacing_rel=spacing, ms_px=diam, n_series=n_series, draw_line=draw_line, shape=shape, n=n)
        for k in range(n_series):
            x = np.linspace(0, 1, n)
            y = 0.5 + 0.4 * S.shape(rng, x)[1] * rng.uniform(0.5, 1.0) + rng.uniform(-0.1, 0.1)
            sh = shape if rng.random() < 0.7 else _levels(rng, MARKERS)
            add_line_markers(*to_data(x, np.clip(y, 0, 1)), ms_pt, sh, colours[k % len(colours)], NAMES[k],
                             lw=float(rng.uniform(0.8, 3.0)), hollow=rng.random() < 0.15, draw_line=draw_line,
                             zorder=2 + 0.01 * k)
    elif kind == "shapes":
        ms_px = _levels(rng, [2, 3, 4, 5, 6, 8, 10, 14, 20])
        ms_pt = ms_px / px_per_pt
        hollow = rng.random() < 0.3
        n_series = int(rng.choice([1, 2, 3, 4]))
        shapes = list(rng.choice(MARKERS, n_series, replace=False))
        probe.update(ms_px=ms_px, hollow=hollow, shapes=[str(s) for s in shapes], n_series=n_series)
        spacing_px = max(4 * ms_px, 14)
        n_total = int(np.clip(area_px / spacing_px ** 2 / 2, 12, 200))
        # A jittered grid keeps every marker apart from every other.
        cols = max(2, int(math.sqrt(n_total * 1.5)))
        rows = max(2, n_total // cols)
        gx, gy = np.meshgrid(np.linspace(0.03, 0.97, cols), np.linspace(0.03, 0.97, rows))
        pts = np.column_stack([gx.ravel(), gy.ravel()])
        jit = 0.3 / max(cols, rows)
        pts += rng.uniform(-jit, jit, pts.shape)
        rng.shuffle(pts)
        per = len(pts) // n_series
        for k in range(n_series):
            p = pts[k * per:(k + 1) * per]
            add_scatter(*to_data(p[:, 0], p[:, 1]), ms_pt, str(shapes[k]), colours[k % len(colours)], NAMES[k],
                        hollow=hollow, zorder=2 + 0.01 * k)
    elif kind == "hollow":
        mode = _levels(rng, ["hollow", "halo", "alpha", "small", "ongrid", "online"])
        n_series = int(rng.choice([1, 2, 3]))
        ms_pt = float(rng.uniform(1.5, 3.0)) if mode == "small" else float(rng.uniform(3, 9))
        probe.update(mode=mode, ms_px=ms_pt * px_per_pt, n_series=n_series)
        if mode in ("ongrid", "online"):
            ax.grid(True, lw=float(rng.uniform(0.6, 1.5)), ls=str(rng.choice(["-", "--", ":"])), alpha=float(rng.uniform(0.4, 1)))
        for k in range(n_series):
            n = int(rng.integers(10, 60))
            shape = _levels(rng, ["o", "o", "s", "D", "^", "v", "h", "p", "*"])
            if mode == "ongrid":
                # y exactly on the grid levels the locator will choose: nice fractions of the span.
                levels = yr[0] + (yr[1] - yr[0]) * np.linspace(0, 1, 6)
                x = np.sort(rng.uniform(0, 1, n))
                y = levels[rng.integers(0, 6, n)]
                x, _ = to_data(x, x)
                add_scatter(x, y, ms_pt, shape, colours[k], NAMES[k], hollow=rng.random() < 0.5, zorder=2 + 0.01 * k)
            elif mode == "online":
                x = np.linspace(0, 1, n)
                y = np.clip(0.5 + 0.4 * S.shape(rng, x)[1], 0, 1)
                add_line_markers(*to_data(x, y), ms_pt, shape, colours[k], NAMES[k], lw=float(rng.uniform(2.0, 5.0)),
                                 hollow=rng.random() < 0.5, halo=rng.random() < 0.5, zorder=2 + 0.01 * k)
            else:
                x, y = xy_cloud(n)
                add_scatter(*to_data(x, y), ms_pt, shape, colours[k], NAMES[k], hollow=mode == "hollow", halo=mode == "halo",
                            alpha=float(rng.uniform(0.25, 0.7)) if mode == "alpha" else None, zorder=2 + 0.01 * k)
        if mode == "small":
            ax.set_ylim(yr[0] - 0.05 * yspan, yr[1] + 0.05 * yspan)
    elif kind == "labels":
        mode = _levels(rng, ["values", "values", "endlabels", "annotate", "legend_in", "numbers_far"])
        n_series = int(rng.choice([1, 2, 3]))
        ms_pt = float(rng.uniform(3, 8))
        probe.update(mode=mode, ms_px=ms_pt * px_per_pt, n_series=n_series)
        fs = float(rng.uniform(6, 11))
        value_colour = rng.random() < 0.5
        for k in range(n_series):
            n = int(rng.integers(5, 25)) if mode in ("values", "numbers_far") else int(rng.integers(8, 40))
            shape = _levels(rng, ["o", "o", "s", "D", "^", "v", "*", "x", "P"])
            x = np.sort(rng.uniform(0, 1, n)) if rng.random() < 0.5 else np.linspace(0, 1, n)
            y = np.clip(0.5 + 0.4 * S.shape(rng, x)[1] + rng.normal(0, 0.03, n), 0, 1)
            xd, yd = to_data(x, y)
            c = colours[k % len(colours)]
            with_line = rng.random() < 0.5
            if with_line:
                art = add_line_markers(xd, yd, ms_pt, shape, c, NAMES[k], lw=float(rng.uniform(1, 2.5)), zorder=2 + 0.01 * k)
            else:
                art = add_scatter(xd, yd, ms_pt, shape, c, NAMES[k], zorder=2 + 0.01 * k)
            col = art.get_color() if isinstance(art, Line2D) else art.get_facecolor()[0]
            tc = col if value_colour else rc.get("text.color", "black")
            if mode == "values":
                off = float(rng.choice([6, 8, 10]))
                side = str(rng.choice(["above", "below", "right"]))
                for xi, yi in zip(xd, yd):
                    dx, dy = {"above": (0, off), "below": (0, -off), "right": (off, 0)}[side]
                    text_extra.append(ax.annotate(f"{yi:.3g}" if rng.random() < 0.8 else f"{yi:.0f}", (xi, yi), xytext=(dx, dy),
                                                  textcoords="offset points", ha="center" if side != "right" else "left",
                                                  va="center", fontsize=fs, color=tc, annotation_clip=False))
            elif mode == "numbers_far":
                # Numbers printed in the plot, a little away from the points they describe.
                for xi, yi in zip(xd, yd):
                    if rng.random() < 0.7:
                        text_extra.append(ax.annotate(f"{yi:.3g}", (xi, yi), xytext=(rng.uniform(-25, 25), rng.uniform(-25, 25)),
                                                      textcoords="offset points", ha="center", va="center", fontsize=fs,
                                                      color=tc, fontweight="bold" if rng.random() < 0.4 else "normal"))
            elif mode == "endlabels":
                text_extra.append(ax.annotate(NAMES[k], (xd[-1], yd[-1]), xytext=(4, 0), textcoords="offset points",
                                              color=tc, va="center", fontsize=fs + 1, annotation_clip=False))
                for j, dx in ((0, -6), (-1, 6)):
                    text_extra.append(ax.annotate(f"{yd[j]:.3g}", (xd[j], yd[j]), xytext=(dx, -12), textcoords="offset points",
                                                  color=tc, ha="center", fontsize=fs + 1, fontweight="bold", annotation_clip=False))
            elif mode == "annotate":
                for _ in range(int(rng.integers(1, 4))):
                    i = int(rng.integers(0, n))
                    text_extra.append(ax.annotate(str(rng.choice(["peak", "min", f"{yd[i]:.3g}", "outlier", "2021"])), (xd[i], yd[i]),
                                                  xytext=(rng.uniform(-40, 40), rng.uniform(-40, 40)), textcoords="offset points",
                                                  fontsize=fs, arrowprops=dict(arrowstyle="->", lw=0.8) if rng.random() < 0.7 else None))
        if mode == "legend_in" or rng.random() < 0.3:
            pass  # the legend is added below, inside the plot
        probe["legend_in"] = mode == "legend_in"
    elif kind == "multi":
        mode = _levels(rng, ["close_colours", "same_colour_shapes", "sizes", "mixed"])
        n_series = int(rng.choice([2, 3, 4, 5]))
        ms_pt = float(rng.uniform(3, 8))
        probe.update(mode=mode, n_series=n_series, ms_px=ms_pt * px_per_pt)
        base = np.array(matplotlib.colors.to_rgb(colours[0]))
        shapes = list(rng.choice(["o", "s", "D", "^", "v", "*", "x", "P", "p", "h"], n_series, replace=False))
        xs, ys = xy_cloud(int(rng.integers(40, 160)) * n_series)
        for k in range(n_series):
            sel = slice(k, None, n_series)
            x, y = xs[sel], ys[sel]
            if mode == "close_colours":
                c = tuple(np.clip(base + rng.normal(0, 0.12, 3), 0, 1))
                sh = "o"
            elif mode == "same_colour_shapes":
                c = colours[0]
                sh = str(shapes[k])
            elif mode == "sizes":
                c = colours[k % len(colours)]
                sh = "o"
            else:
                c = colours[k % len(colours)]
                sh = str(shapes[k])
            size = ms_pt * (1 + 0.6 * k) if mode == "sizes" else ms_pt
            add_scatter(*to_data(x, y), size, sh, c, NAMES[k], zorder=2 + 0.01 * k)
    elif kind == "lines":
        mode = _levels(rng, ["noisy", "dashed", "spiky", "thick_dashed", "steps"])
        n_series = int(rng.choice([1, 2, 3, 4]))
        probe.update(mode=mode, n_series=n_series)
        for k in range(n_series):
            n = int(rng.integers(300, 2500)) if mode in ("noisy", "spiky") else int(rng.integers(20, 200))
            x = np.linspace(0, 1, n)
            if mode == "spiky":
                y = 0.5 + 0.3 * S.shape(rng, x, "spiky_walk")[1]
            elif mode == "noisy":
                y = 0.5 + 0.3 * S.shape(rng, x, str(rng.choice(["noise", "trend_noise", "walk", "flat_then_busy"])))[1]
            elif mode == "steps":
                y = 0.5 + 0.3 * S.shape(rng, x, "steps")[1]
            else:
                y = 0.5 + 0.35 * S.shape(rng, x)[1]
            y = np.clip(y, 0, 1)
            ls = str(rng.choice(["--", ":", "-."])) if mode in ("dashed", "thick_dashed") else "-"
            lw = float(rng.uniform(2.5, 6)) if mode == "thick_dashed" else float(rng.uniform(0.6, 2.5))
            xd, yd = to_data(x, y)
            (art,) = ax.plot(xd, yd, lw=lw, ls=ls, color=colours[k % len(colours)], label=NAMES[k], zorder=2 + 0.01 * k)
            art.set_snap(False)
            data_artists.append(art)
            series_meta.append(dict(kind="line", label=NAMES[k], x=xd, y=yd, lw=lw, ls=ls, where=None, marker=None, ms=0.0))
    else:
        raise ValueError(kind)

    # --- furniture ---
    if rng.random() < 0.6:
        ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(3, 10)), steps=[1, 2, 2.5, 5, 10]))
    if rng.random() < 0.6:
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(3, 10)), steps=[1, 2, 2.5, 5, 10]))
    for axis in (ax.xaxis, ax.yaxis):
        if isinstance(axis.get_major_formatter(), mticker.ScalarFormatter):
            axis.get_major_formatter().set_useOffset(False)
            axis.get_major_formatter().set_scientific(False)
    if rng.random() < 0.5:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    ax.tick_params(direction=str(rng.choice(["out", "in"])), length=float(rng.choice([0, 3.5, 5])))
    flags = P.post(preset, ax, rng) if preset != "none" else {"legend": "auto", "direct_labels": False}
    if preset == "none" and kind != "hollow":
        g = rng.random()
        if g < 0.4:
            ax.grid(True, alpha=float(rng.uniform(0.3, 1)), ls=str(rng.choice(["-", "--", ":"])), lw=float(rng.uniform(0.4, 1.2)))
        elif g < 0.5:
            ax.grid(False)
    if rng.random() < 0.5:
        ax.set_title(str(rng.choice(["Results", "Scatter of measurements", "Figure 2", "Performance", "Sales by region"])))
    if rng.random() < 0.5:
        ax.set_xlabel(str(rng.choice(["x", "Year", "Time (s)", "Dose (mg)"])))
    if rng.random() < 0.5:
        ax.set_ylabel(str(rng.choice(["y", "Value", "Count", "Percent"])))
    legend = None
    n_series = len(series_meta)
    want_legend = probe.get("legend_in") or (n_series > 1 and rng.random() < 0.6) or (n_series == 1 and rng.random() < 0.15)
    if want_legend and flags["legend"] != "none":
        kw = dict(frameon=bool(rng.random() < 0.7), fontsize=float(rng.uniform(6, 12)))
        if probe.get("legend_in") or flags["legend"] == "auto":
            loc = str(rng.choice(["upper left", "upper right", "lower left", "lower right", "center left", "upper center", "best"]))
            legend = ax.legend(loc=loc, ncol=int(rng.choice([1, 1, 2])) if n_series > 2 else 1, **kw)
        elif flags["legend"] == "below":
            legend = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=min(n_series, 4), frameon=False, fontsize=kw["fontsize"])
        else:
            legend = ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=kw["fontsize"])
    return finish(fig, canvas, ax, series_meta, data_artists, grid_extra, legend, seed, style, rc, preset, probe)


def finish(fig, canvas, ax, series_meta, data_artists, grid_extra, legend, seed, style, rc, preset, probe) -> Rendered:
    """Freeze the layout, render, make the label maps and record the geometry (as `mpl_render` does)."""
    try:
        fig.tight_layout(pad=float(np.random.default_rng(seed).uniform(0.2, 1.5)))
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
    grid_ids |= {id(a) for a in grid_extra}
    legend_symbol_ids: set[int] = set()
    legend_text_ids: set[int] = set()
    if legend is not None:
        legend_text_ids = {id(t) for t in legend.get_texts()}
        if legend.get_title().get_text():
            legend_text_ids.add(id(legend.get_title()))
        for a in legend.findobj():
            if a is legend.get_frame() or id(a) in legend_text_ids or a is legend:
                continue
            if isinstance(a, (Line2D, Collection, Patch)):
                legend_symbol_ids.add(id(a))
    text_ids = {id(a) for a in leaves if isinstance(a, Text) and a.get_text() and id(a) not in tick_label_ids}
    # Annotation arrows are text furniture too.
    for a in leaves:
        if isinstance(a, Patch) and type(a).__name__ == "FancyArrowPatch":
            text_ids.add(id(a))

    alphas = {}
    groups = [(GRID, grid_ids), (AXIS, axis_ids), (LEGEND_SYMBOL, legend_symbol_ids), (TICK_LABEL, tick_label_ids), (TEXT, text_ids)]
    for cls, ids in groups:
        alphas[cls] = _render_alpha(fig, canvas, leaves, ids) if ids else np.zeros((H, W), np.uint8)
    series_alpha = [_render_alpha(fig, canvas, leaves, {id(a)}) for a in data_artists]

    thr = 60
    stack = [alphas[GRID], alphas[AXIS]] + series_alpha + [alphas[LEGEND_SYMBOL], alphas[TICK_LABEL], alphas[TEXT]]
    cls_of = [GRID, AXIS] + [DATA] * len(series_alpha) + [LEGEND_SYMBOL, TICK_LABEL, TEXT]
    st = np.stack(stack, 0).astype(np.int16)
    st = st + np.arange(len(stack), dtype=np.int16)[:, None, None]
    idx = st.argmax(0)
    peak = st.max(0) - idx
    sem = np.where(peak >= thr, np.array(cls_of, np.uint8)[idx], BG).astype(np.uint8)
    inst = np.zeros((H, W), np.uint8)
    if series_alpha:
        sa = np.stack(series_alpha, 0).astype(np.int16) + np.arange(len(series_alpha), dtype=np.int16)[:, None, None]
        si = sa.argmax(0)
        inst = np.where(sem == DATA, si + 1, 0).astype(np.uint8)

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
                p = _to_px(ax, H, [v], [ylim[0]])[0]
                pos = float(p[0])
                anchor = [pos, plot_area[3] if side == "low" else plot_area[1]]
            else:
                p = _to_px(ax, H, [xlim[0]], [v])[0]
                pos = float(p[1])
                anchor = [plot_area[0] if side == "low" else plot_area[2], pos]
            out.append(dict(value=float(v), pos=pos, anchor=anchor, side=side, text=_clean_label(label.get_text()),
                            raw=label.get_text(), bbox=[e.x0 - 0.5, H - e.y1 - 0.5, e.x1 - 0.5, H - e.y0 - 0.5]))
        return out

    out_series = []
    all_mk = []
    for m, art in zip(series_meta, data_artists):
        x, y = m["x"], m["y"]
        path = _to_px(ax, H, x, y) if m["kind"] != "scatter" else np.zeros((0, 2))
        markers_data = _to_px(ax, H, x, y) if m["kind"] in ("scatter", "line+markers") else np.zeros((0, 2))
        # Agg stamps every marker at an integer pixel position (whatever `set_snap` says), so the centre
        # actually drawn is the display coordinate rounded: floor(exact + 1) in this pixel convention.
        # Verified to 0.05 px on isolated markers of every symmetric shape. `markers_px` is what is drawn
        # (the heat target and the measurable truth); `markers_data_px` is where the value maps exactly.
        markers = np.floor(markers_data + 1.0) if len(markers_data) else markers_data
        if len(markers):
            all_mk.append(markers)
        color = art.get_color() if isinstance(art, Line2D) else art.get_facecolor()
        if not isinstance(color, str):
            c = np.asarray(color, float).reshape(-1)
            if c.size >= 3 and not (c.size >= 4 and c[3] == 0):
                color = matplotlib.colors.to_hex(c[:4] if c.size >= 4 else c[:3])
            else:
                ec = np.asarray(art.get_edgecolor(), float).reshape(-1)
                color = matplotlib.colors.to_hex(ec[:4]) if ec.size >= 3 else "#000000"
        else:
            color = matplotlib.colors.to_hex(color)
        out_series.append(dict(kind=m["kind"], label=m["label"], color=color, linestyle=m["ls"],
                               linewidth_px=m["lw"] * fig.dpi / 72.0, marker=m["marker"], markersize_px=m["ms"] * fig.dpi / 72.0,
                               hollow=bool(m.get("hollow")), halo=bool(m.get("halo")),
                               x=np.asarray(x).tolist(), y=np.asarray(y).tolist(), path_px=path.round(3).tolist(),
                               markers_px=markers.round(3).tolist(), markers_data_px=markers_data.round(3).tolist()))
    # The exact nearest-neighbour spacing of the markers drawn, in pixels and in marker diameters.
    if all_mk:
        mk = np.vstack(all_mk)
        inside = (mk[:, 0] >= plot_area[0]) & (mk[:, 0] <= plot_area[2]) & (mk[:, 1] >= plot_area[1]) & (mk[:, 1] <= plot_area[3])
        mk = mk[inside]
        if len(mk) > 1:
            from scipy.spatial import cKDTree

            d, _ = cKDTree(mk).query(mk, k=2)
            probe["nn_px_median"] = float(np.median(d[:, 1]))
            diam = float(np.median([s["markersize_px"] for s in out_series if s["markers_px"]]))
            probe["nn_rel_median"] = float(np.median(d[:, 1]) / max(diam, 1e-6))
            probe["n_markers"] = int(len(mk))

    leg_bbox = None
    if legend is not None:
        e = legend.get_window_extent(renderer)
        leg_bbox = [e.x0 - 0.5, H - e.y1 - 0.5, e.x1 - 0.5, H - e.y0 - 0.5]
    meta = dict(seed=seed, generator="probe_t4", marker_centre="drawn", style=style, preset=preset, font=rc["font.family"], width=W, height=H,
                plot_area=plot_area, xscale="linear", xdate=None, yscale="linear", xlim=list(map(float, xlim)),
                ylim=list(map(float, ylim)), xticks=ticks_for("x"), yticks=ticks_for("y"), series=out_series,
                legend_bbox=leg_bbox, offset_text=[_clean_label(o.get_text()) for o in offset_texts], probe=probe)
    plt.close(fig)
    return Rendered(image=image, sem=sem, inst=inst, meta=meta)


def _work(args):
    out, seed, kind = args
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    stem = os.path.join(out, f"{seed:08d}")
    if os.path.exists(stem + ".json"):
        return seed, True
    try:
        r = generate(seed, kind)
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
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--kind", default="mix", choices=KINDS + ["mix"])
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    jobs = [(a.out, s, a.kind) for s in range(a.start, a.start + a.count)]
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
