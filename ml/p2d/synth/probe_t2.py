"""Probe charts for series separation and tracing (team t2-trace).

Each case provokes one difficulty reliably while everything else stays easy
(medium figure, plain style, distinct colours, default ticks), so a change in
the extractor can be measured against one failure at a time:

    cross      smooth series of distinct colours crossing many times at shallow angles
    steep      sparse polylines with large vertical swings crossing each other
    parallel   two series of the same shape a few pixels apart, touching for long runs
    samecolour two series drawn in one colour: solid and dashed, or solid and solid
    dotted     dotted and dashed lines with long gaps, one to three series
    thin       lines under 1.2 px wide, three series, over a grid
    small      small figures (320 to 480 px wide) with three series
    dense      more data points than pixel columns: noise on a trend, one or two series
    legend     a framed legend box and a text annotation sitting on the series
    area       filled areas whose top edge is the data, overlapping
    step       step series crossing each other
    clipped    series leaving the plot area through the y limits and coming back
    multi      six series of mixed styles, the hardest charts of the validation set
    markers    lines under large markers, the ridge interrupted by the marker blobs
    wide       figures 1400 to 1800 px wide, scaled to 0.43 to 0.55 on the canvas, with ordinary 1 to 2 px lines

Seeds encode the case: seed = 12_000_000 + 10_000 * case_index + i. The output
format is the one `p2d.synth.build` writes (PNG, sem.png, inst.png, json), so the
standard evaluate command scores a probe directory unchanged:

    python -m p2d.synth.probe_t2 --case cross --count 100 --out data/t2-cross
    python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/t2-cross --refine

Ground truth is exact by the same construction as `mpl_render`: paths from the
axes transform, label maps from re-rendering one artist group at a time.
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
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.collections import Collection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.text import Text  # noqa: E402

from . import series as S  # noqa: E402
from .mpl_render import (AXIS, BG, DATA, GRID, LEGEND_SYMBOL, TEXT, TICK_LABEL, Rendered, _clean_label, _leaves,  # noqa: E402
                         _render_alpha, _step_path, _to_px)

SEED_BASE = 12_000_000
CASE_STRIDE = 10_000
CASES = ["cross", "steep", "parallel", "samecolour", "dotted", "thin", "small", "dense", "legend", "area", "step",
         "clipped", "multi", "markers", "wide"]

COLOURS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
           "#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#636EFA", "#EF553B", "#00CC96", "#AB63FA"]


def case_of(seed: int) -> str:
    return CASES[(seed - SEED_BASE) // CASE_STRIDE]


def seed_for(case: str, i: int) -> int:
    return SEED_BASE + CASE_STRIDE * CASES.index(case) + i


# ----------------------------------------------------------------------------- the spec


def base_spec(rng: np.random.Generator) -> dict:
    """A plain, medium chart: the easy defaults every case starts from."""
    dpi = float(rng.choice([80, 96, 100, 110, 120]))
    wpx = float(rng.uniform(640, 1100))
    return dict(
        dpi=dpi, wpx=wpx, hpx=wpx * float(rng.uniform(0.5, 0.75)),
        font=str(rng.choice(["DejaVu Sans", "Liberation Sans", "Lato", "FreeSans"])), fontsize=float(rng.uniform(8, 12)),
        series=[], xlog=False, ylog=False, xlim=None, ylim=None,
        grid=bool(rng.random() < 0.5), grid_axis="both",
        legend=str(rng.choice(["upper left", "upper right", "lower left", "lower right"])) if rng.random() < 0.6 else None,
        legend_frame=bool(rng.random() < 0.5), legend_ncol=1,
        title=str(rng.choice(["", "", "Results", "Monthly sales", "Experiment 2"])),
        xlabel=str(rng.choice(["", "Time (s)", "Year", "x"])), ylabel=str(rng.choice(["", "Value", "Amplitude", "y"])),
        spines_off=["top", "right"] if rng.random() < 0.6 else [], annotations=[], facecolor=None, margins=None,
    )


def unit_x(rng: np.random.Generator, n: int) -> np.ndarray:
    kind = rng.choice(["index", "year", "range"])
    if kind == "index":
        return np.arange(n, dtype=float)
    if kind == "year":
        start = int(rng.integers(1950, 2015))
        return np.linspace(start, start + int(rng.integers(5, 40)), n)
    return np.linspace(0, 10.0 ** rng.uniform(0, 3), n)


def line(x, y, color, lw=2.0, ls="-", kind="line", label=None, marker=None, ms=6.0, where=None, alpha=None, dashes=None):
    return dict(kind=kind, x=np.asarray(x, float), y=np.asarray(y, float), color=color, lw=float(lw), ls=ls, label=label,
                marker=marker, ms=float(ms), where=where, alpha=alpha, dashes=dashes)


# ----------------------------------------------------------------------------- the cases


def case_cross(rng: np.random.Generator, spec: dict) -> dict:
    """Smooth sines with different phases: shallow crossings, many of them."""
    n = int(rng.integers(150, 400))
    k = int(rng.choice([2, 3, 3, 4]))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    f = float(rng.uniform(1.5, 4.0))
    cols = rng.permutation(10)[:k]
    for j in range(k):
        amp = float(rng.uniform(0.6, 1.0))
        y = amp * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)) + float(rng.uniform(-0.3, 0.3)) * t
        y += 0.03 * S._smooth_noise(rng, n, 8)
        spec["series"].append(line(x, y, COLOURS[cols[j]], lw=float(rng.uniform(1.2, 2.8)), label=f"Series {j + 1}"))
    return spec


def case_steep(rng: np.random.Generator, spec: dict) -> dict:
    """Sparse polylines with large swings: steep segments, crossings at steep angles."""
    n = int(rng.integers(8, 30))
    k = int(rng.choice([2, 3, 3]))
    x = unit_x(rng, n)
    cols = rng.permutation(10)[:k]
    for j in range(k):
        y = rng.normal(size=n)
        y = (y - y.mean()) / (np.ptp(y) + 1e-9)
        spec["series"].append(line(x, y, COLOURS[cols[j]], lw=float(rng.uniform(1.2, 3.0)), label=f"Series {j + 1}"))
    return spec


def case_parallel(rng: np.random.Generator, spec: dict) -> dict:
    """Two series of one shape, a few pixels apart: a long run of near-touching lines."""
    n = int(rng.integers(100, 400))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    _, y = S.shape(rng, t, kind=str(rng.choice(["sines", "trend_noise", "walk", "poly", "logistic"])))
    # The gap in data units: the y span of the figure is about 1.4 units over ~0.6 * hpx px.
    ph_px = 0.6 * spec["hpx"]
    gap_px = float(rng.choice([1.5, 2.5, 4, 6, 9]))
    gap = gap_px / ph_px * 1.4
    cols = rng.permutation(10)[:2]
    spec["series"].append(line(x, y, COLOURS[cols[0]], lw=float(rng.uniform(1.2, 2.5)), label="Series 1"))
    y2 = y + gap * (1 + 0.5 * np.sin(2 * np.pi * t * rng.uniform(0.5, 2)) if rng.random() < 0.5 else 1.0)
    spec["series"].append(line(x, y2, COLOURS[cols[1]], lw=float(rng.uniform(1.2, 2.5)), label="Series 2"))
    spec["_note"] = f"gap_px={gap_px}"
    return spec


def case_samecolour(rng: np.random.Generator, spec: dict) -> dict:
    """Two series drawn in one colour, told apart only by dash or width, crossing a few times."""
    n = int(rng.integers(60, 300))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    c = COLOURS[int(rng.integers(10))]
    _, y1 = S.shape(rng, t, kind=str(rng.choice(["sines", "trend_noise", "poly"])))
    _, y2 = S.shape(rng, t, kind=str(rng.choice(["sines", "trend_noise", "poly"])))
    mode = str(rng.choice(["dashed", "dashed", "width"]))
    lw = float(rng.uniform(1.5, 2.5))
    spec["series"].append(line(x, y1, c, lw=lw, label="Solid"))
    if mode == "dashed":
        spec["series"].append(line(x, y2, c, lw=lw, ls=str(rng.choice(["--", ":", "-."])), label="Dashed"))
    else:
        spec["series"].append(line(x, y2, c, lw=lw * float(rng.uniform(1.8, 2.5)), label="Thick"))
    if rng.random() < 0.4:
        _, y3 = S.shape(rng, t, kind="trend_noise")
        spec["series"].append(line(x, y3, COLOURS[(int(rng.integers(10)) + 5) % 10], lw=lw, label="Other"))
    return spec


def case_dotted(rng: np.random.Generator, spec: dict) -> dict:
    """Dotted and dashed lines with long gaps."""
    n = int(rng.integers(40, 300))
    k = int(rng.choice([1, 2, 3]))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    cols = rng.permutation(10)[:k]
    for j in range(k):
        _, y = S.shape(rng, t, kind=str(rng.choice(["sines", "trend_noise", "walk", "poly", "damped"])))
        style = str(rng.choice([":", "--", "-.", "custom"]))
        dashes = None
        if style == "custom":
            dashes = (float(rng.uniform(1, 8)), float(rng.uniform(2, 8)))
            style = "--"
        spec["series"].append(line(x, y, COLOURS[cols[j]], lw=float(rng.uniform(0.8, 2.5)), ls=style, dashes=dashes,
                                   label=f"Series {j + 1}"))
    return spec


def case_thin(rng: np.random.Generator, spec: dict) -> dict:
    """Lines under 1.2 px wide, three of them, over a grid."""
    n = int(rng.integers(60, 400))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    spec["dpi"] = float(rng.choice([72, 80, 96]))
    spec["grid"] = True
    cols = rng.permutation(10)[:3]
    for j in range(3):
        _, y = S.shape(rng, t)
        y = y * float(rng.uniform(0.5, 1.0)) + float(rng.uniform(-0.3, 0.3))
        lw_pt = float(rng.uniform(0.4, 0.85)) * 72 / spec["dpi"]  # 0.4 to 0.85 px
        spec["series"].append(line(x, y, COLOURS[cols[j]], lw=lw_pt, label=f"Series {j + 1}"))
    return spec


def case_small(rng: np.random.Generator, spec: dict) -> dict:
    """Small figures: 320 to 480 px wide, three series."""
    spec["wpx"] = float(rng.uniform(320, 480))
    spec["hpx"] = spec["wpx"] * float(rng.uniform(0.5, 0.7))
    spec["fontsize"] = float(rng.uniform(6, 9))
    n = int(rng.integers(30, 200))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    cols = rng.permutation(10)[:3]
    for j in range(3):
        _, y = S.shape(rng, t)
        y = y * float(rng.uniform(0.5, 1.0)) + float(rng.uniform(-0.3, 0.3))
        spec["series"].append(line(x, y, COLOURS[cols[j]], lw=float(rng.uniform(0.8, 2.0)), label=f"Series {j + 1}"))
    return spec


def case_dense(rng: np.random.Generator, spec: dict) -> dict:
    """More points than columns: noise on a trend."""
    k = int(rng.choice([1, 1, 2]))
    n = int(rng.integers(1200, 2500))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    cols = rng.permutation(10)[:k]
    for j in range(k):
        _, y = S.shape(rng, t, kind=str(rng.choice(["trend_noise", "noise", "spiky_walk", "walk"])))
        noise = float(rng.uniform(0.02, 0.2)) * rng.normal(size=n)
        spec["series"].append(line(x, y + noise, COLOURS[cols[j]], lw=float(rng.uniform(0.8, 2.5)), label=f"Series {j + 1}"))
    return spec


def case_legend(rng: np.random.Generator, spec: dict) -> dict:
    """A framed legend and an annotation placed on the series themselves."""
    n = int(rng.integers(60, 300))
    k = int(rng.choice([2, 3]))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    cols = rng.permutation(10)[:k]
    for j in range(k):
        _, y = S.shape(rng, t, kind=str(rng.choice(["sines", "trend_noise", "poly", "walk"])))
        y = y * 0.5 + float(rng.uniform(-0.2, 0.2))
        spec["series"].append(line(x, y, COLOURS[cols[j]], lw=float(rng.uniform(1.2, 2.5)),
                                   label=str(rng.choice(["Revenue", "Control", "Model A", "Measured", "Series 1", "Temperature"]))))
    spec["legend"] = str(rng.choice(["center", "upper center", "lower center", "center left", "center right"]))
    spec["legend_frame"] = True
    spec["legend_ncol"] = int(rng.choice([1, 2])) if k > 2 else 1
    i = int(rng.integers(n // 4, 3 * n // 4))
    s = spec["series"][0]
    spec["annotations"].append(dict(text=str(rng.choice(["peak", "2021 Q3", "launch", "max 42.0"])), xy=(float(s["x"][i]), float(s["y"][i])),
                                    xytext=(float(rng.uniform(-20, 20)), float(rng.uniform(-15, 15))), fontsize=float(rng.uniform(8, 12)),
                                    arrow=bool(rng.random() < 0.5)))
    return spec


def case_area(rng: np.random.Generator, spec: dict) -> dict:
    """Filled areas whose top edge is the data."""
    n = int(rng.integers(40, 300))
    k = int(rng.choice([1, 2, 3]))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    cols = rng.permutation(10)[:k]
    for j in range(k):
        _, y = S.shape(rng, t, kind=str(rng.choice(["sines", "trend_noise", "walk", "logistic"])))
        y = y - y.min() + 0.2 + float(rng.uniform(0, 0.5))
        spec["series"].append(line(x, y, COLOURS[cols[j]], kind="area", lw=float(rng.uniform(1, 2.5)),
                                   alpha=float(rng.uniform(0.25, 0.9)), label=f"Series {j + 1}"))
        spec["series"][-1]["topline"] = bool(rng.random() < 0.5)
    return spec


def case_step(rng: np.random.Generator, spec: dict) -> dict:
    """Step series crossing each other."""
    n = int(rng.integers(8, 60))
    k = int(rng.choice([1, 2, 3]))
    x = unit_x(rng, n)
    cols = rng.permutation(10)[:k]
    for j in range(k):
        _, y = S.shape(rng, np.linspace(0, 1, n), kind=str(rng.choice(["walk", "steps", "trend_noise"])))
        spec["series"].append(line(x, y, COLOURS[cols[j]], kind="step", lw=float(rng.uniform(1.2, 2.5)),
                                   where=str(rng.choice(["pre", "post", "mid"])), label=f"Series {j + 1}"))
    return spec


def case_clipped(rng: np.random.Generator, spec: dict) -> dict:
    """Series leaving the plot through the y limits and coming back; a series over part of x."""
    n = int(rng.integers(100, 400))
    k = int(rng.choice([2, 3]))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    cols = rng.permutation(10)[:k]
    for j in range(k):
        _, y = S.shape(rng, t, kind=str(rng.choice(["sines", "walk", "poly"])))
        if j == 1 and rng.random() < 0.6:
            a, b = sorted(rng.uniform(0.05, 0.95, 2))
            if b - a < 0.25:
                a, b = 0.2, 0.7
            sel = slice(int(a * n), int(b * n))
            spec["series"].append(line(x[sel], y[sel], COLOURS[cols[j]], lw=float(rng.uniform(1.2, 2.5)), label=f"Series {j + 1}"))
        else:
            spec["series"].append(line(x, y * float(rng.uniform(1.0, 1.8)), COLOURS[cols[j]], lw=float(rng.uniform(1.2, 2.5)), label=f"Series {j + 1}"))
    spec["ylim"] = (-0.35, 0.35)
    return spec


def case_multi(rng: np.random.Generator, spec: dict) -> dict:
    """Six series of mixed styles, like the hardest validation charts."""
    n = int(rng.integers(30, 500))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    cols = rng.permutation(10)[:6]
    for j in range(6):
        _, y = S.shape(rng, t)
        y = y * float(rng.uniform(0.4, 1.2)) + float(rng.uniform(-0.5, 0.5))
        ls = str(rng.choice(["-", "-", "-", "--", ":", "-."]))
        kind = str(rng.choice(["line", "line", "line", "step", "area"])) if n < 120 else "line"
        spec["series"].append(line(x, y, COLOURS[cols[j]], kind=kind, lw=float(rng.uniform(0.8, 3.0)), ls=ls,
                                   where="post" if kind == "step" else None, alpha=0.5 if kind == "area" else None,
                                   label=f"Series {j + 1}"))
    spec["legend"] = str(rng.choice(["upper left", "upper right", "lower right", "center"]))
    spec["legend_frame"] = True
    return spec


def case_markers(rng: np.random.Generator, spec: dict) -> dict:
    """Lines drawn with large markers: the ridge is interrupted by a blob at every data point."""
    n = int(rng.integers(10, 45))
    k = int(rng.choice([1, 2, 3]))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    cols = rng.permutation(10)[:k]
    for j in range(k):
        _, y = S.shape(rng, t, kind=str(rng.choice(["sines", "trend_noise", "walk", "poly"])))
        y = y * float(rng.uniform(0.5, 1.0)) + float(rng.uniform(-0.3, 0.3))
        spec["series"].append(line(x, y, COLOURS[cols[j]], lw=float(rng.uniform(1.0, 2.5)), label=f"Series {j + 1}",
                                   marker=str(rng.choice(["o", "s", "^", "D", "v"])), ms=float(rng.uniform(7, 12))))
    return spec


def case_wide(rng: np.random.Generator, spec: dict) -> dict:
    """Large figures that the canvas scales down by half: ordinary lines become sub-pixel."""
    spec["wpx"] = float(rng.uniform(1400, 1800))
    spec["hpx"] = spec["wpx"] * float(rng.uniform(0.45, 0.7))
    if spec["wpx"] * spec["hpx"] > 1.8e6:
        f = math.sqrt(1.8e6 / (spec["wpx"] * spec["hpx"]))
        spec["wpx"], spec["hpx"] = spec["wpx"] * f, spec["hpx"] * f
    spec["dpi"] = float(rng.choice([96, 100, 110, 120]))
    spec["fontsize"] = float(rng.uniform(9, 14))
    n = int(rng.integers(60, 500))
    k = int(rng.choice([2, 3, 3]))
    x = unit_x(rng, n)
    t = np.linspace(0, 1, n)
    cols = rng.permutation(10)[:k]
    for j in range(k):
        _, y = S.shape(rng, t)
        y = y * float(rng.uniform(0.5, 1.0)) + float(rng.uniform(-0.3, 0.3))
        lw_pt = float(rng.uniform(1.0, 2.0)) * 72 / spec["dpi"]  # 1 to 2 source px
        spec["series"].append(line(x, y, COLOURS[cols[j]], lw=lw_pt, label=f"Series {j + 1}"))
    return spec


BUILDERS = {"cross": case_cross, "steep": case_steep, "parallel": case_parallel, "samecolour": case_samecolour,
            "dotted": case_dotted, "thin": case_thin, "small": case_small, "dense": case_dense, "legend": case_legend,
            "area": case_area, "step": case_step, "clipped": case_clipped, "multi": case_multi, "markers": case_markers,
            "wide": case_wide}


# ----------------------------------------------------------------------------- rendering


def generate(seed: int) -> Rendered:
    case = case_of(seed)
    rng = np.random.default_rng(seed)
    spec = BUILDERS[case](rng, base_spec(rng))
    rc = {"font.family": spec["font"], "font.size": spec["fontsize"], "path.simplify": False, "axes.unicode_minus": False}
    with plt.style.context("default"), plt.rc_context(rc):
        return render_spec(spec, seed, case)


def render_spec(spec: dict, seed: int, case: str) -> Rendered:
    dpi = spec["dpi"]
    fig = plt.figure(figsize=(spec["wpx"] / dpi, spec["hpx"] / dpi), dpi=dpi)
    canvas = FigureCanvasAgg(fig)
    if spec.get("facecolor"):
        fig.patch.set_facecolor(spec["facecolor"])
    ax = fig.add_subplot(111)
    data_artists = []
    grid_extra = []
    for k, s in enumerate(spec["series"]):
        kw = dict(color=s["color"], label=s["label"], zorder=2 + k * 0.01)
        if s["kind"] == "area":
            base = 0.0
            fill = ax.fill_between(s["x"], s["y"], base, color=s["color"], alpha=s["alpha"] or 0.5, lw=0, zorder=1.8 + k * 0.01)
            if s.get("topline"):
                grid_extra.append(fill)
                (art,) = ax.plot(s["x"], s["y"], lw=s["lw"], **kw)
            else:
                art = fill
                art.set_label(s["label"])
        elif s["kind"] == "step":
            (art,) = ax.step(s["x"], s["y"], where=s["where"], lw=s["lw"], ls=s["ls"], **kw)
        else:
            mk = dict(marker=s["marker"], markersize=s["ms"]) if s["marker"] else {}
            (art,) = ax.plot(s["x"], s["y"], lw=s["lw"], ls=s["ls"], **kw, **mk)
            if s.get("dashes"):
                art.set_dashes(s["dashes"])
        art.set_snap(False)
        data_artists.append(art)
    text_extra = []
    for an in spec["annotations"]:
        text_extra.append(ax.annotate(an["text"], an["xy"], xytext=an["xytext"], textcoords="offset points", fontsize=an["fontsize"],
                                      arrowprops=dict(arrowstyle="->", lw=0.8) if an.get("arrow") else None))
    if spec["xlog"]:
        ax.set_xscale("log")
    if spec["ylog"]:
        ax.set_yscale("log")
    if spec["xlim"]:
        ax.set_xlim(*spec["xlim"])
    if spec["ylim"]:
        ax.set_ylim(*spec["ylim"])
    if spec.get("margins") is not None:
        ax.margins(x=spec["margins"])
    for name in spec["spines_off"]:
        ax.spines[name].set_visible(False)
    if spec["grid"]:
        ax.grid(True, which="major", alpha=0.6, ls="-", lw=0.8, axis=spec["grid_axis"])
    if spec["title"]:
        ax.set_title(spec["title"])
    if spec["xlabel"]:
        ax.set_xlabel(spec["xlabel"])
    if spec["ylabel"]:
        ax.set_ylabel(spec["ylabel"])
    for axis in (ax.xaxis, ax.yaxis):
        if isinstance(axis.get_major_formatter(), mticker.ScalarFormatter):
            axis.get_major_formatter().set_useOffset(False)
            axis.get_major_formatter().set_scientific(False)
    legend = None
    if spec["legend"] and len(spec["series"]) > 1:
        legend = ax.legend(loc=spec["legend"], frameon=spec["legend_frame"], ncol=spec["legend_ncol"], fontsize=spec["fontsize"])
    try:
        fig.tight_layout(pad=0.8)
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
    tick_label_ids = {id(t) for t in xt_labels + yt_labels}
    axis_ids = {id(s) for s in ax.spines.values()}
    for axis in (ax.xaxis, ax.yaxis):
        for tl in axis.get_ticklines() + axis.get_ticklines(minor=True):
            axis_ids.add(id(tl))
    grid_ids = {id(g) for g in ax.xaxis.get_gridlines() + ax.yaxis.get_gridlines()} | {id(a) for a in grid_extra}
    legend_symbol_ids: set[int] = set()
    legend_text_ids: set[int] = set()
    if legend is not None:
        legend_text_ids = {id(t) for t in legend.get_texts()}
        for a in legend.findobj():
            if a is legend.get_frame() or id(a) in legend_text_ids or a is legend:
                continue
            if isinstance(a, (Line2D, Collection, Patch)):
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
            label = tick.label1
            if not (label.get_visible() and label.get_text()):
                continue
            e = label.get_window_extent(renderer)
            if axis_name == "x":
                pos = float(_to_px(ax, H, [v], [ylim[0]])[0][0])
                anchor = [pos, plot_area[3]]
            else:
                pos = float(_to_px(ax, H, [xlim[0]], [v])[0][1])
                anchor = [plot_area[0], pos]
            out.append(dict(value=float(v), pos=pos, anchor=anchor, side="low", text=_clean_label(label.get_text()),
                            raw=label.get_text(), bbox=[e.x0 - 0.5, H - e.y1 - 0.5, e.x1 - 0.5, H - e.y0 - 0.5]))
        return out

    out_series = []
    for s, art in zip(spec["series"], data_artists):
        x, y = s["x"], s["y"]
        px_x, px_y = _step_path(x, y, s["where"]) if s["kind"] == "step" else (x, y)
        path = _to_px(ax, H, px_x, px_y)
        markers = _to_px(ax, H, x, y) if s["marker"] else np.zeros((0, 2))
        lw_px = s["lw"] * fig.dpi / 72.0 if s["kind"] != "area" or isinstance(art, Line2D) else 1.0
        out_series.append(dict(kind="line+markers" if s["marker"] else s["kind"], label=s["label"], color=s["color"],
                               linestyle=s["ls"], linewidth_px=lw_px, marker=s["marker"], markersize_px=s["ms"] * fig.dpi / 72.0,
                               x=np.asarray(x).tolist(), y=np.asarray(y).tolist(), path_px=path.round(3).tolist(),
                               markers_px=markers.round(3).tolist()))
    leg_bbox = None
    if legend is not None:
        e = legend.get_window_extent(renderer)
        leg_bbox = [e.x0 - 0.5, H - e.y1 - 0.5, e.x1 - 0.5, H - e.y0 - 0.5]
    meta = dict(seed=seed, generator="matplotlib", style="default", preset="probe-" + case, font=spec["font"], width=W, height=H,
                plot_area=plot_area, xscale="log" if spec["xlog"] else "linear", xdate=None, yscale="log" if spec["ylog"] else "linear",
                xlim=list(map(float, xlim)), ylim=list(map(float, ylim)), xticks=ticks_for("x"), yticks=ticks_for("y"),
                series=out_series, legend_bbox=leg_bbox, offset_text=["", ""], probe_note=spec.get("_note", ""))
    plt.close(fig)
    return Rendered(image=image, sem=sem, inst=inst, meta=meta)


# ----------------------------------------------------------------------------- building


def _work(args):
    import cv2

    out, seed = args
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    stem = os.path.join(out, f"{seed:08d}")
    if os.path.exists(stem + ".json"):
        return seed, True
    try:
        r = generate(seed)
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
    ap.add_argument("--case", required=True, choices=CASES)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--start", type=int, default=0, help="first index within the case")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    jobs = [(a.out, seed_for(a.case, i)) for i in range(a.start, a.start + a.count)]
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
