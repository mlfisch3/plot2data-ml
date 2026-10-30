# plot2data-ml showcase site

A static project showcase.
The gallery, the scoreboard, the pipeline diagram and the research story live in
`index.html`, `style.css`, `script.js`.
Numbers come from `../INTEGRATION-REPORT.md` and `../ml/RESULTS.md`.
Images and CSVs come from one real pass of the integrated pipeline over 15 charts,
written by `_build.py` on Fri 30 Oct 2026.

## Open it

The site is static and reads everything over `fetch` from the same folder,
so a static server is the simplest way.

```sh
python -m http.server 8080 --directory site
```

Then open [http://localhost:8080/](http://localhost:8080/).

Opening `site/index.html` directly from `file://` works too, except that some
browsers refuse `fetch("examples/gallery.json")` under `file://` for security.
If the gallery stays empty, use the HTTP server instead.

## Try it live

The live demo wants the backend running too.
The convenience wrapper does both and opens the browser:

```sh
./site/serve.sh
```

Which is:

- `p2d.serve` on `:8417` (the integrated checkpoint and OCR, drop a chart to read it)
- A static HTTP server on `:8080` for this site

Ctrl-C stops both.

## Rebuilding the gallery

```sh
cd ml
source ../.venv/bin/activate
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python ../site/_build.py
python ../site/_charts.py
```

- `_build.py` runs the pipeline over the 15 gallery charts, writes source
  copies, overlays, CSVs and `examples/gallery.json`.
- `_charts.py` renders the four scoreboard figures as SVG into `assets/`.

The gallery entries, their labels, kinds and tags are declared in `_build.py:GALLERY`.
