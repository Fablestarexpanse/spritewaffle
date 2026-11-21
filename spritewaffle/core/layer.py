"""Equipment layers for paper-doll games (Ronan: "Diablo / Ultima Online ... armors like pants,
chest etc. modelled to the player's base model"). A variant is the base with one item fitted on
and the same pose and position, so the item alone = the variant's pixels that differ from the
base. Drawn over the base body, the layer gives back the variant.

Measured 2026-11-21, knight/gold_ref vs knight/p2_002 (2048 canvas, sprite ~700 px tall): bounding
boxes within 2 px of each other. "Moved" check = base pixels the variant no longer covers: real
variants 0.01-0.82 %, the base shifted 4 px 1.83 %, 12 px 5.5 %.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..pixel import chroma
from ..prompts.builder import CARDINALS, DIAGONALS

# Colour difference (CIELAB delta E) that counts as "changed". Measured on knight/caped back views:
# RGB max-channel > 60 lost a band of the dark cape over the dark belt; delta E 25 keeps the whole
# cape and the armor; 18 and below pick up redraw noise on the tunic.
DE = 25
MIN_AREA = 400     # changed specks smaller than this are redraw noise, not the item
MOVED_WARN = 1.5


def _delta_e(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    la = cv2.cvtColor(np.ascontiguousarray(a[..., :3], np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    lb = cv2.cvtColor(np.ascontiguousarray(b[..., :3], np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    return np.sqrt(((la - lb) ** 2).sum(-1))


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Close holes fully enclosed by a piece (a cape over a part that happens to match its colour).
    Gaps that reach the piece's edge are not holes; the delta E threshold is what handles those."""
    cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    out = mask.copy()
    if hier is None:
        return out
    for i, h in enumerate(hier[0]):
        if h[3] >= 0:                                   # a hole: fill it
            cv2.drawContours(out, cnts, i, 1, cv2.FILLED)
    return out


def extract(base_rgb: np.ndarray, variant_rgb: np.ndarray) -> tuple[np.ndarray, float]:
    """(layer RGBA, % of the base body the variant no longer covers) from two green-background
    renders of the same view. A high % means the variant moved the body and the layer won't fit."""
    b, v = chroma.key(base_rgb[..., :3]), chroma.key(variant_rgb[..., :3])
    d = _delta_e(b, v)
    on = v[..., 3] > 0
    m = ((d > DE) & on) | (on & (b[..., 3] == 0))
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = np.isin(lab, [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > MIN_AREA]).astype(np.uint8)
    keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    keep = _fill_holes(keep) & on.astype(np.uint8)
    layer = v.copy()
    layer[..., 3] = np.where(keep > 0, v[..., 3], 0)
    bon = b[..., 3] > 0
    return layer, round(float((bon & ~on).sum() / max(1, bon.sum()) * 100), 2)


def facings(base_dir: Path, variant_dir: Path, out: Path) -> dict:
    """One layer per facing both jobs have: out/<f>.png (transparent, same canvas as the facings)."""
    out.mkdir(parents=True, exist_ok=True)
    rep = {"layers": {}, "uncovered": {}, "warnings": []}
    for f in CARDINALS + DIAGONALS:
        vf, bf = variant_dir / f"{f}.png", base_dir / f"{f}.png"
        if not (vf.exists() and bf.exists()):
            continue
        b, v = np.asarray(Image.open(bf).convert("RGB")), np.asarray(Image.open(vf).convert("RGB"))
        if b.shape != v.shape:
            rep["warnings"].append(f"{f}: variant is {v.shape[1]}x{v.shape[0]}, base {b.shape[1]}x{b.shape[0]}; no layer")
            continue
        layer, err = extract(b, v)
        Image.fromarray(layer).save(out / vf.name)
        px = int((layer[..., 3] > 0).sum())
        rep["layers"][f], rep["uncovered"][f] = px, err
        if px == 0:
            rep["warnings"].append(f"{f}: no item layer (the variant looks the same as the base here)")
        elif err > MOVED_WARN:
            rep["warnings"].append(f"{f}: {err}% of the base body is no longer covered: the variant moved "
                                   "the body, so the layer won't sit cleanly on the base; re-roll this facing")
    return rep
