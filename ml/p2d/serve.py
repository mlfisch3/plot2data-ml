"""A minimal local page for trying the learned pipeline on your own screenshots.

    python -m p2d.serve --ckpt runs/v2/best.pt --ocr runs/ocr1/best.pt [--port 8417]

Then open http://localhost:8417, and drop, pick or paste an image. The page
shows the extraction drawn over the image, what was read off each axis, and the
numbers, with a CSV to download. Nothing leaves the machine. This is a test
bench, not the app: the app in ../src is where the models are meant to end up.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

from .evaluate import draw, load_net
from .ocr import load_reader
from .pipeline import run, to_data, write_csv

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>plot2data-ml test bench</title>
<style>
:root { --bg:#f6f7f9; --fg:#1d2330; --muted:#5b6577; --card:#fff; --line:#d9dee7; --accent:#2b5fd9; }
@media (prefers-color-scheme: dark) { :root { --bg:#14171c; --fg:#e6e9ef; --muted:#9aa4b5; --card:#1c2027; --line:#2d333d; --accent:#7aa2ff; } }
* { box-sizing: border-box; }
body { margin:0; font:15px/1.45 system-ui, sans-serif; background:var(--bg); color:var(--fg); }
main { max-width:1200px; margin:0 auto; padding:16px; }
h1 { font-size:20px; margin:4px 0 12px; }
#drop { border:2px dashed var(--line); border-radius:10px; padding:24px; text-align:center; color:var(--muted); background:var(--card); }
#drop.over { border-color:var(--accent); color:var(--fg); }
.row { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin:12px 0; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px; margin:12px 0; }
.panel { background:#fff; border-radius:6px; }
img { max-width:100%; height:auto; display:block; }
table { border-collapse:collapse; font-variant-numeric:tabular-nums; font-size:13px; }
td, th { border-bottom:1px solid var(--line); padding:3px 10px; text-align:right; }
.scroll { max-height:340px; overflow:auto; }
.warn { color:#b35a00; }
button, select, input { font:inherit; color:inherit; }
input[type=number] { background:var(--card); border:1px solid var(--line); border-radius:6px; padding:3px 6px; }
a { color:var(--accent); }
caption { text-align:left; color:var(--muted); padding:8px 0 4px; white-space:nowrap; }
#table { display:flex; gap:24px; flex-wrap:wrap; align-items:flex-start; }
code { font-size:13px; }
[hidden] { display:none !important; }
</style></head>
<body><main>
<h1>plot2data-ml test bench</h1>
<div id="drop">Drop a chart image here, paste one (Ctrl+V), or <input type="file" id="file" accept="image/*"></div>
<div class="row">
  <label>Curve sampling step (px): <input id="step" type="number" min="0.5" step="0.5" placeholder="auto" style="width:7em"></label>
  <span id="status"></span>
</div>
<div id="out" hidden>
  <div class="card"><div class="panel"><img id="overlay" alt="The extraction drawn over the image"></div>
    <p style="color:var(--muted);margin:8px 0 0">Faded source image; extracted lines and markers drawn in colours unlike the chart's own; red crosses are the ticks used; blue boxes the labels read; orange the plot frame.</p></div>
  <div class="card" id="axes"></div>
  <div class="card"><div class="row"><strong>Numbers</strong><a id="csv" download="extracted.csv">Download CSV</a></div><div class="scroll" id="table"></div></div>
</div>
</main>
<script>
const $ = (id) => document.getElementById(id);
async function send(blob) {
  $('status').textContent = 'Reading the chart...';
  const step = $('step').value;
  const r = await fetch('/analyse' + (step ? '?step=' + encodeURIComponent(step) : ''), { method: 'POST', body: blob });
  const j = await r.json();
  if (!r.ok) { $('status').textContent = 'Failed: ' + j.error; return; }
  $('status').textContent = '';
  $('out').hidden = false;
  $('overlay').src = 'data:image/png;base64,' + j.overlay;
  const ax = (name, a) => a ? `<p><strong>${name} axis</strong>: ${a.scale}${a.date ? ', dates' : ''}; read ${a.ticks.map(t => `<code>${t[0]}</code>`).join(' ')}</p>` : `<p class="warn"><strong>${name} axis</strong>: not calibrated</p>`;
  $('axes').innerHTML = ax('x', j.x_axis) + ax('y', j.y_axis) + j.warnings.map(w => `<p class="warn">${w}</p>`).join('');
  $('csv').href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(j.csv);
  $('table').innerHTML = j.tables.map(t => `<table><caption>${t.name}: ${t.note}</caption><tr><th>x</th><th>${t.name}</th></tr>` +
    t.rows.slice(0, 2000).map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('') + '</table>').join('');
}
$('file').onchange = (e) => e.target.files[0] && send(e.target.files[0]);
const d = $('drop');
d.ondragover = (e) => { e.preventDefault(); d.classList.add('over'); };
d.ondragleave = () => d.classList.remove('over');
d.ondrop = (e) => { e.preventDefault(); d.classList.remove('over'); const f = e.dataTransfer.files[0]; if (f) send(f); };
document.onpaste = (e) => { for (const it of e.clipboardData.items) if (it.type.startsWith('image/')) { send(it.getAsFile()); break; } };
</script></body></html>
"""


def make_handler(net, reader):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            if not self.path.startswith("/analyse"):
                return self._send(404, b"{}", "application/json")
            n = int(self.headers.get("Content-Length", 0))
            data = np.frombuffer(self.rfile.read(n), np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                return self._send(400, json.dumps({"error": "not an image"}).encode(), "application/json")
            img = img[..., ::-1].copy()
            step = None
            if "step=" in self.path:
                try:
                    step = float(self.path.split("step=")[1].split("&")[0])
                except ValueError:
                    step = None
            try:
                res = run(net, reader, img)
                if step:
                    res.series = to_data(res.ex, res.xfit, res.yfit, step_px=step)
                with tempfile.NamedTemporaryFile("r", suffix=".csv", delete=False) as tmp:
                    path = tmp.name
                write_csv(res, path)
                csv = open(path).read()
                os.unlink(path)
                ok, png = cv2.imencode(".png", draw(img, res.ex)[..., ::-1])
                tables = []
                for s in res.series:
                    pts = s.get("sampled") if s["kind"] == "line" else s.get("markers")
                    if pts is None:
                        continue
                    note = f"curve, uniform step {s['step_px']:.2f} px" if s["kind"] == "line" else "one point per marker"
                    tables.append({"name": s["name"], "note": note, "rows": [[f"{x:.6g}", f"{y:.6g}"] for x, y in pts]})
                body = {
                    "tables": tables,
                    "overlay": base64.b64encode(png.tobytes()).decode(),
                    "csv": csv,
                    "warnings": res.warnings,
                    "x_axis": res.xfit and {"scale": res.xfit.scale, "date": res.date_axes.get("x", False),
                                            "ticks": [(r[1], r[3]) for r in sorted(res.tick_reads["x"])]},
                    "y_axis": res.yfit and {"scale": res.yfit.scale, "date": res.date_axes.get("y", False),
                                            "ticks": [(r[1], r[3]) for r in sorted(res.tick_reads["y"], reverse=True)]},
                }
                self._send(200, json.dumps(body, default=str).encode(), "application/json")
            except Exception as e:  # report, keep serving
                self._send(500, json.dumps({"error": repr(e)}).encode(), "application/json")

        def log_message(self, *args):
            pass

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--port", type=int, default=8417)
    a = ap.parse_args()
    net, reader = load_net(a.ckpt), load_reader(a.ocr)
    print(f"http://localhost:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(net, reader)).serve_forever()


if __name__ == "__main__":
    main()
