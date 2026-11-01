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
    """Read every tick's label: the greedy text, and the top-k readings for the joint decode.

    Lax parsing (leading number from "0bo 15" style OCR noise of "0 births") kicks in only
    when NO label strict-parsed: an axis whose readable labels say "1.2bn" + "1.4bn" fits
    cleanly from those two and must not be swamped by lax parses of "200 n n" neighbours
    that would read as 200 instead of 2e8.
    """
    boxes = [(t["pos"], t["label_box"]) for t in ticks if t["label_box"] is not None]
    if reader is None or not boxes:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    crops = [crop(gray, b) for _, b in boxes]
    out = []
    for (pos, _), lp in zip(boxes, read_logits(reader, crops)):
        text, conf = decode(lp)
        out.append(TickRead(pos, text, conf, parse_value(text), lp, candidates(lp)))
    strict_n = sum(r.value is not None for r in out)
    if strict_n < 2:
        lax_vals = [parse_value(r.text, lax=True) for r in out]
        if sum(v is not None for v in lax_vals) > strict_n:
            for r, v in zip(out, lax_vals):
                r.value = v
                # Drop logits so fit_axis is used over decode_axis: the joint decoder builds
                # its hypotheses from the beam-search candidates whose values are strict; a
                # lax axis has none, and the simpler fitter handles outliers well enough from
                # the per-tick leading number.
                r.logits = None
                r.cands = []
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
    """Calibrate one axis from its readings: jointly when the reader's log-probs are there, else plainly.

    Duplicate ticks (two heat peaks at the same position, two sem components) make the pair
    search in the joint decoder skip every pair of them (distance < 3) and leave the axis unfit;
    collapse ticks within 1.5 px of each other so the decoder sees one reading per position.
    """
    if not reads:
        return None
    deduped: list[TickRead] = []
    for r in sorted(reads, key=lambda r: r.pos):
        if deduped and abs(deduped[-1].pos - r.pos) < 1.5:
            # Keep the reading with the higher confidence (or the one that parses).
            if (r.value is not None) and (deduped[-1].value is None):
                deduped[-1] = r
            elif r.conf > deduped[-1].conf:
                deduped[-1] = r
            continue
        deduped.append(r)
    if dates or all(r.logits is None for r in deduped):
        return fit_axis([r.pos for r in deduped], [np.nan if r.value is None else r.value for r in deduped],
                        [r.text for r in deduped], hint=hint)
    return decode_axis(deduped, hint=hint)


_MULT = re.compile(r"^(?:x|\(x)?(?:1e([-+]?\d+)|10\^([-+]?\d+))\)?$")
_OFFSET = re.compile(r"^([-+])(\d*\.\d+(?:e[-+]?\d+)?|\d+e[-+]?\d+)$")
_MAX_MULT_EXP = 15  # mpl axis multipliers run from atto to peta; "1e55" is OCR noise.


def _parse_factor(text: str) -> tuple[float, float] | None:
    """Return (scale, shift) if `text` is a printed multiplier or offset."""
    t = text.replace(" ", "")
    m = _MULT.match(t)
    if m:
        e = int(m.group(1) or m.group(2))
        if abs(e) > _MAX_MULT_EXP:
            return None
        return 10.0 ** e, 0.0
    m = _OFFSET.match(t)
    if m:
        v = float(m.group(2))
        return 1.0, (v if m.group(1) == "+" else -v)
    return None


def _end_search(img: np.ndarray, ex: Extraction, axis: str) -> list[list[int]]:
    """Candidate text boxes at the axis end, measured on source pixels.

    When the printed multiplier (`1e6`) has no sem component of its own (small
    text, big canvas, or an edge-of-plot location), `loose_labels` is empty and
    `axis_factor` cannot find it. This fallback scans a strip just outside the
    plot at the axis end, finds dark-ink components, and returns the component
    boxes most likely to be the multiplier text.
    """
    if ex.plot_area is None:
        return []
    H, W = img.shape[:2]
    x0, y0, x1, y1 = ex.plot_area
    if axis == "y":
        # The multiplier for a y axis sits above the plot area. Either side can host the axis;
        # scan a strip across both ends.
        strip_y = (max(0, int(y0) - 60), max(1, int(y0) - 2))
        strips = []
        wq = max(60, int(0.35 * (x1 - x0)))
        for cx in (int(x0), int(x1)):
            lo, hi = max(0, cx - wq), min(W, cx + wq)
            if hi > lo:
                strips.append((strip_y, (lo, hi)))
    else:
        # x axis: the multiplier sits to the right of the plot area, below the x axis.
        strips = [((max(1, int(y1) + 2), min(H, int(y1) + 60)), (int(x1) - 10, min(W, int(x1) + 100)))]
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    paper = int(np.median(gray))
    cands: list[list[int]] = []
    for (ry0, ry1), (rx0, rx1) in strips:
        if ry1 <= ry0 or rx1 <= rx0:
            continue
        strip = gray[ry0:ry1, rx0:rx1]
        ink = (paper - strip.astype(int)) > 30
        if ink.sum() < 4:
            continue
        n, lab = cv2.connectedComponents(ink.astype(np.uint8))
        for i in range(1, n):
            rows, cols = np.where(lab == i)
            if rows.size < 4:
                continue
            r0, r1 = int(rows.min()), int(rows.max())
            c0, c1 = int(cols.min()), int(cols.max())
            # Keep text-shaped components. The hyphen of "1e-5" is 1-2 rows tall and 2-4 cols
            # wide; it joins its neighbours later. A long horizontal line (an axis spine or
            # under-line) is excluded by the aspect check.
            w, h = c1 - c0 + 1, r1 - r0 + 1
            if h < 1 or h > 40 or w < 1 or w > 300:
                continue
            if w > 12 * h and h <= 2:
                continue  # a bar/underline, not a hyphen
            if h > 12 * w:
                continue  # a vertical line
            cands.append([rx0 + c0, ry0 + r0, rx0 + c1 + 1, ry0 + r1 + 1])
    # Join components close along the horizontal axis into one box (digits + 'e' + exponent).
    # Gap grows with the height of the two pieces: `1e` + `-` + `5` has larger gaps than a single
    # word, and a sign or caret between digits sits in the gap but is often lost to the ink test.
    cands.sort(key=lambda b: b[0])
    merged: list[list[int]] = []
    for b in cands:
        if merged:
            m = merged[-1]
            hb = max(m[3] - m[1], b[3] - b[1])
            if b[0] - m[2] <= max(10, 1.2 * hb) and abs((b[1] + b[3]) - (m[1] + m[3])) < max(12, 0.8 * hb):
                merged[-1] = [m[0], min(m[1], b[1]), b[2], max(m[3], b[3])]
                continue
        merged.append(list(b))
    return merged


def axis_factor(reader, img: np.ndarray, ex: Extraction, axis: str) -> tuple[float, float, str | None]:
    """A printed multiplier or offset for an axis: value = label * scale + shift.

    Matplotlib prints it at the top of the y axis and the right end of the x
    axis, outside the plot area. It is surfaced as a warning, never applied
    silently.
    """
    if reader is None or ex.plot_area is None:
        return 1.0, 0.0, None
    x0, y0, x1, y1 = ex.plot_area
    w, h = x1 - x0, y1 - y0
    cands: list[tuple[float, list[int]]] = []
    for b in ex.loose_labels:
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        # The text's centre is outside the plot; its box may touch or overlap the edge by a few px
        # (Chart.js prints the multiplier right on the top edge).
        if axis == "y" and cy < y0 and y0 - cy < 0.15 * h + 30 and (abs(cx - x0) < 0.25 * w or abs(cx - x1) < 0.25 * w):
            cands.append((abs(cx - x0) + (y0 - cy), b))
        if axis == "x" and cy > y1 and cy - y1 < 0.2 * h + 40 and cx > x1 - 0.3 * w:
            cands.append((abs(cx - x1) + (cy - y1), b))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    # Loose labels first: they are what the net surfaced as separate text pieces.
    for _, b in sorted(cands, key=lambda c: c[0]):
        text, _ = read_crops(reader, [crop(gray, b)])[0]
        got = _parse_factor(text)
        if got is not None:
            return got[0], got[1], text.replace(" ", "")
    # Explicit source-pixel search at the axis end: catches multipliers whose sem component is
    # missing or absorbed into another label. Each candidate is grown by a few pixels before the
    # reader sees it so leading/trailing glyphs are not cut.
    H, W = img.shape[:2]
    for b in _end_search(img, ex, axis):
        pad_x, pad_y = 3, 2
        pb = [max(0, b[0] - pad_x), max(0, b[1] - pad_y),
              min(W, b[2] + pad_x), min(H, b[3] + pad_y)]
        text, _ = read_crops(reader, [crop(gray, pb)])[0]
        got = _parse_factor(text)
        if got is not None:
            return got[0], got[1], text.replace(" ", "")
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


def run(net, reader, img: np.ndarray, oracle_ticks: dict | None = None, refine: bool = True,
        native: bool = True, tta: str | None = None) -> Result:
    """`oracle_ticks` ({"x": [(pos, value)], "y": ...}) bypasses detection and reading, for ablations.

    `native` reads a chart larger than the training canvas at its own resolution
    (`data.placement`); off, it is scaled to fit the canvas as in training.
    `tta` names extra network passes to fuse in (`tta.passes_for`).
    """
    if tta:
        from .tta import run_net_tta

        out, M = run_net_tta(net, img, native=native, tta=tta)
    else:
        out, M = run_net(net, img, native=native)
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
            if text is None:
                continue
            # mpl prints a multiplier when labels are small units (|v| < 1000, e.g. "0, 2, 4" with
            # "1e9" above). A chart whose own tick labels already parse to large magnitudes is not
            # a multiplier chart; the strip search caught title or year text and the OCR noise
            # matched the multiplier regex (owid-military: "1e1"; owid-solar-pv: "1e55"). Keep the
            # offset-annotation win by letting the factor through when labels are small. Also skip
            # a factor whose own magnitude is at most the labels': mpl uses "x10^k" only when the
            # labels would otherwise print with 'k' trailing zeros, so a 0-to-90 axis with a
            # spurious "1e1" from end_search text (owid-life-expectancy-4: "ld" from "would") is
            # certainly noise.
            if scale != 1.0 and reads:
                max_abs_val = max((abs(r.value) for r in reads if r.value is not None), default=0.0)
                if max_abs_val > 1000:
                    continue
                if scale > 1.0 and max_abs_val >= scale:
                    continue
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
