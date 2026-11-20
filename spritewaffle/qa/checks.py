"""QA report for one exported animation: metrics, errors, warnings, re-roll suggestion."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass
class Thresholds:
    pop_ratio: float = 3.0          # adjacent diff > pop_ratio * median adjacent diff -> motion pop
    pop_min: float = 0.15           # ...and above this absolute 1-IoU
    dup_eps: float = 0.0            # identical frames (exact pixel equality) count as duplicates
    max_duplicates: int = 1
    size_cv: float = 0.12           # coefficient of variation of bbox height
    stray_px: int = 3               # isolated opaque pixels allowed per frame
    loop_seam: float = 0.35         # 1-IoU last->first, relative check below
    loop_seam_ratio: float = 2.5    # seam diff vs median adjacent diff


def _bbox(a: np.ndarray):
    ys, xs = np.where(a)
    if not len(ys):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]


def _iou_dist(a, b) -> float:
    u = (a | b).sum()
    return 0.0 if u == 0 else float(1 - (a & b).sum() / u)


def _stray(a: np.ndarray) -> int:
    p = np.pad(a, 1)
    nb = p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return int((a & ~nb).sum())


def run(cells: np.ndarray, placements: list[dict], layout_mode: str, palette_size: int,
        loop: bool, t: Thresholds = Thresholds()) -> dict:
    n, h, w = cells.shape[:3]
    alpha = cells[..., 3] > 0
    errors, warnings, reroll = [], [], set()

    bboxes = [_bbox(a) for a in alpha]
    if any(b is None for b in bboxes):
        errors.append(f"empty frames: {[i for i, b in enumerate(bboxes) if b is None]}")
        reroll.add("select")

    adj = [_iou_dist(alpha[i], alpha[i + 1]) for i in range(n - 1)]
    med = float(np.median(adj)) if adj else 0.0
    pops = [i for i, d in enumerate(adj) if d > t.pop_min and d > t.pop_ratio * max(med, 1e-6)]
    if pops:
        warnings.append(f"motion pops between frames {[(i, i + 1) for i in pops]}")
        reroll.add("select")

    dups = [i for i in range(n - 1) if np.array_equal(cells[i], cells[i + 1])]
    if len(dups) > t.max_duplicates:
        warnings.append(f"{len(dups)} consecutive duplicate frames {dups}")
        reroll.add("select")

    edge = [i for i, a in enumerate(alpha) if a[0].any() or a[-1].any() or a[:, 0].any() or a[:, -1].any()]
    if edge:
        errors.append(f"sprite touches cell border in frames {edge}")
        reroll.add("layout/profile cell_size")

    heights = np.array([b[3] for b in bboxes if b])
    cv = float(heights.std() / heights.mean()) if len(heights) else 0.0
    if cv > t.size_cv:
        warnings.append(f"sprite height varies (CV {cv:.2f})")
        reroll.add("action video")

    colors = {tuple(c) for c in cells[alpha][:, :3].tolist()} if alpha.any() else set()
    if len(colors) > palette_size:
        errors.append(f"{len(colors)} colours used > palette {palette_size}")
        reroll.add("pixelize")

    stray = [_stray(a) for a in alpha]
    if max(stray, default=0) > t.stray_px:
        warnings.append(f"stray pixels per frame up to {max(stray)}")
        reroll.add("pixelize")

    if layout_mode == "preserve-canvas":
        if any(p != placements[0] for p in placements):
            errors.append("preserve-canvas placements differ between frames (fake camera motion)")
            reroll.add("layout")

    seam = _iou_dist(alpha[-1], alpha[0]) if n > 1 else 0.0
    if loop and seam > t.loop_seam and seam > t.loop_seam_ratio * max(med, 1e-6):
        warnings.append(f"loop seam {seam:.2f} vs median step {med:.2f}")
        reroll.add("select (loop point)")

    return {
        "status": "fail" if errors else "pass",
        "errors": errors, "warnings": warnings, "reroll": sorted(reroll),
        "frame_count": n, "cell_size": [w, h], "sheet_size": [w * n, h],
        "layout": layout_mode, "placements": placements,
        "placements_identical": all(p == placements[0] for p in placements),
        "bbox_per_frame": bboxes, "adjacent_silhouette_diff": [round(d, 4) for d in adj],
        "duplicate_frames": dups, "motion_pops": pops, "edge_contact_frames": edge,
        "height_cv": round(cv, 4), "palette_used": len(colors), "palette_size": palette_size,
        "stray_pixels": stray, "loop": loop, "loop_seam_diff": round(seam, 4),
        "thresholds": asdict(t),
    }


def write(report: dict, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    return path
