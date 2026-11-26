"""One export per character: every facing x action in a single .aseprite (a tag per animation,
so Unity's 2D Aseprite Importer creates one clip each) plus one PNG atlas + JSON.

Each action was pixelized with its own palette; they are merged into one indexed palette (exact
colours, no requantization). Above 255 colours the .aseprite falls back to RGBA.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

from ..core import alignment, attach, camera, processing, timeline
from ..core.job import Job
from ..core.profile import GameProfile, resolve
from ..qa import checks
from . import aseprite, receipt
from .sheet import feet_pivot


def _receipt(out_dir: Path) -> Path:
    return out_dir.with_name(f".{out_dir.name}.receipt")


def _valid_set(frame_set) -> bool:
    return isinstance(frame_set, str) and re.fullmatch(r"[a-zA-Z0-9_-]+", frame_set) is not None


def _images(sd: Path, aligned: bool, clip: timeline.Clip) -> list[Path]:
    sources = clip.sources
    aligned_by_source = dict(zip(sources, alignment.frames(sd, sources))) if aligned else {}
    return [item.image if item.replaced else aligned_by_source.get(item.source, item.source) for item in clip.items]


def _map_files(items: list[timeline.Frame], images: list[Path], kind: str) -> list[Path | None]:
    return [None if item.replaced or item.inserted else alignment.map_path(image, kind)
            for item, image in zip(items, images)]


def _sets(root: Path, frame_set: str):
    if not _valid_set(frame_set):
        raise ValueError("Frame set must be a name such as 12f or 24f.")
    for directory in sorted((root / "04_pixel").glob(f"*/*/{frame_set}")):
        active = processing.active_sets(directory.parent)
        if active is None or frame_set in active:
            yield directory, directory.parent.parent.name, directory.parent.name


def _qa_problem(path: Path, clip: timeline.Clip) -> str | None:
    report = checks.read(path) or {}
    if timeline.qa_needs_review(report, clip):
        return "QA needs to review timeline changes"
    if not report:
        return "no QA report"
    if report["status"] != "pass":
        return "QA failed"
    return None


def collect(job_root: Path, frame_set: str = "12f", require_pass: bool = True) -> tuple[list[dict], list[str]]:
    """Animations ready to ship: [{name, facing, action, cells (F,h,w,4), loop, maps}], plus skip
    reasons. maps: {"depth"|"normal": (F,h,w,4)} for the maps that exist (missing frames empty)."""
    anims, skipped = [], []
    aligned = bool(Job(job_root).read_meta()["inputs"].get("align_feet"))
    for sd, facing, action in _sets(job_root, frame_set):
        qa = job_root / "05_qa" / facing / action / frame_set / "report.json"
        clip = timeline.read_clip(job_root, sd)
        items, playback = clip.items, clip.playback
        if error := clip.error:
            skipped.append(f"{action}_{facing}: {error}")
            continue
        if require_pass and (problem := _qa_problem(qa, clip)):
            skipped.append(f"{action}_{facing}: {problem}")
            continue
        if not items:
            skipped.append(f"{action}_{facing}: no colour frames")
            continue
        images = _images(sd, aligned, clip)
        cells = timeline.pixels(images)
        aligned_dir = sd / "frames_aligned"
        transform = alignment.metadata(sd) if any(image.parent == aligned_dir for image in images) else {}
        offsets = [transform.get("offsets", {}).get(image.name) if image.parent == aligned_dir else None for image in images]
        maps = {}
        for kind in alignment.MAP_KINDS:
            mp = _map_files(items, images, kind)
            if any(m and m.exists() for m in mp):
                maps[kind] = np.stack([np.array(Image.open(m).convert("RGBA")) if m and m.exists() else np.zeros_like(cells[0])
                                       for m in mp])
        pl = sd / "placements.json"
        places = json.loads(pl.read_text()) if pl.exists() else []
        pivot = transform.get("pivot") or (places[0].get("pivot") if places else None)
        anims.append({"name": f"{action}_{facing}", "facing": facing, "action": action, "cells": cells,
                      "loop": playback.loop, "playback": playback,
                      "pivot": pivot or feet_pivot(cells), "maps": maps, "timeline": items, "clip": clip,
                      "alignment_offsets": offsets})
    return anims, skipped


def merged_palette(anims: list[dict]) -> np.ndarray:
    colours = set()
    for a in anims:
        c = a["cells"]
        colours |= {tuple(x) for x in c[c[..., 3] > 0][:, :3].tolist()}
    return np.array(sorted(colours), np.uint8).reshape(-1, 3)


def _input_snapshot(root: Path, fps_for, frame_set: str, require_pass: bool, profile: GameProfile | None) -> dict:
    job = Job(root)
    inputs = job.read_meta()["inputs"]
    if profile is None and inputs.get("profile"):
        profile = resolve(inputs["profile"])
    aligned = bool(inputs.get("align_feet"))
    border = camera.effective(job, profile)[0].canvas_border_px if aligned else None
    attachments = inputs.get("attachments") or {}
    jobs_root = root.parent.parent.resolve()
    files = [root / "04_pixel" / "palette.json"]
    settings = {"align_feet": aligned, "fps": {}, "attachments": {}}
    for directory, facing, action in _sets(root, frame_set):
        qa = root / "05_qa" / facing / action / frame_set / "report.json"
        clip = timeline.read_clip(root, directory)
        items, playback = clip.items, clip.playback
        if clip.unavailable:
            settings.setdefault("timeline_unavailable", {})[f"{facing}/{action}"] = clip.unavailable
        if saved := playback.signature():
            settings.setdefault("timeline_playback", {})[f"{facing}/{action}"] = saved
        if clip.tags:
            settings.setdefault("timeline_tags", {})[f"{facing}/{action}"] = clip.describe_tags()
        if clip.error:
            continue
        if require_pass:
            files.append(qa)
            if _qa_problem(qa, clip):
                continue
        if not items:
            continue
        check = processing.status(job, profile, facing, action)
        if check["status"] in ("stale", "incomplete"):
            settings.setdefault("processing", {})[f"{facing}/{action}"] = check
        use_aligned = aligned and any(not (item.replaced or item.inserted) for item in items)
        if use_aligned:
            check = alignment.status(root, directory, border)
            if check["status"] in ("stale", "incomplete"):
                settings.setdefault("alignment", {})[f"{facing}/{action}/{frame_set}"] = check
        settings["fps"][action] = fps_for(action)
        images = _images(directory, use_aligned, clip)
        files.extend(images)
        aligned_dir = directory / "frames_aligned"
        if any(image.parent == aligned_dir for image in images):
            files.append(aligned_dir / alignment.METADATA_NAME)
        for kind in alignment.MAP_KINDS:
            files.extend(path for path in _map_files(items, images, kind) if path is not None)
        if edits := timeline.export_settings(items):
            settings.setdefault("timeline", {})[f"{facing}/{action}"] = edits
        if markers := timeline.pose_markers(items):
            settings.setdefault("pose_markers", {})[f"{facing}/{action}"] = markers
        if clip.order:
            settings.setdefault("timeline_order", {})[f"{facing}/{action}"] = clip.order
        if set(clip.sources) - {f.source for f in items}:
            settings.setdefault("timeline_source_count", {})[f"{facing}/{action}"] = len(clip.sources)
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
    return receipt.snapshot(root, files, settings)


def export_status(job_root: Path, out_dir: Path, fps_for, *, profile: GameProfile | None = None) -> dict:
    """Check the latest character bundle using the options it was exported with."""
    out_dir = Path(out_dir)
    path = _receipt(out_dir)
    record = receipt.load(path)
    if record is None:
        return {"status": "untracked" if path.exists() or any(out_dir.glob("*.aseprite")) else "missing"}
    if record.get("incomplete"):
        return {"status": "incomplete"}
    try:
        frame_set = record["options"]["frame_set"]
        require_pass = record["options"]["require_pass"]
        if not _valid_set(frame_set) or not isinstance(require_pass, bool):
            return {"status": "untracked"}
    except (KeyError, TypeError):
        return {"status": "untracked"}
    current = _input_snapshot(Path(job_root), fps_for, frame_set, require_pass, profile)
    result = {"frame_set": frame_set, **receipt.compare(record, out_dir, current)}
    for key in ("processing", "alignment"):
        if stale := current["settings"].get(key):
            result[key] = stale
    return result


def export(job_root: Path, out_dir: Path, character: str, fps_for, frame_set: str = "12f",
           require_pass: bool = True, max_size: int = 4096, mirror: str = "pack", *,
           profile: GameProfile | None = None, pot: bool = False, extrude: int = 0) -> dict:
    """fps_for(action) -> fps. Returns paths + what was included/skipped. max_size: atlas page
    limit in px; mirror='flip' leaves exact W/NW/SW mirrors out of the atlas (flip at runtime);
    pot / extrude: power-of-two pages and edge extrusion (atlas.pack)."""
    job_root, out_dir = Path(job_root), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with receipt.locked(out_dir):
        snapshot = _input_snapshot(job_root, fps_for, frame_set, require_pass, profile)
        for clip, result in snapshot["settings"].get("processing", {}).items():
            processing.require_current(result, clip)
        if stale := snapshot["settings"].get("alignment"):
            raise RuntimeError(f"Re-align feet for {', '.join(stale)} before exporting the character.")
        result, files = _write_bundle(job_root, out_dir, character, fps_for, frame_set, require_pass, max_size, mirror,
                                      pot, extrude)
        if snapshot != _input_snapshot(job_root, fps_for, frame_set, require_pass, profile):
            raise RuntimeError("Character export inputs changed during export. Wait for processing to finish, then export again.")
        receipt.save(_receipt(out_dir), out_dir, snapshot, files, options={
            "frame_set": frame_set, "require_pass": require_pass, "max_size": max_size, "mirror": mirror,
            "pot": pot, "extrude": extrude,
        })
    return result


def _write_bundle(job_root: Path, out_dir: Path, character: str, fps_for, frame_set: str,
                  require_pass: bool, max_size: int, mirror: str, pot: bool = False,
                  extrude: int = 0) -> tuple[dict, list[Path]]:
    anims, skipped = collect(job_root, frame_set, require_pass)
    if not anims:
        raise RuntimeError(f"nothing to export ({'; '.join(skipped) or 'no pixelized animations'})")
    sizes = {a["cells"].shape[1:3] for a in anims}
    if len(sizes) > 1:
        raise ValueError(f"animations have different cell sizes {sizes}; re-run them with one profile")
    h, w = sizes.pop()
    receipt.incomplete(_receipt(out_dir))

    frames, durations, tags, meta_anims = [], [], [], []
    for a in anims:
        start = len(frames)
        n = len(a["cells"])
        source_count = len(a["clip"].sources)
        fps = fps_for(a["action"]) * max(1, source_count // 12)      # Copies extend duration at the source rate.
        frames += list(a["cells"])
        clip_durations = timeline.timings(a["timeline"], round(1000 / fps))
        durations.extend(clip_durations)
        playback = a["playback"]
        named = a["clip"].export_tags(a["name"])
        tags.extend(aseprite.animation_tags(a["name"], playback.start, playback.end, playback.loop, named, offset=start))
        meta_anims.append({"name": a["name"], "facing": a["facing"], "action": a["action"], "frames": n,
                           "fps": fps, "loop": a["loop"], "pivot": a["pivot"],
                           "row": len(meta_anims), "first": start})
        if playback.frame_range is not None:
            meta_anims[-1]["playback_range"] = playback.frame_range
        if named:
            meta_anims[-1]["tags"] = named
        if markers := timeline.pose_markers(a["timeline"]):
            meta_anims[-1]["pose_markers"] = markers
        if any(f.duration_ms is not None for f in a["timeline"]):
            meta_anims[-1]["durations_ms"] = clip_durations
        if a["clip"].order:
            meta_anims[-1]["frame_ids"] = a["clip"].order
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
        for ma, anim in zip(meta_anims, anims):
            att = atts.get(ma["name"])
            if not att:
                continue
            att = attach.for_timeline(att, anim["clip"])
            if att is None:
                continue
            frame = att["frame"]
            offsets = anim["alignment_offsets"]
            if 0 <= frame < len(offsets) and offsets[frame] is not None:
                point = [value + delta for value, delta in zip(att["point"], offsets[frame])]
                att = {**att, "point": point}
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
    if len(pal) <= 255 and not any(timeline.alternate_images(a["timeline"]) for a in anims):
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
    pages, layout = atlasmod.pack(anims, max_size=max_size, mirror=mirror, pot=pot, extrude=extrude)
    page_files = atlasmod.save_pages(out_dir, base, pages)
    tp_files = atlasmod.write_texturepacker(out_dir, base, pages, layout, (w, h),
                                            {m["name"]: m["pivot"] for m in meta_anims},
                                            {m["name"]: m for m in meta_anims})
    map_pages = {}                                               # depth/normal: same rectangles as the colour pages
    for kind in alignment.MAP_KINDS:
        for old in out_dir.glob(f"{base}_{kind}_*.png"):
            old.unlink()
        if any(kind in a.get("maps", {}) for a in anims):
            map_pages[kind] = [p.name for p in atlasmod.save_map_pages(out_dir, f"{base}_{kind}",
                                                                      atlasmod.map_pages(pages, layout, anims, kind, extrude))]
    for ma in meta_anims:
        ma.pop("row", None)
        ma["frames_atlas"] = layout[ma["name"]]["frames"]
        ma["flip_x_of"] = layout[ma["name"]]["flip_x_of"]
    one = {tuple(m["pivot"]) for m in meta_anims}
    pivot = list(one.pop()) if len(one) == 1 else None          # one pivot for the whole character
    meta = {"character": character, "cell": [w, h], "frame_set": frame_set, "aseprite_mode": mode,
            "pivot": pivot, "pivot_norm": [pivot[0] / w, 1 - pivot[1] / h] if pivot else None,
            **({"palette": [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in pal.tolist()]} if mode == "indexed" else {}),
            "pages": [{"image": p.name, "w": int(pg.shape[1]), "h": int(pg.shape[0])} for p, pg in zip(page_files, pages)],
            "max_size": max_size, "mirror": mirror, "pot": pot, "extrude": extrude, "animations": meta_anims,
            "skipped": skipped, **({"map_pages": map_pages} if map_pages else {})}
    js = out_dir / f"{character}_atlas.json"
    js.write_text(json.dumps(meta, indent=2))
    from . import godot                                          # Godot 4: SpriteFrames .tres + scene
    godot_files = godot.write(out_dir, meta, pixel=mode == "indexed")
    result = {"aseprite": str(ase_path), "atlas": str(page_files[0]), "pages": [str(p) for p in page_files],
            "engine_json": [str(p) for p in tp_files], "json": str(js), "mode": mode,
            "godot": [str(p) for p in godot_files],
            "animations": [a["name"] for a in meta_anims], "colours": len(pal), "skipped": skipped,
            **({"map_pages": map_pages} if map_pages else {})}
    files = [ase_path, js, *page_files, *tp_files, *godot_files, *sorted(effect_outputs)]
    files.extend(out_dir / page for pages in map_pages.values() for page in pages)
    return result, files
