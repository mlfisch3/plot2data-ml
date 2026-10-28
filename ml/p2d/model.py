"""PlotNet: one fully convolutional network with three kinds of output.

- `sem`: per-pixel class (background, data ink, legend symbol, axis, grid,
  tick label, other text).
- `heat`: sigmoid heat maps whose ridges and peaks are the geometry we want at
  sub-pixel precision: series centre lines (through dashes and occlusions),
  marker centres, polyline vertices, labelled tick positions on the x and y
  axes, and the four plot-area corners.
- `emb`: a per-pixel embedding; pixels of the same series land close together,
  which is what separates series that share a colour or cross each other.
- `dir`: at every pixel of a series, where that series' centre line is in the
  next column and in the previous one (two vertical offsets, in units of
  `DIR_SCALE` pixels), which is what carries a trace through a crossing or a
  steep stretch where the embedding is ambiguous.

A U-Net over an ImageNet-pretrained ResNet, plus a small full-resolution stem:
the U-Net's last skip is at stride 2, and the targets are one pixel wide.
"""

from __future__ import annotations

import segmentation_models_pytorch as smp
import torch
from torch import nn

from .data import N_DIR, N_HEAT, N_SEM


def _head(c_in: int, c_out: int, bias: float = 0.0) -> nn.Conv2d:
    h = nn.Conv2d(c_in, c_out, 3, padding=1)
    nn.init.constant_(h.bias, bias)
    return h


class PlotNet(nn.Module):
    def __init__(self, encoder: str = "resnet34", emb_dim: int = 8, pretrained: bool = True, dir_head: bool = True):
        super().__init__()
        u = smp.Unet(encoder, encoder_weights="imagenet" if pretrained else None, classes=1,
                     decoder_channels=(256, 128, 64, 48, 32))
        self.encoder = u.encoder
        self.decoder = u.decoder
        self.stem = nn.Sequential(
            nn.Conv2d(3, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(inplace=True),
        )
        self.fuse = nn.Sequential(nn.Conv2d(32 + 16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(inplace=True))
        self.sem = _head(32, N_SEM)
        self.heat = _head(32, N_HEAT, bias=-4.0)
        self.emb = _head(32, emb_dim)
        self.emb_dim = emb_dim
        self.dir = _head(32, N_DIR) if dir_head else None

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        d = self.decoder(self.encoder(x))
        f = self.fuse(torch.cat([d, self.stem(x)], 1))
        out = {"sem": self.sem(f), "heat": self.heat(f), "emb": self.emb(f)}
        if self.dir is not None:
            out["dir"] = self.dir(f)
        return out

    def load_weights(self, state: dict) -> list[str]:
        """Load a checkpoint's weights; a head the checkpoint lacks keeps its fresh initialisation.

        Returns the names of the parameters that were not in the checkpoint.
        """
        missing, unexpected = self.load_state_dict(state, strict=False)
        if unexpected or any(not k.startswith("dir.") for k in missing):
            raise RuntimeError(f"checkpoint does not match the model: missing {missing}, unexpected {unexpected}")
        return list(missing)


class PlotNetExport(nn.Module):
    """The same network with activations applied, for ONNX: sem softmax, heat sigmoid."""

    def __init__(self, net: PlotNet):
        super().__init__()
        self.net = net

    def forward(self, x):
        o = self.net(x)
        out = (torch.softmax(o["sem"], 1), torch.sigmoid(o["heat"]), o["emb"])
        return out + (o["dir"],) if "dir" in o else out
