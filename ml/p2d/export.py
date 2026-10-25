"""Export PlotNet and the tick reader to ONNX, for onnxruntime-web in the app.

    python -m p2d.export --ckpt runs/v1/best.pt --ocr runs/ocr1/best.pt --out out/onnx [--fp16]

PlotNet takes a 1 x 3 x 512 x 768 float image normalised with ImageNet mean and
std, and returns softmaxed classes, sigmoid heat maps and raw embeddings. The
tick reader takes N x 1 x 32 x 192 crops in [-1, 1] and returns N x T x C
log-probabilities for greedy CTC decoding.
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import torch

from .data import CANVAS_H, CANVAS_W
from .model import PlotNet, PlotNetExport
from .ocr import TickReader


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--out", default="out/onnx")
    ap.add_argument("--fp16", action="store_true", help="store weights in half precision (half the download)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    st = torch.load(a.ckpt, map_location="cpu")
    net = PlotNet(st.get("encoder", "resnet34"), pretrained=False)
    net.load_state_dict(st["model"])
    m = PlotNetExport(net).eval()
    x = torch.zeros(1, 3, CANVAS_H, CANVAS_W)
    p = os.path.join(a.out, "plotnet.onnx")
    torch.onnx.export(m, (x,), p, input_names=["image"], output_names=["sem", "heat", "emb"], opset_version=17,
                      dynamo=False)
    r = TickReader()
    r.load_state_dict(torch.load(a.ocr, map_location="cpu")["model"])
    r.eval()
    q = os.path.join(a.out, "tickreader.onnx")
    torch.onnx.export(r, (torch.zeros(4, 1, 32, 192),), q, input_names=["crops"], output_names=["logprobs"],
                      dynamic_axes={"crops": {0: "n"}, "logprobs": {0: "n"}}, opset_version=17, dynamo=False)
    if a.fp16:
        import onnx
        from onnxruntime.transformers.float16 import convert_float_to_float16

        for path in (p, q):
            mdl = convert_float_to_float16(onnx.load(path), keep_io_types=True)
            onnx.save(mdl, path)
    # A parity check against PyTorch on a random input.
    import onnxruntime as ort

    s = ort.InferenceSession(p, providers=["CPUExecutionProvider"])
    xi = torch.randn(1, 3, CANVAS_H, CANVAS_W)
    with torch.no_grad():
        ref = m(xi)
    got = s.run(None, {"image": xi.numpy()})
    for name, g, rr in zip(["sem", "heat", "emb"], got, ref):
        print(f"{name}: max |onnx - torch| = {np.abs(g - rr.numpy()).max():.2e}")
    for path in (p, q):
        print(f"{path}: {os.path.getsize(path) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
