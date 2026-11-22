"""Cell layouts (rules 8 and 9), sheet component detection, mirroring and asymmetry check."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Placement:
    scale: float
    crop: tuple[int, int, int, int]     # x, y, w, h in source frame
    paste: tuple[int, int]              # x, y in cell
    pivot: tuple[float, float] | None = None   # feet point in cell px (x may be .5: a pixel boundary)

    def as_dict(self) -> dict:
        d = {"scale": self.scale, "crop": list(self.crop), "paste": list(self.paste)}
        return d | ({"pivot": list(self.pivot)} if self.pivot is not None else {})


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask)
    if not len(ys):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


def _place(img: np.ndarray, p: Placement, cell: tuple[int, int]) -> np.ndarray:
    cw, ch = cell
    x, y, w, h = p.crop
    src = img[y:y + h, x:x + w]
    if p.scale != 1:
        src = cv2.resize(src, (max(1, round(w * p.scale)), max(1, round(h * p.scale))), interpolation=cv2.INTER_NEAREST)
    out = np.zeros((ch, cw, 4), np.uint8)
    px, py = p.paste
    sh, sw = src.shape[:2]
    x0, y0 = max(px, 0), max(py, 0)
    x1, y1 = min(px + sw, cw), min(py + sh, ch)
    if x1 > x0 and y1 > y0:
        out[y0:y1, x0:x1] = src[y0 - py:y1 - py, x0 - px:x1 - px]
    return out


def feet_x(frames: list[np.ndarray], bb: tuple[int, int, int, int], band: float = 0.12) -> float:
    """Where the character stands: median over frames of the mean x of opaque pixels in the
    lowest `band` of the clip's union bbox (frames in the air have none there and are skipped).
    A weapon swing or a cape doesn't move it, unlike the bbox centre."""
    x, y, w, h = bb
    y0 = y + h - max(2, round(h * band))
    xs = []
    for f in frames:
        cols = np.where((f[y0:y + h, x:x + w, 3] > 0).any(0))[0]
        if len(cols):
            xs.append(x + (cols.min() + cols.max() + 1) / 2)
    return float(np.median(xs)) if xs else x + w / 2


def preserve_canvas(frames: list[np.ndarray], cell: tuple[int, int], scale: float = 1.0,
                    foot_margin: int = 1) -> tuple[np.ndarray, list[Placement]]:
    """Video frames: ONE crop/scale/paste for every frame (no per-frame recentring = no fake motion).

    The crop is the union bbox of all frames. Its bottom sits `foot_margin` px above the cell
    bottom, and the character's feet (`feet_x`), not the bbox, sit on the cell's centre line, so
    every animation of a character shares one pivot: (cell_w / 2, cell_h - foot_margin). Only when
    that would push a wide action (a long swing) out of the cell is it shifted just enough to fit;
    the pivot then records where the feet ended up. Returns (F,ch,cw,4) cells and the per-frame
    placements (all identical, recorded so QA can prove it)."""
    union = np.zeros(frames[0].shape[:2], bool)
    for f in frames:
        union |= f[..., 3] > 0
    bb = _bbox(union) or (0, 0, frames[0].shape[1], frames[0].shape[0])
    cw, ch = cell
    w, h = round(bb[2] * scale), round(bb[3] * scale)
    feet = (feet_x(frames, bb) - bb[0]) * scale             # feet, from the crop's left edge
    px = round(cw / 2 - feet)                                # feet within half a pixel of the centre line
    pivot_x = cw / 2
    m = 1 if w <= cw - 2 else 0                              # keep off the border (QA fails a touching sprite)
    if w <= cw and not m <= px <= cw - w - m:
        px = min(max(px, m), cw - w - m)                     # never cut a swing off for the pivot's sake
        pivot_x = float(round(px + feet))                    # ...and say where the feet are instead
    p = Placement(scale, bb, (px, ch - foot_margin - h), (pivot_x, float(ch - foot_margin)))
    return np.stack([_place(f, p, cell) for f in frames]), [p] * len(frames)


def foot_point(rgba: np.ndarray, band: float = 0.12) -> list[float] | None:
    """Where this frame touches the ground: x = centre of the opaque columns in the lowest `band` of
    the sprite, y = the bottom edge of its lowest opaque row (a pixel boundary, like the pivot).
    None for an empty frame."""
    bb = _bbox(rgba[..., 3] > 0)
    if bb is None:
        return None
    x, y, w, h = bb
    y0 = y + h - max(1, round(h * band))
    cols = np.where((rgba[y0:y + h, x:x + w, 3] > 0).any(0))[0]
    return [round(float(x + (cols.min() + cols.max() + 1) / 2), 1), float(y + h)]


def align_feet(cells: list[np.ndarray], border: int = 2) -> tuple[np.ndarray, list[list[float] | None], list[str]]:
    """Move every frame so its foot point sits on the set's median foot point (whole pixels, no
    resampling), keeping a `border` px transparent margin. A frame that can't move all the way
    without crossing the border moves as far as it can and is reported."""
    aligned, points, warnings, _ = align_feet_with_offsets(cells, border)
    return aligned, points, warnings


def translate_rgba(cell: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Move visible pixels by a whole-pixel offset inside the same RGBA canvas."""
    height, width = cell.shape[:2]
    out = np.zeros_like(cell)
    ys, xs = np.nonzero(cell[..., 3] > 0)
    ny, nx = ys + dy, xs + dx
    keep = (ny >= 0) & (ny < height) & (nx >= 0) & (nx < width)
    out[ny[keep], nx[keep]] = cell[ys[keep], xs[keep]]
    return out


def align_feet_with_offsets(
    cells: list[np.ndarray], border: int = 2,
) -> tuple[np.ndarray, list[list[float] | None], list[str], list[tuple[int, int]]]:
    """Also return the applied (dx, dy) for each source frame, including border clamps."""
    pts = [foot_point(c) for c in cells]
    have = [p for p in pts if p]
    if not have:
        return np.stack(cells), pts, [], [(0, 0)] * len(cells)
    tx, ty = float(np.median([p[0] for p in have])), float(np.median([p[1] for p in have]))
    ch, cw = cells[0].shape[:2]
    out, warns, new_pts, offsets = [], [], [], []
    for k, (c, p) in enumerate(zip(cells, pts)):
        if not p:
            out.append(c)
            new_pts.append(None)
            offsets.append((0, 0))
            continue
        bb = _bbox(c[..., 3] > 0)
        dx, dy = round(tx - p[0]), round(ty - p[1])
        lo_x, hi_x = border - bb[0], cw - border - (bb[0] + bb[2])
        lo_y, hi_y = border - bb[1], ch - border - (bb[1] + bb[3])
        cx, cy = min(max(dx, lo_x), hi_x) if lo_x <= hi_x else dx, min(max(dy, lo_y), hi_y) if lo_y <= hi_y else dy
        if (cx, cy) != (dx, dy):
            warns.append(f"frame {k}: kept {border}px border, foot point off by {dx - cx},{dy - cy}px")
        out.append(translate_rgba(c, cx, cy))
        new_pts.append([p[0] + cx, p[1] + cy])
        offsets.append((cx, cy))
    return np.stack(out), new_pts, warns, offsets


def foot_anchor(sprites: list[np.ndarray], cell: tuple[int, int], foot_y: int | None = None,
                scale: float = 1.0) -> tuple[np.ndarray, list[Placement]]:
    """Image pose sheets: each sprite's own bbox placed at fixed centre-X and fixed foot-Y."""
    cw, ch = cell
    foot_y = ch - 1 if foot_y is None else foot_y
    cells, places = [], []
    for s in sprites:
        bb = _bbox(s[..., 3] > 0) or (0, 0, s.shape[1], s.shape[0])
        w, h = round(bb[2] * scale), round(bb[3] * scale)
        p = Placement(scale, bb, (cw // 2 - w // 2, foot_y + 1 - h))
        cells.append(_place(s, p, cell))
        places.append(p)
    return np.stack(cells), places


def sheet_components(sheet: np.ndarray, n: int, join_px: int = 6, row_tol: float = 0.5) -> list[np.ndarray]:
    """Find the n largest foreground blobs on a pose sheet (fragments within join_px merge), ordered
    row-major (rows grouped when their centres are within row_tol of a blob height). Returns RGBA crops."""
    mask = (sheet[..., 3] > 0).astype(np.uint8)
    joined = cv2.dilate(mask, np.ones((2 * join_px + 1,) * 2, np.uint8))
    k, lab, stats, cents = cv2.connectedComponentsWithStats(joined, connectivity=8)
    order = sorted(range(1, k), key=lambda i: -stats[i, cv2.CC_STAT_AREA])[:n]
    if len(order) < n:
        raise ValueError(f"found {len(order)} components, expected {n}")
    med_h = np.median([stats[i, cv2.CC_STAT_HEIGHT] for i in order])
    order.sort(key=lambda i: cents[i][1])
    rows, row = [], [order[0]]
    for i in order[1:]:
        if abs(cents[i][1] - cents[row[0]][1]) <= row_tol * med_h:
            row.append(i)
        else:
            rows.append(row)
            row = [i]
    rows.append(row)
    crops = []
    for r in rows:
        for i in sorted(r, key=lambda i: cents[i][0]):
            x, y, w, h = (stats[i, j] for j in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
            crop = sheet[y:y + h, x:x + w].copy()
            crop[lab[y:y + h, x:x + w] != i] = 0
            crops.append(crop)
    return crops


MIRROR_PAIRS = {"E": "W", "W": "E", "NE": "NW", "NW": "NE", "SE": "SW", "SW": "SE"}


def mirror(frames: np.ndarray) -> np.ndarray:
    """Horizontal flip of every frame (E->W etc.). Pivot X stays centred because cells are centred."""
    return np.ascontiguousarray(frames[:, :, ::-1])


def asymmetry(rgba: np.ndarray) -> dict:
    """Compare the sprite with its own mirror about the bbox centre.
    silhouette = 1-IoU of mask vs flipped mask; color = mean colour difference of the two halves (0..1)."""
    m = rgba[..., 3] > 0
    bb = _bbox(m)
    if bb is None:
        return {"silhouette": 0.0, "color": 0.0, "asymmetric": False}
    x, y, w, h = bb
    crop = rgba[y:y + h, x:x + w].astype(float)
    cm = m[y:y + h, x:x + w]
    fm = cm[:, ::-1]
    sil = 1 - (cm & fm).sum() / max((cm | fm).sum(), 1)
    half = w // 2
    left, right = crop[:, :half], crop[:, w - half:][:, ::-1]
    both = (left[..., 3] > 0) & (right[..., 3] > 0)
    col = float(np.abs(left[both, :3] - right[both, :3]).mean() / 255) if both.any() else 0.0
    return {"silhouette": float(sil), "color": col, "asymmetric": bool(sil > 0.12 or col > 0.08)}
