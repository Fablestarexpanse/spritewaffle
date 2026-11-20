"""Frame picker: start -> end -> key beats -> evenly spaced in-betweens, for 12f and 24f sets.

Both sets share start, end and key beats. Key beats are local extremes of (smoothed) silhouette
motion energy: minima are held poses (contact, apex, impact), maxima are the fastest passes.
Blurry, duplicate and malformed frames are never picked as in-betweens.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import analysis


def parse_indices(spec: str) -> list[int]:
    """'1,6,11,17' and ranges '24-48' (inclusive) -> sorted unique ints."""
    out: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return sorted(out)


@dataclass
class Selection:
    indices: list[int]
    reasons: list[str]

    def as_report(self) -> list[dict]:
        return [{"out": i, "source": s, "reason": r} for i, (s, r) in enumerate(zip(self.indices, self.reasons))]


@dataclass
class ClipAnalysis:
    n: int
    energy: np.ndarray
    masks: np.ndarray
    bad: dict = field(default_factory=dict)      # index -> reason (blurry / duplicate / malformed)


def analyse(frames: list[np.ndarray], blur_ratio: float = 0.35, dup_eps: float = 0.002,
            area_tol: float = 0.4) -> ClipAnalysis:
    masks = analysis.silhouettes(frames)
    energy = analysis.motion_energy(masks)
    sharp = analysis.sharpness(frames)
    area = masks.sum((1, 2)).astype(float)
    med_area = np.median(area) if len(area) else 0
    med_sharp = np.median(sharp)
    bad = {}
    for i in range(len(frames)):
        if area[i] == 0:
            bad[i] = "malformed:empty"
        elif med_area and abs(area[i] - med_area) / med_area > area_tol:
            bad[i] = "malformed:area"
        elif sharp[i] < blur_ratio * med_sharp:
            bad[i] = "blurry"
        elif i > 0 and analysis.mask_distance(masks[i], masks[i - 1]) < dup_eps \
                and analysis.frame_diff([frames[i - 1], frames[i]])[0] < 0.3:
            bad[i] = "duplicate"
    return ClipAnalysis(len(frames), energy, masks, bad)


def key_beats(energy: np.ndarray, start: int, end: int, max_keys: int, min_gap: int = 2,
              bad: dict | None = None) -> list[tuple[int, str]]:
    """Local extremes of smoothed motion energy in (start, end), ranked by prominence."""
    if end - start < 3 or max_keys <= 0:
        return []
    e = np.convolve(energy, np.ones(3) / 3, mode="same")
    cands = []
    bad = bad or {}
    for i in range(start + 1, min(end, len(e))):
        if i in bad:
            continue
        lo, hi = e[max(i - 2, 0):i + 3].min(), e[max(i - 2, 0):i + 3].max()
        if e[i] == lo and hi > lo:
            cands.append((hi - e[i], i, "key:hold"))      # motion minimum = held/extreme pose
        elif e[i] == hi and hi > lo:
            cands.append((e[i] - lo, i, "key:fast"))      # motion maximum = passing/impact
    cands.sort(reverse=True)
    keys: list[tuple[int, str]] = []
    for _, i, why in cands:
        if all(abs(i - k) >= min_gap for k, _ in keys) and abs(i - start) >= min_gap and abs(end - i) >= min_gap:
            keys.append((i, why))
        if len(keys) >= max_keys:
            break
    return sorted(keys)


def _fill(start: int, end: int, fixed: dict[int, str], n: int, bad: dict, loop: bool) -> Selection:
    """Add evenly spaced in-betweens until n frames, avoiding bad frames and duplicates."""
    chosen = dict(fixed)
    span_end = end if loop else end + 1         # loop: end is exclusive (≈ start)
    while len(chosen) < n:
        pts = sorted(chosen)
        bounds = pts + ([span_end] if loop else [])
        gaps = [(bounds[j + 1] - bounds[j], bounds[j], bounds[j + 1]) for j in range(len(bounds) - 1)]
        gaps.sort(reverse=True)
        placed = False
        for size, a, b in gaps:
            if size < 2:
                break
            ideal = (a + b) / 2
            options = sorted(range(a + 1, b), key=lambda i: abs(i - ideal))
            for i in options:
                if i not in bad and i not in chosen:
                    chosen[i] = "inbetween"
                    placed = True
                    break
            if placed:
                break
            for i in options:                           # only bad frames left in the biggest gap
                if i not in chosen:
                    chosen[i] = f"inbetween(fallback:{bad.get(i, '')})"
                    placed = True
                    break
            if placed:
                break
        if not placed:
            break
    idx = sorted(chosen)
    return Selection(idx, [chosen[i] for i in idx])


def select(clip: ClipAnalysis, counts=(12, 24), start: int | None = None, end: int | None = None,
           loop: bool = False, manual: str | None = None) -> dict:
    """Pick frame sets. Returns {'start','end','loop','keys','sets': {n: Selection}, 'dropped', 'warnings'}."""
    warnings = []
    if manual:
        idx = [i for i in parse_indices(manual) if 0 <= i < clip.n]
        sel = Selection(idx, ["manual"] * len(idx))
        return {"start": idx[0] if idx else 0, "end": idx[-1] if idx else 0, "loop": loop, "keys": [],
                "sets": {len(idx): sel}, "dropped": {}, "warnings": warnings}

    start = 0 if start is None else start
    while start in clip.bad and start < clip.n - 1:
        start += 1
    loop_d = None
    if end is None:
        if loop:
            end, loop_d = analysis.loop_point(clip.masks, start, min_len=min(counts))
            if loop_d > 0.15:
                warnings.append(f"loop seam weak: best end {end} differs from start by {loop_d:.2f} (1-IoU)")
        else:
            end = clip.n - 1
            while end in clip.bad and end > start:
                end -= 1
    available = (end - start) if loop else (end - start + 1)
    keys = key_beats(clip.energy, start, end, max_keys=max(0, min(counts) // 3), bad=clip.bad)
    sets = {}
    for n in counts:
        if available < n:
            warnings.append(f"only {available} frames in range, {n}f set will be short")
        fixed = {start: "start"}
        if not loop:
            fixed[end] = "end"
        fixed.update({k: why for k, why in keys})
        sets[n] = _fill(start, end, fixed, min(n, available), clip.bad, loop)
    return {"start": start, "end": end, "loop": loop, "loop_seam": loop_d, "keys": keys,
            "sets": sets, "dropped": clip.bad, "warnings": warnings}
