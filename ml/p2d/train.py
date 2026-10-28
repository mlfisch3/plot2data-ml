"""Train PlotNet.

    python -m p2d.train --data data/mpl-v1 --val data/mpl-val --run runs/v1 --iters 30000
"""

from __future__ import annotations

import argparse
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
import json
import math
import time

import torch
from torch.utils.data import DataLoader

from .data import PlotDataset, to_device
from .losses import plotnet_loss
from .model import PlotNet


def evaluate(net, loader, device, max_batches: int = 40) -> dict:
    net.eval()
    agg: dict[str, float] = {}
    n = 0
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for i, b in enumerate(loader):
            if i >= max_batches:
                break
            b = to_device(b, device)
            out = net(b["image"])
            loss, parts = plotnet_loss(out, b)
            parts["loss"] = loss.item()
            for k, v in parts.items():
                agg[k] = agg.get(k, 0.0) + v
            n += 1
    net.train()
    return {k: v / max(n, 1) for k, v in agg.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--val", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--encoder", default="resnet34")
    ap.add_argument("--iters", type=int, default=30000)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=6e-4)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--init", default=None, help="weights to start from")
    ap.add_argument("--eval-every", type=int, default=1000)
    a = ap.parse_args()

    os.makedirs(a.run, exist_ok=True)
    json.dump(vars(a), open(os.path.join(a.run, "args.json"), "w"), indent=1)
    device = torch.device("cuda")
    torch.backends.cudnn.benchmark = True

    train_ds = PlotDataset(a.data, train=True)
    val_ds = PlotDataset(a.val, train=False)
    print(f"train {len(train_ds)}  val {len(val_ds)}", flush=True)
    tl = DataLoader(train_ds, batch_size=a.batch, shuffle=True, num_workers=a.workers, pin_memory=True,
                    drop_last=True, persistent_workers=True, prefetch_factor=4)
    vl = DataLoader(val_ds, batch_size=a.batch, shuffle=False, num_workers=4, pin_memory=True)

    net = PlotNet(a.encoder).to(device).to(memory_format=torch.channels_last)
    if a.init:
        fresh = net.load_weights(torch.load(a.init, map_location=device)["model"])
        if fresh:
            print(f"fresh (not in --init): {sorted(set(k.split('.')[0] for k in fresh))}", flush=True)
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=1e-4)
    warm = 500

    def lr_at(it: int) -> float:
        if it < warm:
            return a.lr * (it + 1) / warm
        p = (it - warm) / max(1, a.iters - warm)
        return a.lr * (0.02 + 0.98 * 0.5 * (1 + math.cos(math.pi * p)))

    log = open(os.path.join(a.run, "log.jsonl"), "a")
    it = 0
    best = float("inf")
    t0 = time.time()
    run_parts: dict[str, float] = {}
    t_data = t_step = 0.0
    while it < a.iters:
        tw = time.time()
        for b in tl:
            if it >= a.iters:
                break
            ts = time.time()
            t_data += ts - tw
            for g in opt.param_groups:
                g["lr"] = lr_at(it)
            b = to_device(b, device)
            img = b["image"].contiguous(memory_format=torch.channels_last)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                out = net(img)
            loss, parts = plotnet_loss(out, b)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
            opt.step()
            parts["loss"] = loss.item()
            for k, v in parts.items():
                run_parts[k] = 0.98 * run_parts.get(k, v) + 0.02 * v
            it += 1
            tw = time.time()
            t_step += tw - ts
            if it % 100 == 0:
                rate = it / (time.time() - t0)
                print(f"it {it}  {rate:.2f} it/s  data {t_data / it:.2f}s step {t_step / it:.2f}s  lr {lr_at(it):.2e}  " +
                      "  ".join(f"{k} {v:.4f}" for k, v in run_parts.items()), flush=True)
            if it % a.eval_every == 0 or it == a.iters:
                v = evaluate(net, vl, device)
                rec = {"it": it, "time": time.time() - t0, "train": dict(run_parts), "val": v}
                log.write(json.dumps(rec) + "\n")
                log.flush()
                print("VAL", it, "  ".join(f"{k} {x:.4f}" for k, x in v.items()), flush=True)
                state = {"model": net.state_dict(), "it": it, "encoder": a.encoder, "val": v}
                torch.save(state, os.path.join(a.run, "last.pt"))
                if v["loss"] < best:
                    best = v["loss"]
                    torch.save(state, os.path.join(a.run, "best.pt"))


if __name__ == "__main__":
    main()
