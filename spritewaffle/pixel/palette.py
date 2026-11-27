"""Shared palette: saliency-weighted k-means in Oklab over every opaque cell of a whole batch."""
from __future__ import annotations

import numpy as np


def saliency_weights(lab: np.ndarray, alpha: np.ndarray, contrast_scale: float = 0.1,
                     rarity_cap: float = 10.0, bin_size: float = 0.05) -> np.ndarray:
    """Per-cell weight = rarity * (1 + local contrast / scale).

    Rare colours (few cells) and cells that differ strongly from their 4-neighbours (eyes, gems,
    a red hat) get more pull, so k-means doesn't merge them into large flat areas.
    lab: (F,h,w,3), alpha: (F,h,w) bool -> (F,h,w) weights (0 for transparent).
    """
    contrast = np.zeros(alpha.shape)
    for axis in (1, 2):
        for shift in (1, -1):
            nb = np.roll(lab, shift, axis=axis)
            nba = np.roll(alpha, shift, axis=axis)
            d = np.linalg.norm(lab - nb, axis=-1) * nba
            contrast = np.maximum(contrast, d)
    bins = np.floor(lab[alpha] / bin_size).astype(np.int64)
    _, inv, counts = np.unique(bins, axis=0, return_inverse=True, return_counts=True)
    rarity = np.minimum(np.sqrt(counts.max() / counts[inv.ravel()]), rarity_cap)
    w = np.zeros(alpha.shape)
    w[alpha] = rarity * (1 + contrast[alpha] / contrast_scale)
    return w


def kmeans(x: np.ndarray, w: np.ndarray, k: int, iters: int = 40, n_init: int = 4, seed: int = 0) -> np.ndarray:
    """Weighted k-means (k-means++ init, best of n_init by weighted inertia). Returns (k,3) centroids."""
    uniq = np.unique(np.round(x, 4), axis=0)
    k = min(k, len(uniq))
    rng = np.random.default_rng(seed)
    best, best_inertia = None, np.inf
    for _ in range(n_init):
        c = [x[rng.choice(len(x), p=w / w.sum())]]
        for _ in range(1, k):
            d2 = np.min(((x[:, None] - np.array(c)[None]) ** 2).sum(-1), axis=1) * w
            c.append(x[rng.choice(len(x), p=d2 / d2.sum())] if d2.sum() > 0 else x[rng.integers(len(x))])
        c = np.array(c)
        for _ in range(iters):
            lbl = ((x[:, None] - c[None]) ** 2).sum(-1).argmin(1)
            new = np.array([np.average(x[lbl == j], axis=0, weights=w[lbl == j]) if (lbl == j).any() else c[j]
                            for j in range(k)])
            if np.allclose(new, c, atol=1e-6):
                break
            c = new
        inertia = (((x - c[lbl]) ** 2).sum(-1) * w).sum()
        if inertia < best_inertia:
            best, best_inertia = c, inertia
    return best


def merge_close(pal: np.ndarray, x: np.ndarray, w: np.ndarray, min_delta: float) -> np.ndarray:
    """Merge palette entries closer than min_delta (Oklab): k is a maximum, not a quota, so noise
    doesn't get its own near-duplicate colours. The lighter-weight entry folds into the heavier."""
    while len(pal) > 1:
        lbl = ((x[:, None] - pal[None]) ** 2).sum(-1).argmin(1)
        mass = np.bincount(lbl, weights=w, minlength=len(pal))
        d = np.linalg.norm(pal[:, None] - pal[None], axis=-1) + np.eye(len(pal)) * 9
        i, j = np.unravel_index(d.argmin(), d.shape)
        if d[i, j] >= min_delta:
            break
        drop = i if mass[i] < mass[j] else j
        pal = np.delete(pal, drop, axis=0)
        lbl = ((x[:, None] - pal[None]) ** 2).sum(-1).argmin(1)
        pal = np.array([np.average(x[lbl == c], axis=0, weights=w[lbl == c]) if (lbl == c).any() else pal[c]
                        for c in range(len(pal))])
    return pal


def fit(lab: np.ndarray, alpha: np.ndarray, k: int, saliency: bool = True, seed: int = 0,
        min_delta: float = 0.04) -> np.ndarray:
    """Fit one palette (<=k,3 Oklab) on all opaque cells of all frames."""
    x = lab[alpha]
    w = saliency_weights(lab, alpha)[alpha] if saliency else np.ones(len(x))
    # unique colours with summed weights: much faster, same result
    q = np.round(x, 3)
    uq, inv = np.unique(q, axis=0, return_inverse=True)
    inv = inv.ravel()
    ws = np.bincount(inv, weights=w)
    xs = np.zeros_like(uq)
    for c in range(3):
        xs[:, c] = np.bincount(inv, weights=x[:, c] * w) / ws
    pal = kmeans(xs, ws, k, seed=seed)
    return merge_close(pal, xs, ws, min_delta) if min_delta > 0 else pal


def extend(lab: np.ndarray, alpha: np.ndarray, base: np.ndarray, k_new: int, keep_delta: float = 0.06,
           saliency: bool = True, seed: int = 0, min_delta: float = 0.04) -> np.ndarray:
    """Family palette: keep `base` (n,3 Oklab) exactly and add at most k_new colours for the cells the
    base cannot draw (nearest base colour further than keep_delta), e.g. a cloak fitted on a body.
    New colours closer than min_delta to a base colour are dropped. Returns (n+m,3), base first."""
    x = lab[alpha]
    if not len(x) or k_new < 1:
        return base
    w = saliency_weights(lab, alpha)[alpha] if saliency else np.ones(len(x))
    near = np.sqrt(((x[:, None] - base[None]) ** 2).sum(-1)).min(1)
    miss = near > keep_delta
    if miss.sum() < 4:
        return base
    xm, wm = x[miss], w[miss]
    q = np.round(xm, 3)
    uq, inv = np.unique(q, axis=0, return_inverse=True)
    inv = inv.ravel()
    ws = np.bincount(inv, weights=wm)
    xs = np.zeros_like(uq)
    for c in range(3):
        xs[:, c] = np.bincount(inv, weights=xm[:, c] * wm) / ws
    new = kmeans(xs, ws, k_new, seed=seed)
    new = merge_close(new, xs, ws, min_delta) if min_delta > 0 else new
    far = np.sqrt(((new[:, None] - base[None]) ** 2).sum(-1)).min(1) >= min_delta
    return np.concatenate([base, new[far]]) if far.any() else base
