"""Test-time augmentation: the network run more than once, its maps fused.

A convolutional network with strided stages is not quite shift- or scale-
equivariant: the same chart half a pixel to the right, or a quarter smaller,
gets slightly different heat maps. Averaging the maps of a few such passes,
each warped back into the primary canvas, cancels that noise. Heat maps and
class probabilities fuse by the mean; the embedding stays that of the primary
pass, since each pass has its own embedding space.

Flips are not used: a mirrored chart has mirrored text, which the network has
never seen.
"""

from __future__ import annotations

import numpy as np
import torch
import cv2

from .data import MEAN, STD, apply, placement
from .extract import inv_affine


def _canvas(img: np.ndarray, M: np.ndarray, size: tuple[int, int]) -> torch.Tensor:
    cw, ch = size
    h, w = img.shape[:2]
    bg = np.full((ch, cw, 3), img[0, 0], np.float32)
    valid = cv2.warpAffine(np.ones((h, w), np.uint8), M, (cw, ch), flags=cv2.INTER_NEAREST)
    c = cv2.warpAffine(img, M, (cw, ch), flags=cv2.INTER_AREA if M[0, 0] < 1 else cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    c = np.where(valid[..., None] > 0, c, bg)
    x = (c - MEAN) / STD
    return torch.from_numpy(x.transpose(2, 0, 1).copy())[None]


def _infer(net, x: torch.Tensor, device: str) -> dict:
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=device == "cuda"):
        o = net(x.to(device))
    return {
        "sem": torch.softmax(o["sem"].float(), 1)[0].cpu().numpy(),
        "heat": torch.sigmoid(o["heat"].float())[0].cpu().numpy(),
        "emb": o["emb"].float()[0].cpu().numpy(),
    }


def passes_for(tta: str) -> list[tuple[str, float]]:
    """The extra passes a `tta` spec asks for: 'shift', 'scale', or 'shift+scale'."""
    out = []
    for name in tta.split("+"):
        if name == "shift":
            out.append(("shift", 0.5))
        elif name == "scale":
            out.append(("scale", 0.75))
        elif name:
            raise ValueError(f"unknown tta pass {name!r}")
    return out


def run_net_tta(net, img: np.ndarray, device: str = "cuda", native: bool = True, tta: str = "shift") -> tuple[dict, np.ndarray]:
    """Like `extract.run_net`, with the extra passes of `tta` fused in."""
    h, w = img.shape[:2]
    M, size = placement(w, h, native)
    out = _infer(net, _canvas(img, M, size), device)
    extra = passes_for(tta)
    if not extra:
        return out, M
    cw, ch = size
    sem_sum, heat_sum, n = out["sem"].copy(), out["heat"].copy(), 1
    for kind, f in extra:
        if kind == "shift":
            M2 = M.copy()
            M2[:, 2] += f
            size2 = size
        else:
            s = float(M[0, 0]) * f
            M2 = np.array([[s, 0, 0.5 * s - 0.5], [0, s, 0.5 * s - 0.5]], np.float64)
            size2 = (max(32, 32 * int(np.ceil(s * w / 32))), max(32, 32 * int(np.ceil(s * h / 32))))
        o2 = _infer(net, _canvas(img, M2, size2), device)
        # Canvas 2 -> canvas 1: A = M @ inv(M2).
        A = (np.vstack([M, [0, 0, 1]]) @ np.vstack([inv_affine(M2), [0, 0, 1]]))[:2]
        for k, acc in (("sem", sem_sum), ("heat", heat_sum)):
            for c in range(acc.shape[0]):
                acc[c] += cv2.warpAffine(o2[k][c], A, (cw, ch), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                         borderValue=float(out[k][c][0, 0]) if k == "sem" else 0.0)
        n += 1
    out["sem"] = sem_sum / n
    out["heat"] = heat_sum / n
    return out, M
