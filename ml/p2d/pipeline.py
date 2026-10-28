"""Image in, numbers out: PlotNet, then geometry, then tick labels, then calibration.

    python -m p2d.pipeline chart.png --ckpt runs/v1/best.pt --ocr runs/ocr1/best.pt
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from .axis import TickRead, candidates, decode_axis
from .calibrate import AxisFit, fit_axis
from .dates import resolve
from .extract import Extraction, extract, refine_labels, refine_lines, refine_markers, refine_ticks, run_net
from .ocr import crop, decode, parse_value, read_crops, read_logits
from .sampling import auto_step, resample


@dataclass
class Result:
    ex: Extraction
    xfit: AxisFit | None
    yfit: AxisFit | None
    tick_reads: dict = field(default_factory=dict)  # axis -> [(pos, text, conf, value)]
    series: list[dict] = field(default_factory=list)  # data units
    warnings: list[str] = field(default_factory=list)
    date_axes: dict = field(default_factory=dict)  # axis -> True when its values are days since 1970
    reads: dict = field(default_factory=dict)  # axis -> [TickRead], with how each label was read


def read_ticks(reader, img: np.ndarray, ticks: list[dict]) -> list[TickRead]:
    """Read every tick's label: the greedy text, and the top-k readings for the joint decode."""
    boxes = [(t["pos"], t["label_box"]) for t in ticks if t["label_box"] is not None]
    if reader is None or not boxes:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    crops = [crop(gray, b) for _, b in boxes]
    out = []
    for (pos, _), lp in zip(boxes, read_logits(reader, crops)):
        text, conf = decode(lp)
        out.append(TickRead(pos, text, conf, parse_value(text), lp, candidates(lp)))
    return out


def as_dates(reads: list[TickRead], axis: str) -> bool:
    """If an axis's labels are mostly not numbers but are dates, re-read them as days since 1970."""
    numeric = sum(r.value is not None for r in reads)
    if len(reads) < 2 or numeric >= len(reads) / 2:
        return False
    # Dates run left to right on x and bottom to top on y.
    order = sorted(range(len(reads)), key=lambda i: reads[i].pos if axis == "x" else -reads[i].pos)
    vals = resolve([reads[i].text for i in order])
    if sum(v is not None for v in vals) < 2:
        return False
    for i, v in zip(order, vals):
        reads[i].value = v
    return True


def fit_reads(reads: list[TickRead], dates: bool, hint: str | None = None) -> AxisFit | None:
    """Calibrate one axis from its readings: jointly when the reader's log-probs are there, else plainly."""
    if not reads:
        return None
    if dates or all(r.logits is None for r in reads):
        return fit_axis([r.pos for r in reads], [np.nan if r.value is None else r.value for r in reads],
                        [r.text for r in reads], hint=hint)
    return decode_axis(reads, hint=hint)


_MULT = re.compile(r"^(?:x|\(x)?(?:1e([-+]?\d+)|10\^([-+]?\d+))\)?$")
_OFFSET = re.compile(r"^([-+])(\d*\.?\d+(?:e[-+]?\d+)?)$")


def axis_factor(reader, img: np.ndarray, ex: Extraction, axis: str) -> tuple[float, float, str | None]:
    """A printed multiplier or offset for an axis: value = label * scale + shift.

    Matplotlib prints it at the top of the y axis and the right end of the x
    axis, outside the plot area. It is surfaced as a warning, never applied
    silently.
    """
    if reader is None or ex.plot_area is None or not ex.loose_labels:
        return 1.0, 0.0, None
    x0, y0, x1, y1 = ex.plot_area
    w, h = x1 - x0, y1 - y0
    cands = []
    for b in ex.loose_labels:
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if axis == "y" and b[3] <= y0 + 3 and y0 - cy < 0.15 * h + 30 and (abs(cx - x0) < 0.25 * w or abs(cx - x1) < 0.25 * w):
            cands.append((abs(cx - x0) + (y0 - cy), b))
        if axis == "x" and b[1] >= y1 - 3 and cy - y1 < 0.2 * h + 40 and cx > x1 - 0.3 * w:
            cands.append((abs(cx - x1) + (cy - y1), b))
    if not cands:
        return 1.0, 0.0, None
    cands.sort(key=lambda c: c[0])
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    text, conf = read_crops(reader, [crop(gray, cands[0][1])])[0]
    t = text.replace(" ", "")
    m = _MULT.match(t)
    if m:
        e = int(m.group(1) or m.group(2))
        return 10.0 ** e, 0.0, t
    m = _OFFSET.match(t)
    if m:
        v = float(m.group(2))
        return 1.0, (v if m.group(1) == "+" else -v), t
    return 1.0, 0.0, None


def apply_factor(fit: AxisFit | None, reads: list[TickRead], scale: float, shift: float) -> AxisFit | None:
    """A printed multiplier or offset: the labels are in units of it, the values are not."""
    for r in reads:
        if r.value is not None:
            r.value = r.value * scale + shift
    if fit is None:
        return fit
    if fit.scale == "log":
        if scale > 0:
            fit.a += math.log10(scale)
        if shift:
            fit.warnings.append("an offset is printed on a log axis and was not applied")
        return fit
    fit.a = fit.a * scale + shift
    fit.b = fit.b * scale
    return fit


def to_data(ex: Extraction, xfit: AxisFit | None, yfit: AxisFit | None, step_px: float | None = None,
            tol_px: float = 0.5) -> list[dict]:
    """Series in data units. A line also gets `sampled`: uniform samples at `step_px` pixels, or by
    default at the coarsest step whose linear reconstruction stays within `tol_px` of the trace.

    The step is chosen in pixels, which makes it uniform in x on a linear axis and
    uniform in log x on a log axis, as the axis is drawn.
    """
    out = []
    for k, s in enumerate(ex.series):
        d = {"name": f"series_{k + 1}", "kind": s.kind, "color": s.color}
        if xfit and yfit:
            if len(s.line_px):
                d["line"] = np.column_stack([xfit.to_value(s.line_px[:, 0]), yfit.to_value(s.line_px[:, 1])])
                lp = s.line_px[np.argsort(s.line_px[:, 0], kind="stable")]
                if len(lp) >= 3:
                    step = step_px if step_px else auto_step(lp[:, 0], lp[:, 1], tol_px, min_step=1.0)
                    gx, gy = resample(lp[:, 0], lp[:, 1], step=step)
                    d["step_px"] = float(step)
                    d["sampled"] = np.column_stack([xfit.to_value(gx), yfit.to_value(gy)])
            if len(s.markers_px):
                mk = s.markers_px[np.argsort(s.markers_px[:, 0], kind="stable")]
                d["markers"] = np.column_stack([xfit.to_value(mk[:, 0]), yfit.to_value(mk[:, 1])])
        out.append(d)
    return out


def run(net, reader, img: np.ndarray, oracle_ticks: dict | None = None, refine: bool = True) -> Result:
    """`oracle_ticks` ({"x": [(pos, value)], "y": ...}) bypasses detection and reading, for ablations."""
    out, M = run_net(net, img)
    ex = extract(out, M, img)
    if refine:
        ex = refine_lines(img, ex)
        ex = refine_ticks(img, ex)
        ex = refine_markers(img, ex)
    if reader is not None and oracle_ticks is None:
        ex = refine_labels(img, ex)
    if oracle_ticks is not None:
        rx = [TickRead(p, "", 1.0, v) for p, v in oracle_ticks["x"]]
        ry = [TickRead(p, "", 1.0, v) for p, v in oracle_ticks["y"]]
        xfit, yfit = fit_reads(rx, False), fit_reads(ry, False)
    else:
        rx, ry = read_ticks(reader, img, ex.xticks), read_ticks(reader, img, ex.yticks)
        xdate, ydate = as_dates(rx, "x"), as_dates(ry, "y")
        xfit, yfit = fit_reads(rx, xdate), fit_reads(ry, ydate)
        factors = {}
        for name, reads in (("x", rx), ("y", ry)):
            scale, shift, text = axis_factor(reader, img, ex, name)
            if text is not None:
                factors[name] = text
                if name == "x":
                    xfit = apply_factor(xfit, reads, scale, shift)
                else:
                    yfit = apply_factor(yfit, reads, scale, shift)
    res = Result(ex=ex, xfit=xfit, yfit=yfit, tick_reads={"x": [r.as_tuple() for r in rx], "y": [r.as_tuple() for r in ry]},
                 reads={"x": rx, "y": ry})
    if oracle_ticks is None:
        res.date_axes = {"x": xdate, "y": ydate}
        for name, text in factors.items():
            res.warnings.append(f"{name} axis: values scaled by the printed '{text}'")
    for name, f in (("x", xfit), ("y", yfit)):
        if f is None:
            res.warnings.append(f"{name} axis: could not calibrate from the tick labels")
        else:
            res.warnings += [f"{name} axis: {w}" for w in f.warnings]
    res.series = to_data(ex, xfit, yfit)
    return res


def write_csv(res: Result, path: str) -> None:
    """One block per series: a curve as its uniform samples, markers as the points found."""
    import csv
    import datetime as dt

    xdate = res.date_axes.get("x", False)

    def fx(v: float) -> str:
        if xdate:
            return (dt.datetime(1970, 1, 1) + dt.timedelta(days=float(v))).isoformat(timespec="minutes")
        return f"{v:.6g}"

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        for warn in res.warnings:
            w.writerow([f"# {warn}"])
        for s in res.series:
            pts = s.get("sampled") if s["kind"] == "line" else s.get("markers")
            if pts is None:
                continue
            note = f"uniform step {s['step_px']:.2f} px" if s["kind"] == "line" else "one point per marker"
            w.writerow([f"# {s['name']} ({s['kind']}, {note})"])
            w.writerow(["x", s["name"]])
            for x, y in pts:
                w.writerow([fx(x), f"{y:.6g}"])


def main() -> None:
    from .evaluate import draw, load_net
    from .ocr import load_reader

    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--csv", help="write the extracted series here")
    ap.add_argument("--overlay", help="write the extraction drawn over the image here")
    ap.add_argument("--step-px", type=float, default=None, help="sampling step for curves (default: automatic)")
    a = ap.parse_args()
    img = cv2.imread(a.image)[..., ::-1].copy()
    res = run(load_net(a.ckpt), load_reader(a.ocr), img)
    if a.step_px:
        res.series = to_data(res.ex, res.xfit, res.yfit, step_px=a.step_px)
    if a.csv:
        write_csv(res, a.csv)
    if a.overlay:
        cv2.imwrite(a.overlay, draw(img, res.ex)[..., ::-1])
    print(json.dumps({
        "x_axis": res.xfit and {"scale": res.xfit.scale, "date": res.date_axes.get("x", False),
                                "ticks": [(r[1], r[3]) for r in res.tick_reads["x"]]},
        "y_axis": res.yfit and {"scale": res.yfit.scale, "ticks": [(r[1], r[3]) for r in res.tick_reads["y"]]},
        "warnings": res.warnings,
        "series": [{"name": s["name"], "kind": s["kind"], "color": s["color"],
                    "points": len(s.get("sampled", s.get("markers", []))),
                    "step_px": s.get("step_px")} for s in res.series],
    }, indent=1, default=str))


if __name__ == "__main__":
    main()
