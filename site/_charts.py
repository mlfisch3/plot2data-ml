"""Render a few scoreboard figures as inline-ready SVG with matplotlib.

Writes:
- site/assets/scoreboard-corpus.svg
- site/assets/scoreboard-mpl-val.svg
- site/assets/scoreboard-plotly.svg

Everything is theme-neutral: transparent background, dark text, so CSS can colour it either way.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import rcParams

SITE = Path(__file__).resolve().parent
ASSETS = SITE / "assets"
ASSETS.mkdir(exist_ok=True)

rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = ["Inter", "SF Pro", "DejaVu Sans", "Helvetica"]
rcParams["svg.fonttype"] = "none"
rcParams["axes.spines.top"] = False
rcParams["axes.spines.right"] = False

INK = "#8a8a94"
PRIMARY = "#2563eb"
PRIMARY_LIGHT = "#60a5fa"
ACCENT = "#059669"


def _finish(fig, path: Path) -> None:
    for ax in fig.axes:
        ax.tick_params(colors=INK)
        ax.yaxis.label.set_color(INK)
        ax.xaxis.label.set_color(INK)
        ax.title.set_color("#1f1f28")
        for spine in ax.spines.values():
            spine.set_color(INK)
    fig.patch.set_alpha(0)
    for ax in fig.axes:
        ax.set_facecolor("none")
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)
    print(f"wrote {path.relative_to(SITE)}")


def corpus_worst() -> None:
    """Worst-case Chart.js corpus RMS (full scale, %) across versions."""
    labels = ["Classical", "v1", "v2", "v3", "Integrated"]
    values = [61.222, 61.222, 61.222, 61.222, 0.214]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    colors = [INK, INK, INK, INK, PRIMARY]
    ax.bar(labels, values, color=colors, width=0.55)
    ax.set_yscale("log")
    ax.set_ylim(0.1, 200)
    ax.set_ylabel("worst-case RMS, % of plot height")
    ax.set_title("Chart.js corpus: worst-case RMS, log scale")
    for i, v in enumerate(values):
        txt = f"{v:.3f}" if v < 1 else f"{v:.1f}"
        ax.text(i, v * 1.1, txt, ha="center", va="bottom", fontsize=9, color=INK)
    _finish(fig, ASSETS / "scoreboard-corpus.svg")


def mpl_val() -> None:
    """mpl-val headline numbers: find rate (simple) and peak error (simple)."""
    labels = ["Classical", "v3 base", "Integrated"]
    find = [None, 62, 75]   # % of simple series found
    peak = [None, 0.39, 0.23]  # peak error % (median)
    rms = [0.38, 0.31, 0.21]  # median rms simple

    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.2))

    ax = axes[0]
    xs = [0, 1, 2]
    bars = ax.bar(xs, [v or 0 for v in find],
                  color=[INK, INK, PRIMARY], width=0.55)
    # classical: 14 (from mpl-val row)
    bars[0].set_height(14)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% of simple series found")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_title("mpl-val: line_found (simple)")
    for i, v in enumerate([14, 62, 75]):
        ax.text(i, v + 2, f"{v}%", ha="center", va="bottom", fontsize=9, color=INK)

    ax = axes[1]
    bars = ax.bar(xs, [0.19, 0.39, 0.23], color=[INK, INK, PRIMARY], width=0.55)
    ax.set_ylabel("median peak error, % of plot height")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_title("mpl-val: peak error (simple)")
    for i, v in enumerate([0.19, 0.39, 0.23]):
        ax.text(i, v + 0.01, f"{v}", ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_ylim(0, 0.5)

    fig.tight_layout()
    _finish(fig, ASSETS / "scoreboard-mpl-val.svg")


def plotly_val() -> None:
    """Held-out Plotly set: line_found and marker metrics across versions."""
    xs = [0, 1, 2]
    labels = ["Classical", "v3 base", "Integrated"]
    found = [13, 78, 93]   # simple find rate %
    rms = [0.15, 0.18, 0.145]

    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.2))

    ax = axes[0]
    ax.bar(xs, found, color=[INK, INK, ACCENT], width=0.55)
    ax.set_ylim(0, 110)
    ax.set_ylabel("% of simple series found")
    ax.set_xticks(xs); ax.set_xticklabels(labels)
    ax.set_title("Plotly held out: line_found (simple)")
    for i, v in enumerate(found):
        ax.text(i, v + 2, f"{v}%", ha="center", va="bottom", fontsize=9, color=INK)

    ax = axes[1]
    ax.bar(xs, rms, color=[INK, INK, ACCENT], width=0.55)
    ax.set_ylim(0, 0.3)
    ax.set_ylabel("median RMS, % of plot height")
    ax.set_xticks(xs); ax.set_xticklabels(labels)
    ax.set_title("Plotly held out: median RMS (simple)")
    for i, v in enumerate(rms):
        ax.text(i, v + 0.005, f"{v:.3f}", ha="center", va="bottom", fontsize=9, color=INK)

    fig.tight_layout()
    _finish(fig, ASSETS / "scoreboard-plotly.svg")


def real_screenshots() -> None:
    """Px error at hand-measured tick anchors on 3 dashboard panels."""
    labels = ["panel 1", "panel 2", "panel 3"]
    base_x = [1.08, 0.48, 1.02]
    base_y = [1.94, 3.99, 1.61]
    int_x = [0.82, 0.44, 0.85]
    int_y = [1.89, 2.62, 1.32]
    import numpy as np
    i = np.arange(len(labels))
    width = 0.18

    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    ax.bar(i - 1.5 * width, base_x, width, color=INK, label="v3 base, x err")
    ax.bar(i - 0.5 * width, base_y, width, color="#c0c0c8", label="v3 base, y err")
    ax.bar(i + 0.5 * width, int_x, width, color=PRIMARY, label="Integrated, x err")
    ax.bar(i + 1.5 * width, int_y, width, color=PRIMARY_LIGHT, label="Integrated, y err")
    ax.set_xticks(i); ax.set_xticklabels(labels)
    ax.set_ylabel("px error at hand-measured tick anchors")
    ax.set_title("Real screenshots (01-panel1/2/3)")
    ax.legend(frameon=False, fontsize=8, labelcolor=INK)
    _finish(fig, ASSETS / "scoreboard-real.svg")


if __name__ == "__main__":
    corpus_worst()
    mpl_val()
    plotly_val()
    real_screenshots()
