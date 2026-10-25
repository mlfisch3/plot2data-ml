"""Tick-label reader: a small convolutional CTC recogniser.

Trained on label crops cut out of the synthetic charts, whose text and box are
known exactly. Fully convolutional (no recurrent layers) so it exports cleanly
to ONNX and runs fast in a browser. Input is a grey crop scaled to 32 px high.

    python -m p2d.ocr train --data data/mpl-v1 --val data/mpl-val --run runs/ocr1
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import time

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, Dataset

cv2.setNumThreads(1)

# Digits and number decorations, plus what month names and dates need ("Jan '21", "2020-03", "Q1", "3/2020").
CHARS = "0123456789.,-+eE%$kKMBGTbnx^() JFAprySOcNDalgutvoQ/'"
BLANK = 0
H = 32
W = 192


def encode(s: str) -> list[int] | None:
    out = []
    for ch in s:
        i = CHARS.find(ch)
        if i < 0:
            return None
        out.append(i + 1)
    return out


def decode(logits: np.ndarray) -> tuple[str, float]:
    """Greedy CTC decode of T x C log-probabilities, with a confidence."""
    best = logits.argmax(-1)
    conf = float(np.exp(logits.max(-1)).min()) if len(best) else 0.0
    out, prev = [], BLANK
    for b in best:
        if b != prev and b != BLANK:
            out.append(CHARS[b - 1])
        prev = b
    return "".join(out), conf


def normalise_crop(gray: np.ndarray) -> np.ndarray:
    """Dark text on light paper, scaled to H, padded to W, values in [-1, 1]."""
    g = gray.astype(np.float32)
    if g.size == 0:
        return np.zeros((H, W), np.float32)
    border = np.concatenate([g[0], g[-1], g[:, 0], g[:, -1]])
    if np.median(border) < g.mean():  # light text on dark: invert
        g = 255 - g
    lo, hi = np.percentile(g, 1), np.percentile(g, 99)
    g = np.clip((g - lo) / max(hi - lo, 1), 0, 1)
    h, w = g.shape
    s = H / h
    nw = max(1, int(round(w * s)))
    if nw > W:
        s = W / w
        nw = W
    nh = max(1, int(round(h * s)))
    g = cv2.resize(g, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    out = np.ones((H, W), np.float32)
    y0 = (H - nh) // 2
    out[y0:y0 + nh, :nw] = g
    return out * 2 - 1


def crop(img: np.ndarray, box, pad: tuple[float, float, float, float] = (2, 2, 2, 2)) -> np.ndarray:
    x0 = int(np.floor(box[0] - pad[0]))
    y0 = int(np.floor(box[1] - pad[1]))
    x1 = int(np.ceil(box[2] + pad[2])) + 1
    y1 = int(np.ceil(box[3] + pad[3])) + 1
    hh, ww = img.shape[:2]
    return img[max(0, y0):min(hh, y1), max(0, x0):min(ww, x1)]


MARGIN = 8


def _cut_crops(path: str) -> list[tuple[np.ndarray, list[float], str]]:
    """Every readable tick label of one chart, cut with a margin, box relative to the cut."""
    m = json.load(open(path))
    img = None
    out = []
    for t in m["xticks"] + m["yticks"]:
        b = t["bbox"]
        # Rotated labels are left out: their boxes hold diagonal text.
        if (b[2] - b[0]) < (b[3] - b[1]) * 0.9 and len(t["text"]) > 1:
            continue
        if not t["text"] or encode(t["text"]) is None:
            continue
        if img is None:
            img = cv2.imread(path[:-5] + ".png", cv2.IMREAD_GRAYSCALE)
        if b[0] < 0 or b[1] < 0 or b[2] > img.shape[1] - 1 or b[3] > img.shape[0] - 1 or b[2] - b[0] < 2 or b[3] - b[1] < 2:
            continue  # a label cut off by the figure edge
        x0 = max(0, int(np.floor(b[0])) - MARGIN)
        y0 = max(0, int(np.floor(b[1])) - MARGIN)
        x1 = min(img.shape[1], int(np.ceil(b[2])) + MARGIN + 1)
        y1 = min(img.shape[0], int(np.ceil(b[3])) + MARGIN + 1)
        out.append((img[y0:y1, x0:x1].copy(), [b[0] - x0, b[1] - y0, b[2] - x0, b[3] - y0], t["text"]))
    return out


class LabelCrops(Dataset):
    """Tick-label crops, cut once from the charts and held in memory."""

    def __init__(self, roots, train: bool, limit_images: int | None = None, workers: int = 8):
        from multiprocessing import Pool

        roots = [roots] if isinstance(roots, str) else roots
        files = []
        for r in roots:
            files += sorted(glob.glob(os.path.join(r, "*.json")))
        if limit_images:
            files = files[:limit_images]
        with Pool(workers) as pool:
            parts = pool.map(_cut_crops, files, chunksize=64)
        self.items = [c for p in parts for c in p]
        self.train = train

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        img, b, text = self.items[i]
        if self.train:
            rng = random.Random()
            if rng.random() < 0.5:
                f = rng.uniform(0.5, 1.6)
                img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR)
                b = [v * f + (f - 1) * 0.5 for v in b]
            if rng.random() < 0.3:
                ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(25, 90)])
                img = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
            pad = tuple(rng.uniform(-0.5, 5) for _ in range(4))
            c = crop(img, b, pad)
            if rng.random() < 0.1:
                c = cv2.GaussianBlur(c, (0, 0), rng.uniform(0.3, 0.8))
        else:
            c = crop(img, b)
        x = normalise_crop(c)
        return torch.from_numpy(x)[None], torch.tensor(encode(text), dtype=torch.long), len(text)


def collate(batch):
    xs, ys, ls = zip(*batch)
    return torch.stack(xs), torch.cat(ys), torch.tensor(ls, dtype=torch.long)


class TickReader(nn.Module):
    """Conv feature extractor collapsing height, then a 1-D conv sequence model over width."""

    def __init__(self, n_cls: int = len(CHARS) + 1):
        super().__init__()

        def blk(i, o, pool):
            return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                                 nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                                 nn.MaxPool2d(pool))

        self.cnn = nn.Sequential(blk(1, 32, (2, 2)), blk(32, 64, (2, 1)), blk(64, 128, (2, 2)), blk(128, 160, (2, 1)))
        # 32 -> 2 high; 192 -> 48 wide
        self.seq = nn.Sequential(
            nn.Conv1d(160 * 2, 192, 3, padding=1), nn.BatchNorm1d(192), nn.ReLU(inplace=True),
            nn.Conv1d(192, 192, 5, padding=2), nn.BatchNorm1d(192), nn.ReLU(inplace=True),
            nn.Conv1d(192, 192, 5, padding=2), nn.BatchNorm1d(192), nn.ReLU(inplace=True),
            nn.Conv1d(192, n_cls, 1),
        )

    def forward(self, x):  # B x 1 x 32 x 192 -> B x T x C log-probs
        f = self.cnn(x)
        B, C, h, w = f.shape
        f = f.reshape(B, C * h, w)
        return F.log_softmax(self.seq(f).transpose(1, 2), -1)


def load_reader(path: str, device: str = "cuda") -> TickReader:
    m = TickReader().to(device)
    m.load_state_dict(torch.load(path, map_location=device)["model"])
    m.eval()
    return m


def read_crops(model: TickReader, crops: list[np.ndarray], device: str = "cuda") -> list[tuple[str, float]]:
    if not crops:
        return []
    x = torch.from_numpy(np.stack([normalise_crop(c) for c in crops]))[:, None].to(device)
    with torch.no_grad():
        lp = model(x).float().cpu().numpy()
    return [decode(l) for l in lp]


_NUM = re.compile(r"^\(?([-+]?)\$?([0-9][0-9,]*\.?[0-9]*|\.[0-9]+)(?:[eE]([-+]?[0-9]+))?(k|K|M|B|bn|G|T)?%?\)?$")
_POW = re.compile(r"^([-+]?[0-9.]*)\s*(?:x)?\s*10\^([-+]?[0-9]+)$")
SUFFIX = {"k": 1e3, "K": 1e3, "M": 1e6, "B": 1e9, "bn": 1e9, "G": 1e9, "T": 1e12}


def parse_value(s: str) -> float | None:
    """Printed tick text to a number: 1,000  -2.5  45%  $1.2M  3e5  10^3  2x10^4."""
    t = s.strip().replace(" ", "").replace("\u2212", "-").replace("\u2013", "-")
    if not t:
        return None
    neg = False
    if t.startswith("-$"):
        neg, t = True, t[2:]
    # "0^3" is a "10^3" whose "1" was cropped off; nothing else prints like that.
    t = re.sub(r"^0\^", "10^", t)
    m = _POW.match(t)
    if m:
        mant = m.group(1)
        mv = 1.0 if mant in ("", "+") else (-1.0 if mant == "-" else float(mant))
        return mv * 10.0 ** int(m.group(2))
    m = _NUM.match(t)
    if not m:
        return None
    sign, digits, exp, suf = m.groups()
    parts = digits.split(",")
    if len(parts) > 1 and not all(len(p) == 3 for p in parts[1:-1] + [parts[-1].split(".")[0]]):
        return None
    try:
        v = float(digits.replace(",", ""))
    except ValueError:
        return None
    if exp:
        v *= 10.0 ** int(exp)
    if suf:
        v *= SUFFIX[suf]
    if sign == "-" or neg:
        v = -v
    return v


def train(a) -> None:
    device = torch.device("cuda")
    tr = LabelCrops(a.data, train=True)
    va = LabelCrops(a.val, train=False)
    print(f"train crops {len(tr)}  val crops {len(va)}", flush=True)
    tl = DataLoader(tr, batch_size=128, shuffle=True, num_workers=a.workers, collate_fn=collate, drop_last=True,
                    persistent_workers=True)
    vl = DataLoader(va, batch_size=256, shuffle=False, num_workers=4, collate_fn=collate)
    m = TickReader().to(device)
    opt = torch.optim.AdamW(m.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=2e-3, total_steps=a.iters, pct_start=0.05)
    ctc = nn.CTCLoss(blank=BLANK, zero_infinity=True)
    os.makedirs(a.run, exist_ok=True)
    it, t0, best = 0, time.time(), 0.0
    while it < a.iters:
        for x, y, ln in tl:
            x, y = x.to(device), y.to(device)
            lp = m(x)
            T = lp.shape[1]
            loss = ctc(lp.transpose(0, 1), y, torch.full((x.shape[0],), T, dtype=torch.long), ln)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            it += 1
            if it % 200 == 0:
                print(f"it {it} loss {loss.item():.4f} {it / (time.time() - t0):.1f} it/s", flush=True)
            if it % 2000 == 0 or it == a.iters:
                acc = evaluate(m, vl, device)
                print(f"VAL it {it} exact {acc:.4f}", flush=True)
                st = {"model": m.state_dict(), "it": it, "acc": acc}
                torch.save(st, os.path.join(a.run, "last.pt"))
                if acc >= best:
                    best = acc
                    torch.save(st, os.path.join(a.run, "best.pt"))
                m.train()
            if it >= a.iters:
                break


def evaluate(m, vl, device) -> float:
    m.eval()
    ok = n = 0
    with torch.no_grad():
        for x, y, ln in vl:
            lp = m(x.to(device)).cpu().numpy()
            ys = y.tolist()
            off = 0
            for i, L in enumerate(ln.tolist()):
                truth = "".join(CHARS[c - 1] for c in ys[off:off + L])
                off += L
                ok += decode(lp[i])[0] == truth
                n += 1
    return ok / max(n, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--data", nargs="+", required=True)
    t.add_argument("--val", required=True)
    t.add_argument("--run", required=True)
    t.add_argument("--iters", type=int, default=20000)
    t.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "train":
        train(a)


if __name__ == "__main__":
    main()
