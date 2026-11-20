"""Post-processing for non-pixel styles (hand-painted, anime cel, comic ink): no grid, no palette.

Chroma key + despill (same rules as the pixel path), specks removed, then ONE scale factor for the
whole clip (median sprite height -> target height) so the motion is never rescaled frame by frame.
Resizing is done on premultiplied colour, which keeps the soft anti-aliased edge free of the green
fringe a straight resize of keyed pixels would pull in.
"""
from __future__ import annotations

import cv2
import numpy as np

from . import chroma


def _height(rgba: np.ndarray) -> int:
    ys = np.where((rgba[..., 3] > 0).any(1))[0]
    return int(ys[-1] - ys[0] + 1) if len(ys) else 0


def process(frames: list[np.ndarray], target_height: int, despill: str = "all", speck_px: int = 16) -> tuple[list[np.ndarray], float]:
    """RGB/RGBA frames -> RGBA frames scaled so the median sprite is `target_height` px tall.
    Returns (frames, scale)."""
    keyed = []
    for f in frames:
        rgba = chroma.key(f[..., :3], despill=despill) if f.shape[2] == 3 or (f[..., 3] == 255).all() else f.copy()
        keyed.append(chroma.remove_specks(rgba, speck_px) if speck_px else rgba)
    heights = [h for h in map(_height, keyed) if h]
    if not heights:
        raise ValueError("no sprite found in the frames (nothing left after the chroma key)")
    k = target_height / float(np.median(heights))
    out = []
    for f in keyed:
        h, w = f.shape[:2]
        size = (max(1, round(w * k)), max(1, round(h * k)))
        a = f[..., 3:4].astype(np.float32) / 255.0
        pre = f[..., :3].astype(np.float32) * a                       # premultiplied colour
        interp = cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC
        pre = cv2.resize(pre, size, interpolation=interp)
        a = np.clip(cv2.resize(a, size, interpolation=interp), 0, 1)
        if a.ndim == 2:
            a = a[..., None]
        rgb = np.where(a > 1e-3, pre / np.maximum(a, 1e-3), 0)
        alpha = np.where(a < 0.03, 0, a)                             # drop near-invisible haze
        out.append(np.dstack([np.clip(rgb, 0, 255), alpha * 255]).round().astype(np.uint8))
    return out, k
