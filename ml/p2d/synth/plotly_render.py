"""Random Plotly charts with exact ground truth: a second renderer.

A model that has only ever seen matplotlib's rasteriser and fonts learns
matplotlib. Plotly draws through Chrome (Skia antialiasing, browser fonts,
its own house style), and it is a common look in screenshots.

The geometry is exact by construction: margins and axis ranges are fixed, so
the plot area is known in pixels and a value maps to a pixel linearly (in log10
on a log axis), and ticks are given explicitly, values and text alike. Label
maps come from re-rendering with every group but one made transparent, which
cannot move the layout, as hiding things could.

Same output as `mpl_render.generate`: a `Rendered` with image, sem, inst, meta.
"""

from __future__ import annotations

import io
import math

import cv2
import numpy as np
import plotly.graph_objects as go
from PIL import Image

from . import series as S
from .mpl_render import AXIS, BG, DATA, GRID, LEGEND_SYMBOL, TEXT, TICK_LABEL, Rendered

TRANSPARENT = "rgba(0,0,0,0)"
FONTS = ["Arial", "Liberation Sans", "DejaVu Sans", "Open Sans", "Lato", "Ubuntu", "Helvetica", "Times New Roman",
         "Liberation Serif", "Courier New"]
PALETTES = [
    ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3", "#FF6692", "#B6E880"],
    ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2", "#7F7F7F"],
    ["#4C78A8", "#F58518", "#E45756", "#72B7B2", "#54A24B", "#EECA3B", "#B279A2", "#FF9DA6"],
    ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"],
]
SYMBOLS = ["circle", "square", "diamond", "triangle-up", "triangle-down", "cross", "x", "star", "circle-open",
           "square-open", "diamond-open", "triangle-up-open", "hexagon", "pentagon"]
TEMPLATES = ["plotly", "plotly_white", "simple_white", "ggplot2", "seaborn", "presentation", "plotly_dark", "none"]

_server = False


def _render(fig: go.Figure, w: int, h: int) -> np.ndarray:
    import kaleido

    global _server
    if not _server:
        kaleido.start_sync_server(silence_warnings=True)
        _server = True
    png = kaleido.calc_fig_sync(fig, opts=dict(format="png", width=w, height=h, scale=1))
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


def _nice_ticks(lo: float, hi: float, n: int) -> np.ndarray:
    import matplotlib.ticker as mt

    v = mt.MaxNLocator(nbins=n, steps=[1, 2, 2.5, 5, 10]).tick_values(lo, hi)
    return v[(v >= lo - 1e-9 * abs(hi - lo)) & (v <= hi + 1e-9 * abs(hi - lo))]


def _fmt(vals: np.ndarray, style: str) -> list[str]:
    from .mpl_render import StyledFormatter

    if style == "default":
        style = "plain"
    f = StyledFormatter(style if style in ("plain", "thousands", "pct", "dollar", "sci") else "plain")
    return f.format_ticks(list(vals))


def generate(seed: int) -> Rendered:
    rng = np.random.default_rng(seed)
    W = int(rng.uniform(380, 1500))
    H = int(W * rng.uniform(0.4, 0.85))
    H = max(H, 240)
    template = str(rng.choice(TEMPLATES))
    dark = template == "plotly_dark"
    font = str(rng.choice(FONTS))
    fsize = float(rng.uniform(9, 16))
    m = dict(l=int(rng.uniform(45, 110)), r=int(rng.uniform(10, 150)), t=int(rng.uniform(20, 80)), b=int(rng.uniform(40, 90)))
    x0, y0, x1, y1 = m["l"], m["t"], W - m["r"], H - m["b"]

    xlog = rng.random() < 0.06
    ylog = rng.random() < 0.14
    n_series = int(rng.choice([1, 1, 2, 2, 3, 3, 4, 5]))
    plot_kind = str(rng.choice(["line", "scatter", "mixed"], p=[0.68, 0.17, 0.15]))
    n_line = int(rng.choice([rng.integers(4, 25), rng.integers(25, 120), rng.integers(120, 600), rng.integers(600, 2000)],
                            p=[0.3, 0.3, 0.25, 0.15]))
    _, xbase = S.x_values(rng, n_line, xlog)
    yc, ys = S.y_scale(rng, ylog)
    pal = PALETTES[int(rng.integers(len(PALETTES)))]

    sers = []
    for k in range(n_series):
        kind = {"line": "line", "scatter": "scatter"}.get(plot_kind) or str(rng.choice(["line", "scatter", "line+markers"]))
        if kind == "line" and rng.random() < 0.15 and n_line <= 80:
            kind = "line+markers"
        if kind == "line" and rng.random() < 0.07:
            kind = "area"
        t = (np.log10(xbase) - np.log10(xbase[0])) / (np.log10(xbase[-1]) - np.log10(xbase[0])) if xlog else \
            (xbase - xbase[0]) / (xbase[-1] - xbase[0] + 1e-300)
        if kind == "scatter":
            n = int(rng.integers(5, 150))
            ti = np.sort(rng.uniform(0, 1, n))
            x = 10 ** (np.log10(xbase[0]) + ti * (np.log10(xbase[-1]) - np.log10(xbase[0]))) if xlog else xbase[0] + ti * (xbase[-1] - xbase[0])
            cur = S.shape(rng, ti)[1] + rng.normal(0, rng.uniform(0, 0.25), n)
        else:
            x = xbase
            cur = S.shape(rng, t)[1] * rng.uniform(0.4, 1.2) + rng.uniform(-0.5, 0.5)
        if ylog:
            y = 10 ** (rng.uniform(-2, 3) + rng.uniform(1, 5) * (cur - cur.min()) / (np.ptp(cur) + 1e-9))
        else:
            y = yc + ys * cur
        sers.append(dict(kind=kind, x=x, y=y, color=pal[k % len(pal)], lw=float(rng.uniform(1, 4)),
                         dash=str(rng.choice(["solid", "solid", "solid", "solid", "dash", "dot", "dashdot"])),
                         symbol=str(rng.choice(SYMBOLS)), ms=float(rng.uniform(4, 12)), label=f"Series {k + 1}"))

    # Axis ranges, with a little padding, and explicit ticks.
    def axis_range(vals, log):
        lo, hi = float(np.min(vals)), float(np.max(vals))
        if log:
            lo, hi = math.log10(lo), math.log10(hi)
        pad = (hi - lo) * float(rng.choice([0, 0.02, 0.05]))
        return lo - pad, hi + pad

    allx = np.concatenate([s["x"] for s in sers])
    ally = np.concatenate([s["y"] for s in sers])
    xr = axis_range(allx, xlog)
    yr = axis_range(ally, ylog)
    if xlog:
        xt = 10.0 ** np.arange(math.ceil(xr[0]), math.floor(xr[1]) + 1)
    else:
        xt = _nice_ticks(xr[0], xr[1], int(rng.integers(4, 10)))
    if ylog:
        yt = 10.0 ** np.arange(math.ceil(yr[0]), math.floor(yr[1]) + 1)
    else:
        yt = _nice_ticks(yr[0], yr[1], int(rng.integers(4, 9)))
    xstyle = str(rng.choice(["plain", "thousands", "default"]))
    ystyle = str(rng.choice(["plain", "thousands", "pct", "dollar", "default"]))
    xtext = [f"{v:g}" for v in xt] if xlog else _fmt(xt, xstyle)
    ytext = ([f"{v:g}" if rng.random() < 2 else "" for v in yt]) if ylog else _fmt(yt, ystyle)

    grid_on = rng.random() < 0.75
    line_on = rng.random() < 0.6
    ticks_mode = str(rng.choice(["outside", "inside", ""], p=[0.45, 0.15, 0.4]))
    show_legend = n_series > 1 and rng.random() < 0.7
    title = str(rng.choice(["", "Monthly sales", "Results by year", "Signal", "Performance", "Growth"])) if rng.random() < 0.6 else ""
    xtitle = str(rng.choice(["", "Year", "Time (s)", "x", "Date"]))
    ytitle = str(rng.choice(["", "Value", "Count", "Revenue ($)", "y"]))

    def build(mode: str, only: int | None = None) -> go.Figure:
        """mode: full | series | grid | axis | ticklabels | text | legend"""
        fig = go.Figure()
        for k, s in enumerate(sers):
            show = mode == "full" or (mode == "series" and k == only) or mode == "legend"
            col = s["color"] if show else TRANSPARENT
            xs, ys_ = (s["x"], s["y"]) if mode != "legend" else ([None], [None])
            if s["kind"] == "scatter":
                tr = go.Scatter(x=xs, y=ys_, mode="markers", name=s["label"],
                                marker=dict(color=col, size=s["ms"], symbol=s["symbol"],
                                            line=dict(width=1 if "open" in s["symbol"] else 0, color=col)))
            else:
                md = "lines+markers" if s["kind"] == "line+markers" else "lines"
                tr = go.Scatter(x=xs, y=ys_, mode=md, name=s["label"], line=dict(color=col, width=s["lw"], dash=s["dash"]),
                                marker=dict(color=col, size=s["ms"], symbol=s["symbol"]),
                                fill="tozeroy" if s["kind"] == "area" else None,
                                fillcolor=(col if col == TRANSPARENT else _rgba(s["color"], 0.3)) if s["kind"] == "area" else None)
            fig.add_trace(tr)
        tpl = template
        txt = "#ccc" if dark else "#333"
        def c(group, colour):
            return colour if mode in ("full", group) else TRANSPARENT
        axis_common = dict(automargin=False, showgrid=grid_on, zeroline=False)
        fig.update_layout(
            template=tpl, width=W, height=H, margin=dict(**m, pad=0, autoexpand=False),
            font=dict(family=font, size=fsize, color=c("text", txt)),
            paper_bgcolor=None if mode == "full" else TRANSPARENT,
            plot_bgcolor=None if mode == "full" else TRANSPARENT,
            showlegend=show_legend and mode in ("full", "legend", "text"),
            legend=dict(font=dict(color=c("text", txt)), bgcolor=TRANSPARENT if mode != "full" else None),
            title=dict(text=title, font=dict(color=c("text", txt))),
        )
        for ax_name, rng_, tv, tt, log, ttl in (("xaxis", xr, xt, xtext, xlog, xtitle), ("yaxis", yr, yt, ytext, ylog, ytitle)):
            fig.update_layout(**{ax_name: dict(
                **axis_common, type="log" if log else "linear", range=list(rng_), tickmode="array", tickvals=list(tv),
                ticktext=list(tt), ticks=ticks_mode, ticklen=int(rng_ticklen), showline=line_on,
                linecolor=c("axis", "#444"), tickcolor=c("axis", "#444"),
                gridcolor=c("grid", "#888" if dark else ("#E5ECF6" if template == "plotly" else "#DDDDDD")),
                tickfont=dict(color=c("ticklabels", txt), family=font, size=fsize),
                title=dict(text=ttl, font=dict(color=c("text", txt))),
            )})
        return fig

    rng_ticklen = int(rng.uniform(3, 8))
    full = _render(build("full"), W, H)
    image = full[..., :3].copy()
    alpha = {g: _render(build(g), W, H)[..., 3] for g in ("grid", "axis", "ticklabels", "text")}
    alpha["legend"] = _render(build("legend"), W, H)[..., 3] if show_legend else np.zeros((H, W), np.uint8)
    series_alpha = [_render(build("series", k), W, H)[..., 3] for k in range(n_series)]

    thr = 60
    stack = [alpha["grid"], alpha["axis"]] + series_alpha + [alpha["legend"], alpha["ticklabels"], alpha["text"]]
    cls_of = [GRID, AXIS] + [DATA] * n_series + [LEGEND_SYMBOL, TICK_LABEL, TEXT]
    st = np.stack(stack, 0).astype(np.int16) + np.arange(len(stack), dtype=np.int16)[:, None, None]
    idx = st.argmax(0)
    peak = st.max(0) - idx
    sem = np.where(peak >= thr, np.array(cls_of, np.uint8)[idx], BG).astype(np.uint8)
    sa = np.stack(series_alpha, 0).astype(np.int16) + np.arange(n_series, dtype=np.int16)[:, None, None]
    inst = np.where(sem == DATA, sa.argmax(0) + 1, 0).astype(np.uint8)

    # Exact mapping, pixel centres at integers.
    def px_x(v):
        t = np.log10(v) if xlog else np.asarray(v, float)
        return x0 + (t - xr[0]) / (xr[1] - xr[0]) * (x1 - x0) - 0.5

    def px_y(v):
        t = np.log10(v) if ylog else np.asarray(v, float)
        return y0 + (yr[1] - t) / (yr[1] - yr[0]) * (y1 - y0) - 0.5

    plot_area = [x0 - 0.5, y0 - 0.5, x1 - 0.5, y1 - 0.5]
    lab = (alpha["ticklabels"] > 40).astype(np.uint8)
    n_cc, cc, stats, cent = cv2.connectedComponentsWithStats(cv2.dilate(lab, np.ones((3, 7), np.uint8)), 8)

    def boxes_for(positions, axis):
        """Tick-label boxes from the label pass: the components nearest each tick along the axis."""
        out = []
        for p in positions:
            best = None
            for i in range(1, n_cc):
                cx, cy = cent[i]
                if axis == "x":
                    if cy < y1 or abs(cx - p) > stats[i, 2] / 2 + 3:
                        continue
                    d = abs(cx - p)
                else:
                    if cx > x0 or abs(cy - p) > stats[i, 3] / 2 + 3:
                        continue
                    d = abs(cy - p)
                if best is None or d < best[0]:
                    best = (d, i)
            if best is None:
                out.append(None)
                continue
            i = best[1]
            ys_, xs_ = np.nonzero((cc == i) & (lab > 0))
            out.append([float(xs_.min()), float(ys_.min()), float(xs_.max()), float(ys_.max())] if len(xs_) else None)
        return out

    def tick_list(vals, texts, axis):
        pos = px_x(vals) if axis == "x" else px_y(vals)
        out = []
        for v, t, p, b in zip(vals, texts, pos, boxes_for(pos, axis)):
            if not t or b is None:
                continue
            anchor = [float(p), plot_area[3]] if axis == "x" else [plot_area[0], float(p)]
            out.append(dict(value=float(v), pos=float(p), anchor=anchor, side="low", text=t.replace("−", "-"),
                            raw=t, bbox=b))
        return out

    out_series = []
    for s in sers:
        path = np.column_stack([px_x(s["x"]), px_y(s["y"])]) if s["kind"] != "scatter" else np.zeros((0, 2))
        mk = np.column_stack([px_x(s["x"]), px_y(s["y"])]) if s["kind"] in ("scatter", "line+markers") else np.zeros((0, 2))
        out_series.append(dict(kind=s["kind"], label=s["label"], color=s["color"], linestyle=s["dash"],
                               linewidth_px=s["lw"] if s["kind"] != "scatter" else 1.0, marker=s["symbol"],
                               markersize_px=s["ms"], x=s["x"].tolist(), y=s["y"].tolist(),
                               path_px=path.round(3).tolist(), markers_px=mk.round(3).tolist()))
    meta = dict(seed=seed, generator="plotly", style=template, preset="plotly-" + template, font=font, width=W, height=H,
                plot_area=plot_area, xscale="log" if xlog else "linear", yscale="log" if ylog else "linear",
                xlim=[10 ** v for v in xr] if xlog else list(xr), ylim=[10 ** v for v in yr] if ylog else list(yr),
                xticks=tick_list(xt, xtext, "x"), yticks=tick_list(yt, ytext, "y"), series=out_series, legend_bbox=None,
                offset_text=["", ""])
    return Rendered(image=image, sem=sem, inst=inst, meta=meta)


def _rgba(hex_colour: str, a: float) -> str:
    h = hex_colour.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"
