"""One export per character: every facing x action in a single .aseprite (a tag per animation,
so Unity's 2D Aseprite Importer creates one clip each) plus one PNG atlas + JSON.

Each action was pixelized with its own palette; they are merged into one indexed palette (exact
colours, no requantization). Above 255 colours the .aseprite falls back to RGBA.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from . import aseprite
from .sheet import feet_pivot


def collect(job_root: Path, frame_set: str = "12f", require_pass: bool = True) -> tuple[list[dict], list[str]]:
    """Animations ready to ship: [{name, facing, action, cells (F,h,w,4), loop}], plus skip reasons."""
    anims, skipped = [], []
    for sd in sorted((job_root / "04_pixel").glob(f"*/*/{frame_set}")):
        facing, action = sd.parent.parent.name, sd.parent.name
        qa = job_root / "05_qa" / facing / action / frame_set / "report.json"
        if require_pass:
            if not qa.exists():
                skipped.append(f"{action}_{facing}: no QA report")
                continue
            if json.loads(qa.read_text())["status"] != "pass":
                skipped.append(f"{action}_{facing}: QA failed")
                continue
        cells = np.stack([np.array(Image.open(p).convert("RGBA")) for p in sorted((sd / "frames").glob("*.png"))])
        sel = job_root / "03_actions" / facing / action / "selection_report.json"
        loop = json.loads(sel.read_text())["loop"] if sel.exists() else True
        anims.append({"name": f"{action}_{facing}", "facing": facing, "action": action, "cells": cells, "loop": loop})
    return anims, skipped


def merged_palette(anims: list[dict]) -> np.ndarray:
    colours = set()
    for a in anims:
        c = a["cells"]
        colours |= {tuple(x) for x in c[c[..., 3] > 0][:, :3].tolist()}
    return np.array(sorted(colours), np.uint8).reshape(-1, 3)


def export(job_root: Path, out_dir: Path, character: str, fps_for, frame_set: str = "12f",
           require_pass: bool = True) -> dict:
    """fps_for(action) -> fps. Returns paths + what was included/skipped."""
    anims, skipped = collect(Path(job_root), frame_set, require_pass)
    if not anims:
        raise RuntimeError(f"nothing to export ({'; '.join(skipped) or 'no pixelized animations'})")
    sizes = {a["cells"].shape[1:3] for a in anims}
    if len(sizes) > 1:
        raise ValueError(f"animations have different cell sizes {sizes}; re-run them with one profile")
    h, w = sizes.pop()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    frames, durations, tags, meta_anims = [], [], [], []
    for a in anims:
        start = len(frames)
        n = len(a["cells"])
        fps = fps_for(a["action"]) * (n // 12 if n > 12 else 1)       # 24f plays twice as fast
        frames += list(a["cells"])
        durations += [round(1000 / fps)] * n
        tags.append((a["name"], start, start + n - 1, "forward"))
        meta_anims.append({"name": a["name"], "facing": a["facing"], "action": a["action"], "frames": n,
                           "fps": fps, "loop": a["loop"], "pivot": feet_pivot(a["cells"]),
                           "row": len(meta_anims), "first": start})
    frames = np.stack(frames)

    pal = merged_palette(anims)
    ase_path = out_dir / f"{character}.aseprite"
    if len(pal) <= 255:
        lut = {tuple(c): i for i, c in enumerate(pal.tolist())}
        idx = np.full(frames.shape[:3], -1, int)
        m = frames[..., 3] > 0
        idx[m] = [lut[tuple(c)] for c in frames[m][:, :3].tolist()]
        aseprite.write(ase_path, idx, pal, durations, tags)
        mode = "indexed"
    else:
        aseprite.write_rgba(ase_path, frames, durations, tags)
        mode = "rgba"

    cols = max(a["frames"] for a in meta_anims)
    atlas = np.zeros((h * len(anims), w * cols, 4), np.uint8)
    for r, a in enumerate(anims):
        for c, cell in enumerate(a["cells"]):
            atlas[r * h:(r + 1) * h, c * w:(c + 1) * w] = cell
    png = out_dir / f"{character}_atlas.png"
    Image.fromarray(atlas, "RGBA").save(png)
    for ma in meta_anims:
        ma["rects"] = [[c * w, ma["row"] * h, w, h] for c in range(ma["frames"])]
    meta = {"character": character, "cell": [w, h], "frame_set": frame_set, "aseprite_mode": mode,
            "palette": [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in pal.tolist()], "animations": meta_anims,
            "skipped": skipped}
    js = out_dir / f"{character}_atlas.json"
    js.write_text(json.dumps(meta, indent=2))
    return {"aseprite": str(ase_path), "atlas": str(png), "json": str(js), "mode": mode,
            "animations": [a["name"] for a in meta_anims], "colours": len(pal), "skipped": skipped}
