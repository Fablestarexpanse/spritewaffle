"""One export per character: every facing x action in a single .aseprite (a tag per animation,
so Unity's 2D Aseprite Importer creates one clip each) plus one PNG atlas + JSON.

Each action was pixelized with its own palette; they are merged into one indexed palette (exact
colours, no requantization). Above 255 colours the .aseprite falls back to RGBA.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image

from ..core import attach, fsutil
from ..core.job import Job
from ..frames.video import colour_frames
from . import aseprite
from .sheet import feet_pivot


MAPS = ("depth", "normal")       # reserved per-frame maps: <frame>_depth.png, <frame>_normal.png


def _receipt(out_dir: Path) -> Path:
    return out_dir.with_name(f".{out_dir.name}.receipt")


def _valid_set(frame_set) -> bool:
    return isinstance(frame_set, str) and re.fullmatch(r"[a-zA-Z0-9_-]+", frame_set) is not None


def _frames(sd: Path, aligned: bool) -> list[Path]:
    """The colour frames of a set (000.png, 001.png... only: never a _depth/_normal map). The
    aligned copies when the asset uses align_feet and they are complete."""
    plain = colour_frames(sd / "frames")
    if aligned:
        al = colour_frames(sd / "frames_aligned")
        if len(al) == len(plain):
            return al
    return plain


def _sets(root: Path, frame_set: str):
    if not _valid_set(frame_set):
        raise ValueError("Frame set must be a name such as 12f or 24f.")
    for directory in sorted((root / "04_pixel").glob(f"*/*/{frame_set}")):
        yield directory, directory.parent.parent.name, directory.parent.name


def _qa_problem(path: Path) -> str | None:
    if not path.exists():
        return "no QA report"
    if json.loads(path.read_text(encoding="utf-8"))["status"] != "pass":
        return "QA failed"
    return None


def collect(job_root: Path, frame_set: str = "12f", require_pass: bool = True) -> tuple[list[dict], list[str]]:
    """Animations ready to ship: [{name, facing, action, cells (F,h,w,4), loop, maps}], plus skip
    reasons. maps: {"depth"|"normal": (F,h,w,4)} for the maps that exist (missing frames empty)."""
    anims, skipped = [], []
    aligned = bool(Job(job_root).read_meta()["inputs"].get("align_feet"))
    for sd, facing, action in _sets(job_root, frame_set):
        qa = job_root / "05_qa" / facing / action / frame_set / "report.json"
        if require_pass and (problem := _qa_problem(qa)):
            skipped.append(f"{action}_{facing}: {problem}")
            continue
        files = _frames(sd, aligned)
        if not files:
            skipped.append(f"{action}_{facing}: no colour frames")
            continue
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


def _digest(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except FileNotFoundError:
        return None


def _input_snapshot(root: Path, fps_for, frame_set: str, require_pass: bool) -> dict:
    inputs = Job(root).read_meta()["inputs"]
    aligned = bool(inputs.get("align_feet"))
    attachments = inputs.get("attachments") or {}
    jobs_root = root.parent.parent.resolve()
    files = [root / "04_pixel" / "palette.json"]
    settings = {"align_feet": aligned, "fps": {}, "attachments": {}}
    for directory, facing, action in _sets(root, frame_set):
        qa = root / "05_qa" / facing / action / frame_set / "report.json"
        if require_pass:
            files.append(qa)
            if _qa_problem(qa):
                continue
        frames = _frames(directory, aligned)
        if not frames:
            continue
        settings["fps"][action] = fps_for(action)
        files.extend(frames)
        files.extend(directory / "frames" / f"{frame.stem}_{kind}.png" for frame in frames for kind in MAPS)
        files.extend([directory / "placements.json", root / "03_actions" / facing / action / "selection_report.json"])
        name = f"{action}_{facing}"
        if att := attachments.get(name):
            settings["attachments"][name] = att
            effect_root = (jobs_root / att["effect_job"]).resolve()
            if jobs_root not in effect_root.parents:
                continue
            try:
                effect_dir = attach.effect_directory(effect_root)
            except FileNotFoundError:
                continue
            files.extend(p for p in effect_dir.rglob("*") if p.is_file())
    return {
        "settings": settings,
        "files": {Path(os.path.relpath(p, root)).as_posix(): digest for p in files if (digest := _digest(p)) is not None},
    }


def export_status(job_root: Path, out_dir: Path, fps_for) -> dict:
    """Check the latest character bundle using the options it was exported with."""
    out_dir = Path(out_dir)
    try:
        receipt = json.loads(fsutil.read_text(_receipt(out_dir)))
    except FileNotFoundError:
        return {"status": "untracked" if any(out_dir.glob("*.aseprite")) else "missing"}
    except (ValueError, UnicodeError):
        return {"status": "untracked"}
    if not isinstance(receipt, dict) or receipt.get("version") != 1:
        return {"status": "untracked"}
    if receipt.get("incomplete"):
        return {"status": "incomplete"}
    try:
        frame_set = receipt["options"]["frame_set"]
        require_pass = receipt["options"]["require_pass"]
        previous = receipt["inputs"]
        outputs = receipt["outputs"]
        if (not _valid_set(frame_set) or not isinstance(require_pass, bool) or
                not isinstance(previous["files"], dict) or not isinstance(previous["settings"], dict) or
                not isinstance(outputs, dict) or not outputs or not all(isinstance(digest, str) for digest in outputs.values())):
            return {"status": "untracked"}
    except (KeyError, TypeError):
        return {"status": "untracked"}
    current = _input_snapshot(Path(job_root), fps_for, frame_set, require_pass)
    changed_inputs = sorted(name for name in previous["files"].keys() | current["files"].keys()
                            if previous["files"].get(name) != current["files"].get(name))
    settings_changed = sorted(name for name in current["settings"] if previous["settings"].get(name) != current["settings"][name])
    changed_outputs = []
    resolved_out = out_dir.resolve()
    for name, digest in outputs.items():
        path = (out_dir / name).resolve()
        if resolved_out not in path.parents or _digest(path) != digest:
            changed_outputs.append(name)
    return {"status": "stale" if changed_inputs or settings_changed or changed_outputs else "current",
            "frame_set": frame_set, "changed_inputs": changed_inputs,
            "settings_changed": settings_changed, "changed_outputs": sorted(changed_outputs)}


@contextmanager
def _bundle_lock(out_dir: Path):
    """The OS releases this lock when the writer exits, including after a crash."""
    with out_dir.with_name(f".{out_dir.name}.export.lock").open("a+b") as lock:
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            raise RuntimeError("A character export is already running for this job. Retry when it finishes.") from error
        yield


def export(job_root: Path, out_dir: Path, character: str, fps_for, frame_set: str = "12f",
           require_pass: bool = True, max_size: int = 4096, mirror: str = "pack") -> dict:
    """fps_for(action) -> fps. Returns paths + what was included/skipped. max_size: atlas page
    limit in px; mirror='flip' leaves exact W/NW/SW mirrors out of the atlas (flip at runtime)."""
    job_root, out_dir = Path(job_root), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with _bundle_lock(out_dir):
        snapshot = _input_snapshot(job_root, fps_for, frame_set, require_pass)
        result, files = _write_bundle(job_root, out_dir, character, fps_for, frame_set, require_pass, max_size, mirror)
        if snapshot != _input_snapshot(job_root, fps_for, frame_set, require_pass):
            raise RuntimeError("Character export inputs changed during export. Wait for processing to finish, then export again.")
        outputs = {p.relative_to(out_dir).as_posix(): _digest(p) for p in files}
        if any(digest is None for digest in outputs.values()):
            raise RuntimeError("An export file disappeared before the bundle finished. Export again.")
        fsutil.write_text(_receipt(out_dir), json.dumps({
            "version": 1, "options": {"frame_set": frame_set, "require_pass": require_pass, "max_size": max_size, "mirror": mirror},
            "inputs": snapshot, "outputs": outputs,
        }, indent=2))
    return result


def _write_bundle(job_root: Path, out_dir: Path, character: str, fps_for, frame_set: str,
                  require_pass: bool, max_size: int, mirror: str) -> tuple[dict, list[Path]]:
    anims, skipped = collect(job_root, frame_set, require_pass)
    if not anims:
        raise RuntimeError(f"nothing to export ({'; '.join(skipped) or 'no pixelized animations'})")
    sizes = {a["cells"].shape[1:3] for a in anims}
    if len(sizes) > 1:
        raise ValueError(f"animations have different cell sizes {sizes}; re-run them with one profile")
    h, w = sizes.pop()
    fsutil.write_text(_receipt(out_dir), json.dumps({"version": 1, "incomplete": True}))

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
    job_meta = Job(job_root).read_meta()
    atts = job_meta["inputs"].get("attachments") or {}
    effect_outputs = set()
    if atts:
        import shutil
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
            effect_outputs.update(p for p in dest.rglob("*") if p.is_file())
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
    result = {"aseprite": str(ase_path), "atlas": str(page_files[0]), "pages": [str(p) for p in page_files],
            "engine_json": [str(p) for p in tp_files], "json": str(js), "mode": mode,
            "animations": [a["name"] for a in meta_anims], "colours": len(pal), "skipped": skipped,
            **({"map_pages": map_pages} if map_pages else {})}
    files = [ase_path, js, *page_files, *tp_files, *sorted(effect_outputs)]
    files.extend(out_dir / page for pages in map_pages.values() for page in pages)
    return result, files
