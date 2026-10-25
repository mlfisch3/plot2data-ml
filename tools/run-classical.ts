/**
 * Run the classical engine over a directory of chart images and dump what it
 * extracted, in data units, as JSON. This is the baseline the learned model in
 * `ml/` is scored against, on exactly the same images and the same metric.
 *
 *   node --experimental-strip-types tools/run-classical.ts <dir> <out.json> [limit]
 */

import { readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { analyse, buildSeries } from '../src/engine/index.ts';
import { loadImage } from '../test/helpers/load-image.ts';
import { NodeOcr } from '../test/helpers/node-ocr.ts';

const [dir, outPath, limitArg] = process.argv.slice(2);
const limit = limitArg ? Number(limitArg) : Infinity;
const files = readdirSync(dir)
  .filter((f) => /^\d+\.png$/.test(f))
  .sort()
  .slice(0, limit);

const ocr = new NodeOcr();
await ocr.start();
const results: Record<string, unknown> = {};
let i = 0;
for (const f of files) {
  const id = f.replace('.png', '');
  const t0 = Date.now();
  try {
    const img = loadImage(join(dir, f));
    const analysis = await analyse(img, { ocr });
    const series = buildSeries(analysis, { resample: { kind: 'native' } });
    results[id] = {
      ms: Date.now() - t0,
      frame: analysis.frame.rect,
      xScale: analysis.calibration.x.scale,
      yScale: analysis.calibration.y.scale,
      series: series.map((s) => ({ mode: s.mode, points: s.points.map((p) => [p.x, p.y]) })),
      warnings: analysis.warnings.map((w) => w.code),
    };
  } catch (err: unknown) {
    results[id] = { error: String((err as Error).message ?? err) };
  }
  i++;
  if (i % 25 === 0) process.stderr.write(`${i}/${files.length}\n`);
}
await ocr.stop?.();
writeFileSync(outPath, JSON.stringify(results));
process.exit(0);
