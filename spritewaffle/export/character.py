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


MAPS = ("depth", "normal")       # reserved per-frame maps: <frame>_depth.png, <frame>_normal.png


def _frames(sd: Path, aligned: bool) -> list[Path]:
    """The colour frames of a set (000.png, 001.png... only: never a _depth/_normal map). The
    aligned copies when the asset uses align_feet and they are complete."""
    plain = sorted((sd / "frames").glob("[0-9][0-9][0-9].png"))
    if aligned:
        al = sorted((sd / "frames_aligned").glob("[0-9][0-9][0-9].png"))
        if len(al) == len(plain):
            return al
    return plain


def collect(job_root: Path, frame_set: str = "12f", require_pass: bool = True) -> tuple[list[dict], list[str]]:
    """Animations ready to ship: [{name, facing, action, cells (F,h,w,4), loop, maps}], plus skip
    reasons. maps: {"depth"|"normal": (F,h,w,4)} for the maps that exist (missing frames empty)."""
    anims, skipped = [], []
    aligned = bool(json.loads((Path(job_root) / "job.json").read_text())["inputs"].get("align_feet"))
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
        files = _frames(sd, aligned)
        cells = np.stack([np.array(Image.open(p).convert("RGBA")) for p in files])
        maps = {}
        for kind in MAPS:
            mp = [sd / "frames" / f"{p.stem}_{kind}.png" for p in files]
            if any(m.exists() for m in mp):
                maps[kind] = np.stack([np.array(Image.open(m).convert("RGBA")) if m.exists() else np.zeros_like(cells[0])
                                       for m in mp])
        sel = job_root / "03_actions" / facing / action / "selection_report.json"
        loop = json.loads(sel.read_text())["loop"] if sel.exists() else True
        pl = sd / "placements.json"
        places = json.loads(pl.read_text()) if pl.exists() else []
        pivot = places[0].get("pivot") if places else None
        anims.append({"name": f"{action}_{facing}", "facing": facing, "action": action, "cells": cells, "loop": loop,
                      "pivot": pivot or feet_pivot(cells), "maps": maps})
    return anims, skipped


def merged_palette(anims: list[dict]) -> np.ndarray:
    colours = set()
    for a in anims:
        c = a["cells"]
        colours |= {tuple(x) for x in c[c[..., 3] > 0][:, :3].tolist()}
    return np.array(sorted(colours), np.uint8).reshape(-1, 3)


def export(job_root: Path, out_dir: Path, character: str, fps_for, frame_set: str = "12f",
           require_pass: bool = True, max_size: int = 4096, mirror: str = "pack") -> dict:
    """fps_for(action) -> fps. Returns paths + what was included/skipped. max_size: atlas page
    limit in px; mirror='flip' leaves exact W/NW/SW mirrors out of the atlas (flip at runtime)."""
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
        tags.append((a["name"], start, start + n - 1, "forward", 0 if a["loop"] else 1))
        meta_anims.append({"name": a["name"], "facing": a["facing"], "action": a["action"], "frames": n,
                           "fps": fps, "loop": a["loop"], "pivot": a["pivot"],
                           "row": len(meta_anims), "first": start})
    frames = np.stack(frames)

    pal = merged_palette(anims)
    jp = Path(job_root) / "04_pixel" / "palette.json"           # job palette: keep its order (the artist's ramp)
    if jp.exists():
        jpal = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in json.loads(jp.read_text())["colours"]], np.uint8)
        if {tuple(c) for c in pal.tolist()} <= {tuple(c) for c in jpal.tolist()}:
            pal = jpal
    # attached effects: events per animation, and the effect's files next to the character
    job_meta = json.loads((Path(job_root) / "job.json").read_text())
    atts = job_meta["inputs"].get("attachments") or {}
    if atts:
        import shutil
        from ..core import attach
        for ma in meta_anims:
            att = atts.get(ma["name"])
            if not att:
                continue
            try:
                _, fxmeta, fxdir = attach.effect_files(Path(job_root).parent.parent / att["effect_job"])
            except FileNotFoundError:
                continue
            ma["events"] = [attach.event(att, fxmeta["fps"])]
            dest = out_dir / "effects" / fxdir.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(fxdir, dest)
    keys, last = [], None                                        # one "pivot" slice, a key where it changes
    for ma in meta_anims:
        pv = (int(ma["pivot"][0]), int(ma["pivot"][1]))
        if pv != last:
            keys.append((ma["first"], 0, 0, w, h, *pv))
            last = pv
    slices = [("pivot", keys)]
    ase_path = out_dir / f"{character}.aseprite"
    if len(pal) <= 255:
        lut = {tuple(c): i for i, c in enumerate(pal.tolist())}
        idx = np.full(frames.shape[:3], -1, int)
        m = frames[..., 3] > 0
        idx[m] = [lut[tuple(c)] for c in frames[m][:, :3].tolist()]
        aseprite.write(ase_path, idx, pal, durations, tags, slices=slices)
        mode = "indexed"
    else:
        aseprite.write_rgba(ase_path, frames, durations, tags, slices=slices)
        mode = "rgba"

    from . import atlas as atlasmod
    base = f"{character}_atlas"
    old = out_dir / f"{base}.png"                              # the old single-sheet atlas
    old.unlink(missing_ok=True)
    pages, layout = atlasmod.pack(anims, max_size=max_size, mirror=mirror)
    page_files = atlasmod.save_pages(out_dir, base, pages)
    tp_files = atlasmod.write_texturepacker(out_dir, base, pages, layout, (w, h),
                                            {m["name"]: m["pivot"] for m in meta_anims})
    map_pages = {}                                               # depth/normal: same rectangles as the colour pages
    for kind in MAPS:
        for old in out_dir.glob(f"{base}_{kind}_*.png"):
            old.unlink()
        if any(kind in a.get("maps", {}) for a in anims):
            map_pages[kind] = [p.name for p in atlasmod.save_map_pages(out_dir, f"{base}_{kind}",
                                                                      atlasmod.map_pages(pages, layout, anims, kind))]
    for ma in meta_anims:
        ma.pop("row", None)
        ma["frames_atlas"] = layout[ma["name"]]["frames"]
        ma["flip_x_of"] = layout[ma["name"]]["flip_x_of"]
    one = {tuple(m["pivot"]) for m in meta_anims}
    pivot = list(one.pop()) if len(one) == 1 else None          # one pivot for the whole character
    meta = {"character": character, "cell": [w, h], "frame_set": frame_set, "aseprite_mode": mode,
            "pivot": pivot, "pivot_norm": [pivot[0] / w, 1 - pivot[1] / h] if pivot else None,
            "palette": [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in pal.tolist()],
            "pages": [{"image": p.name, "w": int(pg.shape[1]), "h": int(pg.shape[0])} for p, pg in zip(page_files, pages)],
            "max_size": max_size, "mirror": mirror, "animations": meta_anims,
            "skipped": skipped, **({"map_pages": map_pages} if map_pages else {})}
    js = out_dir / f"{character}_atlas.json"
    js.write_text(json.dumps(meta, indent=2))
    return {"aseprite": str(ase_path), "atlas": str(page_files[0]), "pages": [str(p) for p in page_files],
            "engine_json": [str(p) for p in tp_files], "json": str(js), "mode": mode,
            "animations": [a["name"] for a in meta_anims], "colours": len(pal), "skipped": skipped,
            **({"map_pages": map_pages} if map_pages else {})}
