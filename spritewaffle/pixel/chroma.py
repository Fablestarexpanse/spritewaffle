"""Conservative chroma key for flat #00FF00 backgrounds (rule 11).

1. Background colour = median of the border if it is near #00FF00 (handles video compression).
2. Key near-bg pixels that are connected to the border (loose tolerance).
3. Key enclosed pixels only if they are near-exact bg (strict tolerance) — e.g. gaps between legs.
4. Despill: in a thin band along the keyed edge, clamp G down to max(R, B).
A pixel is never removed just because it contains green.
"""
from __future__ import annotations

import cv2
import numpy as np

KEY = np.array([0, 255, 0], float)


def background_color(rgb: np.ndarray, max_dist: float = 90) -> np.ndarray:
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]).astype(float)
    med = np.median(border, axis=0)
    return med if np.abs(med - KEY).max() <= max_dist else KEY


def key(rgb: np.ndarray, loose_tol: float = 70, strict_tol: float = 30, despill_px: int = 2) -> np.ndarray:
    """RGB uint8 (H,W,3) -> RGBA uint8 with hard alpha and despilled edges."""
    rgb = np.ascontiguousarray(rgb[..., :3])
    bg = background_color(rgb)
    dist = np.abs(rgb.astype(float) - bg).max(-1)
    loose = (dist <= loose_tol).astype(np.uint8)
    n, lab = cv2.connectedComponents(loose, connectivity=4)
    border_labels = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    border_labels = border_labels[border_labels > 0]
    keyed = np.isin(lab, border_labels) | (dist <= strict_tol)

    out = np.dstack([rgb, np.where(keyed, 0, 255).astype(np.uint8)])
    if despill_px > 0:
        k = np.ones((3, 3), np.uint8)
        band = cv2.dilate(keyed.astype(np.uint8), k, iterations=despill_px).astype(bool) & ~keyed
        r, g, b = (out[..., i].astype(int) for i in range(3))
        cap = np.maximum(r, b)
        out[..., 1] = np.where(band & (g > cap), cap, g).astype(np.uint8)
    out[keyed, :3] = 0
    return out


def remove_specks(rgba: np.ndarray, min_px: int = 16) -> np.ndarray:
    """Drop opaque connected components smaller than min_px pixels."""
    opaque = (rgba[..., 3] > 0).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(opaque, connectivity=8)
    small = np.where(stats[:, cv2.CC_STAT_AREA] < min_px)[0]
    small = small[small > 0]
    out = rgba.copy()
    if len(small):
        m = np.isin(lab, small)
        out[m] = 0
    return out
