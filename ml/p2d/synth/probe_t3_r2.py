"""Round-2 probe set for t3-precision: isolated tick measurements for the joint-affine refine_ticks angle.

    python -m p2d.synth.probe_t3_r2 --family ticks --out data/t3-ticks-r2 --start 14000000 --count 500 --workers 3

Each chart is one line series across a plot with controlled tick geometry.
Factors (mixed-radix sampling per seed, uniform over any contiguous seed range):

  N_ticks        in {3, 4, 5, 6, 8, 10, 12}   per axis
  axis_style     in {linear, log}             per axis
  dpi            in {80, 100, 160}            chart-level
  label_density  in {sparse, dense}           per axis (dense: minor ticks on)
  grid           in {off, on}                 per axis
  label_rot      in {0, 45, 90} degrees       per axis
  has_offset     in {False, True} with prob 0.25  chart-level (y-axis gets a +1eN offset label)

Each chart's meta.probe records:
  - factor values at chart level
  - per-tick annotations under meta.probe.axes.{x,y}.ticks[]:
      {value, pos_canvas, text, mark_drawn, grid_drawn, is_minor}
    `pos_canvas` is the ground-truth canvas pixel position (sub-pixel, float).
    `mark_drawn` is True when the renderer drew a visible tick mark at that tick.
    `grid_drawn` is True when a gridline sits at that tick (major grid only; the
    minor-grid condition is read from meta.probe.axes.{x,y}.minor_grid).
  - meta.probe.axes.{x,y}.n_ticks: integer count of VISIBLE major ticks (the probed N; the
    rendered figure may show fewer than the requested N when the locator culls edge ticks).

The ground-truth xticks/yticks arrays recorded in meta.xticks/yticks (set by
mpl_render.finish's `ticks_for`) carry the sub-pixel position of each labelled
major tick (what the brainstormer joins on). The per-tick annotations above
sit on top of that for the factor splits.

Seed base is 14,000,000. Family name "ticks" (one family in this file).
"""

from __future__ import annotations

import argparse
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

from .mpl_render import Rendered, _to_px  # noqa: E402
from .probe_t3 import _figure, _plot, _smooth, finish  # noqa: E402

SEED_BASE = 14_000_000
FAMILY_BASE = {"ticks": 14_000_000}

# Factor grids (per axis independently where noted)
N_TICKS = (3, 4, 5, 6, 8, 10, 12)
AXIS_STYLES = ("linear", "log")
DPIS = (80.0, 100.0, 160.0)
LABEL_DENSITY = ("sparse", "dense")
GRID = (False, True)
LABEL_ROT = (0, 45, 90)


def _pick(seed: int, *sizes: int) -> list[int]:
    """One random point of a factor grid per seed (uniform over contiguous seed ranges)."""
    rng = np.random.default_rng(seed + 23)
    return [int(rng.integers(n)) for n in sizes]


def _axis_params(seed: int, which: str) -> dict:
    """Pick independent factor values for one axis of this chart."""
    salt = 1 if which == "x" else 2
    rng = np.random.default_rng(seed * 7 + salt * 13 + 991)
    i_n, i_style, i_dens, i_grid, i_rot = (
        int(rng.integers(len(N_TICKS))),
        int(rng.integers(len(AXIS_STYLES))),
        int(rng.integers(len(LABEL_DENSITY))),
        int(rng.integers(len(GRID))),
        int(rng.integers(len(LABEL_ROT))),
    )
    return dict(
        n_ticks=N_TICKS[i_n],
        axis_style=AXIS_STYLES[i_style],
        label_density=LABEL_DENSITY[i_dens],
        grid=GRID[i_grid],
        label_rotation=LABEL_ROT[i_rot],
    )


def _series(rng: np.random.Generator, xp: dict, yp: dict, n: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """A smooth, well-behaved curve on the chosen axis styles."""
    if xp["axis_style"] == "log":
        x = np.logspace(0.3, 3.2, n)  # 2 to ~1600 on log x
    else:
        x = np.linspace(0.0, 100.0, n)
    if yp["axis_style"] == "log":
        y = np.logspace(0.1, 2.8, n) * (0.8 + 0.4 * _smooth(rng, n))
    else:
        y = 100.0 + 60.0 * _smooth(rng, n)
    return x, y


def _apply_offset(ax, has_offset: bool, rng: np.random.Generator) -> dict | None:
    """When requested, place the y data at a value range that forces matplotlib to print an offset label.

    `axes.formatter.useoffset = True` plus a y range whose midpoint is far from
    its span triggers the offset. We shift y so the range is (base + eps_lo,
    base + eps_hi) with base in {1e3, 1e4, 1e5}.
    """
    if not has_offset:
        return None
    base = float(rng.choice([1e3, 1e4, 1e5]))
    ax.ticklabel_format(axis="y", useOffset=True, style="plain")
    return {"applied": True, "offset_value": base, "axis": "y"}


def _axis_locator(ax, which: str, p: dict) -> None:
    """Install a locator and minor-tick behaviour for one axis."""
    axis = ax.xaxis if which == "x" else ax.yaxis
    if p["axis_style"] == "log":
        if which == "x":
            ax.set_xscale("log")
        else:
            ax.set_yscale("log")
        axis.set_major_locator(mticker.LogLocator(base=10.0, numticks=p["n_ticks"]))
        if p["label_density"] == "dense":
            axis.set_minor_locator(mticker.LogLocator(base=10.0, subs=(2, 3, 4, 5, 6, 7, 8, 9), numticks=100))
    else:
        axis.set_major_locator(mticker.MaxNLocator(nbins=max(3, p["n_ticks"] - 1), steps=[1, 2, 2.5, 5, 10]))
        if p["label_density"] == "dense":
            axis.set_minor_locator(mticker.AutoMinorLocator(5))


def _per_tick_records(ax, which: str) -> list[dict]:
    """Build per-tick annotations for one axis after render.

    One record per major tick that produced a visible label (matching
    mpl_render.ticks_for), plus any minor ticks that drew gridlines.
    """
    axis = ax.xaxis if which == "x" else ax.yaxis
    lim = ax.get_xlim() if which == "x" else ax.get_ylim()
    lo, hi = min(lim), max(lim)
    eps = (hi - lo) * 1e-9
    canvas = ax.figure.canvas
    H = ax.figure.canvas.get_renderer().height
    out = []
    # Major ticks
    for tick, v in zip(axis.get_major_ticks(), axis.get_majorticklocs()):
        if not (lo - eps <= v <= hi + eps):
            continue
        label = tick.label1 if tick.label1.get_visible() and tick.label1.get_text() else tick.label2
        if not (label.get_visible() and label.get_text()):
            continue
        if which == "x":
            pos = float(_to_px(ax, H, [v], [ax.get_ylim()[0]])[0][0])
        else:
            pos = float(_to_px(ax, H, [ax.get_xlim()[0]], [v])[0][1])
        # Mark drawn: tick1line or tick2line visible AND has non-zero length
        marker_lines = [tick.tick1line, tick.tick2line]
        mark_drawn = any(ml.get_visible() and ml.get_markersize() and ml.get_markersize() > 0 for ml in marker_lines)
        grid_drawn = bool(tick.gridline.get_visible())
        out.append(dict(
            value=float(v), pos_canvas=pos, text=label.get_text(), mark_drawn=mark_drawn,
            grid_drawn=grid_drawn, is_minor=False,
        ))
    # Minor ticks (only recorded when a minor gridline would be drawn, for the dense-grid signal)
    for tick, v in zip(axis.get_minor_ticks(), axis.get_minorticklocs()):
        if not (lo - eps <= v <= hi + eps):
            continue
        if not tick.gridline.get_visible():
            continue
        if which == "x":
            pos = float(_to_px(ax, H, [v], [ax.get_ylim()[0]])[0][0])
        else:
            pos = float(_to_px(ax, H, [ax.get_xlim()[0]], [v])[0][1])
        out.append(dict(
            value=float(v), pos_canvas=pos, text="", mark_drawn=False,
            grid_drawn=True, is_minor=True,
        ))
    return out


def ticks(seed: int) -> Rendered:
    """One line series across a plot with per-axis controlled tick geometry (r2 probe family)."""
    rng = np.random.default_rng(seed)
    i_dpi, i_offset = _pick(seed, len(DPIS), 4)  # 1/4 of charts carry a y-offset
    dpi = DPIS[i_dpi]
    has_offset = (i_offset == 0)
    xp = _axis_params(seed, "x")
    yp = _axis_params(seed, "y")
    if has_offset:
        # Offset only applies on linear axes
        yp["axis_style"] = "linear"
    wpx = int(rng.choice([600, 900, 1200, 1500]))
    hpx = int(wpx * 0.62)
    font = str(rng.choice(["DejaVu Sans", "Liberation Sans"]))
    fig, ax, canvas, ctx = _figure(wpx, hpx, dpi, max(8.0, 10 * wpx / 900), font)
    try:
        x, y = _series(rng, xp, yp)
        if has_offset:
            y_offset = float(rng.choice([1e3, 1e4, 1e5]))
            # Place y data on a narrow window above the offset base, so matplotlib prints "+1e4" above the axis.
            y = y_offset + 0.01 * y_offset * (y - y.min()) / max(1e-9, (y.max() - y.min())) + rng.uniform(0.5, 1.5) * y_offset * 0.001
        # Scale set BEFORE locators (log scale resets the locator)
        if xp["axis_style"] == "log":
            ax.set_xscale("log")
        if yp["axis_style"] == "log" and not has_offset:
            ax.set_yscale("log")
        _axis_locator(ax, "x", xp)
        _axis_locator(ax, "y", yp)
        # Label rotation
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(xp["label_rotation"])
            if xp["label_rotation"] in (45, 90):
                lbl.set_horizontalalignment("right")
        for lbl in ax.get_yticklabels():
            lbl.set_rotation(yp["label_rotation"])
        # Grid
        if xp["grid"] or yp["grid"]:
            which_axis = "x" if (xp["grid"] and not yp["grid"]) else "y" if (yp["grid"] and not xp["grid"]) else "both"
            ax.grid(True, axis=which_axis, which="major", color="#cccccc", lw=0.8, ls="-")
            if xp["label_density"] == "dense" and xp["grid"]:
                ax.grid(True, axis="x", which="minor", color="#eeeeee", lw=0.5, ls="--")
            if yp["label_density"] == "dense" and yp["grid"]:
                ax.grid(True, axis="y", which="minor", color="#eeeeee", lw=0.5, ls="--")
        # Visible tick marks (both axes)
        ax.tick_params(axis="both", which="major", length=4.0, width=1.0, direction="out")
        if xp["label_density"] == "dense" or yp["label_density"] == "dense":
            ax.tick_params(axis="both", which="minor", length=2.0, width=0.6, direction="out")
        # Offset formatter wiring (only after locators + scales)
        axis_offset = _apply_offset(ax, has_offset, rng)
        # Plot
        art = _plot(ax, x, y, 1.6, dpi, "#0072B2")
        fig.tight_layout(pad=0.8)
        canvas.draw()
        # Collect per-tick records AFTER layout
        tick_records = dict(x=_per_tick_records(ax, "x"), y=_per_tick_records(ax, "y"))
        n_major_x = sum(1 for t in tick_records["x"] if not t["is_minor"])
        n_major_y = sum(1 for t in tick_records["y"] if not t["is_minor"])
        probe = dict(
            family="ticks_r2",
            width=wpx,
            height=hpx,
            dpi=dpi,
            has_offset=has_offset,
            axis_offset=axis_offset,
            axes=dict(
                x=dict(n_ticks_target=xp["n_ticks"], n_ticks=n_major_x, axis_style=xp["axis_style"],
                       label_density=xp["label_density"], grid=xp["grid"], label_rotation=xp["label_rotation"],
                       ticks=tick_records["x"]),
                y=dict(n_ticks_target=yp["n_ticks"], n_ticks=n_major_y, axis_style=yp["axis_style"],
                       label_density=yp["label_density"], grid=yp["grid"], label_rotation=yp["label_rotation"],
                       ticks=tick_records["y"]),
            ),
        )
        return finish(
            fig, ax, canvas,
            [dict(kind="line", label="Series 1", x=x, y=y, lw=1.6 * 72 / dpi, ls="-")],
            [art], seed, probe,
        )
    finally:
        ctx.__exit__(None, None, None)


FAMILIES = {"ticks": ticks}


def generate(family: str, seed: int) -> Rendered:
    return FAMILIES[family](seed)


def _work(args):
    out, family, seed = args
    import json
    import logging

    import cv2

    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    stem = os.path.join(out, f"{seed:08d}")
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
    ap.add_argument("--start", type=int, default=None, help="default: the family's own seed base (14,000,000)")
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    if a.start is None:
        a.start = FAMILY_BASE[a.family]
    if a.start < 13_100_000:
        sys.exit("seeds for round-2 start at 13,100,000; use 14,000,000+ to avoid colliding with round-1 t3 families")
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
