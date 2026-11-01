"""The real-chart benchmark (team t5): published charts scored against their published data.

`data/t5-real/` holds, per chart, the image as published (`<id>.png`), the data
file the publisher serves for the same query (`<id>.data.csv`, verbatim) and a
record of where both came from (`<id>.json`); `teams/t5-robust/tools/fetch_real.py`
fetches them. Sources: Our World in Data (D3), FRED (its own server renderer),
NASA GISS and NOAA GML. Nothing here was rendered by matplotlib or Plotly.

Scoring, per truth series: the extracted series whose RMS against it is lowest
(each extracted series used once), RMS over the truth's own x samples inside the
extraction's x extent, as a percentage of the chart's y data span (max minus min
over all its series, in log10 on a log axis), plus the coverage: the fraction of
the truth's x range that the extraction spans. The unit is the data span, not
the axis span as in `eval_corpus`, because the axis range of a published chart
is not in the data file; it is within 10 to 30% of the axis span for charts
that autoscale. Dates are decimal years, which is what year labels read as.

    python -m p2d.eval_t5real --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --viz out/t5real-viz
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os

import cv2
import numpy as np

from .evaluate import draw, load_net
from .ocr import load_reader
from .pipeline import run

REAL = os.path.join(os.path.dirname(__file__), "..", "data", "t5-real")


def _year(s: str) -> float:
    d = dt.date.fromisoformat(s.strip())
    start = dt.date(d.year, 1, 1)
    end = dt.date(d.year + 1, 1, 1)
    return d.year + (d - start).days / (end - start).days


def _float(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return np.nan


def load_truth(meta: dict, path: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """name -> (x, y) arrays, x in years (decimal for dates), NaN-free, sorted."""
    text = open(path, encoding="utf-8", errors="replace").read()
    kind = meta["kind"]
    out: dict[str, list[tuple[float, float]]] = {}
    if kind == "owid":
        rows = list(csv.DictReader(io.StringIO(text)))
        cols = [c for c in rows[0].keys() if c not in ("Entity", "Code", "Year") and not c.startswith("World region")]
        col = cols[0]
        for r in rows:
            out.setdefault(r["Entity"], []).append((_float(r["Year"]), _float(r[col])))
    elif kind == "fred":
        rows = list(csv.DictReader(io.StringIO(text)))
        cols = [c for c in rows[0].keys() if c != "observation_date"]
        # The chart's date window (cosd/coed) applies to every series drawn; the file is only cut for the first.
        q = dict(p.split("=", 1) for p in meta.get("q", "").strip("&").split("&") if "=" in p)
        lo = _year(q["cosd"]) if "cosd" in q else -np.inf
        hi = _year(q["coed"]) if "coed" in q else np.inf
        for r in rows:
            x = _year(r["observation_date"])
            if lo <= x <= hi:
                for c in cols:
                    out.setdefault(c, []).append((x, _float(r[c])))
    elif kind == "giss":
        lines = [ln for ln in text.splitlines() if ln and ln[0].isdigit() or ln.startswith("Year")]
        rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
        cols = [c for c in rows[0].keys() if c != "Year"]
        for r in rows:
            for c in cols:
                out.setdefault(c, []).append((_float(r["Year"]), _float(r[c])))
    elif kind == "noaa":
        lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
        rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
        for r in rows:
            out.setdefault("average", []).append((_float(r["decimal date"]), _float(r["average"])))
            out.setdefault("deseasonalized", []).append((_float(r["decimal date"]), _float(r["deseasonalized"])))
    else:
        raise ValueError(kind)
    truth = {}
    for name, pts in out.items():
        a = np.array(pts, float)
        a = a[np.all(np.isfinite(a), axis=1)]
        if len(a) >= 2:
            a = a[np.argsort(a[:, 0], kind="stable")]
            truth[name] = (a[:, 0], a[:, 1])
    return truth


def score_chart(meta: dict, truth: dict, res) -> list[dict]:
    # Trust the extractor's own determination of the y-axis scale when it has one. FRED's
    # `log_scales=Left` URL argument is only a request: when the data range is narrow (gdp,
    # m2sl, where y spans less than two decades) FRED silently renders a linear axis with
    # linear labels (0, 4000, ..., 36000) instead. Scoring that in log10 blows up error at
    # the small-value tail. Fall back to the URL hint only when the extractor failed to fit.
    yfit = getattr(res, "yfit", None)
    if yfit is not None:
        ylog = yfit.scale == "log"
    else:
        ylog = "yScale=log" in meta.get("q", "") or "log_scales" in meta.get("q", "")
    # When the extractor read the x axis as dates (labels like "2022-01"), its series x values
    # are in days since 1970; convert to the decimal years the truth is in before scoring.
    xdate = bool(getattr(res, "date_axes", {}).get("x", False))

    def t(v):
        v = np.asarray(v, float)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.log10(v) if ylog else v

    def to_years(days):
        days = np.asarray(days, float)
        out = np.empty_like(days)
        for i, d in enumerate(days):
            if not np.isfinite(d):
                out[i] = np.nan
                continue
            dd = dt.date(1970, 1, 1) + dt.timedelta(days=float(d))
            s = dt.date(dd.year, 1, 1)
            e = dt.date(dd.year + 1, 1, 1)
            out[i] = dd.year + (dd - s).days / (e - s).days
        return out

    ally = np.concatenate([t(y) for _, y in truth.values()])
    yspan = float(np.nanmax(ally) - np.nanmin(ally)) or 1.0
    preds = [s["line"] for s in res.series if "line" in s and len(s["line"]) >= 2]
    preds += [s["markers"] for s in res.series if "line" not in s and "markers" in s and len(s["markers"]) >= 2]
    used = set()
    rows = []
    for name, (tx, ty) in truth.items():
        best = None
        for j, p in enumerate(preds):
            if j in used:
                continue
            px, py = p[:, 0], t(p[:, 1])
            if xdate:
                px = to_years(px)
            ok = np.isfinite(px) & np.isfinite(py)
            px, py = px[ok], py[ok]
            if len(px) < 2:
                continue
            o = np.argsort(px, kind="stable")
            px, py = px[o], py[o]
            inside = (tx >= px[0]) & (tx <= px[-1])
            if inside.sum() < 3:
                continue
            e = (np.interp(tx[inside], px, py) - t(ty)[inside]) / yspan
            rms = float(np.sqrt(np.nanmean(e ** 2)))
            cov = float(np.clip((min(px[-1], tx[-1]) - max(px[0], tx[0])) / max(tx[-1] - tx[0], 1e-9), 0, 1))
            key = rms + 0.5 * (1 - cov)  # a short fragment that fits well is not the series
            if best is None or key < best[0]:
                best = (key, j, rms, cov)
        if best is None:
            rows.append({"series": name, "rms_pct": np.nan, "cover": 0.0})
        else:
            used.add(best[1])
            rows.append({"series": name, "rms_pct": best[2] * 100, "cover": best[3]})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--data", default=REAL)
    ap.add_argument("--viz", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--tta", default=None, help="extra passes to fuse: shift, scale, or shift+scale")
    a = ap.parse_args()
    net, reader = load_net(a.ckpt), load_reader(a.ocr)
    if a.viz:
        os.makedirs(a.viz, exist_ok=True)
    allrows, per_chart = [], []
    for f in sorted(os.listdir(a.data)):
        if not f.endswith(".json"):
            continue
        meta = json.load(open(os.path.join(a.data, f)))
        cid = meta["id"]
        img = cv2.imread(os.path.join(a.data, cid + ".png"))[..., ::-1].copy()
        truth = load_truth(meta, os.path.join(a.data, cid + ".data.csv"))
        res = run(net, reader, img, tta=a.tta)
        rows = score_chart(meta, truth, res)
        xs_ = res.xfit.scale if res.xfit else "-"
        ys_ = res.yfit.scale if res.yfit else "-"
        print(f"{cid:26s} found {len(res.series)}/{len(truth)}  scales {xs_}/{ys_}  " +
              "  ".join(f"{r['rms_pct']:.2f}% cov {r['cover']:.0%}" for r in rows) +
              ("  WARN " + "; ".join(res.warnings) if res.warnings else ""))
        allrows += rows
        per_chart.append({"id": cid, "found": len(res.series), "truth": len(truth), "rows": rows, "warnings": res.warnings,
                          "xscale": xs_, "yscale": ys_})
        if a.viz:
            cv2.imwrite(os.path.join(a.viz, cid + ".png"), draw(img, res.ex)[..., ::-1])
    v = np.array([r["rms_pct"] for r in allrows], float)
    cov = np.array([r["cover"] for r in allrows], float)
    good = np.isfinite(v) & (cov >= 0.8)
    print(f"series {len(v)}  found (cover >= 80%) {good.mean():.0%}  median rms {np.nanmedian(v):.2f}%  "
          f"median rms of found {np.median(v[good]) if good.any() else float('nan'):.2f}%  within 1% {np.mean(np.nan_to_num(v, nan=1e9) < 1):.0%}  "
          f"within 0.5% {np.mean(np.nan_to_num(v, nan=1e9) < 0.5):.0%}  failed {np.isnan(v).sum()}")
    if a.json:
        json.dump(per_chart, open(a.json, "w"), default=float, indent=1)


if __name__ == "__main__":
    main()
