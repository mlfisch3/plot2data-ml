"""Random Chart.js charts with exact ground truth: a third renderer (team t5).

Chart.js draws on an HTML canvas in Chrome, with the browser's text rasteriser,
its own tick-label placement (the em box is centred on the tick, where
matplotlib centres the digits), pixel-aligned gridlines, minor gridlines on log
axes, mitred joins, and a house style that half the dashboards on the web use.
It is the renderer of `../corpus/`, which no network had trained on.

`chartjs_render.mjs` keeps one headless Chrome and renders a spec once per
group with every other group transparent, so each pass's alpha is one group's
ink coverage; the layout cannot move because only colours change. The exact
geometry (chart area, ticks with value, text and pixel, every data point in
pixels) is read from Chart.js's own scales. Same output as `mpl_render.generate`.

    python -m p2d.synth.chartjs_render --out out/t5/cjs-check --start 15100000 --count 5   # renders with truth overlays
"""

from __future__ import annotations

import base64
import json
import math
import os
import subprocess
from typing import Any

import cv2
import numpy as np

from . import series as S
from .mpl_render import AXIS, BG, DATA, GRID, LEGEND_SYMBOL, TEXT, TICK_LABEL, Rendered, StyledFormatter, _step_path

HERE = os.path.dirname(os.path.abspath(__file__))
NODE_SCRIPT = os.path.join(HERE, "chartjs_render.mjs")

FONTS = ["DejaVu Sans", "DejaVu Sans", "Liberation Sans", "Liberation Sans", "Lato", "FreeSans", "Nimbus Sans",
         "TeX Gyre Heros", "Liberation Serif", "DejaVu Serif", "Liberation Mono", "Ubuntu", "Open Sans", "Roboto",
         "Arial", "Helvetica", "system-ui", "sans-serif"]
PALETTES = [
    ["#36A2EB", "#FF6384", "#4BC0C0", "#FF9F40", "#9966FF", "#FFCD56", "#C9CBCF"],  # Chart.js defaults
    ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442"],  # Okabe-Ito, the corpus palette
    ["#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2", "#7F7F7F"],
    ["#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5", "#70AD47"],
    ["#7cb5ec", "#434348", "#90ed7d", "#f7a35c", "#8085e9", "#f15c80", "#e4d354"],
    ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3"],
    ["#000000", "#333333", "#666666", "#999999"],
    ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00"],
]
POINT_STYLES = ["circle", "circle", "circle", "rect", "rectRot", "triangle", "cross", "crossRot", "star", "rectRounded"]

_proc: subprocess.Popen | None = None


def _node() -> subprocess.Popen:
    global _proc
    if _proc is None or _proc.poll() is not None:
        _proc = subprocess.Popen(["node", NODE_SCRIPT], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True, bufsize=1, cwd=HERE)
    return _proc


def render_spec(spec: dict) -> dict:
    p = _node()
    assert p.stdin is not None and p.stdout is not None
    p.stdin.write(json.dumps(spec) + "\n")
    p.stdin.flush()
    line = p.stdout.readline()
    if not line:
        raise RuntimeError("chartjs renderer died")
    r = json.loads(line)
    if not r.get("ok"):
        raise RuntimeError("chartjs: " + str(r.get("error"))[:400])
    return r


def _png(data_url: str) -> np.ndarray:
    raw = base64.b64decode(data_url.split(",", 1)[1])
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)  # BGRA


def _hex(c: str) -> str:
    return c


def _rgba(hex_colour: str, a: float) -> str:
    h = hex_colour.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def _nice_ticks(lo: float, hi: float, n: int) -> np.ndarray:
    import matplotlib.ticker as mt

    v = mt.MaxNLocator(nbins=n, steps=[1, 2, 2.5, 5, 10]).tick_values(lo, hi)
    return v[(v >= lo - 1e-9 * abs(hi - lo)) & (v <= hi + 1e-9 * abs(hi - lo))]


def _labels(rng: np.random.Generator, vals: np.ndarray, log: bool, axis: str) -> list[tuple[float, str]]:
    """(value, text) for the labelled ticks of an axis."""
    if log:
        decades = [v for v in vals if abs(math.log10(v) - round(math.log10(v))) < 1e-9]
        style = str(rng.choice(["plain", "plain", "sci", "comma"]))
        out = []
        for v in decades:
            e = round(math.log10(v))
            if style == "sci" and (e > 4 or e < -3):
                out.append((v, f"1e{e}"))
            elif style == "comma":
                out.append((v, f"{v:,.0f}" if v >= 1 else f"{v:g}"))
            else:
                out.append((v, f"{v:,.0f}" if v >= 1000 and rng.random() < 0.5 else f"{v:g}"))
        return out
    style = str(rng.choice(["chartjs", "plain", "thousands", "pct", "dollar", "suffix"],
                           p=[0.35, 0.2, 0.15, 0.1, 0.1, 0.1] if axis == "y" else [0.5, 0.3, 0.2, 0, 0, 0]))
    minus = "−" if rng.random() < 0.2 else "-"
    if style == "chartjs":
        # Chart.js's own formatting: locale separators and as many decimals as the step needs.
        step = float(np.min(np.diff(vals))) if len(vals) > 1 else 1.0
        d = max(0, min(6, -int(math.floor(math.log10(step))))) if step < 1 else 0
        return [(float(v), f"{v:,.{d}f}".replace("-", minus)) for v in vals]
    if style == "suffix":
        m = float(np.abs(vals).max())
        if m >= 1e6:
            f = StyledFormatter("plain", 1e6, "M", minus)
        elif m >= 1e4:
            f = StyledFormatter("plain", 1e3, str(rng.choice(["k", "K"])), minus)
        else:
            f = StyledFormatter("plain", minus=minus)
    else:
        f = StyledFormatter(style, minus=minus, extra=1 if rng.random() < 0.1 else 0)
    return list(zip([float(v) for v in vals], f.format_ticks(list(vals))))


def make_spec(seed: int) -> tuple[dict, dict]:
    """A random chart spec for the renderer, plus what the truth needs that the spec does not carry."""
    rng = np.random.default_rng(seed)
    dpr = 2 if rng.random() < 0.2 else 1
    W = int(rng.uniform(380, 1000 if dpr == 2 else 1500))
    H = max(240, int(W * rng.uniform(0.4, 0.85)))
    dark = rng.random() < 0.15
    if dark:
        paper = str(rng.choice(["#1e1e1e", "#15181c", "#202124", "#23272e", "#0d1117"]))
        fg = str(rng.choice(["#e8eaed", "#cccccc", "#dddddd", "#c9d1d9"]))
        grid_colour = str(rng.choice(["rgba(255,255,255,0.18)", "rgba(255,255,255,0.1)", "#333c45", "#3a3a3a"]))
    else:
        paper = "#ffffff" if rng.random() < 0.8 else "#%02x%02x%02x" % tuple(int(v) for v in rng.uniform(238, 255, 3))
        fg = str(rng.choice(["#202124", "#333333", "#000000", "#444444"]))
        grid_colour = str(rng.choice(["rgba(0,0,0,0.1)", "rgba(0,0,0,0.12)", "#e5e5e5", "#dddddd", "#cccccc", "#eeeeee"]))
    tick_colour = fg if rng.random() < 0.5 else str(rng.choice(["#666666", "#777777", "#555555", "#999999"] if not dark else ["#aaaaaa", "#bbbbbb"]))
    font = str(rng.choice(FONTS))
    fsize = int(rng.uniform(10, 16))
    xlog = rng.random() < 0.06
    ylog = rng.random() < 0.15
    n_series = int(rng.choice([1, 1, 1, 2, 2, 3, 3, 4, 5]))
    plot_kind = str(rng.choice(["line", "scatter", "mixed"], p=[0.68, 0.17, 0.15]))
    n_line = int(rng.choice([rng.integers(4, 25), rng.integers(25, 120), rng.integers(120, 600), rng.integers(600, 2000)],
                            p=[0.3, 0.3, 0.25, 0.15]))
    _, xbase = S.x_values(rng, n_line, xlog)
    yc, ys = S.y_scale(rng, ylog)
    pal = PALETTES[int(rng.integers(len(PALETTES)))]
    if dark and pal[0] == "#000000":
        pal = PALETTES[0]
    sers = []
    for k in range(n_series):
        kind = {"line": "line", "scatter": "scatter"}.get(plot_kind) or str(rng.choice(["line", "scatter", "line+markers"]))
        if kind == "line" and rng.random() < 0.12 and n_line <= 80:
            kind = "line+markers"
        if kind == "line" and rng.random() < 0.07:
            kind = "area"
        stepped: Any = False
        if kind == "line" and rng.random() < 0.06:
            stepped = str(rng.choice(["before", "after", "middle"]))
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
        colour = pal[k % len(pal)]
        sers.append(dict(
            kind=kind, label=str(rng.choice([f"Series {k + 1}", "Revenue", "Users", "Sales", "Temperature", "Model A", "Model B", "Actual", "Forecast", "North", "South"])),
            x=[float(v) for v in x], y=[float(v) for v in y], color=colour, fillColor=_rgba(colour, float(rng.uniform(0.15, 0.5))),
            width=float(rng.choice([1, 1.5, 2, 2, 2.5, 3, 4])),
            dash=[] if rng.random() < 0.8 else [int(v) for v in rng.choice([[6, 4], [2, 2], [8, 4, 2, 4], [10, 6], [4, 4]])],
            join=str(rng.choice(["miter", "miter", "round", "bevel"])), cap=str(rng.choice(["butt", "butt", "round"])),
            pointRadius=float(rng.uniform(2.5, 6)), pointStyle=str(rng.choice(POINT_STYLES)),
            hollow=bool(rng.random() < 0.15), pointBorderWidth=float(rng.uniform(1, 2)), stepped=stepped,
            clip=0 if rng.random() < 0.9 else False,
        ))

    def axis_range(vals, log):
        lo, hi = float(np.min(vals)), float(np.max(vals))
        if log:
            lo, hi = math.log10(lo), math.log10(hi)
        pad = (hi - lo) * float(rng.choice([0, 0, 0.02, 0.05, 0.1]))
        lo, hi = lo - pad, hi + pad
        if rng.random() < 0.5 and not log:
            # Snap the range to nice ticks, as Chart.js does by default.
            t = _nice_ticks(lo, hi, 6)
            if len(t) >= 2:
                step = t[1] - t[0]
                lo, hi = math.floor(lo / step) * step, math.ceil(hi / step) * step
        return lo, hi

    allx = np.concatenate([s["x"] for s in sers])
    ally = np.concatenate([s["y"] for s in sers])
    xr, yr = axis_range(allx, xlog), axis_range(ally, ylog)
    if xlog:
        xt = 10.0 ** np.arange(math.ceil(xr[0] - 1e-9), math.floor(xr[1] + 1e-9) + 1)
    else:
        xt = _nice_ticks(xr[0], xr[1], int(rng.integers(4, 11)))
    if ylog:
        yt = 10.0 ** np.arange(math.ceil(yr[0] - 1e-9), math.floor(yr[1] + 1e-9) + 1)
    else:
        yt = _nice_ticks(yr[0], yr[1], int(rng.integers(4, 10)))
    xlab, ylab = _labels(rng, xt, xlog, "x"), _labels(rng, yt, ylog, "y")
    grid_mode = str(rng.choice(["both", "both", "y", "none"]))
    border_on = rng.random() < 0.6
    border_colour = fg if rng.random() < 0.5 else (grid_colour if rng.random() < 0.5 else str(rng.choice(["#666666", "#999999", "#bbbbbb"])))
    border_w = 1 if rng.random() < 0.7 else 2
    tick_marks = rng.random() < 0.5
    ticklen = int(rng.uniform(4, 10))

    def axis(name, log, rng_, labels):
        return dict(
            type="logarithmic" if log else "linear", min=10 ** rng_[0] if log else rng_[0], max=10 ** rng_[1] if log else rng_[1],
            position=("left" if rng.random() < 0.92 else "right") if name == "y" else ("bottom" if rng.random() < 0.95 else "top"),
            tickValues=[float(v) for v in (xt if name == "x" else yt)],
            labels=[dict(value=float(v), label=t) for v, t in labels],
            decadeTicksOnly=bool(rng.random() < 0.5),
            grid=grid_mode == "both" or (grid_mode == "y" and name == "y"), gridColor=grid_colour,
            gridWidth=float(rng.choice([1, 1, 1, 0.5, 1.5])), gridZ=int(rng.choice([0, 0, -1])),
            tickMarks=tick_marks, tickLength=ticklen, border=border_on, borderColor=border_colour, borderWidth=border_w,
            tickFontColor=tick_colour, tickFontSize=fsize, tickPadding=int(rng.uniform(3, 9)),
            maxRotation=0 if (name == "y" or rng.random() < 0.85) else 45, minRotation=0,
            align="center", crossAlign="near",
            title=(str(rng.choice(["Year", "Time (s)", "x", "Date", "Month"])) if name == "x" else str(rng.choice(["Value", "Count", "Revenue ($)", "Percent", "y"]))) if rng.random() < 0.35 else "",
            titleFontSize=fsize,
        )

    legend = None
    p_leg = 0.3 if n_series == 1 else 0.75
    if rng.random() < p_leg:
        legend = dict(position=str(rng.choice(["top", "top", "top", "bottom", "right"])), align=str(rng.choice(["center", "center", "start", "end"])),
                      boxWidth=int(rng.choice([40, 40, 20, 12])), boxHeight=int(rng.choice([12, 12, 2, 6])),
                      usePointStyle=bool(rng.random() < 0.3), fontSize=int(rng.uniform(10, 14)))
    spec = dict(
        width=W, height=H, dpr=dpr, font=dict(family=font, size=fsize, color=fg), paper=paper,
        plotBg=None if rng.random() < 0.85 or dark else "#%02x%02x%02x" % tuple(int(v) for v in rng.uniform(240, 252, 3)),
        padding=dict(top=int(rng.uniform(0, 30)), right=int(rng.uniform(0, 40)), bottom=int(rng.uniform(0, 20)), left=int(rng.uniform(0, 20))),
        title=str(rng.choice(["Monthly sales", "Results by year", "Signal", "Performance", "Growth", "Figure 2", "Temperature anomaly"])) if rng.random() < 0.45 else "",
        titleAlign=str(rng.choice(["center", "start"])), titleFontSize=int(fsize * rng.uniform(1.1, 1.5)), titleWeight=str(rng.choice(["bold", "normal"])),
        legend=legend, x=axis("x", xlog, xr, xlab), y=axis("y", ylog, yr, ylab), datasets=sers,
    )
    extra = dict(xlog=xlog, ylog=ylog, dark=dark, font=font, xr=xr, yr=yr)
    return spec, extra


def generate(seed: int) -> Rendered:
    spec, extra = make_spec(seed)
    r = render_spec(spec)
    dpr = spec["dpr"]
    passes = {k: _png(v) for k, v in r["passes"].items()}
    full = passes["full"]
    image = np.ascontiguousarray(full[..., :3][..., ::-1])  # BGRA -> RGB
    H, W = image.shape[:2]
    n_series = len(spec["datasets"])
    alpha = {k: v[..., 3] for k, v in passes.items()}
    series_alpha = [alpha[f"series_{k}"] for k in range(n_series)]
    thr = 60
    stack = [alpha["grid"], alpha["axis"]] + series_alpha + [alpha["legend"], alpha["ticklabels"], alpha["text"]]
    cls_of = [GRID, AXIS] + [DATA] * n_series + [LEGEND_SYMBOL, TICK_LABEL, TEXT]
    st = np.stack(stack, 0).astype(np.int16) + np.arange(len(stack), dtype=np.int16)[:, None, None]
    idx = st.argmax(0)
    peak = st.max(0) - idx
    sem = np.where(peak >= thr, np.array(cls_of, np.uint8)[idx], BG).astype(np.uint8)
    sa = np.stack(series_alpha, 0).astype(np.int16) + np.arange(n_series, dtype=np.int16)[:, None, None]
    inst = np.where(sem == DATA, sa.argmax(0) + 1, 0).astype(np.uint8)

    g = r["geom"]
    f = lambda v: float(v) * dpr - 0.5  # noqa: E731  CSS edge/position -> device pixel-centre coordinate
    a = g["chartArea"]
    plot_area = [f(a["left"]), f(a["top"]), f(a["right"]), f(a["bottom"])]
    lab = (alpha["ticklabels"] > 40).astype(np.uint8)
    n_cc, cc, stats, cent = cv2.connectedComponentsWithStats(cv2.dilate(lab, np.ones((3, 7), np.uint8)), 8)

    def box_for(p: float, axis: str, side: str):
        best = None
        for i in range(1, n_cc):
            cx, cy = cent[i]
            if axis == "x":
                if (side == "bottom" and cy < plot_area[3]) or (side == "top" and cy > plot_area[1]) or abs(cx - p) > stats[i, 2] / 2 + 3:
                    continue
                d = abs(cx - p)
            else:
                if (side == "left" and cx > plot_area[0]) or (side == "right" and cx < plot_area[2]) or abs(cy - p) > stats[i, 3] / 2 + 3:
                    continue
                d = abs(cy - p)
            if best is None or d < best[0]:
                best = (d, i)
        if best is None:
            return None
        ys_, xs_ = np.nonzero((cc == best[1]) & (lab > 0))
        return [float(xs_.min()), float(ys_.min()), float(xs_.max()), float(ys_.max())] if len(xs_) else None

    def ticks(axis: str):
        side = spec[axis]["position"]
        out = []
        for t in g[axis]["ticks"]:
            if not t["label"]:
                continue
            p = f(t["px"])
            b = box_for(p, axis, side)
            if b is None:
                continue
            if axis == "x":
                anchor = [p, plot_area[3] if side == "bottom" else plot_area[1]]
            else:
                anchor = [plot_area[0] if side == "left" else plot_area[2], p]
            out.append(dict(value=float(t["value"]), pos=p, anchor=anchor, side="low" if side in ("bottom", "left") else "high",
                            text=t["label"].replace("−", "-"), raw=t["label"], bbox=b))
        return out

    out_series = []
    for s, gd in zip(spec["datasets"], g["datasets"]):
        px = np.array([f(v) for v in gd["px"]])
        py = np.array([f(v) for v in gd["py"]])
        if s["kind"] == "scatter":
            path = np.zeros((0, 2))
        elif s["stepped"]:
            sx, sy = _step_path(px, py, {"before": "pre", "after": "post", "middle": "mid"}[s["stepped"]])
            path = np.column_stack([sx, sy])
        else:
            path = np.column_stack([px, py])
        mk = np.column_stack([px, py]) if s["kind"] in ("scatter", "line+markers") else np.zeros((0, 2))
        kind = "step" if s["stepped"] else s["kind"]
        out_series.append(dict(kind=kind, label=s["label"], color=s["color"], linestyle="--" if s["dash"] else "-",
                               linewidth_px=(s["width"] if s["kind"] != "scatter" else 1.0) * dpr, marker=s["pointStyle"],
                               markersize_px=2 * s["pointRadius"] * dpr, x=s["x"], y=s["y"],
                               path_px=path.round(3).tolist(), markers_px=mk.round(3).tolist()))
    leg = g.get("legend")
    legend_bbox = [f(leg["left"]), f(leg["top"]), f(leg["right"]), f(leg["bottom"])] if leg else None
    xr, yr = extra["xr"], extra["yr"]
    meta = dict(seed=seed, generator="chartjs", style="chartjs-dark" if extra["dark"] else "chartjs", preset="chartjs",
                font=extra["font"], width=W, height=H, dpr=dpr, plot_area=plot_area,
                xscale="log" if extra["xlog"] else "linear", yscale="log" if extra["ylog"] else "linear",
                xlim=[10 ** v for v in xr] if extra["xlog"] else list(xr), ylim=[10 ** v for v in yr] if extra["ylog"] else list(yr),
                xticks=ticks("x"), yticks=ticks("y"), series=out_series, legend_bbox=legend_bbox, offset_text=["", ""])
    return Rendered(image=image, sem=sem, inst=inst, meta=meta)


def main() -> None:
    """Render a few charts with the recorded truth drawn over them, to check the generator by eye."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, default=15_100_000)
    ap.add_argument("--count", type=int, default=5)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    from ..evaluate import draw
    from ..extract import Extraction

    for seed in range(a.start, a.start + a.count):
        r = generate(seed)
        m = r.meta
        ex = Extraction(M=np.eye(2, 3), plot_area=m["plot_area"],
                        xticks=[dict(anchor=t["anchor"], label_box=t["bbox"], pos=t["pos"]) for t in m["xticks"]],
                        yticks=[dict(anchor=t["anchor"], label_box=t["bbox"], pos=t["pos"]) for t in m["yticks"]])
        ov = draw(r.image, ex, m)
        for s in m["series"]:
            for x, y in s["markers_px"]:
                cv2.drawMarker(ov, (int(round(x)), int(round(y))), (0, 180, 0), cv2.MARKER_TILTED_CROSS, 7, 1)
        cv2.imwrite(os.path.join(a.out, f"{seed}.png"), r.image[..., ::-1])
        cv2.imwrite(os.path.join(a.out, f"{seed}.overlay.png"), ov[..., ::-1])
        pal = np.array([[255, 255, 255], [220, 0, 0], [255, 140, 0], [0, 0, 0], [160, 160, 255], [0, 150, 0], [150, 0, 150]], np.uint8)
        cv2.imwrite(os.path.join(a.out, f"{seed}.sem.png"), pal[r.sem][..., ::-1])
        print(seed, m["width"], m["height"], "dpr", m["dpr"], "series", [s["kind"] for s in m["series"]],
              "xticks", [t["text"] for t in m["xticks"]], "yticks", [t["text"] for t in m["yticks"]], m["xscale"], m["yscale"])


if __name__ == "__main__":
    main()
