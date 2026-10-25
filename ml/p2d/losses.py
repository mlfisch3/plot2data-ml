"""Losses for PlotNet."""

from __future__ import annotations

import torch
import torch.nn.functional as F

# Background is most pixels; data ink and tick labels are what matter.
SEM_WEIGHTS = [0.4, 3.0, 2.0, 1.5, 1.0, 2.0, 1.0]
HEAT_WEIGHTS = [2.0, 1.5, 0.5, 1.5, 1.5, 1.0]


def quality_focal(logits: torch.Tensor, target: torch.Tensor, beta: float = 2.0) -> torch.Tensor:
    """Focal loss for soft targets (Li et al., GFL): BCE scaled by |p - t|^beta.

    Normalised per channel by the target mass over the whole batch, so a long
    curve and a few ticks weigh alike, and an image with nothing in a channel
    (a scatter plot has no line) still counts without dividing by nothing.
    """
    p = torch.sigmoid(logits)
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    loss = bce * (p - target).abs().pow(beta)
    mass = target.sum(dim=(0, 2, 3)).clamp(min=10.0)
    return loss.sum(dim=(0, 2, 3)) / mass  # C


def discriminative(emb: torch.Tensor, ids: torch.Tensor, dv: float = 0.5, dd: float = 3.0, stride: int = 2):
    """De Brabandere et al. 2017: pull pixels to their instance mean, push means apart.

    All images of the batch at once: instance ids are offset per image, and the
    push term only compares means from the same image.
    """
    B, E = emb.shape[:2]
    emb = emb[:, :, ::stride, ::stride]
    ids = ids[:, ::stride, ::stride]
    m = ids > 0
    if not m.any():
        return emb.sum() * 0
    bidx = torch.arange(B, device=ids.device)[:, None, None].expand_as(ids)[m]
    e = emb.permute(0, 2, 3, 1)[m].float()
    key = bidx * 256 + ids[m]
    uniq, inv = torch.unique(key, return_inverse=True)
    K = len(uniq)
    sums = torch.zeros(K, E, device=e.device).index_add_(0, inv, e)
    cnt = torch.zeros(K, device=e.device).index_add_(0, inv, torch.ones_like(inv, dtype=torch.float))
    mu = sums / cnt[:, None]
    pull = F.relu((e - mu[inv]).norm(dim=1) - dv).pow(2)
    pull = (torch.zeros(K, device=e.device).index_add_(0, inv, pull) / cnt).mean()
    img = uniq // 256
    same = (img[:, None] == img[None, :]) & ~torch.eye(K, dtype=torch.bool, device=e.device)
    push = F.relu(2 * dd - torch.cdist(mu, mu)[same]).pow(2).mean() if same.any() else e.new_zeros(())
    reg = mu.norm(dim=1).mean() * 0.001
    return pull + push + reg


def plotnet_loss(out: dict, batch: dict) -> tuple[torch.Tensor, dict]:
    sem_w = torch.tensor(SEM_WEIGHTS, device=out["sem"].device)
    l_sem = F.cross_entropy(out["sem"].float(), batch["sem"], weight=sem_w)
    l_heat_c = quality_focal(out["heat"].float(), batch["heat"])  # C
    hw = torch.tensor(HEAT_WEIGHTS, device=l_heat_c.device)
    l_heat = (l_heat_c * hw).sum()
    l_emb = discriminative(out["emb"], batch["emb_id"])
    loss = l_sem + l_heat + 0.5 * l_emb
    parts = {"sem": l_sem.item(), "heat": l_heat.item(), "emb": l_emb.item()}
    for i, n in enumerate(["line", "marker", "vertex", "xtick", "ytick", "corner"]):
        parts["h_" + n] = l_heat_c[i].item()
    return loss, parts
