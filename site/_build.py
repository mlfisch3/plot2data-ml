"""Run the integrated pipeline over the gallery of chart images, save overlays, CSVs and JSON.

Call from the `ml/` directory under this worktree, with its venv active:

    cd ml
    source ../.venv/bin/activate
    flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python ../site/_build.py

The checkpoint is `runs/t5-chartjs/best.pt`, the OCR is `runs/ocr1/best.pt`, and the TTA mode is `shift`.
Overlays are resized to at most 960 px wide and saved as PNGs; CSVs land next to them.
A `gallery.json` file is written for the site to read.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))

from p2d.evaluate import draw, load_net
from p2d.ocr import load_reader
from p2d.pipeline import run, to_data, write_csv


SITE = Path(__file__).resolve().parent
EX_DIR = SITE / "examples"
EX_DIR.mkdir(exist_ok=True)
CKPT = SITE.parent / "ml" / "runs" / "t5-chartjs" / "best.pt"
OCR = SITE.parent / "ml" / "runs" / "ocr1" / "best.pt"
CORPUS = SITE.parent / "corpus"
REAL = SITE.parent / "examples" / "real"
T5R = SITE.parent / "ml" / "data" / "t5-real"


# A diverse selection of 14 charts: Chart.js corpus, hand-picked real screenshots, FRED, OWID, GISS, NOAA.
# Each one tells a different story about what the integrated pipeline handles.
GALLERY = [
    # id              , source path                        , label                       , kind, tags
    ("log-y",            CORPUS / "log-y.png",                "Chart.js log y axis",         "Chart.js corpus",     ["log axis", "chartjs"]),
    ("log-y-multi",      CORPUS / "log-y-multi.png",          "Chart.js two series on log y","Chart.js corpus",     ["log axis", "two series", "chartjs"]),
    ("log-log",          CORPUS / "log-log.png",              "Chart.js log x log y",        "Chart.js corpus",     ["log-log", "chartjs"]),
    ("retina-2x",        CORPUS / "retina-2x.png",            "Chart.js retina 2x",          "Chart.js corpus",     ["retina", "chartjs"]),
    ("dark-theme",       CORPUS / "dark-theme.png",           "Chart.js dark theme",         "Chart.js corpus",     ["dark", "two series", "chartjs"]),
    ("scatter-markers",  CORPUS / "scatter-markers.png",      "Chart.js scatter markers",    "Chart.js corpus",     ["scatter", "markers", "chartjs"]),
    ("linear-multi",     CORPUS / "linear-multi.png",         "Chart.js three series",       "Chart.js corpus",     ["multi series", "chartjs"]),
    ("linear-single-nogrid", CORPUS / "linear-single-nogrid.png", "Chart.js no gridlines",   "Chart.js corpus",     ["no grid", "chartjs"]),
    ("real-01-panel1",   REAL / "01-panel1.png",              "Dashboard panel (no axis lines)", "Real screenshot",  ["dashboard", "no axis"]),
    ("real-03-women-men", REAL / "03-women-men-percent.png",  "News chart with direct labels",   "Real screenshot",  ["news", "direct labels"]),
    ("real-05-retail",   REAL / "05-retail-sales-monthly.png","Retail sales monthly spikes",     "Real screenshot",  ["spikes", "two series"]),
    ("fred-sp500",       T5R / "fred-sp500.png",              "FRED S&P 500 daily",          "FRED screenshot",     ["dates", "thin line"]),
    ("fred-unrate-dark", T5R / "fred-unrate-dark.png",        "FRED unemployment, dark",     "FRED screenshot",     ["dark", "dates"]),
    ("owid-life-expectancy-4", T5R / "owid-life-expectancy-4.png", "Our World in Data: life expectancy, 4 countries", "OWID screenshot", ["four series", "dates"]),
    ("owid-solar-pv",    T5R / "owid-solar-pv.png",           "Our World in Data: solar PV capacity", "OWID screenshot", ["dates", "steep"]),
]


def _fit_width(img: np.ndarray, target_w: int = 960) -> np.ndarray:
    h, w = img.shape[:2]
    if w <= target_w:
        return img
    s = target_w / w
    return cv2.resize(img, (target_w, int(round(h * s))), interpolation=cv2.INTER_AREA)


def _summarise(res, name: str) -> dict:
    xticks = []
    for r in res.tick_reads["x"]:
        txt, val = r[1], r[3]
        xticks.append({"text": txt, "value": None if val is None else float(val)})
    yticks = []
    for r in res.tick_reads["y"]:
        txt, val = r[1], r[3]
        yticks.append({"text": txt, "value": None if val is None else float(val)})
    series_info = []
    for s in res.series:
        info = {
            "name": s["name"],
            "kind": s["kind"],
            "color": [int(c) for c in s["color"]],
            "points": int(len(s.get("sampled", s.get("markers", [])))),
        }
        if "step_px" in s:
            info["step_px"] = float(s["step_px"])
        series_info.append(info)
    return {
        "name": name,
        "x_axis": None if res.xfit is None else {
            "scale": res.xfit.scale,
            "date": res.date_axes.get("x", False),
            "ticks": xticks,
        },
        "y_axis": None if res.yfit is None else {
            "scale": res.yfit.scale,
            "date": res.date_axes.get("y", False),
            "ticks": yticks,
        },
        "warnings": list(res.warnings),
        "series": series_info,
    }


def _preview_rows(csv_path: Path, max_rows: int = 6) -> list[dict]:
    """Return a list of {caption, header, rows} per series block in the CSV.

    Skips comment-only blocks (axis warnings printed before the first series).
    """
    out = []
    cur = None
    with open(csv_path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            # Only treat a quoted "# ..." line as a block start; a bare "# ..." is a
            # warning line between series blocks and should land as a top-note.
            if line.startswith('"# '):
                raw = line.strip('"').lstrip("# ")
                if cur:
                    out.append(cur)
                cur = {"caption": raw, "header": None, "rows": []}
            elif line.startswith("# ") and cur is None:
                # Top-of-file warning, included as its own block with no table.
                out.append({"caption": line[2:], "header": [], "rows": []})
            elif cur and cur["header"] is None:
                cur["header"] = line.split(",")
            elif cur and len(cur["rows"]) < max_rows:
                cur["rows"].append(line.split(","))
    if cur:
        out.append(cur)
    # Drop blocks with no header and no rows (they are warnings only).
    return [b for b in out if b.get("header") or b.get("rows")]


def main() -> None:
    assert CKPT.exists(), f"missing checkpoint {CKPT}"
    assert OCR.exists(), f"missing OCR checkpoint {OCR}"

    print(f"Loading network from {CKPT}", flush=True)
    net = load_net(str(CKPT))
    reader = load_reader(str(OCR))

    results = []
    for i, (gid, src, label, kind, tags) in enumerate(GALLERY):
        if not src.exists():
            print(f"[{i + 1}/{len(GALLERY)}] skip (missing): {src}", flush=True)
            continue
        print(f"[{i + 1}/{len(GALLERY)}] {gid}: {src.name}", flush=True)
        t0 = time.time()
        img = cv2.imread(str(src))
        if img is None:
            print(f"  skip (unreadable)")
            continue
        img = img[..., ::-1].copy()

        res = run(net, reader, img, native=True, tta="shift")
        # Default auto-step is fine; the pipeline already picked it.

        src_small = _fit_width(img, 960)
        # Also save a thumbnail of the original.
        cv2.imwrite(str(EX_DIR / f"{gid}.png"), src_small[..., ::-1])
        overlay = draw(img, res.ex)
        overlay_small = _fit_width(overlay, 960)
        cv2.imwrite(str(EX_DIR / f"{gid}-overlay.png"), overlay_small[..., ::-1])

        csv_path = EX_DIR / f"{gid}.csv"
        write_csv(res, str(csv_path))

        summary = _summarise(res, gid)
        summary.update({
            "label": label,
            "kind": kind,
            "tags": tags,
            "src": f"examples/{gid}.png",
            "overlay": f"examples/{gid}-overlay.png",
            "csv": f"examples/{gid}.csv",
            "preview": _preview_rows(csv_path, max_rows=5),
            "image_size": [int(src_small.shape[1]), int(src_small.shape[0])],
            "elapsed_s": round(time.time() - t0, 2),
        })
        results.append(summary)
        print(f"  {summary['elapsed_s']}s, {len(summary['series'])} series, warnings={len(summary['warnings'])}")

    with open(EX_DIR / "gallery.json", "w") as f:
        json.dump({
            "checkpoint": str(CKPT.relative_to(SITE.parent)),
            "ocr": str(OCR.relative_to(SITE.parent)),
            "tta": "shift",
            "generated": time.strftime("%a %d %b %Y, %H:%M %Z"),
            "entries": results,
        }, f, indent=2, default=str)
    print(f"\nWrote gallery.json with {len(results)} entries.")


if __name__ == "__main__":
    main()
