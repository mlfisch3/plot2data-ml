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
import math
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


def beam_decode(logits: np.ndarray, beam: int = 8, prune: float = -9.0) -> list[tuple[str, float]]:
    """CTC prefix beam search over T x C log-probabilities: the `beam` best strings with log P.

    Standard prefix search (Hannun et al.): every prefix carries the log
    probability of ending in blank and of ending in its last character, so
    repeats are collapsed exactly. Characters below `prune` nats at a time step
    are skipped, which keeps the search near linear in T.
    """
    T, C = logits.shape
    NEG = -1e30

    def lse(*xs):
        m = max(xs)
        if m <= NEG:
            return NEG
        return m + math.log(sum(math.exp(x - m) for x in xs))

    beams: dict[tuple[int, ...], tuple[float, float]] = {(): (0.0, NEG)}  # prefix -> (p_blank, p_nonblank)
    for t in range(T):
        lp = logits[t]
        chars = np.nonzero(lp > prune)[0]
        if lp[BLANK] <= prune:
            chars = np.concatenate([[BLANK], chars])
        nxt: dict[tuple[int, ...], tuple[float, float]] = {}

        def add(pref, pb, pnb):
            ob, onb = nxt.get(pref, (NEG, NEG))
            nxt[pref] = (lse(ob, pb), lse(onb, pnb))

        for pref, (pb, pnb) in beams.items():
            tot = lse(pb, pnb)
            for c in chars:
                c = int(c)
                p = float(lp[c])
                if c == BLANK:
                    add(pref, tot + p, NEG)
                    continue
                last = pref[-1] if pref else None
                if c == last:
                    add(pref, NEG, pnb + p)  # a repeat without a blank between: same string
                    add(pref + (c,), NEG, pb + p)
                else:
                    add(pref + (c,), NEG, tot + p)
        beams = dict(sorted(nxt.items(), key=lambda kv: -lse(*kv[1]))[:beam])
    out = [("".join(CHARS[c - 1] for c in pref), lse(*v)) for pref, v in beams.items()]
    out.sort(key=lambda s: -s[1])
    return out


def ctc_score(logits: np.ndarray, text: str) -> float:
    """log P(text | logits) under CTC: the forward algorithm over the blank-interleaved label."""
    lab = encode(text)
    if lab is None:
        return -1e30
    ext = [BLANK]
    for c in lab:
        ext += [c, BLANK]
    S = len(ext)
    T = logits.shape[0]
    if S > 2 * T + 1:
        return -1e30
    NEG = -1e30
    alpha = np.full(S, NEG)
    alpha[0] = logits[0, BLANK]
    if S > 1:
        alpha[1] = logits[0, ext[1]]
    for t in range(1, T):
        lp = logits[t]
        prev = alpha
        alpha = np.full(S, NEG)
        for s in range(S):
            cands = [prev[s]]
            if s >= 1:
                cands.append(prev[s - 1])
            if s >= 2 and ext[s] != BLANK and ext[s] != ext[s - 2]:
                cands.append(prev[s - 2])
            m = max(cands)
            if m > NEG:
                alpha[s] = m + math.log(sum(math.exp(c - m) for c in cands)) + lp[ext[s]]
    fin = [alpha[S - 1]] + ([alpha[S - 2]] if S > 1 else [])
    m = max(fin)
    return float(m + math.log(sum(math.exp(c - m) for c in fin))) if m > NEG else NEG


def normalise_crop(gray: np.ndarray) -> np.ndarray:
    """Dark text on light paper, scaled to H, padded to W, values in [-1, 1].

    A crop much taller than wide is a 90-degree rotated label (matplotlib rotates
    counter-clockwise, so text reads bottom-to-top in the crop); rotating the crop
    90 degrees clockwise brings the text back to its normal reading order before
    the reader, which was trained on horizontal text, sees it.
    """
    g = gray.astype(np.float32)
    if g.size == 0:
        return np.zeros((H, W), np.float32)
    h, w = g.shape
    if h > 1.5 * w and h > 10:
        g = np.rot90(g, k=-1)  # 90 degrees clockwise
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


def read_logits(model: TickReader, crops: list[np.ndarray], device: str | None = None) -> list[np.ndarray]:
    """The reader's T x C log-probabilities for each crop."""
    if not crops:
        return []
    if device is None:
        device = next(model.parameters()).device
    x = torch.from_numpy(np.stack([normalise_crop(c) for c in crops]))[:, None].to(device)
    with torch.no_grad():
        lp = model(x).float().cpu().numpy()
    return list(lp)


def read_crops(model: TickReader, crops: list[np.ndarray], device: str | None = None) -> list[tuple[str, float]]:
    return [decode(l) for l in read_logits(model, crops, device)]


# Numeric parse. Strict recognises standard tick-label shapes (1,000 -2.5 45%
# $1.2M 3e5 10^3 2x10^4). `_NUM` includes OWID-style word suffixes (billion,
# trillion, million, thousand, bn, mn, plus single-letter SI). Lax allows any
# tail after the suffix and is the fallback for OWID-garbled OCR ("0bo 15"
# from "0 births", "80,000c kw" from "80,000 kWh", "500b   n 1" from
# "500 billion t"); the caller opts in only when strict yielded nothing.
_NUM = re.compile(
    r"^\(?([-+]?)\$?\s*"
    r"([0-9][0-9,]*\.?[0-9]*|\.[0-9]+)"
    r"(?:[eE]([-+]?[0-9]+))?"
    r"\s*"
    r"(billion|trillion|million|thousand|bn|mn|k|K|M|B|G|T|b|m|t)?"
    r"(?:\s+[a-zA-Z\.][a-zA-Z \.]*)?"
    r"%?\s*\)?$"
)
_NUM_LAX = re.compile(
    r"^\(?([-+]?)\$?\s*"
    r"([0-9][0-9,]*\.?[0-9]*|\.[0-9]+)"
    r"(?:[eE]([-+]?[0-9]+))?"
    r"\s*"
    r"(billion|trillion|million|thousand|bn|mn|k|K|M|B|G|T|b|m|t)?"
    r"(?:.*)?$"
)
_POW = re.compile(r"^([-+]?[0-9.]*)\s*(?:x)?\s*10\^([-+]?[0-9]+)$")
SUFFIX = {
    "k": 1e3, "K": 1e3, "thousand": 1e3,
    "m": 1e6, "M": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "B": 1e9, "G": 1e9, "bn": 1e9, "billion": 1e9,
    "T": 1e12, "trillion": 1e12,
    "t": 1.0,  # tonne: unit, no scale
}


def parse_value(s: str, lax: bool = False) -> float | None:
    """Printed tick text to a number: 1,000  -2.5  45%  $1.2M  3e5  10^3  2x10^4.

    Also handles OWID-style noise via the strict regex's trailing-noise clause:
    "500 billion t" (ocr `500b   n 1`) -> 5e11; "25 t" -> 25; "$1 billion" -> 1e9.
    `lax` is a final fallback that drops all tail restrictions ("0bo 15" -> 0,
    "80,000c kw" -> 80000); the caller opts in only when strict yielded nothing,
    to avoid poisoning an axis with half-noisy labels.
    """
    t = s.replace("\u2212", "-").replace("\u2013", "-").strip()
    if not t:
        return None
    neg = False
    # "-$1,200" and "- $1,200" strip the leading sign+currency so the body regex matches.
    if t.startswith(("-$", "- $")):
        neg = True
        t = t[1:].lstrip().lstrip("$")
    # "0^3" is a "10^3" whose "1" was cropped off; nothing else prints like that.
    t_pow = re.sub(r"^0\^", "10^", t.replace(" ", ""))
    m = _POW.match(t_pow)
    if m:
        mant = m.group(1)
        try:
            mv = 1.0 if mant in ("", "+") else (-1.0 if mant == "-" else float(mant))
            return mv * 10.0 ** int(m.group(2))
        except (ValueError, OverflowError):
            return None
    m = _NUM.match(t)
    tail = ""
    if not m:
        if not lax:
            return None
        m = _NUM_LAX.match(t)
        if not m:
            return None
        tail = m.group(5) or ""
        # The tail must start with a letter: "0bo 15" is a unit-tail OCR of "0 births", while
        # a continuation of digits ("1 50") is almost never one label and must not be matched
        # as the leading number alone. A clear SI suffix anchors the match enough that a
        # short trailing-digit tail (OCR often adds a "1" for a dropped "t") is still noise.
        if not tail or (not tail[0].isalpha() and not (m.group(4) in ("bn", "M", "B", "G", "T"))):
            return None
    sign, digits, exp, suf = m.groups()[:4]
    # In lax mode, a single-letter SI prefix (k/K/M/B/G/T) that touches a letter tail is
    # almost always the first letter of a unit word ("kWh" is kilowatt-hour, not kilo-); the
    # two-letter "bn" is unambiguously billion so stays.
    if tail and suf and suf != "bn" and tail[0].isalpha():
        suf = None
    parts = digits.split(",")
    if len(parts) > 1 and not all(len(p) == 3 for p in parts[1:-1] + [parts[-1].split(".")[0]]):
        return None
    try:
        v = float(digits.replace(",", ""))
        if exp:
            v *= 10.0 ** int(exp)
    except (ValueError, OverflowError):
        return None
    if suf:
        v *= SUFFIX[suf]
    if not math.isfinite(v):
        return None
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
