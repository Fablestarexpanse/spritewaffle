"""Palette assignment with temporal hysteresis (anti-flicker)."""
from __future__ import annotations

import numpy as np


def _pass(lab, alpha, pal, threshold, prev):
    out = np.full(alpha.shape, -1, int)
    for f in range(len(lab)):
        d = np.linalg.norm(lab[f][..., None, :] - pal, axis=-1)       # (h,w,k)
        best = d.argmin(-1)
        if prev is not None and threshold > 0:
            keep = prev >= 0
            pi = np.where(keep, prev, 0)
            d_prev = np.take_along_axis(d, pi[..., None], -1)[..., 0]
            d_best = np.take_along_axis(d, best[..., None], -1)[..., 0]
            best = np.where(keep & (d_prev - d_best < threshold), pi, best)
        out[f] = np.where(alpha[f], best, -1)
        prev = out[f]
    return out


def assign(lab: np.ndarray, alpha: np.ndarray, pal: np.ndarray, threshold: float = 0.03,
           loop: bool = False) -> np.ndarray:
    """Map Oklab frames (F,h,w,3) to palette indices (F,h,w); -1 where transparent.

    A cell keeps its previous frame's index unless another colour is closer by more than
    `threshold` (Oklab distance). With loop=True, a warm-up pass seeds frame 0 from the last frame
    so the loop seam doesn't pop.
    """
    if loop and len(lab) > 1:
        warm = _pass(lab, alpha, pal, threshold, None)
        return _pass(lab, alpha, pal, threshold, warm[-1])
    return _pass(lab, alpha, pal, threshold, None)
