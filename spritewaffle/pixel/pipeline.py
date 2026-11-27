"""Pixelizer: batch of frames (one clip or one pose sheet) -> pixel art on one grid, one palette."""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from . import chroma, cleanup, grid as gridmod, palette as palmod, quantize
from .color import hex_to_rgb, oklab_to_srgb, srgb_to_oklab


@dataclass
class PixelParams:
    palette: int | list[str] = 16          # size N, or locked master palette (hex list)
    pixel_size: int | None = None          # manual grid override
    grid_offset: tuple[int, int] = (0, 0)  # phase for manual override
    target_height: int | None = None       # sprite height in art px; used when no grid is detected
    alpha_threshold: float = 0.5
    speck_px: int = 16                     # source-pixel speck removal before downscale
    despill: str = "all"                   # all (default) | edge (keeps deliberate green parts)
    green_gaps: bool = False               # key wide dark-green gap mush (sprite has no green)
    saliency: bool = True
    hysteresis: float = 0.03               # Oklab distance a new colour must win by
    loop: bool = False
    outline: str = "none"                  # none | dark_1px | selout
    orphan_delta: float = 0.1              # 0 disables orphan cleanup
    seed: int = 0


@dataclass
class PixelResult:
    indices: np.ndarray        # (F,h,w) int, -1 transparent
    palette: np.ndarray        # (k,3) uint8
    grid: gridmod.Grid
    resample: float = 1.0      # nearest-neighbour pre-scale applied before the grid (fallback only)
    info: dict = field(default_factory=dict)

    def rgba(self, i: int) -> np.ndarray:
        idx = self.indices[i]
        out = np.zeros(idx.shape + (4,), np.uint8)
        m = idx >= 0
        out[m, :3] = self.palette[idx[m]]
        out[m, 3] = 255
        return out


def _ensure_rgba(f: np.ndarray, speck_px: int, despill: str = "edge", green_gaps: bool = False) -> np.ndarray:
    if f.shape[2] == 3 or (f[..., 3] == 255).all():
        f = chroma.key(f[..., :3], despill=despill, green_gaps=green_gaps)
    else:
        f = f.copy()
        f[..., 3] = np.where(f[..., 3] >= 128, 255, 0)
    return chroma.remove_specks(f, speck_px) if speck_px else f


def _fallback_grid(frames: list[np.ndarray], target_height: int | None) -> tuple[gridmod.Grid, float]:
    """No real grid: choose a pixel size that makes the median sprite `target_height` art px tall."""
    if not target_height:
        return gridmod.Grid(size=1, confident=False, source="fallback"), 1.0
    heights = []
    for f in frames:
        ys = np.where(f[..., 3].any(1))[0]
        if len(ys):
            heights.append(ys[-1] - ys[0] + 1)
    s_float = max(1.0, float(np.median(heights)) / target_height) if heights else 1.0
    s = max(1, round(s_float))
    return gridmod.Grid(size=s, confident=False, source="fallback"), s / s_float


def pixelize(frames: list[np.ndarray], p: PixelParams = PixelParams(), *,
             locked_grid: tuple[gridmod.Grid, float] | None = None) -> PixelResult:
    rgba = [_ensure_rgba(f, p.speck_px, p.despill, p.green_gaps) for f in frames]

    if locked_grid is not None:
        g, scale = locked_grid
    elif p.pixel_size:
        g = gridmod.Grid(size=p.pixel_size, ox=p.grid_offset[0], oy=p.grid_offset[1], source="override")
        scale = 1.0
    else:
        g = gridmod.detect(rgba)
        scale = 1.0
        if not g.confident:
            g, scale = _fallback_grid(rgba, p.target_height)
    if abs(scale - 1.0) > 0.01:
        h, w = rgba[0].shape[:2]
        size = (max(1, round(w * scale)), max(1, round(h * scale)))
        rgba = [cv2.resize(f, size, interpolation=cv2.INTER_NEAREST) for f in rgba]

    small = np.stack([gridmod.downscale(f, g.size, g.ox, g.oy, p.alpha_threshold) for f in rgba])
    alpha = small[..., 3] > 0
    lab = srgb_to_oklab(small[..., :3].astype(float))

    if isinstance(p.palette, list):
        pal_lab = srgb_to_oklab(np.array([hex_to_rgb(h) for h in p.palette], float))
    elif alpha.any():
        pal_lab = palmod.fit(lab, alpha, int(p.palette), saliency=p.saliency, seed=p.seed)
    else:
        pal_lab = np.zeros((1, 3))

    idx = quantize.assign(lab, alpha, pal_lab, p.hysteresis, p.loop)
    if p.orphan_delta > 0:
        idx = np.stack([cleanup.remove_orphans(i, pal_lab, p.orphan_delta) for i in idx])
    if isinstance(p.palette, list):
        pal_rgb = np.array([hex_to_rgb(h) for h in p.palette], np.uint8)
    else:
        pal_rgb = np.clip(np.rint(oklab_to_srgb(pal_lab)), 0, 255).astype(np.uint8)
    if p.outline != "none":
        idx = np.stack([cleanup.outline(i, pal_rgb, p.outline) for i in idx])

    return PixelResult(indices=idx, palette=pal_rgb, grid=g, resample=scale,
                       info={"grid_score": g.score, "grid_source": g.source})
