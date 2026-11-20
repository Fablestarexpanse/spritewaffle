"""Index-image cleanup: orphan noise removal and outline passes. -1 = transparent."""
from __future__ import annotations

import numpy as np

from .color import srgb_to_oklab

_N4 = ((-1, 0), (1, 0), (0, -1), (0, 1))


def _neighbours(idx: np.ndarray) -> np.ndarray:
    p = np.pad(idx, 1, constant_values=-1)
    h, w = idx.shape
    return np.stack([p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy, dx in _N4])


def remove_orphans(idx: np.ndarray, pal_lab: np.ndarray, max_delta: float = 0.1) -> np.ndarray:
    """A pixel whose 4 neighbours all share one other index is noise if that colour is close
    (Oklab < max_delta); then it takes the neighbours' index. Distinct details (eyes) survive."""
    nb = _neighbours(idx)
    same = (nb == nb[0]).all(0) & (nb[0] >= 0) & (idx >= 0) & (nb[0] != idx)
    if not same.any():
        return idx
    d = np.linalg.norm(pal_lab[np.where(idx >= 0, idx, 0)] - pal_lab[np.where(nb[0] >= 0, nb[0], 0)], axis=-1)
    out = idx.copy()
    m = same & (d < max_delta)
    out[m] = nb[0][m]
    return out


def remove_isolated(idx: np.ndarray) -> np.ndarray:
    """Opaque pixels with no opaque 4-neighbour become transparent."""
    nb = _neighbours(idx)
    out = idx.copy()
    out[(idx >= 0) & (nb < 0).all(0)] = -1
    return out


def outline(idx: np.ndarray, pal_rgb: np.ndarray, mode: str) -> np.ndarray:
    """dark_1px: transparent pixels touching the sprite get the darkest palette colour.
    selout: the sprite's own edge pixels get a darker palette colour of similar hue."""
    if mode == "none":
        return idx
    lab = srgb_to_oklab(np.asarray(pal_rgb, float))
    nb = _neighbours(idx)
    out = idx.copy()
    if mode == "dark_1px":
        ring = (idx < 0) & (nb >= 0).any(0)
        out[ring] = int(lab[:, 0].argmin())
    elif mode == "selout":
        edge = (idx >= 0) & (nb < 0).any(0)
        target = lab.copy()
        target[:, 0] -= 0.15
        darker = np.array([np.linalg.norm(lab - t, axis=1).argmin() for t in target])
        out[edge] = darker[idx[edge]]
    else:
        raise ValueError(f"unknown outline mode {mode}")
    return out
