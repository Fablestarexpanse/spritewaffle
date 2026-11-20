"""Per-clip signals: silhouettes, motion energy, blur, frozen-clip and loop-point detection."""
from __future__ import annotations

import cv2
import numpy as np

from ..pixel import chroma


def silhouettes(frames: list[np.ndarray], max_side: int = 256) -> np.ndarray:
    """Boolean foreground masks (F,h,w), downsampled for speed. Uses alpha if present, else chroma key."""
    out = []
    for f in frames:
        k = min(1.0, max_side / max(f.shape[:2]))
        small = cv2.resize(f, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else f
        a = small[..., 3] > 0 if small.shape[2] == 4 else chroma.key(small)[..., 3] > 0
        out.append(a)
    return np.stack(out)


def motion_energy(masks: np.ndarray) -> np.ndarray:
    """energy[i] = silhouette pixels changed between frame i and i+1, normalised by mean area."""
    area = max(masks.sum((1, 2)).mean(), 1)
    return (masks[1:] ^ masks[:-1]).sum((1, 2)) / area


def frame_diff(frames: list[np.ndarray], max_side: int = 128) -> np.ndarray:
    """Mean absolute grey difference between consecutive frames (0..255 scale)."""
    g = []
    for f in frames:
        k = min(1.0, max_side / max(f.shape[:2]))
        small = cv2.resize(f[..., :3], None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        g.append(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(float))
    g = np.stack(g)
    return np.abs(np.diff(g, axis=0)).mean((1, 2))


def is_frozen(frames: list[np.ndarray], threshold: float = 0.6) -> tuple[bool, float]:
    """Frozen clip (rule 7): mean frame-to-frame difference below threshold."""
    if len(frames) < 2:
        return True, 0.0
    d = float(frame_diff(frames).mean())
    return d < threshold, d


def sharpness(frames: list[np.ndarray]) -> np.ndarray:
    """Variance of the Laplacian on the grey image (low = motion blur)."""
    return np.array([cv2.Laplacian(cv2.cvtColor(f[..., :3], cv2.COLOR_RGB2GRAY), cv2.CV_64F).var() for f in frames])


def mask_distance(a: np.ndarray, b: np.ndarray) -> float:
    """1 - IoU of two silhouettes."""
    u = (a | b).sum()
    return 0.0 if u == 0 else 1.0 - (a & b).sum() / u


def loop_point(masks: np.ndarray, start: int = 0, min_len: int = 8) -> tuple[int, float]:
    """End index e (exclusive) > start+min_len whose frame best matches `start` (frame e ≈ frame start,
    so playing start..e-1 on repeat is seamless). Returns (e, distance)."""
    best, best_d = len(masks), np.inf
    for e in range(start + min_len, len(masks)):
        d = mask_distance(masks[start], masks[e])
        if d < best_d - 1e-9:
            best, best_d = e, d
    return best, float(best_d)
