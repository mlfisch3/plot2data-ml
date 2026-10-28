"""Overlay the brainstormer's label_from_source boxes on the four 10^k crops."""
import json, os, sys
import numpy as np, cv2
from PIL import Image, ImageDraw

sys.path.insert(0, '/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis/ml')
from p2d.extract import label_from_source

D = '/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis/ml/data/mpl-val'
OUT = '/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis/ml/out/t1/crops'

for seed in (9000016, 9000021, 9000024, 9000074):
    meta = json.load(open(f'{D}/{seed:07d}.json'))
    img = cv2.imread(f'{D}/{seed:07d}.png')[..., ::-1].astype(np.float32)
    pa = meta['plot_area']
    H, W = img.shape[:2]
    for key in ('xticks', 'yticks'):
        txts = [t.get('text','') for t in meta[key]]
        if not any('10^' in t or ('e' in t.lower() and t[0].isdigit()) for t in txts):
            continue
        ticks = meta[key]
        p = np.sort(np.array([t['pos'] for t in ticks]))
        spacing = float(np.median(np.diff(p))) if len(p) > 1 else 60.0
        half = max(6.0, 0.48 * spacing)
        boxes = []
        for t in ticks:
            ax_, ay = t['anchor']
            if key == 'xticks':
                mid = (pa[1] + pa[3]) / 2
                outward = 1 if ay >= mid else -1
                b = label_from_source(img, t['pos'], ay, outward, True, half, extent=(pa[0], pa[2]))
            else:
                mid = (pa[0] + pa[2]) / 2
                outward = -1 if ax_ <= mid else 1
                b = label_from_source(img, t['pos'], ax_, outward, False, half, extent=(pa[1], pa[3]))
            boxes.append((t, b))
        # Load the already-made truebox crop; overlay red for computed box.
        name = f'{seed}-{key}-truebox.png'
        src = f'{OUT}/{name}'
        if not os.path.exists(src):
            continue
        im = Image.open(src)
        draw = ImageDraw.Draw(im)
        if key == 'xticks':
            dx = max(0, int(ticks[0]['anchor'][0] if False else pa[0]) - 10)
            dy = max(0, int(ticks[0]['anchor'][1]) - 5)
        else:
            dx = max(0, int(ticks[0]['anchor'][0]) - 130)
            dy = max(0, int(pa[1]) - 10)
        # Zoom 2x used in axis_crop.py
        for t, b in boxes[:6]:
            if b is None:
                continue
            x0 = (b[0] - dx) * 2
            y0 = (b[1] - dy) * 2
            x1 = (b[2] - dx) * 2
            y1 = (b[3] - dy) * 2
            draw.rectangle([x0, y0, x1, y1], outline='red', width=2)
        out = src.replace('-truebox.png', '-boxes-v244.png')
        im.save(out)
        print(f'wrote {out} - computed boxes (red) over true (green)')
        for t, b in boxes[:5]:
            print(f'  tick pos={t["pos"]:.1f} text="{t["text"]}" true_bbox={t["bbox"]} computed_box={b}')
