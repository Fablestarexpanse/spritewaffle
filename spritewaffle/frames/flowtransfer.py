"""Pixel-exact motion transfer: warp a target art sprite with a driving clip's optical flow.

Every output pixel is copied (nearest lookup) from the target sprite, so the palette and identity
are exactly the target's. Motion comes from dense DIS optical flow of the driving clip, computed
from each frame back to frame 0 inside the subject mask (chroma key; green-screen clips only).
It can only move existing pixels: no new views (turns) and no unseen parts.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..pixel import chroma


@dataclass
class Alignment:
    """Maps source-frame pixel coords to target-art coords: art = (src - src_anchor) * k + art_anchor."""
    k: float
    src_anchor: tuple[float, float]     # bottom-centre of source frame-0 silhouette (x, y)
    art_anchor: tuple[float, float]     # bottom-centre of target art silhouette (x, y)


def _bbox_anchor(mask: np.ndarray) -> tuple[tuple[float, float], int]:
    ys, xs = np.where(mask)
    if not len(ys):
        raise ValueError("empty silhouette")
    return ((xs.min() + xs.max() + 1) / 2, float(ys.max() + 1)), int(ys.max() - ys.min() + 1)


def masks_of(frames: list[np.ndarray]) -> list[np.ndarray]:
    return [(f[..., 3] > 0) if f.shape[2] == 4 else (chroma.key(f[..., :3])[..., 3] > 0) for f in frames]


def align(src_mask0: np.ndarray, target_alpha: np.ndarray) -> Alignment:
    (sa, sh) = _bbox_anchor(src_mask0)
    (ta, th) = _bbox_anchor(target_alpha)
    return Alignment(k=th / sh, src_anchor=sa, art_anchor=ta)


def backward_flows(frames: list[np.ndarray], masks: list[np.ndarray]) -> list[np.ndarray]:
    """flow_i(p) = displacement from pixel p of frame i to its match in frame 0 (frame 0: zeros)."""
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)

    def gray(f, m):
        g = cv2.cvtColor(np.ascontiguousarray(f[..., :3]), cv2.COLOR_RGB2GRAY)
        return np.where(m, g, 0).astype(np.uint8)

    g0 = gray(frames[0], masks[0])
    out = [np.zeros(frames[0].shape[:2] + (2,), np.float32)]
    for f, m in zip(frames[1:], masks[1:]):
        out.append(dis.calc(gray(f, m), g0, None))
    return out


def _nearest_opaque(alpha: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For every pixel, coordinates (y, x) of the nearest opaque pixel."""
    _, labels = cv2.distanceTransformWithLabels((~alpha).astype(np.uint8), cv2.DIST_L2, 5,
                                                labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.where(alpha)
    lut_y = np.zeros(labels.max() + 1, np.int32)
    lut_x = np.zeros(labels.max() + 1, np.int32)
    # label ids of zero pixels in the input (= opaque pixels) are numbered in scan order
    lut_y[1:len(ys) + 1], lut_x[1:len(xs) + 1] = ys, xs
    return lut_y[labels], lut_x[labels]


def warp(target: np.ndarray, frames: list[np.ndarray], masks: list[np.ndarray] | None = None,
         flows: list[np.ndarray] | None = None, canvas: tuple[int, int] | None = None) -> list[np.ndarray]:
    """Animate `target` (RGBA art) with the motion of `frames` (driving clip, any size).

    Output frames are RGBA at the target's art scale on `canvas` (w, h; default: target size),
    every opaque pixel copied from `target`. Opacity follows the target's own silhouette (measured:
    using the driver's silhouette clipped a goblin's club and ears to a mannequin's outline)."""
    masks = masks or masks_of(frames)
    flows = flows or backward_flows(frames, masks)
    t_alpha = target[..., 3] > 0
    al = align(masks[0], t_alpha)
    th, tw = target.shape[:2]
    cw, ch = canvas or (tw, th)
    ny, nx = _nearest_opaque(t_alpha)
    # art pixel centres -> source coordinates
    ay, ax = np.mgrid[0:ch, 0:cw].astype(np.float32) + 0.5
    sx = (ax - al.art_anchor[0]) / al.k + al.src_anchor[0]
    sy = (ay - al.art_anchor[1]) / al.k + al.src_anchor[1]
    sh, sw = masks[0].shape
    inside = (sx >= 0) & (sx < sw) & (sy >= 0) & (sy < sh)
    sxi = np.clip(sx.astype(int), 0, sw - 1)
    syi = np.clip(sy.astype(int), 0, sh - 1)
    out = []
    for m, fl in zip(masks, flows):
        # flow is only meaningful on the driving subject: extend it outward so parts the target has
        # and the driver lacks (a held club, long ears) move with the nearest body part
        my, mx = _nearest_opaque(m)
        fl = fl[my, mx]
        # follow the flow back to frame 0, then into target-art coordinates
        qx = (sx + fl[syi, sxi, 0] - al.src_anchor[0]) * al.k + al.art_anchor[0]
        qy = (sy + fl[syi, sxi, 1] - al.src_anchor[1]) * al.k + al.art_anchor[1]
        valid = inside & (qx >= 0) & (qx < tw) & (qy >= 0) & (qy < th)
        qxi = np.clip(np.floor(qx).astype(int), 0, tw - 1)
        qyi = np.clip(np.floor(qy).astype(int), 0, th - 1)
        hit = valid & t_alpha[qyi, qxi]
        # the TARGET's silhouette decides opacity; inside the driver's silhouette, 1-px gaps next to
        # hits (disocclusion) are filled from the nearest opaque target pixel
        on = inside & m[syi, sxi]
        near = cv2.dilate(hit.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        fill = on & ~hit & near
        frame = np.zeros((ch, cw, 4), np.uint8)
        frame[hit] = target[qyi[hit], qxi[hit]]
        fy, fx = ny[qyi[fill], qxi[fill]], nx[qyi[fill], qxi[fill]]
        frame[fill] = target[fy, fx]
        out.append(frame)
    return out
