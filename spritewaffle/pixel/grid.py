"""Pixel-grid detection and dominant-colour downscaling.

Detection: colour-edge energy per column/row (summed over all frames), non-max suppressed, then for
each candidate size s the share of edge energy that falls on one phase. A true grid of size s puts
~all edges on one phase; multiples of s tie, so the smallest size within 80% of the best wins.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Grid:
    size: int
    ox: int = 0           # phase: first cell boundary at x = ox (mod size)
    oy: int = 0
    confident: bool = True
    score: float = 0.0
    source: str = "detected"   # detected | override | fallback

    def _lead(self, o: int) -> int:
        return 1 if o % self.size else 0

    def cell_x(self, x: int) -> int:
        return (x - self.ox % self.size) // self.size + self._lead(self.ox)

    def cell_y(self, y: int) -> int:
        return (y - self.oy % self.size) // self.size + self._lead(self.oy)


def _edge_profile(frames: list[np.ndarray], axis: int, min_edge: float = 24.0) -> np.ndarray:
    """Edge energy between neighbouring columns (axis=1) or rows (axis=0), summed over frames.

    Per pixel: colour difference between two opaque pixels (the keyed silhouette edge wanders by
    ±1 px, so alpha edges are ignored), kept only where it is a local peak along the axis
    (blur spreads one edge over 2-3 px) and above `min_edge` (flat-area noise would otherwise
    dominate once summed over hundreds of rows)."""
    total = None
    for f in frames:
        img = f[..., :3].astype(float)
        op = f[..., 3] > 0
        both = op[1:] & op[:-1] if axis == 0 else op[:, 1:] & op[:, :-1]
        d = np.abs(np.diff(img, axis=axis)).sum(-1) * both
        if axis == 0:
            d = d.T
        left = np.pad(d, ((0, 0), (1, 0)), constant_values=-1)[:, :-1]
        right = np.pad(d, ((0, 0), (0, 1)), constant_values=-1)[:, 1:]
        noise = np.median(d[d > 0]) if (d > 0).any() else 0.0
        peak = (d >= left) & (d > right) & (d > max(min_edge, 4 * noise))
        e = np.where(peak, d, 0.0).sum(0)
        total = e if total is None else total + e
    return total


def _phase_scores(e: np.ndarray, s: int) -> np.ndarray:
    n = len(e) // s * s
    return e[:n].reshape(-1, s).sum(0) if n else np.zeros(s)


def _peak_ratio(e: np.ndarray, s: int) -> float:
    """Best phase energy / mean energy of the other phases (≈1 when there is no grid)."""
    ps = _phase_scores(e, s)
    best = ps.argmax()
    return float(ps[best] / (np.delete(ps, best).mean() + 1e-9))


def detect(frames: list[np.ndarray], max_size: int = 32, min_conf: float = 6.0) -> Grid:
    """Estimate the integer pixel size and phase of pixel-art-like RGBA frames."""
    ex, ey = _edge_profile(frames, 1), _edge_profile(frames, 0)
    tx, ty = ex.sum() + 1e-9, ey.sum() + 1e-9
    max_size = max(2, min(max_size, len(ex) // 4, len(ey) // 4))
    # excess over chance: f(s) - 1/s. A divisor of the true size also catches noise; a multiple
    # loses part of the real edges; so the true size maximises the excess.
    excess = {}
    for s in range(2, max_size + 1):
        fx = _phase_scores(ex, s).max() / tx
        fy = _phase_scores(ey, s).max() / ty
        excess[s] = (fx + fy) / 2 - 1 / s
    s = max(excess, key=excess.get)
    conf = min(_peak_ratio(ex, s), _peak_ratio(ey, s))
    ox = (int(_phase_scores(ex, s).argmax()) + 1) % s
    oy = (int(_phase_scores(ey, s).argmax()) + 1) % s
    return Grid(size=s, ox=ox, oy=oy, confident=conf >= min_conf, score=float(conf))


def downscale(rgba: np.ndarray, size: int, ox: int = 0, oy: int = 0, alpha_threshold: float = 0.5,
              bin_bits: int = 4, refine: int = 20) -> np.ndarray:
    """Reduce each size x size cell to its dominant colour (mode of coarse colour bins, never a blend).

    The outer ring of each cell is ignored when size >= 4 (that is where blur mixes neighbours).
    A cell is opaque when at least `alpha_threshold` of its pixels are opaque.
    """
    s = size
    px, py = ox % s, oy % s
    lead_x, lead_y = (s - px) % s, (s - py) % s
    h, w = rgba.shape[:2]
    H = -(-(h + lead_y) // s) * s
    W = -(-(w + lead_x) // s) * s
    pad = np.zeros((H, W, 4), np.uint8)
    pad[lead_y:lead_y + h, lead_x:lead_x + w] = rgba
    ch, cw = H // s, W // s
    cells = pad.reshape(ch, s, cw, s, 4).transpose(0, 2, 1, 3, 4)
    if s >= 4:
        cells = cells[:, :, 1:-1, 1:-1]
    m = cells.shape[2] * cells.shape[3]
    cells = cells.reshape(ch * cw, m, 4).astype(np.int32)
    opaque = cells[..., 3] > 0

    shift = 8 - bin_bits
    codes = ((cells[..., 0] >> shift) << (2 * bin_bits)) | ((cells[..., 1] >> shift) << bin_bits) | (cells[..., 2] >> shift)
    codes = np.where(opaque, codes, -1 - np.arange(m))     # transparent pixels never form runs
    srt = np.sort(codes, axis=1)
    idx = np.arange(m)
    change = np.ones_like(srt, bool)
    change[:, 1:] = srt[:, 1:] != srt[:, :-1]
    start = np.maximum.accumulate(np.where(change, idx, 0), axis=1)
    runlen = np.where(srt >= 0, idx - start + 1, 0)
    mode = srt[np.arange(len(srt)), runlen.argmax(1)]

    rgb = cells[..., :3].astype(float)
    sel = (codes == mode[:, None]) & opaque
    mean = (rgb * sel[..., None]).sum(1) / np.maximum(sel.sum(1), 1)[:, None]
    # refine: average every opaque pixel close to the mode colour (bins can split one colour)
    near = (np.abs(rgb - mean[:, None]).max(-1) <= refine) & opaque
    near |= sel
    col = (rgb * near[..., None]).sum(1) / np.maximum(near.sum(1), 1)[:, None]

    a = np.where(opaque.mean(1) >= alpha_threshold, 255, 0)
    out = np.zeros((ch * cw, 4), np.uint8)
    out[:, :3] = np.clip(np.rint(col), 0, 255)
    out[:, 3] = a
    out[a == 0, :3] = 0
    return out.reshape(ch, cw, 4)
