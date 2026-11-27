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


def _greenish(rgb: np.ndarray) -> np.ndarray:
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    return (g > r + 60) & (g > b + 60)


def _clean_holes(rgb: np.ndarray, bg: np.ndarray, dist: np.ndarray, keyed: np.ndarray, loose: np.ndarray,
                 strict_tol: float, outer: np.ndarray, passes: int = 4) -> np.ndarray:
    """Enclosed background the strict tolerance misses, cleaned in passes until nothing changes.

    Measured 2026-11-26 on H3 image-edit output (an item fitted on a base body): gaps between the
    arms and body and between the legs came back as green full of dark speckle, or as solid black
    ringed by a thin green line, and the strict enclosed key left both opaque. Each pass:
    1. an enclosed near-green region whose MEDIAN colour is background (speckled green) is keyed;
    2. a near-black region at least 80 % ringed by green or keyed pixels is a filled gap (the
       sprite's own outline borders the background on one side only, so it stays);
       2b. the same black fill touching the outline is found as the inside of the keyed green loop;
    3. tiny opaque islands cut off from everything else are removed;
    4. dark specks mostly surrounded by keyed enclosed background are removed.
    Keying one region can expose the next (specks left inside a keyed gap), hence the passes."""
    h, w = keyed.shape
    k3 = np.ones((3, 3), np.uint8)
    green = _greenish(rgb)
    dark = rgb.max(-1) < 48
    min_hole = max(12, h * w // 20000)
    max_speck = max(16, h * w // 10000)
    start = keyed.copy()
    def regions(mask: np.ndarray, connectivity: int, min_px: int | None = None):
        """(slice, component mask inside it) for every component of at least min_px (min_hole) pixels."""
        n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=connectivity)
        for i in np.where(stats[:, cv2.CC_STAT_AREA] >= (min_hole if min_px is None else min_px))[0]:
            if i == 0:
                continue
            x, y, bw, bh = stats[i, :4]
            sl = (slice(max(0, y - 3), min(h, y + bh + 3)), slice(max(0, x - 3), min(w, x + bw + 3)))
            yield sl, lab[sl] == i

    for _ in range(passes):
        before = int(keyed.sum())
        # 1. speckled green holes
        for sl, m in regions(loose & ~keyed, 8):
            if np.median(dist[sl][m]) <= strict_tol + 15:
                # with the dark specks inside it, also those touching its edge (closing, 2 px)
                near = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, k3, iterations=2).astype(bool)
                keyed[sl] |= m | (near & (dark[sl] | loose[sl]))
        # 2. black fills ringed by green
        for sl, m in regions(dark & ~keyed, 4):
            ring = cv2.dilate(m.astype(np.uint8), k3, iterations=2).astype(bool) & ~m
            if ring.any() and (green[sl][ring] | keyed[sl][ring]).mean() >= 0.8:
                keyed[sl] |= m
        # 2b. black fills that merge into the sprite outline (so 2. sees one big dark region): the
        #     thin keyed green line around them still closes a loop; key a loop's inside when it is
        #     almost all black. Closing (2 px) seals small breaks in the line.
        ring_all = cv2.morphologyEx((keyed & ~outer).astype(np.uint8), cv2.MORPH_CLOSE, k3, iterations=2)
        #     Loops this thin are small, so they are not held to min_hole.
        for sl, m in regions(ring_all.astype(bool), 8, 12):
            n3, l3 = cv2.connectedComponents((~m).astype(np.uint8), connectivity=4)
            edge = np.unique(np.concatenate([l3[0], l3[-1], l3[:, 0], l3[:, -1]]))
            for j in range(1, n3):
                inside = l3 == j
                if j not in edge and inside.sum() >= 4 and dark[sl][inside].mean() >= 0.9:
                    keyed[sl] |= inside
        # 3. small islands, plus the green rim pixels left around a keyed gap
        opaque = (~keyed).astype(np.uint8)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(opaque, connectivity=8)
        if n > 2:
            main = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            small = [i for i in range(1, n) if i != main and stats[i, cv2.CC_STAT_AREA] <= max_speck]
            if small:
                keyed |= np.isin(lab, small)
        # 4. dark specks mostly surrounded (5 of 8 neighbours) by keyed ENCLOSED background; outline
        #    pixels border a gap on one side only, and the outer background is left out
        inner = (keyed & ~outer).astype(np.float32)
        around = cv2.filter2D(inner, -1, np.ones((3, 3), np.float32), borderType=cv2.BORDER_CONSTANT) - inner
        keyed |= dark & ~keyed & (around >= 5)
        added = keyed & ~start                      # only gaps keyed here: the outer edge keeps its despilled fringe
        rim = green & ~keyed & cv2.dilate(added.astype(np.uint8), k3, iterations=2).astype(bool)
        keyed |= rim
        if int(keyed.sum()) == before:
            break
    return keyed


def _green_gaps(rgb: np.ndarray, keyed: np.ndarray) -> np.ndarray:
    """Wide green-hue mush (dark green mixed with black) where a video model blurred a gap.

    Measured 2026-11-26 on H3 clips of a fitted body (S idle): the arm-torso gaps came back as
    (0,62,0)..(22,167,30) with black between, far from #00FF00, so no tolerance keys them and the
    sprite showed dark slivers at the hips. Video models also tint the dark OUTLINE green, but only
    1-2 px deep, so a region counts as a gap only when it is wider than that (distance transform),
    with the black pixels its closing takes in. Only for sprites with no green of their own (the
    caller decides, from the approved facing): it would cut a deliberately green part."""
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    hue = ((g > np.maximum(r, b) + 25) & ~keyed).astype(np.uint8)
    if not hue.any():
        return keyed
    dark = rgb.max(-1) < 48
    wide = max(2.5, 2.5 * min(keyed.shape) / 800)
    k3 = np.ones((3, 3), np.uint8)
    # black specks inside the mush break it up; measure width on the mush with them closed in
    mush = cv2.morphologyEx(hue, cv2.MORPH_CLOSE, k3, iterations=2) & ((hue > 0) | dark).astype(np.uint8)
    dt = cv2.distanceTransform(mush, cv2.DIST_L2, 3)
    n, lab = cv2.connectedComponents(mush, connectivity=8)
    big = np.unique(lab[dt >= wide])
    keyed = keyed.copy()
    for i in big[big > 0]:
        keyed |= lab == i
    return keyed


def has_green(rgba: np.ndarray, frac: float = 0.002) -> bool:
    """Does a keyed sprite have green parts of its own (more than `frac` of its opaque pixels)?"""
    op = rgba[..., 3] > 0
    r, g, b = (rgba[..., i].astype(int) for i in range(3))
    return bool(op.any()) and ((g > np.maximum(r, b) + 25) & op).sum() > frac * op.sum()


def key(rgb: np.ndarray, loose_tol: float = 70, strict_tol: float = 30, despill_px: int = 2,
        despill: str = "edge", clean_holes: bool = True, green_gaps: bool = False) -> np.ndarray:
    """RGB uint8 (H,W,3) -> RGBA uint8 with hard alpha and despilled edges.

    despill='all' clamps green on every opaque pixel (video models tint dark outlines green deep
    inside the sprite); it also greys out deliberately green parts, so 'edge' is the default.
    clean_holes: the multi-pass cleanup of enclosed gaps (_clean_holes).
    green_gaps: also key wide dark-green gap mush (_green_gaps); only for sprites with no green."""
    rgb = np.ascontiguousarray(rgb[..., :3])
    bg = background_color(rgb)
    dist = np.abs(rgb.astype(float) - bg).max(-1)
    loose = (dist <= loose_tol).astype(np.uint8)
    n, lab = cv2.connectedComponents(loose, connectivity=4)
    border_labels = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    border_labels = border_labels[border_labels > 0]
    keyed = np.isin(lab, border_labels) | (dist <= strict_tol)

    if green_gaps:
        keyed = _green_gaps(rgb, keyed)
    if clean_holes:
        keyed = _clean_holes(rgb, bg, dist, keyed, loose.astype(bool), strict_tol, np.isin(lab, border_labels))
    out = np.dstack([rgb, np.where(keyed, 0, 255).astype(np.uint8)])
    if despill_px > 0:
        k = np.ones((3, 3), np.uint8)
        band = cv2.dilate(keyed.astype(np.uint8), k, iterations=despill_px).astype(bool) & ~keyed
        if despill == "all":
            band = ~keyed
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


def crop_sprite(rgb: np.ndarray, pad_frac: float = 1 / 12) -> np.ndarray:
    """RGBA of just the sprite: keyed, cropped to its silhouette with a small transparent margin."""
    rgba = key(rgb[..., :3])
    ys, xs = np.where(rgba[..., 3] > 0)
    if not len(ys):
        return rgba
    pad = max(4, int((ys.max() - ys.min()) * pad_frac))
    return rgba[max(0, ys.min() - pad):ys.max() + pad, max(0, xs.min() - pad):xs.max() + pad]
