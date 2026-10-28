// Chart.js through headless Chrome, driven by `chartjs_render.py` over stdin/stdout.
//
// One JSON spec per input line; one JSON result per output line:
//   {ok: true, passes: {full, grid, axis, ticklabels, text, legend, series_0, ...}, geom: {...}}
// where each pass is a PNG data URL of the canvas backing store (width * dpr by
// height * dpr) with everything but that group drawn transparent, so its alpha
// is that group's ink coverage, and `geom` holds the exact layout in CSS pixels:
// the chart area, every tick with its value, label text and pixel position, and
// every data point of every dataset in pixels. Layout is identical across passes
// because only colours change.
//
//   node chartjs_render.mjs  <  specs.jsonl

import { readFileSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..', '..', '..');
const CHART_JS = readFileSync(resolve(ROOT, 'node_modules/chart.js/dist/chart.umd.js'), 'utf8');
const CHROME = process.env.CHROME_PATH ?? '/usr/bin/google-chrome';

// Runs inside the page.
const PAGE_SCRIPT = `
const T = 'rgba(0,0,0,0)';
function vis(pass, group, colour) { return (pass === 'full' || pass === group) ? colour : T; }
function build(spec, pass) {
  const canvas = document.getElementById('c');
  canvas.width = spec.width; canvas.height = spec.height;
  canvas.style.width = spec.width + 'px'; canvas.style.height = spec.height + 'px';
  const full = pass === 'full';
  const datasets = spec.datasets.map((d, k) => {
    const show = full || pass === 'series_' + k;
    const col = show ? d.color : T;
    const fillCol = show ? d.fillColor : T;
    const ds = {
      label: d.label,
      data: d.x.map((x, i) => ({ x, y: d.y[i] })),
      borderColor: col, backgroundColor: d.kind === 'area' ? fillCol : col,
      borderWidth: d.kind === 'scatter' ? 0 : d.width,
      borderDash: d.dash, borderJoinStyle: d.join, borderCapStyle: d.cap,
      pointRadius: (d.kind === 'scatter' || d.kind === 'line+markers') ? d.pointRadius : 0,
      pointStyle: d.pointStyle, pointBackgroundColor: d.hollow ? T : col, pointBorderColor: col,
      pointBorderWidth: d.hollow ? d.pointBorderWidth : 0, pointHoverRadius: 0,
      showLine: d.kind !== 'scatter', tension: 0, fill: d.kind === 'area' ? 'origin' : false,
      stepped: d.stepped, spanGaps: false, clip: d.clip,
    };
    return ds;
  });
  const fg = (group) => vis(pass, group, spec.font.color);
  const scale = (ax) => {
    const o = {
      type: ax.type, min: ax.min, max: ax.max, position: ax.position, offset: false,
      bounds: 'data',
      grid: { display: true, color: vis(pass, 'grid', ax.grid ? ax.gridColor : T), lineWidth: ax.gridWidth,
              drawTicks: true, tickLength: ax.tickMarks ? ax.tickLength : 0,
              tickColor: vis(pass, 'axis', ax.tickMarks ? ax.borderColor : T), tickWidth: ax.borderWidth, drawOnChartArea: !!ax.grid,
              z: ax.gridZ },
      border: { display: true, color: vis(pass, 'axis', ax.border ? ax.borderColor : T), width: ax.borderWidth, z: ax.gridZ },
      ticks: { color: vis(pass, 'ticklabels', ax.tickFontColor), font: { family: spec.font.family, size: ax.tickFontSize },
               padding: ax.tickPadding, maxRotation: ax.maxRotation, minRotation: ax.minRotation, autoSkip: false,
               align: ax.align, crossAlign: ax.crossAlign, display: true,
               callback: function (value) { const l = ax.labels[String(value)]; return l === undefined ? '' : l; } },
      title: { display: !!ax.title, text: ax.title, color: fg('text'), font: { family: spec.font.family, size: ax.titleFontSize } },
    };
    if (ax.type === 'linear') {
      o.afterBuildTicks = (s) => { s.ticks = ax.tickValues.map((v) => ({ value: v })); };
    } else {
      // Logarithmic: keep Chart.js's own 1-2-5 ticks (so minor gridlines are drawn) and label what the spec labels.
      o.ticks.autoSkip = false;
      if (ax.decadeTicksOnly) {
        o.afterBuildTicks = (s) => { s.ticks = s.ticks.filter((t) => Math.abs(Math.log10(t.value) - Math.round(Math.log10(t.value))) < 1e-6); };
      }
    }
    return o;
  };
  const legendShow = !!spec.legend;
  const cfg = {
    type: 'scatter',
    data: { datasets },
    options: {
      responsive: false, animation: false, devicePixelRatio: spec.dpr, events: [],
      layout: { padding: spec.padding },
      font: { family: spec.font.family, size: spec.font.size },
      plugins: {
        legend: { display: legendShow, position: legendShow ? spec.legend.position : 'top', align: legendShow ? spec.legend.align : 'center',
                  labels: { color: fg('text'), boxWidth: legendShow ? spec.legend.boxWidth : 40, boxHeight: legendShow ? spec.legend.boxHeight : 12,
                            usePointStyle: legendShow ? spec.legend.usePointStyle : false,
                            font: { family: spec.font.family, size: legendShow ? spec.legend.fontSize : 12 },
                            generateLabels: (chart) => chart.data.datasets.map((d, k) => {
                              const sd = spec.datasets[k];
                              const show = pass === 'full' || pass === 'legend';
                              const c = show ? sd.color : T;
                              return { text: sd.label, fillStyle: show ? (sd.kind === 'area' ? sd.fillColor : sd.color) : T, strokeStyle: c,
                                       fontColor: fg('text'), lineWidth: sd.kind === 'scatter' ? 0 : sd.width, lineDash: sd.dash,
                                       pointStyle: sd.pointStyle, hidden: false, datasetIndex: k };
                            }) } },
        title: { display: !!spec.title, text: spec.title, color: fg('text'), align: spec.titleAlign,
                 font: { family: spec.font.family, size: spec.titleFontSize, weight: spec.titleWeight } },
        tooltip: { enabled: false },
      },
      scales: { x: scale(spec.x), y: scale(spec.y) },
    },
    plugins: [{
      id: 'bg',
      beforeDraw(chart) {
        if (pass !== 'full') return;
        const ctx = chart.ctx;
        ctx.save();
        ctx.fillStyle = spec.paper;
        ctx.fillRect(0, 0, chart.width, chart.height);
        if (spec.plotBg) {
          const a = chart.chartArea;
          ctx.fillStyle = spec.plotBg;
          ctx.fillRect(a.left, a.top, a.right - a.left, a.bottom - a.top);
        }
        ctx.restore();
      },
    }],
  };
  const chart = new Chart(canvas.getContext('2d'), cfg);
  return chart;
}
window.renderSpec = function (spec) {
  const passes = {};
  const names = ['full', 'grid', 'axis', 'ticklabels', 'text', 'legend'].concat(spec.datasets.map((_, k) => 'series_' + k));
  let geom = null;
  for (const name of names) {
    const chart = build(spec, name);
    const canvas = document.getElementById('c');
    passes[name] = canvas.toDataURL('image/png');
    if (name === 'full') {
      const a = chart.chartArea;
      const sc = (s) => ({
        min: s.min, max: s.max, type: s.type,
        ticks: s.ticks.map((t, i) => ({ value: t.value, label: Array.isArray(t.label) ? t.label.join(' ') : String(t.label ?? ''), px: s.getPixelForTick(i) })),
      });
      geom = {
        chartArea: { left: a.left, top: a.top, right: a.right, bottom: a.bottom },
        x: sc(chart.scales.x), y: sc(chart.scales.y),
        datasets: spec.datasets.map((d) => ({
          px: d.x.map((v) => chart.scales.x.getPixelForValue(v)),
          py: d.y.map((v) => chart.scales.y.getPixelForValue(v)),
        })),
        legend: chart.legend && spec.legend ? { left: chart.legend.left, top: chart.legend.top, right: chart.legend.right, bottom: chart.legend.bottom } : null,
        width: chart.width, height: chart.height, dpr: chart.currentDevicePixelRatio,
      };
    }
    chart.destroy();
  }
  return { passes, geom };
};
`;

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--force-device-scale-factor=1', '--font-render-hinting=none'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });
  await page.setContent(`<!doctype html><meta charset="utf-8"><style>html,body{margin:0;padding:0;background:#fff}canvas{display:block}</style>
<canvas id="c" width="800" height="500"></canvas><script>${CHART_JS}</script><script>${PAGE_SCRIPT}</script>`, { waitUntil: 'load' });
  const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of rl) {
    if (!line.trim()) continue;
    let out;
    try {
      const spec = JSON.parse(line);
      const r = await page.evaluate((s) => window.renderSpec(s), spec);
      out = { ok: true, ...r };
    } catch (e) {
      out = { ok: false, error: String(e && e.stack ? e.stack : e) };
    }
    process.stdout.write(JSON.stringify(out) + '\n');
  }
  await browser.close();
}

main().catch((e) => {
  process.stderr.write(String(e && e.stack ? e.stack : e) + '\n');
  process.exit(1);
});
