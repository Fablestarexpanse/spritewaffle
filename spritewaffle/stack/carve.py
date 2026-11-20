"""Sprite stacking for rigid props/vehicles: orthographic pixel-art views -> slices.

Coordinates: x = width (left->right in the front view), y = depth (front->back), z = height
(bottom->top). Views are RGBA pixel art on a transparent background:
  front (z rows top->bottom, x cols)   back (z, x mirrored)   right (z, y cols front->back)
  top (y rows back->front, x cols)     — looking down with the front at the bottom of the image.
The volume is the visual hull of the three silhouettes (array maths only, no mesh/rendering); each
voxel takes the colour of the view that sees it first. The left side is the mirrored right side.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Views:
    front: np.ndarray
    right: np.ndarray
    top: np.ndarray
    back: np.ndarray | None = None


def _crop(img: np.ndarray) -> np.ndarray:
    ys, xs = np.where(img[..., 3] > 0)
    if not len(ys):
        raise ValueError("empty view")
    return img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _fit(img: np.ndarray, w: int, h: int) -> np.ndarray:
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_NEAREST) if img.shape[:2] != (h, w) else img


def normalize(v: Views) -> tuple[Views, tuple[int, int, int]]:
    """Crop every view to its silhouette and resample (nearest) so shared axes agree:
    W from front (and top), H from front (and right), D from right (and top)."""
    f, r, t = _crop(v.front), _crop(v.right), _crop(v.top)
    H, W = f.shape[:2]
    D = max(1, round(r.shape[1] * H / r.shape[0]))           # side scaled to the front's height
    out = Views(front=f, right=_fit(r, D, H), top=_fit(t, W, D),
                back=_fit(_crop(v.back), W, H) if v.back is not None else None)
    return out, (W, D, H)


def carve(v: Views) -> tuple[np.ndarray, np.ndarray]:
    """Visual hull + colours. Returns (occupancy (H,D,W) bool, colour (H,D,W,3) uint8), z index 0 = bottom."""
    v, (W, D, H) = normalize(v)
    fa = v.front[..., 3] > 0                                   # (H rows top->bottom, W)
    ra = v.right[..., 3] > 0                                   # (H, D front->back)
    ta = v.top[..., 3] > 0                                     # (D rows back->front, W)
    z = np.arange(H)[:, None, None]
    occ = (fa[::-1][:, None, :]                                # front: z bottom-up, broadcast over y
           & ra[::-1][:, :, None]                              # right: z bottom-up, y, broadcast over x
           & ta[::-1][None, :, :])                             # top: y front->back
    del z

    col = np.zeros((H, D, W, 3), np.uint8)
    have = np.zeros((H, D, W), bool)
    front_c = v.front[::-1, :, :3]                             # (H, W)
    back_c = (v.back[::-1, ::-1, :3] if v.back is not None else front_c)   # back image is mirrored in x
    right_c = v.right[::-1, :, :3]                             # (H, D)
    left_c = right_c                                           # left = mirrored right (symmetric prop)
    top_c = v.top[::-1, :, :3]                                 # (D front->back, W)

    def paint(mask, colours):
        new = mask & occ & ~have
        col[new] = colours[new]
        have[new] = True

    zz, yy, xx = np.nonzero(occ)
    # topmost voxel in each (y, x) column -> top colour
    top_z = np.full((D, W), -1)
    np.maximum.at(top_z, (yy, xx), zz)
    is_top = np.zeros_like(occ)
    ok = top_z >= 0
    is_top[top_z[ok], np.nonzero(ok)[0], np.nonzero(ok)[1]] = True
    paint(is_top, np.broadcast_to(top_c[None], (H, D, W, 3)))
    # first voxel along each viewing ray
    def first_along(axis, reverse):
        o = occ[(slice(None),) * axis + (slice(None, None, -1),)] if reverse else occ
        idx = np.argmax(o, axis=axis)
        hit = o.any(axis=axis)
        if reverse:
            idx = occ.shape[axis] - 1 - idx
        m = np.zeros_like(occ)
        grids = np.indices(idx.shape)
        coords = list(grids)
        coords.insert(axis, idx)
        sel = tuple(c[hit] for c in coords)
        m[sel] = True
        return m
    paint(first_along(1, False), np.broadcast_to(front_c[:, None], (H, D, W, 3)))   # seen from the front
    paint(first_along(1, True), np.broadcast_to(back_c[:, None], (H, D, W, 3)))     # seen from the back
    paint(first_along(2, True), np.broadcast_to(right_c[:, :, None], (H, D, W, 3)))  # from the right
    paint(first_along(2, False), np.broadcast_to(left_c[:, :, None], (H, D, W, 3)))  # from the left
    paint(occ, np.broadcast_to(front_c[:, None], (H, D, W, 3)))                      # interior fallback
    return occ, col


def slices(occ: np.ndarray, col: np.ndarray) -> np.ndarray:
    """(H, D, W, 4) RGBA slices, index 0 = bottom. Each slice is the top-down image of one layer
    (rows back->front, so the front of the prop is at the bottom of the slice image)."""
    H, D, W = occ.shape
    out = np.zeros((H, D, W, 4), np.uint8)
    out[..., :3] = col[:, ::-1]
    out[..., 3] = np.where(occ[:, ::-1], 255, 0)
    return out


def render(sl: np.ndarray, angle_deg: float, layer_px: int = 1, scale: int = 1) -> np.ndarray:
    """Draw a slice stack at a rotation (2D compositing: each slice rotated, stacked upward by
    layer_px). Nearest-neighbour throughout, so the result stays pixel art."""
    H, D, W = sl.shape[:3]
    side = int(np.ceil(np.hypot(D, W))) + 2
    canvas_h = side + H * layer_px + 2
    out = np.zeros((canvas_h, side, 4), np.uint8)
    M = cv2.getRotationMatrix2D((W / 2, D / 2), angle_deg, 1.0)
    M[:, 2] += (side / 2 - W / 2, side / 2 - D / 2)
    for z in range(H):
        rot = cv2.warpAffine(sl[z], M, (side, side), flags=cv2.INTER_NEAREST,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        y0 = canvas_h - side - z * layer_px - 1
        m = rot[..., 3] > 0
        region = out[y0:y0 + side]
        region[m] = rot[m]
    if scale > 1:
        out = cv2.resize(out, (out.shape[1] * scale, out.shape[0] * scale), interpolation=cv2.INTER_NEAREST)
    return out


def turntable(sl: np.ndarray, steps: int = 16, layer_px: int = 1) -> list[np.ndarray]:
    return [render(sl, 360 * i / steps, layer_px) for i in range(steps)]
