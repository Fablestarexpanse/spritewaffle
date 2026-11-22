"""Phase 1 stages. Each reads/writes only inside the job folder and can be re-run alone."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from ..export import aseprite, receipt, sheet as sheetmod
from ..frames import analysis, contact, layout, picker, video
from ..pixel.pipeline import PixelParams, pixelize
from ..qa import checks
from . import fsutil, processing, timeline
from .job import Job
from .profile import GameProfile

CYCLIC = {"idle", "walk", "run", "march"}


def _ctx(job: Job, facing: str | None, action: str | None) -> tuple[str, str]:
    inp = job.read_meta()["inputs"]
    facing, action = facing or inp.get("facing"), action or inp.get("action")
    if not facing or not action:
        raise ValueError("facing/action unknown: pass --facing/--action or run extract first")
    return facing, action


def _save_pngs(frames, folder: Path, names) -> None:
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for f, n in zip(frames, names):
        Image.fromarray(f).save(folder / f"{n}.png")


def extract(job: Job, src: str | Path, facing: str, action: str) -> dict:
    d = _clip_path(job, "03_actions", facing, action)
    d.mkdir(parents=True, exist_ok=True)
    raw = d / ("raw" + Path(src).suffix.lower())
    extracted = d / "extracted"
    if not extracted.resolve().is_relative_to(d.resolve()):
        raise ValueError("Extracted frames must stay inside the action directory.")
    if Path(src).resolve() != raw.resolve():
        shutil.copyfile(src, raw)
    digest = receipt.digest(raw)
    extracted.mkdir(exist_ok=True)
    report = extracted / "extraction_report.json"
    fsutil.write_text(report, json.dumps({"clip_source": {"name": raw.name, "incomplete": True}}))
    rep = video.extract(raw, extracted, write_report=False)
    if receipt.digest(raw) != digest:
        raise RuntimeError("The saved clip changed during extraction. Re-process frames again.")
    # The decoder overwrites its numbered frames. A shorter replacement leaves an old tail.
    for path in extracted.glob("*.png"):
        if len(path.stem) >= 5 and path.stem.isdecimal() and int(path.stem) >= rep["frame_count"]:
            path.unlink()
    frames = video.load(video.list_frames(extracted))
    frozen, diff = analysis.is_frozen(frames)
    rep.update(frozen=frozen, mean_frame_diff=round(diff, 3), clip_source={"name": raw.name, "sha256": digest})
    contact.write(frames, d / "contact_sheet.png")
    fsutil.write_text(report, json.dumps(rep, indent=2))
    job.update_inputs(facing=facing, action=action)
    job.log_provenance(str(raw.relative_to(job.root)), source=str(src))
    job.set_stage(f"extract:{facing}/{action}", "warn" if frozen else "done", frames=rep["frame_count"], frozen=frozen)
    return rep


def contact_sheet(job: Job, folder: str | Path, facing=None, action=None) -> Path:
    facing, action = _ctx(job, facing, action)
    folder = Path(folder)
    paths = video.list_frames(folder)
    out = job.action_dir(facing, action) / f"contact_{folder.name}.png"
    return contact.write(video.load(paths), out, labels=[p.stem for p in paths])


def select(job: Job, facing=None, action=None, counts=(12, 24), indices: str | None = None,
           loop: bool | None = None) -> dict:
    facing, action = _ctx(job, facing, action)
    d = job.action_dir(facing, action)
    processing.require_extracted(d)
    paths = video.list_frames(d / "extracted")
    frames = video.load(paths)
    if loop is None:                                   # the action's own setting (edited, AI, animal preset)
        rep = job.action_dir(facing, action) / "action_report.json"
        spec = json.loads(rep.read_text()).get("spec", {}) if rep.exists() else {}
        loop = bool(spec["cyclic"]) if "cyclic" in spec else action in CYCLIC
    clip = picker.analyse(frames)
    res = picker.select(clip, counts=counts, loop=loop, manual=indices)
    report = {"start": res["start"], "end": res["end"], "loop": loop, "loop_seam": res.get("loop_seam"),
              "keys": [{"source": k, "reason": r} for k, r in res["keys"]],
              "dropped": {str(k): v for k, v in res["dropped"].items()}, "warnings": res["warnings"], "sets": {}}
    for n, sel in res["sets"].items():
        _save_pngs([frames[i] for i in sel.indices], d / f"selected_{n}f", [f"{o:03d}_src{s:05d}" for o, s in enumerate(sel.indices)])
        report["sets"][str(n)] = sel.as_report()
    (d / "selection_report.json").write_text(json.dumps(report, indent=2))
    job.set_stage(f"select:{facing}/{action}", "done", sets=list(report["sets"]), warnings=res["warnings"])
    return report


def pixel(job: Job, profile: GameProfile, facing=None, action=None, palette: int | None = None) -> dict:
    """Pixelize the union of all selected sets as ONE batch (one palette, temporal order), then lay
    every set out with preserve-canvas."""
    facing, action = _ctx(job, facing, action)
    d = job.action_dir(facing, action)
    processing.require_extracted(d)
    inputs = processing.selection(d)
    sets, loop, paths = inputs
    from ..prompts import styles
    from . import camera, job_palette
    st = styles.get(styles.of_job(job))
    pal = (palette or job_palette.resolve(job, profile)[0]) if st["post"] == "pixel" else None
    tracked = {"version": 1, "palette_override": palette, "profile_palette": profile.locked_palette is not None,
               "inputs": processing.snapshot(job, profile, d, inputs, palette, pal)}
    frames = video.load(list(paths.values()))
    pos = {source: n for n, source in enumerate(paths)}
    if st["post"] == "smooth":                       # hand-painted / anime / comic: no grid, no palette
        from ..pixel import smooth
        art, k = smooth.process(frames, camera.character_height(job, profile) * st["scale"], despill=profile.despill)
        info = _write_pixel_sets(job, profile, facing, action,
                                 {n: ([art[pos[i]] for i in idxs], idxs) for n, idxs in sets.items()},
                                 None, {"style": st["name"], "scale": round(k, 4), "processing": tracked},
                                 cell=profile.cell_size * st["scale"])
        processing.require_current(processing.status(job, profile, facing, action), f"{facing}/{action}")
        job.set_stage(f"pixelize:{facing}/{action}", "done", style=st["name"], scale=round(k, 4))
        return info
    params = PixelParams(palette=pal, pixel_size=profile.pixel_size, target_height=camera.character_height(job, profile),
                         loop=loop, outline=profile.outline, despill=profile.despill)
    res = pixelize(frames, params)
    if not palette and not isinstance(pal, list):
        job_palette.lock_from_clip(job, res.palette, f"{facing}/{action}")
        tracked["inputs"]["settings"]["palette"] = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in res.palette.tolist()]
    grid = {"size": res.grid.size, "ox": res.grid.ox, "oy": res.grid.oy, "source": res.grid.source,
            "score": round(res.grid.score, 3), "resample": res.resample}
    info = _write_pixel_sets(job, profile, facing, action,
                             {n: ([res.rgba(pos[i]) for i in idxs], idxs) for n, idxs in sets.items()},
                             res.palette, {"grid": grid, "processing": tracked})
    processing.require_current(processing.status(job, profile, facing, action), f"{facing}/{action}")
    job.set_stage(f"pixelize:{facing}/{action}", "done", grid=info["grid"], palette_size=len(res.palette))
    return info


def _write_pixel_sets(job: Job, profile: GameProfile, facing: str, action: str, sets: dict, palette: np.ndarray | None,
                      info: dict, cell: int | None = None) -> dict:
    """Write the 04_pixel layout every later stage reads. sets: {"12": (art_frames, sources), ...}.
    Each set is laid out with preserve-canvas (one placement for all frames). palette=None: a
    full-colour style (no indices.npy; export writes RGBA)."""
    out = job.stage_dir("04_pixel") / facing / action
    cell = cell or profile.cell_size
    pal_list = [] if palette is None else [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in np.asarray(palette).tolist()]
    info = {**info, "palette": pal_list, "cell": cell, "sets": {}, "warnings": list(info.get("warnings", []))}
    report_path = out / "pixel_report.json"
    if "processing" in info:
        out.mkdir(parents=True, exist_ok=True)
        fsutil.write_text(report_path, json.dumps({**info, "processing": {**info["processing"], "incomplete": True}}))
    for n, (art, sources) in sets.items():
        cells, places = layout.preserve_canvas(list(art), (cell, cell))
        for w in (x.replace(" in this clip", "").replace(" (a ", f" in the {n}f frames (a ", 1)
                  for x in _fit_warnings(places[0], cell, profile.cell_size)):
            if not any(w.split("(")[0] == x.split("(")[0] for x in info["warnings"]):
                info["warnings"].append(w)
        sd = out / f"{n}f"
        _save_pngs(cells, sd / "frames", [f"{k:03d}" for k in range(len(cells))])
        (sd / "indices.npy").unlink(missing_ok=True)
        if palette is not None:
            np.save(sd / "indices.npy", np.stack([_rgba_to_index(c, palette) for c in cells]))
        (sd / "placements.json").write_text(json.dumps([p.as_dict() for p in places], indent=2))
        (sd / "footpoints.json").write_text(json.dumps([layout.foot_point(c) for c in cells]))   # manifest
        prev = np.concatenate(list(cells), axis=1)
        k = 4 if palette is not None else 1                      # pixel art previews upscaled, smooth art as is
        Image.fromarray(prev).resize((prev.shape[1] * k, prev.shape[0] * k), Image.NEAREST).save(sd / "preview_4x.png")
        info["sets"][str(n)] = {"frames": len(cells), "sources": list(sources)}
    fsutil.write_text(report_path, json.dumps(info, indent=2))
    return info


def _events(job: Job, facing: str, action: str, clip: timeline.Clip | None = None) -> list:
    """Attached effects as export events (see core/attach.py)."""
    from . import attach
    att = attach.get(job, facing, action)
    if not att:
        return []
    if clip is not None:
        att = attach.for_timeline(att, clip)
        if att is None:
            return []
    try:
        directory = attach.effect_directory(job.root.parent.parent / att["effect_job"])
        meta = json.loads((directory / f"{directory.name}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    return [attach.event(att, meta["fps"])]


def _fit_warnings(pl, cell: int, profile_cell: int) -> list[str]:
    """Does the action fit the cell with the feet centred? Too wide: the feet were moved off centre.
    Too tall: the top was cut off. Both name the profile cell size that would fit (painted styles
    draw at x4, so the suggestion is in profile units)."""
    if pl.pivot is None:
        return []
    w, h = round(pl.crop[2] * pl.scale), round(pl.crop[3] * pl.scale)
    feet = pl.pivot[0] - pl.paste[0]                         # feet, from the art's left edge
    need = max(2 * max(feet, w - feet) + 2, h + 2)           # feet centred, 1 px margin all round
    mult = max(1, cell // profile_cell)
    fit = max(-(-int(-(-need // mult)) // 8) * 8, profile_cell + 8)
    out = []
    off = pl.pivot[0] - cell / 2
    if off:
        out.append(f"pivot: the action is too wide for the {cell}px cell, so the feet sit {abs(off):.0f}px "
                   f"{'left' if off < 0 else 'right'} of centre in this clip (a {fit}px profile cell would fit it: Sizes…)")
    if pl.paste[0] < 0 or pl.paste[0] + w > cell:
        cut = max(0, -pl.paste[0]) + max(0, pl.paste[0] + w - cell)
        out.append(f"cut off: {cut}px of the sides don't fit in the {cell}px cell (the sprite is {w}px wide; "
                   f"a {fit}px profile cell would fit it: Sizes…)")
    if pl.paste[1] < 0:
        out.append(f"cut off: the top {-pl.paste[1]}px of the action don't fit in the {cell}px cell "
                   f"(a {fit}px profile cell would fit it: Sizes…)")
    return out


def _rgba_to_index(cell: np.ndarray, pal: np.ndarray) -> np.ndarray:
    idx = np.full(cell.shape[:2], -1, int)
    m = cell[..., 3] > 0
    lut = {tuple(c): i for i, c in enumerate(pal.tolist())}
    idx[m] = [lut[tuple(c)] for c in cell[m][:, :3].tolist()]
    return idx


def _load_set(sd: Path, items: list[timeline.Frame]) -> tuple[np.ndarray, list[dict]]:
    cells = timeline.pixels([frame.image for frame in items])
    return cells, json.loads((sd / "placements.json").read_text(encoding="utf-8"))


def _playable_clips(root: Path, sets: list[Path]) -> list[tuple[Path, timeline.Clip]]:
    clips = []
    for sd in sets:
        clip = timeline.read_clip(root, sd)
        clip.require_valid()
        clips.append((sd, clip))
    return clips


def qa(job: Job, profile: GameProfile, facing=None, action=None) -> dict:
    facing, action = _ctx(job, facing, action)
    pdir = job.root / "04_pixel" / facing / action
    prep = json.loads((pdir / "pixel_report.json").read_text())
    pal_n = len(prep["palette"])
    from . import job_palette
    jp = job_palette.current(job, profile)
    cap = len(jp["colours"]) if jp else profile.palette_size     # a loaded palette may be larger than the profile's
    results = {}
    for sd, clip in _playable_clips(job.root, _action_sets(pdir)):
        sources, items, playback = clip.sources, clip.items, clip.playback
        cells, places = _load_set(sd, items)
        if len(places) == len(sources):
            placement_by_source = dict(zip(sources, places))
            if places:
                places = [placement_by_source.get(f.source, places[0]) for f in items]
        limit = min(pal_n, cap) if pal_n else 1 << 30      # full-colour styles: no palette limit
        tags = clip.describe_tags()
        r = checks.run(cells, places, "preserve-canvas", palette_size=limit, loop=playback.loop,
                       playback_range=playback.frame_range, named_tags=tags)
        r["frame_files"] = [frame.source_id for frame in items]
        if settings := playback.signature():
            r["timeline_playback"] = settings
        if tags:
            r["timeline_tags"] = tags
        if active := timeline.alternate_images(items):
            r["timeline_replacements"] = active
        if clip.order:
            r["timeline_order"] = clip.order
        r.setdefault("warnings", []).extend(prep.get("warnings", []))
        checks.write(r, job.stage_dir("05_qa") / facing / action / sd.name / "report.json")
        results[sd.name] = r["status"]
    status = "fail" if "fail" in results.values() else "pass"
    job.set_stage(f"qa:{facing}/{action}", status, sets=results)
    return results


def qa_review(job: Job, facing=None, action=None) -> dict:
    facing, action = _ctx(job, facing, action)
    directory = _clip_path(job, "05_qa", facing, action)
    return {path.parent.name: checks.review(report) for path in sorted(directory.glob("*/report.json"))
            if (report := checks.read(path)) is not None}


def _clip_path(job: Job, stage: str, facing: str, action: str) -> Path:
    if any(name in (".", "..") or any(c in name for c in "/\\:\0") for name in (facing, action)):
        raise ValueError("Facing and action must each be a single name.")
    path = job.root / stage / facing / action
    if job.root.resolve() not in path.resolve().parents:
        raise ValueError("Action paths must stay inside the job.")
    return path


def _action_sets(pdir: Path) -> list[Path]:
    if not pdir.is_dir():
        return []
    active = processing.active_sets(pdir)
    return sorted(p for p in pdir.iterdir() if p.is_dir() and p.name.rstrip("f").isdecimal()
                  and (active is None or p.name in active))


def _action_receipt(out: Path, fmt: str) -> Path:
    return out.with_name(f".{out.name}.{fmt}.receipt")


def _action_snapshot(job: Job, profile: GameProfile, facing: str, action: str, pdir: Path, fmt: str) -> dict:
    sel = _clip_path(job, "03_actions", facing, action) / "selection_report.json"
    report = pdir / "pixel_report.json"
    sets = _action_sets(pdir)
    indices = [sd / "indices.npy" for sd in sets if (sd / "indices.npy").is_file()]
    files = [sd / "placements.json" for sd in sets]
    settings = {"fps": profile.fps(action), "sets": [sd.name for sd in sets],
                "loop": json.loads(sel.read_text(encoding="utf-8"))["loop"] if sel.is_file() else None,
                "indexed_sets": [p.parent.name for p in indices]}
    if fmt == "png":
        settings["events"] = _events(job, facing, action)
    elif indices:
        settings["palette"] = json.loads(report.read_text(encoding="utf-8"))["palette"] if report.is_file() else None
        files.extend(indices)
    for sd in sets:
        clip = timeline.read_clip(job.root, sd)
        items, playback = clip.items, clip.playback
        files.extend(frame.image for frame in items)
        if clip.unavailable:
            settings.setdefault("timeline_unavailable", {})[sd.name] = clip.unavailable
        if saved := playback.signature():
            settings.setdefault("timeline_playback", {})[sd.name] = saved
        if clip.tags:
            settings.setdefault("timeline_tags", {})[sd.name] = clip.describe_tags()
        if edits := timeline.export_settings(items):
            settings.setdefault("timeline", {})[sd.name] = edits
        if clip.order:
            settings.setdefault("timeline_order", {})[sd.name] = clip.order
        if fmt == "png":
            if (events := _events(job, facing, action, clip)) != settings["events"]:
                settings.setdefault("events_by_set", {})[sd.name] = events
            if markers := timeline.pose_markers(items):
                settings.setdefault("pose_markers", {})[sd.name] = markers
    return receipt.snapshot(job.root, files, settings)


def export_status(job: Job, profile: GameProfile, facing=None, action=None) -> dict:
    """Check the PNG and Aseprite packages from the most recent write of each format."""
    facing, action = _ctx(job, facing, action)
    pdir = _clip_path(job, "04_pixel", facing, action)
    out = _clip_path(job, "06_export", facing, action)
    upstream = processing.status(job, profile, facing, action)
    result = {}
    for fmt, patterns in (("png", ("*.png", "*.json", "*_preview.gif", "frames/*.png")), ("aseprite", ("*.aseprite",))):
        path = _action_receipt(out, fmt)
        record = receipt.load(path)
        if record is None:
            legacy = path.exists() or any(any(out.glob(f"*/{pattern}")) for pattern in patterns)
            result[fmt] = {"status": "untracked" if legacy else "missing"}
        elif record.get("incomplete"):
            result[fmt] = {"status": "incomplete"}
        elif upstream["status"] in ("stale", "incomplete"):
            result[fmt] = {"status": "stale"}
        else:
            result[fmt] = receipt.compare(record, out, _action_snapshot(job, profile, facing, action, pdir, fmt))
    return {"facing": facing, "action": action, "formats": result, "processing": upstream}


def export(job: Job, profile: GameProfile, facing=None, action=None, fmt: str = "both") -> dict:
    facing, action = _ctx(job, facing, action)
    if fmt not in ("png", "aseprite", "both"):
        raise ValueError("Export format must be png, aseprite, or both.")
    pdir = _clip_path(job, "04_pixel", facing, action)
    out = _clip_path(job, "06_export", facing, action)
    formats = ("png", "aseprite") if fmt == "both" else (fmt,)
    out.parent.mkdir(parents=True, exist_ok=True)
    with receipt.locked(out):
        upstream = processing.status(job, profile, facing, action)
        processing.require_current(upstream, f"{facing}/{action}")
        previous_png = (receipt.load(_action_receipt(out, "png")) or {}) if "png" in formats else {}
        before = {kind: _action_snapshot(job, profile, facing, action, pdir, kind) for kind in formats}
        sets = [pdir / name for name in before[formats[0]]["settings"]["sets"]]
        if not sets:
            raise RuntimeError(f"No processed frame sets for {facing}/{action}. Pixelize the action first.")
        written, artifacts = _write_action_export(job, profile, facing, action, pdir, out, sets, formats)
        after = {kind: _action_snapshot(job, profile, facing, action, pdir, kind) for kind in formats}
        if before != after or upstream != processing.status(job, profile, facing, action):
            raise RuntimeError("Action export inputs changed during export. Wait for processing to finish, then export again.")
        if previous_png:
            receipt.prune_exported_frames(out, previous_png, artifacts["png"])
        for kind in formats:
            receipt.save(_action_receipt(out, kind), out, before[kind], artifacts[kind])
        job.set_stage(f"export:{facing}/{action}", "done", formats=fmt)
    return written


def _write_action_export(job, profile, facing, action, pdir, out_dir, sets, formats):
    pal = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)]
                    for h in json.loads((pdir / "pixel_report.json").read_text(encoding="utf-8"))["palette"]], np.uint8).reshape(-1, 3)
    base_fps = profile.fps(action)
    written = {}
    artifacts = {kind: [] for kind in formats}
    for sd, clip in _playable_clips(job.root, sets):
        sources, items, playback = clip.sources, clip.items, clip.playback
        fps = timeline.action_fps(base_fps, sd.name)
        cells, places = _load_set(sd, items)
        durations = timeline.timings(items, round(1000 / fps))
        pivot = places[0].get("pivot") if places else None        # None: laid out before pivots existed
        name = f"{action}_{facing}_{sd.name}"
        animation = f"{action}_{facing}"
        named = clip.export_tags(animation)
        out = out_dir / sd.name
        files = {}
        original_indexed = (sd / "indices.npy").is_file()
        indexed = original_indexed and not timeline.alternate_images(items)
        if "aseprite" in formats and indexed:
            ind = np.load(sd / "indices.npy")
            opaque = cells[..., 3] > 0
            if ind.shape != (len(sources), *opaque.shape[1:]):
                raise ValueError(f"{sd.name} indexed pixels disagree with the PNG frames. Pixelize again before exporting Aseprite.")
            index_by_source = {path: i for i, path in enumerate(sources)}
            ind = ind[[index_by_source[f.source] for f in items]]
            if (not np.issubdtype(ind.dtype, np.integer) or
                    not np.array_equal(ind >= 0, opaque) or np.any(ind[opaque] >= len(pal)) or
                    not np.array_equal(pal[ind[opaque]], cells[opaque, :3])):
                raise ValueError(f"{sd.name} indexed pixels disagree with the PNG frames. Pixelize again before exporting Aseprite.")
        if "png" in formats:
            if not artifacts["png"]:
                receipt.incomplete(_action_receipt(out_dir, "png"))
            png = sheetmod.export_png(out, name, cells, fps, loop=playback.loop, pivot=pivot,
                                      events=_events(job, facing, action, clip),
                                      preview_scale=4 if original_indexed else 1,
                                      durations_ms=durations if any(f.duration_ms is not None for f in items) else None,
                                      frame_ids=clip.order,
                                      playback_range=playback.frame_range,
                                      preview_once=not playback.loop and bool(playback.signature()), tags=named,
                                      pose_markers=timeline.pose_markers(items))
            artifacts["png"].extend(png.pop("frames"))
            artifacts["png"].extend(png.values())
            files.update({key: str(path) for key, path in png.items()})
        if "aseprite" in formats:
            tags = aseprite.animation_tags(animation, playback.start, playback.end, playback.loop, named)
            pv = pivot or sheetmod.feet_pivot(cells)
            slices = [("pivot", [(0, 0, 0, cells.shape[2], cells.shape[1], int(pv[0]), int(pv[1]))])]
            if not artifacts["aseprite"]:
                receipt.incomplete(_action_receipt(out_dir, "aseprite"))
            if indexed:
                p = aseprite.write(out / f"{name}.aseprite", ind, pal, durations, tags=tags,
                                   slices=slices)
            else:
                p = aseprite.write_rgba(out / f"{name}.aseprite", cells, durations, tags=tags,
                                         slices=slices)
            files["aseprite"] = str(p)
            artifacts["aseprite"].append(p)
        written[sd.name] = files
    return written, artifacts


def flow_transfer(job: Job, profile: GameProfile, facing: str, action: str, motion_name: str,
                  counts=(12, 24), loop: bool | None = None) -> dict:
    """Pixel-exact motion transfer (experimental): the approved facing, pixelized once, is warped
    by the optical flow of an approved library motion. Output pixels are copied from the facing's
    art, so palette and identity are exactly the facing's. Writes the same 04_pixel layout as
    `pixel`, so qa/export run unchanged."""
    from ..frames import flowtransfer
    from . import job_palette, motion
    d = _clip_path(job, "03_actions", facing, action)
    job.require_approved("facings")
    from ..prompts import styles
    if styles.get(styles.of_job(job))["post"] != "pixel":
        raise RuntimeError("pixel-exact flow transfer works on pixel art only; this job's style is "
                           f"'{styles.of_job(job)}' (use an H3 render)")
    m = motion.get(motion_name, job.root.parent.parent)
    if m["status"] != "approved":
        raise RuntimeError(f"motion '{motion_name}' is {m['status']}; approve it first")
    face = job.root / "02_facings" / f"{facing}.png"
    if not face.exists():
        raise FileNotFoundError(f"facing {facing} not generated")
    pal = job_palette.resolve(job, profile)[0]
    loop = action in CYCLIC if loop is None else loop
    tracked = {"version": 1, "profile_palette": profile.locked_palette is not None,
               "counts": list(counts), "loop": loop, "inputs": processing.flow_snapshot(job, profile, facing, m, pal)}

    # 1. target art: the facing, pixelized once at the PROFILE's sprite height (same scale as H3
    #    actions). Grid detection on stills can lock onto a coarse grid (measured: 29 px -> a 19 px
    #    sprite next to 48 px H3 animations of the same character).
    rgb = np.array(Image.open(face).convert("RGB"))
    from ..pixel import chroma as _chroma
    ys = np.where((_chroma.key(rgb)[..., 3] > 0).any(1))[0]
    size = profile.pixel_size or max(1, round((ys[-1] - ys[0] + 1) / profile.sprite_height_px))
    params = PixelParams(palette=pal, pixel_size=size, outline=profile.outline, despill=profile.despill)
    res = pixelize([rgb], params)
    if not isinstance(pal, list):
        job_palette.lock_from_clip(job, res.palette, f"{facing}/{action} (flow)")
        tracked["inputs"]["settings"]["palette"] = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in res.palette.tolist()]
    target = res.rgba(0)

    # 2. driving clip -> warped art frames
    clip = video.read_frames(m["clip"])
    masks = flowtransfer.masks_of(clip)
    frames = flowtransfer.warp(target, clip, masks=masks)

    # 3. frame selection on the driving clip (same rules as H3 actions)
    d.mkdir(parents=True, exist_ok=True)
    sel = picker.select(picker.analyse(clip), counts=counts, loop=loop)
    report = {"start": sel["start"], "end": sel["end"], "loop": loop, "loop_seam": sel.get("loop_seam"),
              "keys": [{"source": k, "reason": r} for k, r in sel["keys"]],
              "dropped": {str(k): v for k, v in sel["dropped"].items()}, "warnings": sel["warnings"],
              "sets": {str(n): s.as_report() for n, s in sel["sets"].items()},
              "source": {"method": "flow", "motion": motion_name}}
    fsutil.write_text(d / "selection_report.json", json.dumps(report, indent=2))
    contact.write(clip, d / "contact_sheet.png")

    # 4. layout + 04_pixel output (same files as `pixel`)
    info = _write_pixel_sets(job, profile, facing, action,
                             {n: ([frames[i] for i in s.indices], s.indices) for n, s in sel["sets"].items()},
                             res.palette, {"grid": {"size": res.grid.size, "source": res.grid.source,
                                                    "resample": res.resample}, "method": "flow", "motion": motion_name,
                                           "processing": tracked})
    processing.require_current(processing.status(job, profile, facing, action), f"{facing}/{action}")
    (d / "action_report.json").write_text(json.dumps({"experimental": True, "mode_used": "flow", "motion": motion_name,
                                                       "facing": facing, "action": action, "frames": len(frames)}, indent=2))
    job.set_stage(f"action:{facing}/{action}", "review", mode="flow", motion=motion_name)
    return info


MIRROR_OF = {"W": "E", "NW": "NE", "SW": "SE", "E": "W", "NE": "NW", "SE": "SW"}


def mirror_action(job: Job, profile: GameProfile, facing: str, action: str, source: str | None = None) -> dict:
    """Make `facing` by flipping an already pixelized facing (default: its mirror partner, e.g. W
    from E). Mirroring is code, not prompts (kickoff rule 10); exact same pixels, zero renders.
    Warns when the anchor is asymmetric (a mirrored shield/plume swaps sides)."""
    if not profile.mirror_allowed:
        raise RuntimeError(f"profile '{profile.name}' has mirror_allowed = false")
    source = source or MIRROR_OF.get(facing)
    if not source:
        raise ValueError(f"facing {facing} has no mirror partner")
    d = _clip_path(job, "03_actions", facing, action)
    processing.validate_mirror(job, facing, action, source)
    processing.require_current(processing.status(job, profile, source, action), f"{source}/{action}")
    before, frame_paths, sel = processing.mirror_inputs(job, source, action)
    rep = before["settings"]
    palette = (np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in rep["palette"]], np.uint8)
               if rep["palette"] else None)                          # None: full-colour style
    sets = {}
    for n, paths in frame_paths.items():
        frames = video.load(paths)
        frames = [f if f.shape[2] == 4 else np.dstack([f, np.full(f.shape[:2], 255, np.uint8)]) for f in frames]
        sets[n] = ([np.ascontiguousarray(f[:, ::-1]) for f in frames], rep["sources"][n])
    warnings = []
    anchor = job.root / "01_anchor" / "anchor.png"
    if anchor.exists():
        from ..pixel import chroma as _chroma
        asym = layout.asymmetry(_chroma.key(np.array(Image.open(anchor).convert("RGB"))))
        if asym["asymmetric"]:
            warnings.append("anchor is asymmetric: details swap sides in the mirrored facing")
    d.mkdir(parents=True, exist_ok=True)
    if sel.exists():
        shutil.copyfile(sel, d / "selection_report.json")
    out = _write_pixel_sets(job, profile, facing, action, sets, palette,
                            {"grid": rep["grid"], "style": rep["style"], "method": "mirror", "source": source,
                             "processing": {"version": 1, "inputs": before}},
                            cell=rep.get("cell"))
    processing.require_current(processing.status(job, profile, facing, action), f"{facing}/{action}")
    (d / "action_report.json").write_text(json.dumps({"mode_used": "mirror", "source": source, "facing": facing,
                                                       "action": action, "warnings": warnings}, indent=2))
    job.set_stage(f"action:{facing}/{action}", "review", mode="mirror", source=source, warnings=warnings)
    return {**out, "warnings": warnings}


def align(job: Job, profile: GameProfile, facing: str | None = None, action: str | None = None) -> dict:
    """Optional: every frame's foot point on the set's median foot point, with the camera profile's
    transparent border (default 2 px). Writes <n>f/frames_aligned/ next to frames/ (the originals
    stay) and turns on the asset's align_feet, so the manifest and the character export use the
    aligned frames. Whole-pixel moves only; no resampling."""
    from . import camera
    border = int(camera.effective(job, profile)[0].canvas_border_px)
    root = job.root / "04_pixel"
    sets = sorted(root.glob(f"{facing or '*'}/{action or '*'}/*f"))
    sets = [sd for sd in sets if (sd / "frames").is_dir()]
    if not sets:
        raise FileNotFoundError("nothing pixelized to align" + (f" for {facing} {action}" if facing or action else ""))
    report = {"border": border, "sets": {}}
    for sd in sets:
        files = sorted((sd / "frames").glob("[0-9][0-9][0-9].png"))
        cells = [np.array(Image.open(f).convert("RGBA")) for f in files]
        out, pts, warns = layout.align_feet(cells, border=border)
        _save_pngs(list(out), sd / "frames_aligned", [f.stem for f in files])
        (sd / "frames_aligned" / "footpoints.json").write_text(json.dumps(pts))
        key = f"{sd.parent.parent.name}/{sd.parent.name}/{sd.name}"
        report["sets"][key] = {"frames": len(files), "foot_point": pts[0] if pts else None, "warnings": warns}
    (root / "align_report.json").write_text(json.dumps(report, indent=2))
    job.update_inputs(align_feet=True)
    job.set_stage("align", "done", border=border, sets=len(sets),
                  warnings=sum(len(v["warnings"]) for v in report["sets"].values()))
    return report
