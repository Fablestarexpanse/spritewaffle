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


def _key_frame(frame: np.ndarray, despill: str, speck_px: int) -> np.ndarray:
    rgba = chroma.key(frame[..., :3], despill=despill) if frame.shape[2] == 3 or (frame[..., 3] == 255).all() else frame.copy()
    return chroma.remove_specks(rgba, speck_px) if speck_px else rgba


def _scale_frame(frame: np.ndarray, scale: float) -> np.ndarray:
    h, w = frame.shape[:2]
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    alpha = frame[..., 3:4].astype(np.float32) / 255.0
    pre = frame[..., :3].astype(np.float32) * alpha
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    pre = cv2.resize(pre, size, interpolation=interp)
    alpha = np.clip(cv2.resize(alpha, size, interpolation=interp), 0, 1)
    if alpha.ndim == 2:
        alpha = alpha[..., None]
    rgb = np.where(alpha > 1e-3, pre / np.maximum(alpha, 1e-3), 0)
    alpha = np.where(alpha < 0.03, 0, alpha)
    return np.dstack([np.clip(rgb, 0, 255), alpha * 255]).round().astype(np.uint8)


def reprocess_frame(frame: np.ndarray, scale: float, despill: str, speck_px: int = 16) -> np.ndarray:
    """Apply an existing clip scale to one frame with the normal painted-art processing."""
    return _scale_frame(_key_frame(frame, despill, speck_px), scale)


def process(frames: list[np.ndarray], target_height: int, despill: str = "all", speck_px: int = 16) -> tuple[list[np.ndarray], float]:
    """RGB/RGBA frames -> RGBA frames scaled so the median sprite is `target_height` px tall.
    Returns (frames, scale)."""
    keyed = [_key_frame(frame, despill, speck_px) for frame in frames]
    heights = [h for h in map(_height, keyed) if h]
    if not heights:
        raise ValueError("no sprite found in the frames (nothing left after the chroma key)")
    k = target_height / float(np.median(heights))
    return [_scale_frame(frame, k) for frame in keyed], k
