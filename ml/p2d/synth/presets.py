"""House styles of the charts people actually screenshot.

matplotlib's own style sheets cover the scientific look. Charts in the wild are
as often Plotly, Excel, a news graphic or a dashboard, and they differ in ways a
model must not be surprised by: no axis lines at all, labels with no tick marks,
tinted paper, gridlines lighter than antialiasing, labels on the right, series
named by text at the end of the line instead of a legend. Each preset is an
rcParams overlay, a palette, and a hook run on the finished axes.
"""

from __future__ import annotations

import numpy as np

PALETTES = {
    "plotly": ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3", "#FF6692", "#B6E880"],
    "excel": ["#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5", "#70AD47", "#264478", "#9E480E"],
    "news": ["#2E7D6B", "#D4A72C", "#8C6BB1", "#E07B39", "#3C6E9F", "#B5465C", "#6B8E23"],
    "highcharts": ["#7cb5ec", "#434348", "#90ed7d", "#f7a35c", "#8085e9", "#f15c80", "#e4d354", "#2b908f"],
    "ft": ["#0F5499", "#990F3D", "#FF7FAA", "#00A0DD", "#96CC28", "#593380", "#FF8833"],
    "dash": ["#73BF69", "#F2CC0C", "#5794F2", "#FF9830", "#F2495C", "#B877D9", "#8AB8FF"],
    "economist": ["#006BA2", "#3EBCD2", "#379A8B", "#EBB434", "#B4BA39", "#9A607F", "#D1B07C"],
}

WEIGHTS = [("none", 50), ("plotly", 9), ("excel", 8), ("news", 9), ("highcharts", 6), ("ft", 4), ("dash", 5),
           ("economist", 4), ("minimal", 5)]


def choose(rng: np.random.Generator) -> str:
    names = [n for n, _ in WEIGHTS]
    w = np.array([w for _, w in WEIGHTS], float)
    return names[int(rng.choice(len(names), p=w / w.sum()))]


def rc(name: str, rng: np.random.Generator) -> dict:
    if name == "plotly":
        return {"axes.facecolor": "#E5ECF6", "figure.facecolor": "white", "axes.grid": True, "grid.color": "white",
                "grid.linewidth": float(rng.uniform(0.8, 1.5)), "grid.alpha": 1.0, "grid.linestyle": "-",
                "xtick.major.size": 0, "ytick.major.size": 0, "text.color": "#2a3f5f", "xtick.color": "#2a3f5f",
                "ytick.color": "#2a3f5f", "axes.labelcolor": "#2a3f5f", "lines.linewidth": 2.0}
    if name == "excel":
        return {"font.family": "Liberation Sans", "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#D9D9D9",
                "grid.linestyle": "-", "grid.alpha": 1.0, "xtick.major.size": 0, "ytick.major.size": 0,
                "xtick.color": "#595959", "ytick.color": "#595959", "axes.facecolor": "white", "figure.facecolor": "white",
                "lines.linewidth": 2.25}
    if name == "news":
        return {"axes.grid": True, "axes.grid.axis": "y", "grid.color": str(rng.choice(["#DDDDDD", "#E5E5E5", "#CCCCCC"])),
                "grid.linestyle": str(rng.choice(["-", ":", "--"])), "grid.alpha": 1.0, "xtick.major.size": float(rng.choice([0, 4])),
                "ytick.major.size": 0, "axes.facecolor": "white", "figure.facecolor": "white",
                "xtick.color": "#666666", "ytick.color": "#666666", "lines.linewidth": float(rng.uniform(1.8, 3.2))}
    if name == "highcharts":
        return {"font.family": "Lato", "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#e6e6e6", "grid.alpha": 1.0,
                "grid.linestyle": "-", "xtick.major.size": 6, "ytick.major.size": 0, "xtick.color": "#666666",
                "ytick.color": "#666666", "axes.facecolor": "white", "figure.facecolor": "white", "lines.linewidth": 2.0}
    if name == "ft":
        return {"axes.facecolor": "#FFF1E5", "figure.facecolor": "#FFF1E5", "axes.grid": True, "axes.grid.axis": "y",
                "grid.color": "#E6D9CE", "grid.alpha": 1.0, "grid.linestyle": "-", "xtick.major.size": 4,
                "ytick.major.size": 0, "xtick.color": "#66605C", "ytick.color": "#66605C", "lines.linewidth": 2.0}
    if name == "dash":
        return {"axes.facecolor": "#181b1f", "figure.facecolor": "#181b1f", "axes.grid": True, "grid.color": "#2c3235",
                "grid.alpha": 1.0, "grid.linestyle": "-", "xtick.major.size": 0, "ytick.major.size": 0,
                "xtick.color": "#ccccdc", "ytick.color": "#ccccdc", "text.color": "#ccccdc", "axes.labelcolor": "#ccccdc",
                "lines.linewidth": float(rng.uniform(1, 2))}
    if name == "economist":
        return {"axes.facecolor": "white", "figure.facecolor": "white", "axes.grid": True, "axes.grid.axis": "y",
                "grid.color": "#B7C6CF", "grid.alpha": 1.0, "grid.linestyle": "-", "xtick.major.size": 4,
                "ytick.major.size": 0, "lines.linewidth": 2.2}
    if name == "minimal":
        return {"axes.grid": False, "xtick.direction": "out", "ytick.direction": "out"}
    return {}


def palette(name: str) -> list[str] | None:
    return PALETTES.get(name)


def post(name: str, ax, rng: np.random.Generator) -> dict:
    """Adjust the finished axes. Returns flags for the caller (legend, direct labels)."""
    flags = {"legend": "auto", "direct_labels": False}
    sp = ax.spines
    if name in ("plotly", "dash"):
        for s in sp.values():
            s.set_visible(False)
        ax.set_axisbelow(True)
        flags["legend"] = "outside" if name == "plotly" else "below"
    elif name in ("excel", "highcharts"):
        for k in ("left", "right", "top"):
            sp[k].set_visible(False)
        sp["bottom"].set_color("#BFBFBF" if name == "excel" else "#ccd6eb")
        ax.set_axisbelow(True)
        flags["legend"] = "below"
    elif name in ("news", "economist"):
        for k in ("left", "right", "top"):
            sp[k].set_visible(False)
        if rng.random() < 0.5:
            sp["bottom"].set_visible(False)
        else:
            sp["bottom"].set_color("#333333" if name == "news" else "#0C0C0C")
        ax.set_axisbelow(True)
        if name == "economist" or rng.random() < 0.25:
            ax.yaxis.tick_right()
        flags["direct_labels"] = rng.random() < 0.6
        flags["legend"] = "none" if flags["direct_labels"] else "auto"
    elif name == "ft":
        for k in ("left", "right", "top"):
            sp[k].set_visible(False)
        ax.yaxis.tick_right()
        ax.set_axisbelow(True)
    elif name == "minimal":
        sp["top"].set_visible(False)
        sp["right"].set_visible(False)
        off = float(rng.uniform(3, 12))
        sp["left"].set_position(("outward", off))
        sp["bottom"].set_position(("outward", off))
    return flags
