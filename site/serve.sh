#!/usr/bin/env bash
# Start the live p2d.serve backend on 8417 and open the showcase site at a tiny
# static server on 8080. The site links to http://localhost:8417/ as its demo.
# Ctrl-C stops both.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"

cd "$REPO/ml"
# shellcheck disable=SC1091
source "$REPO/.venv/bin/activate"

CKPT="runs/t5-chartjs/best.pt"
OCR="runs/ocr1/best.pt"

echo "Starting p2d.serve on :8417 (ckpt=$CKPT, ocr=$OCR)"
python -m p2d.serve --ckpt "$CKPT" --ocr "$OCR" --port 8417 &
BACKEND=$!

echo "Starting static site on :8080"
python -m http.server 8080 --directory "$REPO/site" &
STATIC=$!

cleanup() {
  echo
  echo "Stopping ..."
  kill "$BACKEND" "$STATIC" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM

sleep 1
# Open browser if we can (xdg-open on Linux).
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:8080/" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
  open "http://localhost:8080/" || true
fi

echo
echo "Site:    http://localhost:8080/"
echo "Backend: http://localhost:8417/   (drop a chart; the integrated reader lives here)"
echo
echo "Ctrl-C to stop."
wait
