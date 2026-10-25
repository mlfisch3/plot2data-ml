"""Render a random matplotlib chart together with its exact ground truth.

`generate(seed)` returns the RGB image, per-pixel label maps and a JSON-able
record of everything a model should recover: the plot area, every labelled tick
with its pixel position, value and printed text, and every series as data
values, as the drawn centre-line polyline in pixels and as marker centres.

Pixel coordinates follow one convention throughout the ML code: the centre of
pixel column i is x = i, and of pixel row j is y = j, with y growing down.

Label maps come from re-rendering the same figure once per artist group with
everything else hidden, so a pixel's class is the group whose ink it actually
is, antialiasing included, rather than a guess from colour.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.artist import Artist  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.collections import Collection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.text import Text  # noqa: E402

from . import presets as P  # noqa: E402
from . import series as S  # noqa: E402

# Semantic classes of the per-pixel label map.
BG, DATA, LEGEND_SYMBOL, AXIS, GRID, TICK_LABEL, TEXT = range(7)
CLASS_NAMES = ["bg", "data", "legend_symbol", "axis", "grid", "tick_label", "text"]

STYLES = [
    ("default", 30), ("seaborn-v0_8", 6), ("seaborn-v0_8-whitegrid", 6), ("seaborn-v0_8-darkgrid", 4),
    ("seaborn-v0_8-white", 4), ("seaborn-v0_8-ticks", 4), ("ggplot", 6), ("bmh", 4), ("fivethirtyeight", 4),
    ("classic", 4), ("dark_background", 4), ("grayscale", 2), ("Solarize_Light2", 2), ("tableau-colorblind10", 3),
    ("seaborn-v0_8-colorblind", 2), ("seaborn-v0_8-muted", 2), ("seaborn-v0_8-pastel", 1), ("seaborn-v0_8-bright", 2),
    ("petroff10", 2),
]
FONTS = [
    "DejaVu Sans", "DejaVu Sans", "DejaVu Serif", "Liberation Sans", "Liberation Serif", "Lato", "Ubuntu",
    "FreeSans", "Nimbus Sans", "TeX Gyre Heros", "TeX Gyre Termes", "Liberation Sans Narrow", "Noto Sans Mono",
    "URW Gothic", "C059", "P052", "Bitstream Charter", "Liberation Mono",
]
MARKERS = ["o", "s", "^", "v", "D", "d", "<", ">", "p", "h", "*", "x", "+", ".", "P", "X", "8"]


def _pick(rng: np.random.Generator, items_weights):
    items = [i for i, _ in items_weights]
    w = np.array([w for _, w in items_weights], dtype=float)
    return items[int(rng.choice(len(items), p=w / w.sum()))]


@dataclass
class Rendered:
    image: np.ndarray  # H x W x 3 uint8
    sem: np.ndarray  # H x W uint8, CLASS_NAMES
    inst: np.ndarray  # H x W uint8, 0 = none, k = series k-1 (topmost wins)
    meta: dict


def _fmt_number(v: float, decimals: int, thousands: bool) -> str:
    s = f"{v:,.{decimals}f}" if thousands else f"{v:.{decimals}f}"
    return s


class StyledFormatter(mticker.Formatter):
    """Tick text in a chosen house style, with as many decimals as the ticks need.

    Like matplotlib's own ScalarFormatter, the decimals are chosen from all tick
    values together, so 0.25 is never printed as 0.2. `extra` adds trailing
    zeros some charts carry (1.50, 2.00).
    """

    def __init__(self, style: str, div: float = 1.0, suffix: str = "", minus: str = "-", extra: int = 0):
        self.style, self.div, self.suffix, self.minus, self.extra = style, div, suffix, minus, extra
        self.decimals = 0

    def _decimals_for(self, values) -> int:
        vals = [v / self.div for v in values]
        if self.style == "sci":
            for d in range(0, 7):
                if all(abs(float(f"{v:.{d}e}") - v) <= 1e-9 * max(1e-300, abs(v)) for v in vals):
                    return d
            return 6
        for d in range(0, 7):
            if all(abs(round(v, d) - v) <= 1e-9 * max(1.0, abs(v)) for v in vals):
                return d
        return 6

    def format_ticks(self, values):
        self.decimals = self._decimals_for(values) + self.extra
        return [self(v) for v in values]

    def __call__(self, v, pos=None):
        d = self.decimals
        x = v / self.div
        a = abs(x)
        if self.style == "sci":
            body = f"{a:.{d}e}"
        elif self.style in ("thousands", "dollar"):
            body = f"{a:,.{d}f}"
        else:
            body = f"{a:.{d}f}"
        if self.style == "dollar":
            body = "$" + body
        body += self.suffix
        if self.style == "pct":
            body += "%"
        return (self.minus + body) if x < 0 and float(body.strip("$%kKMBGbn").replace(",", "") or 0) != 0 else body


def _make_formatter(rng: np.random.Generator, span: float, maxabs: float):
    """A tick formatter, plus a name for it. Returns None for matplotlib's default."""
    choice = str(rng.choice(["default", "plain", "thousands", "suffix", "pct", "dollar", "sci"],
                            p=[0.35, 0.2, 0.12, 0.12, 0.08, 0.08, 0.05]))
    minus = "\u2212" if rng.random() < 0.5 else "-"
    extra = 1 if rng.random() < 0.15 else 0
    if choice == "default":
        return "default", None
    if choice == "suffix":
        if maxabs >= 1e9:
            return "suffix", StyledFormatter("plain", 1e9, str(rng.choice(["B", "bn", "G"])), minus)
        if maxabs >= 1e6:
            return "suffix", StyledFormatter("plain", 1e6, "M", minus)
        if maxabs >= 1e4:
            return "suffix", StyledFormatter("plain", 1e3, str(rng.choice(["k", "K"])), minus)
        choice = "plain"
    if choice == "sci":
        return "sci", StyledFormatter("sci", minus=minus)
    return choice, StyledFormatter(choice, minus=minus, extra=extra)


def _clean_label(s: str) -> str:
    """Matplotlib mathtext label to the plain text a reader should produce."""
    s = s.replace("$\\mathdefault{", "").replace("}$", "").replace("$", "")
    s = s.replace("\\mathdefault{", "").replace("{", "").replace("}", "")
    s = s.replace("\\times", "x").replace("\\cdot", "x").replace("\\minus", "-").replace("−", "-")
    return s.strip()


def _leaves(fig) -> list[Artist]:
    out = []
    for a in fig.findobj():
        if isinstance(a, (Line2D, Text, Patch, Collection)) or type(a).__name__ in ("AxesImage",):
            out.append(a)
    return out


def _render_alpha(fig, canvas, leaves, keep: set[int]) -> np.ndarray:
    saved = [a.get_visible() for a in leaves]
    for a in leaves:
        if id(a) not in keep:
            a.set_visible(False)
    canvas.draw()
    alpha = np.asarray(canvas.buffer_rgba())[..., 3].copy()
    for a, v in zip(leaves, saved):
        a.set_visible(v)
    return alpha


def _to_px(ax, H: int, xs, ys) -> np.ndarray:
    pts = ax.transData.transform(np.column_stack([xs, ys]))
    return np.column_stack([pts[:, 0] - 0.5, H - pts[:, 1] - 0.5])


def _step_path(x: np.ndarray, y: np.ndarray, where: str) -> tuple[np.ndarray, np.ndarray]:
    if len(x) < 2:
        return x, y
    if where == "post":
        xs = np.repeat(x, 2)[1:]
        ys = np.repeat(y, 2)[:-1]
    elif where == "pre":
        xs = np.repeat(x, 2)[:-1]
        ys = np.repeat(y, 2)[1:]
    else:
        mid = (x[:-1] + x[1:]) / 2
        xs = np.concatenate([[x[0]], np.repeat(mid, 2), [x[-1]]])
        ys = np.repeat(y, 2)
    return xs, ys


def generate(seed: int) -> Rendered:
    rng = np.random.default_rng(seed)
    preset = P.choose(rng)
    style = _pick(rng, STYLES) if preset == "none" else "default"
    rc = {
        "font.family": str(rng.choice(FONTS)),
        "font.size": float(rng.uniform(7, 15)),
        "axes.unicode_minus": bool(rng.random() < 0.5),
        "path.simplify": False,
    }
    rc.update(P.rc(preset, rng))
    with plt.style.context(style), plt.rc_context(rc):
        return _generate(rng, seed, style, rc, preset)


def _generate(rng: np.random.Generator, seed: int, style: str, rc: dict, preset: str = "none") -> Rendered:
    pal = P.palette(preset)
    # --- figure size: pixel width 320..1800, aspect 0.35..0.95, capped area ---
    dpi = float(rng.choice([60, 72, 80, 96, 100, 110, 120, 144, 150, 200]))
    wpx = rng.uniform(320, 1800)
    hpx = wpx * rng.uniform(0.35, 0.95)
    area = wpx * hpx
    if area > 1.8e6:
        f = math.sqrt(1.8e6 / area)
        wpx, hpx = wpx * f, hpx * f
    hpx = max(hpx, 220)
    fig = plt.figure(figsize=(wpx / dpi, hpx / dpi), dpi=dpi)
    canvas = FigureCanvasAgg(fig)
    if rng.random() < 0.15 and preset == "none":
        fig.patch.set_facecolor(tuple(rng.uniform(0.85, 1.0, 3)))
    ax = fig.add_subplot(111)
    if rng.random() < 0.12 and preset == "none":
        ax.set_facecolor(tuple(rng.uniform(0.88, 1.0, 3)))

    xlog = rng.random() < 0.07
    ylog = rng.random() < 0.16
    n_series = int(rng.choice([1, 1, 1, 2, 2, 3, 3, 4, 5, 6]))
    plot_kind = str(rng.choice(["line", "scatter", "mixed"], p=[0.68, 0.17, 0.15]))

    # --- data ---
    n_line = int(rng.choice([rng.integers(4, 25), rng.integers(25, 120), rng.integers(120, 600), rng.integers(600, 2500)],
                            p=[0.3, 0.3, 0.25, 0.15]))
    _, xbase = S.x_values(rng, n_line, xlog)
    date_axis = None
    if not xlog and rng.random() < 0.12:
        # A time axis: x in days since 1970, labelled as dates.
        from ..dates import date_axis as _date_axis

        xbase, dloc, dfmt, dname = _date_axis(rng, n_line)
        date_axis = (dloc, dfmt, dname)
    xr = (xbase.min(), xbase.max())
    yc, ys = S.y_scale(rng, ylog)
    ylog_lo = rng.uniform(-3, 4)
    ylog_dec = rng.uniform(1, 6)
    shared_shape = rng.random() < 0.3
    base_kind, base_curve = S.shape(rng, (np.log10(xbase) - np.log10(xr[0])) / (np.log10(xr[1]) - np.log10(xr[0])) if xlog else (xbase - xr[0]) / (xr[1] - xr[0] + 1e-300))

    series_meta = []
    data_artists = []
    grid_extra_pre = []
    for k in range(n_series):
        if plot_kind == "line":
            kind = "line+markers" if (rng.random() < 0.18 and n_line <= 80) else ("step" if rng.random() < 0.05 else ("area" if rng.random() < 0.07 else "line"))
        elif plot_kind == "scatter":
            kind = "scatter"
        else:
            kind = str(rng.choice(["line", "scatter", "line+markers"]))
        if kind == "scatter":
            n = int(rng.integers(5, 160))
            if rng.random() < 0.5:
                xi = np.sort(rng.uniform(0, 1, n))
            else:
                xi = np.sort(np.clip(np.linspace(0, 1, n) + rng.normal(0, 0.3 / n, n), 0, 1))
            if xlog:
                x = 10 ** (np.log10(xr[0]) + xi * (np.log10(xr[1]) - np.log10(xr[0])))
            else:
                x = xr[0] + xi * (xr[1] - xr[0])
            _, cur = S.shape(rng, xi)
            cur = cur + rng.normal(0, rng.uniform(0, 0.25), n)
        else:
            if rng.random() < 0.15 and n_line > 30:
                # A series that covers only part of the x range.
                a, b = sorted(rng.uniform(0, 1, 2))
                if b - a < 0.3:
                    a, b = 0.0, 1.0
                sel = slice(int(a * n_line), max(int(a * n_line) + 3, int(b * n_line)))
            else:
                sel = slice(None)
            x = xbase[sel]
            if shared_shape:
                cur = base_curve[sel] + rng.uniform(-0.4, 0.4) + 0.15 * S.shape(rng, (x - xr[0]) / (xr[1] - xr[0] + 1e-300))[1]
            else:
                cur = S.shape(rng, (np.log10(x) - np.log10(xr[0])) / (np.log10(xr[1]) - np.log10(xr[0])) if xlog else (x - xr[0]) / (xr[1] - xr[0] + 1e-300))[1]
                cur = cur * rng.uniform(0.4, 1.2) + rng.uniform(-0.5, 0.5)
        if ylog:
            y = 10 ** (ylog_lo + ylog_dec * (cur - cur.min()) / (cur.max() - cur.min() + 1e-9) * rng.uniform(0.5, 1) + rng.uniform(0, 0.5))
        else:
            y = yc + ys * cur

        lw = float(rng.choice([rng.uniform(0.6, 1.5), rng.uniform(1.5, 2.5), rng.uniform(2.5, 4.5)], p=[0.4, 0.45, 0.15]))
        ls = str(rng.choice(["-", "--", ":", "-."], p=[0.82, 0.1, 0.05, 0.03]))
        marker = str(rng.choice(MARKERS))
        ms = float(rng.uniform(2.5, 11))
        hollow = rng.random() < 0.15 and marker not in ("x", "+", ".")
        color = None
        if pal is not None:
            color = pal[k % len(pal)]
        elif rng.random() < 0.25:
            color = tuple(rng.uniform(0, 0.9, 3))
        label = f"Series {k + 1}" if rng.random() < 0.5 else str(rng.choice(["Revenue", "Women", "Men", "Control", "Model A", "Model B", "Baseline", "Measured", "Predicted", "Total", "Sales", "Temperature", "GDP", "Price", "Signal", "Noise", "Fit", "Theory", "Experiment", "2021", "2022", "North", "South", "East", "West"]))
        kw = dict(color=color, label=label, zorder=2 + k * 0.01)
        where = None
        if kind == "scatter":
            art = ax.scatter(x, y, s=ms ** 2, marker=marker, color=color, label=label, zorder=2 + k * 0.01,
                             facecolors="none" if hollow else None, edgecolors=color if hollow else None,
                             linewidths=float(rng.uniform(0.5, 1.5)) if hollow or marker in ("x", "+") else None,
                             alpha=float(rng.uniform(0.6, 1)) if rng.random() < 0.15 else None)
            if hollow and color is None:
                art.set_edgecolor(f"C{k}")
        elif kind == "area":
            # A filled area whose upper edge is the data, with or without a line drawn along it.
            c = color if color is not None else f"C{k}"
            base = (y.min() * 0.5 if ylog else (0.0 if y.min() > 0 else y.min() - 0.1 * (y.max() - y.min())))
            fill = ax.fill_between(x, y, base, color=c, alpha=float(rng.uniform(0.2, 1.0)), lw=0, zorder=1.8 + k * 0.01)
            if rng.random() < 0.5:
                grid_extra_pre.append(fill)
                (art,) = ax.plot(x, y, lw=lw, color=c, label=label, zorder=2 + k * 0.01)
            else:
                art = fill
                art.set_label(label)
        elif kind == "step":
            where = str(rng.choice(["pre", "post", "mid"]))
            (art,) = ax.step(x, y, where=where, lw=lw, ls=ls, **kw)
        else:
            mk = dict(marker=marker, markersize=ms, markevery=None) if kind == "line+markers" else {}
            if kind == "line+markers" and hollow:
                mk["markerfacecolor"] = "none"
            (art,) = ax.plot(x, y, lw=lw, ls=ls, **kw, **mk)
        art.set_snap(False)
        data_artists.append(art)
        series_meta.append(dict(kind=kind, label=label, x=x, y=y, lw=lw, ls=ls, where=where,
                                marker=marker if kind in ("scatter", "line+markers") else None, ms=ms))

    # --- distractors: reference lines, bands, in-plot text ---
    grid_extra = list(grid_extra_pre)
    text_extra = []
    if rng.random() < 0.15:
        yv = float(np.median(series_meta[0]["y"]))
        grid_extra.append(ax.axhline(yv, color=str(rng.choice(["gray", "k", "r"])), lw=float(rng.uniform(0.5, 1.5)), ls=str(rng.choice(["--", ":", "-"])), zorder=1.5))
    if rng.random() < 0.08:
        xv = float(np.quantile(xbase, rng.uniform(0.2, 0.8)))
        grid_extra.append(ax.axvline(xv, color="gray", lw=1, ls="--", zorder=1.5))
    if rng.random() < 0.1 and series_meta[0]["kind"] != "scatter":
        m = series_meta[0]
        spread = (np.abs(m["y"]).max() + 1e-9) * rng.uniform(0.03, 0.15)
        lo = m["y"] - spread if not ylog else m["y"] / 1.5
        hi = m["y"] + spread if not ylog else m["y"] * 1.5
        grid_extra.append(ax.fill_between(m["x"], lo, hi, alpha=float(rng.uniform(0.1, 0.3)), color=data_artists[0].get_color() if hasattr(data_artists[0], "get_color") else "C0", lw=0, zorder=1.4))
    if rng.random() < 0.2:
        m = series_meta[int(rng.integers(0, n_series))]
        i = int(rng.integers(0, len(m["x"])))
        text_extra.append(ax.annotate(m["label"] if rng.random() < 0.6 else f"{m['y'][i]:.3g}", (m["x"][i], m["y"][i]),
                                      xytext=(rng.uniform(-30, 30), rng.uniform(-30, 30)), textcoords="offset points",
                                      fontsize=float(rng.uniform(7, 12)),
                                      arrowprops=dict(arrowstyle="->", lw=0.8) if rng.random() < 0.4 else None))

    # --- axes ---
    if xlog:
        ax.set_xscale("log")
    if ylog:
        ax.set_yscale("log")
    if rng.random() < 0.35:
        lo, hi = xr
        if xlog:
            ax.set_xlim(lo, hi)
        else:
            ax.set_xlim(lo, hi)
    if not ylog and rng.random() < 0.25:
        allys = np.concatenate([m["y"] for m in series_meta])
        if allys.min() > 0 and rng.random() < 0.5:
            ax.set_ylim(0, allys.max() * rng.uniform(1.02, 1.2))
    if rng.random() < 0.3:
        ax.margins(x=float(rng.uniform(0, 0.03)))

    if date_axis is not None:
        ax.xaxis.set_major_locator(date_axis[0])
    elif not xlog and rng.random() < 0.7:
        ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(3, 11)), steps=[1, 2, 2.5, 5, 10]))
    if not ylog and rng.random() < 0.7:
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=int(rng.integers(3, 11)), steps=[1, 2, 2.5, 5, 10]))
    for axis, is_log, vals in ((ax.xaxis, xlog, xbase), (ax.yaxis, ylog, np.concatenate([m["y"] for m in series_meta]))):
        if axis is ax.xaxis and date_axis is not None:
            axis.set_major_formatter(date_axis[1])
            continue
        if is_log:
            c = rng.choice(["default", "plain", "suffix_log"], p=[0.6, 0.25, 0.15])
            if c == "plain":
                axis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:,.10g}" if v >= 1 else f"{v:g}"))
            elif c == "suffix_log":
                axis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:.0e}".replace("e+0", "e").replace("e-0", "e-")))
            axis.set_minor_formatter(mticker.NullFormatter())
        else:
            span = float(vals.max() - vals.min()) or 1.0
            name, f = _make_formatter(rng, span, float(np.abs(vals).max()))
            if f is not None:
                axis.set_major_formatter(f)
            else:
                if isinstance(axis.get_major_formatter(), mticker.ScalarFormatter):
                    axis.get_major_formatter().set_useOffset(bool(rng.random() < 0.1))
                    if rng.random() < 0.7:
                        axis.get_major_formatter().set_scientific(False)

    if rng.random() < 0.5:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    elif rng.random() < 0.1:
        for s in ax.spines.values():
            s.set_visible(False)
    if rng.random() < 0.08:
        ax.spines["left"].set_visible(False)
    tick_dir = str(rng.choice(["out", "in", "inout"], p=[0.7, 0.2, 0.1]))
    ax.tick_params(direction=tick_dir, length=float(rng.choice([0, 2, 3.5, 5, 7], p=[0.1, 0.2, 0.4, 0.2, 0.1])),
                   width=float(rng.uniform(0.5, 1.5)))
    if rng.random() < 0.08:
        ax.yaxis.tick_right()
    if rng.random() < 0.12:
        ax.tick_params(axis="x", labelrotation=float(rng.choice([30, 45, 90])))
    flags = P.post(preset, ax, rng) if preset != "none" else {"legend": "auto", "direct_labels": False}
    grid = rng.random() if preset == "none" else 1.0
    if grid < 0.35:
        ax.grid(True, which="major", alpha=float(rng.uniform(0.3, 1)), ls=str(rng.choice(["-", "--", ":"])),
                lw=float(rng.uniform(0.4, 1.2)), axis=str(rng.choice(["both", "both", "y", "x"])))
    elif grid < 0.45:
        ax.grid(False)

    if rng.random() < 0.55:
        ax.set_title(str(rng.choice(["Monthly retail sales", "Results", "Figure 3: response vs. dose", "Population growth", "Performance over time", "Temperature anomaly", "Experiment 2", "Microprocessor trend data"])),
                     loc=str(rng.choice(["center", "left"])))
    if rng.random() < 0.6:
        ax.set_xlabel(str(rng.choice(["Time (s)", "Year", "x", "Frequency (Hz)", "Date", "Iteration", "Distance [m]", "Dose (mg)"])))
    if rng.random() < 0.6:
        ax.set_ylabel(str(rng.choice(["Value", "Amplitude", "Sales ($M)", "Percent", "Count", "Loss", "Voltage (V)", "y"])))

    if flags["direct_labels"] or rng.random() < 0.04:
        # Series named by text at the end of each line, in its colour, as news graphics do; often with the
        # first and last values printed too ("12" ... "46"), which must not pass for tick labels.
        values_too = rng.random() < 0.5
        for m, art in zip(series_meta, data_artists):
            c = art.get_color() if isinstance(art, Line2D) else None
            if c is None:
                continue
            fs = float(rng.uniform(8, 12))
            text_extra.append(ax.annotate(m["label"], (m["x"][-1], m["y"][-1]), xytext=(4, 0), textcoords="offset points",
                                          color=c, va="center", fontsize=fs, annotation_clip=False))
            if values_too:
                for j, dx in ((0, -6), (-1, 6)):
                    text_extra.append(ax.annotate(f"{m['y'][j]:.3g}", (m["x"][j], m["y"][j]), xytext=(dx, -12),
                                                  textcoords="offset points", color=c, ha="center", fontsize=fs,
                                                  fontweight="bold", annotation_clip=False))
    legend = None
    if flags["legend"] == "none":
        pass
    elif flags["legend"] in ("below", "outside") and n_series > 1:
        kw = dict(frameon=False, fontsize=float(rng.uniform(7, 11)))
        if flags["legend"] == "below":
            legend = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=min(n_series, 4), **kw)
        else:
            legend = ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), **kw)
    elif n_series > 1 and rng.random() < 0.65 or n_series == 1 and rng.random() < 0.15:
        loc = str(rng.choice(["upper left", "upper right", "lower left", "lower right", "center left", "upper center", "outside"]))
        kw = dict(frameon=bool(rng.random() < 0.7), fontsize=float(rng.uniform(6, 12)))
        if loc == "outside":
            legend = ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), **kw)
        else:
            legend = ax.legend(loc=loc, ncol=int(rng.choice([1, 1, 2])) if n_series > 2 else 1, **kw)

    # Freeze layout, so the per-group re-renders match pixel for pixel.
    try:
        fig.tight_layout(pad=float(rng.uniform(0.2, 1.5)))
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

    # --- groups for the label maps ---
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

    alphas = {}
    groups = [
        (GRID, grid_ids), (AXIS, axis_ids), (LEGEND_SYMBOL, legend_symbol_ids),
        (TICK_LABEL, tick_label_ids), (TEXT, text_ids),
    ]
    for cls, ids in groups:
        alphas[cls] = _render_alpha(fig, canvas, leaves, ids) if ids else np.zeros((H, W), np.uint8)
    series_alpha = [_render_alpha(fig, canvas, leaves, {id(a)}) for a in data_artists]

    thr = 60
    stack = [alphas[GRID], alphas[AXIS]] + series_alpha + [alphas[LEGEND_SYMBOL], alphas[TICK_LABEL], alphas[TEXT]]
    cls_of = [GRID, AXIS] + [DATA] * len(series_alpha) + [LEGEND_SYMBOL, TICK_LABEL, TEXT]
    st = np.stack(stack, 0).astype(np.int16)
    # Later groups are drawn on top: break ties towards them by a tiny bias.
    st = st + np.arange(len(stack), dtype=np.int16)[:, None, None]
    idx = st.argmax(0)
    peak = st.max(0) - idx
    sem = np.where(peak >= thr, np.array(cls_of, np.uint8)[idx], BG).astype(np.uint8)
    inst = np.zeros((H, W), np.uint8)
    if series_alpha:
        sa = np.stack(series_alpha, 0).astype(np.int16) + np.arange(len(series_alpha), dtype=np.int16)[:, None, None]
        si = sa.argmax(0)
        inst = np.where(sem == DATA, si + 1, 0).astype(np.uint8)

    # --- geometry ---
    bb = ax.get_window_extent(renderer=canvas.get_renderer())
    plot_area = [bb.x0 - 0.5, H - bb.y1 - 0.5, bb.x1 - 0.5, H - bb.y0 - 0.5]
    renderer = canvas.get_renderer()
    xlim, ylim = ax.get_xlim(), ax.get_ylim()

    def ticks_for(axis_name: str):
        axis = ax.xaxis if axis_name == "x" else ax.yaxis
        lim = xlim if axis_name == "x" else ylim
        out = []
        majors = axis.get_major_ticks()
        locs = axis.get_majorticklocs()
        for tick, v in zip(majors, locs):
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

    xticks = ticks_for("x")
    yticks = ticks_for("y")

    out_series = []
    for m, art in zip(series_meta, data_artists):
        x, y = m["x"], m["y"]
        if m["kind"] == "step":
            px_x, px_y = _step_path(x, y, m["where"])
        else:
            px_x, px_y = x, y
        path = _to_px(ax, H, px_x, px_y) if m["kind"] != "scatter" else np.zeros((0, 2))
        markers = _to_px(ax, H, x, y) if m["kind"] in ("scatter", "line+markers") else np.zeros((0, 2))
        color = art.get_color() if isinstance(art, Line2D) else art.get_facecolor()
        if isinstance(color, np.ndarray) and color.size >= 4 and m["kind"] == "area":
            color = np.asarray(color, float).reshape(-1)[:3]
        if not isinstance(color, str):
            c = np.asarray(color, float).reshape(-1)
            if c.size >= 3 and not (c.size >= 4 and c[3] == 0):
                color = matplotlib.colors.to_hex(c[:4] if c.size >= 4 else c[:3])
            else:
                ec = np.asarray(art.get_edgecolor(), float).reshape(-1)
                color = matplotlib.colors.to_hex(ec[:4]) if ec.size >= 3 else "#000000"
        else:
            color = matplotlib.colors.to_hex(color)
        lw_px = m["lw"] * fig.dpi / 72.0 if m["kind"] != "area" or isinstance(art, Line2D) else 1.0
        out_series.append(dict(kind=m["kind"], label=m["label"], color=color, linestyle=m["ls"],
                               linewidth_px=lw_px, marker=m["marker"], markersize_px=m["ms"] * fig.dpi / 72.0,
                               x=x.tolist(), y=y.tolist(), path_px=path.round(3).tolist(), markers_px=markers.round(3).tolist()))

    leg_bbox = None
    if legend is not None:
        e = legend.get_window_extent(renderer)
        leg_bbox = [e.x0 - 0.5, H - e.y1 - 0.5, e.x1 - 0.5, H - e.y0 - 0.5]

    meta = dict(
        seed=seed, generator="matplotlib", style=style, preset=preset, font=rc["font.family"], width=W, height=H,
        plot_area=plot_area, xscale="log" if xlog else "linear", xdate=date_axis[2] if date_axis else None, yscale="log" if ylog else "linear",
        xlim=list(map(float, xlim)), ylim=list(map(float, ylim)),
        xticks=xticks, yticks=yticks, series=out_series, legend_bbox=leg_bbox,
        offset_text=[_clean_label(o.get_text()) for o in offset_texts],
    )
    plt.close(fig)
    return Rendered(image=image, sem=sem, inst=inst, meta=meta)
