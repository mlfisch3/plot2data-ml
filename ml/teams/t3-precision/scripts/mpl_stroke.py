"""Render a polyline with matplotlib Agg in pixel coordinates, exactly as the synthetic charts are drawn."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams["path.simplify"] = False
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg


def render(path, lw_px, W=300, H=200, color="#c83c1e", join="round", dpi=100.0, dashes=None):
    fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(-0.5, W - 0.5)
    ax.set_ylim(H - 0.5, -0.5)
    ax.axis("off")
    p = np.asarray(path, float)
    (ln,) = ax.plot(p[:, 0], p[:, 1], lw=lw_px * 72 / dpi, color=color, solid_joinstyle=join, solid_capstyle="butt")
    if dashes:
        ln.set_dashes(dashes)
    ln.set_snap(False)
    canvas.draw()
    img = np.asarray(canvas.buffer_rgba())[..., :3].copy()
    plt.close(fig)
    return img
