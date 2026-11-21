"""Phase 1 stages. Each reads/writes only inside the job folder and can be re-run alone."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from ..export import aseprite, sheet as sheetmod
from ..frames import analysis, contact, layout, picker, video
from ..pixel.pipeline import PixelParams, pixelize
from ..qa import checks
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
    d = job.action_dir(facing, action)
    raw = d / ("raw" + Path(src).suffix.lower())
    if Path(src).resolve() != raw.resolve():
        shutil.copyfile(src, raw)
    rep = video.extract(raw, d / "extracted")
    frames = video.load(video.list_frames(d / "extracted"))
    frozen, diff = analysis.is_frozen(frames)
    rep.update(frozen=frozen, mean_frame_diff=round(diff, 3))
    (d / "extracted" / "extraction_report.json").write_text(json.dumps(rep, indent=2))
    contact.write(frames, d / "contact_sheet.png")
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
    paths = video.list_frames(d / "extracted")
    frames = video.load(paths)
    loop = action in CYCLIC if loop is None else loop
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
    rep = json.loads((d / "selection_report.json").read_text())
    sets = {n: [e["source"] for e in rows] for n, rows in rep["sets"].items()}
    union = sorted({i for v in sets.values() for i in v})
    src = video.list_frames(d / "extracted")
    frames = video.load([src[i] for i in union])
    from ..prompts import styles
    st = styles.get(styles.of_job(job))
    if st["post"] == "smooth":                       # hand-painted / anime / comic: no grid, no palette
        from ..pixel import smooth
        art, k = smooth.process(frames, profile.sprite_height_px * st["scale"], despill=profile.despill)
        pos = {s: n for n, s in enumerate(union)}
        info = _write_pixel_sets(job, profile, facing, action,
                                 {n: ([art[pos[i]] for i in idxs], idxs) for n, idxs in sets.items()},
                                 None, {"style": st["name"], "scale": round(k, 4)}, cell=profile.cell_size * st["scale"])
        job.set_stage(f"pixelize:{facing}/{action}", "done", style=st["name"], scale=round(k, 4))
        return info
    from . import job_palette
    pal = palette or job_palette.resolve(job, profile)[0]    # explicit size = a one-off per-clip fit
    params = PixelParams(palette=pal, pixel_size=profile.pixel_size, target_height=profile.sprite_height_px,
                         loop=rep["loop"], outline=profile.outline, despill=profile.despill)
    res = pixelize(frames, params)
    if not palette and not isinstance(pal, list):
        job_palette.lock_from_clip(job, res.palette, f"{facing}/{action}")
    pos = {s: k for k, s in enumerate(union)}
    grid = {"size": res.grid.size, "ox": res.grid.ox, "oy": res.grid.oy, "source": res.grid.source,
            "score": round(res.grid.score, 3), "resample": res.resample}
    info = _write_pixel_sets(job, profile, facing, action,
                             {n: ([res.rgba(pos[i]) for i in idxs], idxs) for n, idxs in sets.items()},
                             res.palette, {"grid": grid})
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
    for n, (art, sources) in sets.items():
        cells, places = layout.preserve_canvas(list(art), (cell, cell))
        off = places[0].pivot[0] - cell / 2 if places and places[0].pivot else 0
        if off and not any("pivot" in w for w in info["warnings"]):
            info["warnings"].append(f"pivot: the action is too wide for the {cell}px cell, so the feet sit {abs(off):.0f}px "
                                    f"{'left' if off < 0 else 'right'} of centre in this clip (a bigger profile cell fixes it)")
        sd = out / f"{n}f"
        _save_pngs(cells, sd / "frames", [f"{k:03d}" for k in range(len(cells))])
        (sd / "indices.npy").unlink(missing_ok=True)
        if palette is not None:
            np.save(sd / "indices.npy", np.stack([_rgba_to_index(c, palette) for c in cells]))
        (sd / "placements.json").write_text(json.dumps([p.as_dict() for p in places], indent=2))
        prev = np.concatenate(list(cells), axis=1)
        k = 4 if palette is not None else 1                      # pixel art previews upscaled, smooth art as is
        Image.fromarray(prev).resize((prev.shape[1] * k, prev.shape[0] * k), Image.NEAREST).save(sd / "preview_4x.png")
        info["sets"][str(n)] = {"frames": len(cells), "sources": list(sources)}
    (out / "pixel_report.json").write_text(json.dumps(info, indent=2))
    return info


def _rgba_to_index(cell: np.ndarray, pal: np.ndarray) -> np.ndarray:
    idx = np.full(cell.shape[:2], -1, int)
    m = cell[..., 3] > 0
    lut = {tuple(c): i for i, c in enumerate(pal.tolist())}
    idx[m] = [lut[tuple(c)] for c in cell[m][:, :3].tolist()]
    return idx


def _load_set(sd: Path) -> tuple[np.ndarray, list[dict]]:
    cells = np.stack(video.load(video.list_frames(sd / "frames")))
    if cells.shape[-1] == 3:
        cells = np.dstack([cells, np.full(cells.shape[:3], 255, np.uint8)])
    return cells, json.loads((sd / "placements.json").read_text())


def qa(job: Job, profile: GameProfile, facing=None, action=None) -> dict:
    facing, action = _ctx(job, facing, action)
    pdir = job.root / "04_pixel" / facing / action
    loop = json.loads((job.action_dir(facing, action) / "selection_report.json").read_text())["loop"]
    prep = json.loads((pdir / "pixel_report.json").read_text())
    pal_n = len(prep["palette"])
    from . import job_palette
    jp = job_palette.get(job)
    cap = len(jp["colours"]) if jp else profile.palette_size     # a loaded palette may be larger than the profile's
    results = {}
    for sd in sorted(p for p in pdir.iterdir() if p.is_dir()):
        cells, places = _load_set(sd)
        limit = min(pal_n, cap) if pal_n else 1 << 30      # full-colour styles: no palette limit
        r = checks.run(cells, places, "preserve-canvas", palette_size=limit, loop=loop)
        r.setdefault("warnings", []).extend(prep.get("warnings", []))
        checks.write(r, job.stage_dir("05_qa") / facing / action / sd.name / "report.json")
        results[sd.name] = r["status"]
    status = "fail" if "fail" in results.values() else "pass"
    job.set_stage(f"qa:{facing}/{action}", status, sets=results)
    return results


def export(job: Job, profile: GameProfile, facing=None, action=None, fmt: str = "both") -> dict:
    facing, action = _ctx(job, facing, action)
    pdir = job.root / "04_pixel" / facing / action
    loop = json.loads((job.action_dir(facing, action) / "selection_report.json").read_text())["loop"]
    pal = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)]
                    for h in json.loads((pdir / "pixel_report.json").read_text())["palette"]], np.uint8).reshape(-1, 3)
    base_fps = profile.fps(action)
    written = {}
    for sd in sorted(p for p in pdir.iterdir() if p.is_dir()):
        n = int(sd.name.rstrip("f"))
        fps = base_fps if n <= 12 else base_fps * n // 12            # same duration for 12f and 24f
        cells, places = _load_set(sd)
        pivot = places[0].get("pivot") if places else None        # None: laid out before pivots existed
        name = f"{action}_{facing}_{sd.name}"
        out = job.stage_dir("06_export") / facing / action / sd.name
        files = {}
        indexed = (sd / "indices.npy").exists()
        if fmt in ("png", "both"):
            files.update({k: str(v) for k, v in sheetmod.export_png(out, name, cells, fps, loop=loop, pivot=pivot,
                                                                    preview_scale=4 if indexed else 1).items() if k != "frames"})
        if fmt in ("aseprite", "both"):
            tags = [(f"{action}_{facing}", 0, len(cells) - 1, "forward", 0 if loop else 1)]
            pv = pivot or sheetmod.feet_pivot(cells)
            slices = [("pivot", [(0, 0, 0, cells.shape[2], cells.shape[1], int(pv[0]), int(pv[1]))])]
            if indexed:
                ind = np.load(sd / "indices.npy")
                p = aseprite.write(out / f"{name}.aseprite", ind, pal, [round(1000 / fps)] * len(ind), tags=tags,
                                   slices=slices)
            else:
                p = aseprite.write_rgba(out / f"{name}.aseprite", cells, [round(1000 / fps)] * len(cells), tags=tags,
                                         slices=slices)
            files["aseprite"] = str(p)
        written[sd.name] = files
    job.set_stage(f"export:{facing}/{action}", "done", formats=fmt)
    return written


def flow_transfer(job: Job, profile: GameProfile, facing: str, action: str, motion_name: str,
                  counts=(12, 24), loop: bool | None = None) -> dict:
    """Pixel-exact motion transfer (experimental): the approved facing, pixelized once, is warped
    by the optical flow of an approved library motion. Output pixels are copied from the facing's
    art, so palette and identity are exactly the facing's. Writes the same 04_pixel layout as
    `pixel`, so qa/export run unchanged."""
    from ..frames import flowtransfer
    from . import motion
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

    # 1. target art: the facing, pixelized once at the PROFILE's sprite height (same scale as H3
    #    actions). Grid detection on stills can lock onto a coarse grid (measured: 29 px -> a 19 px
    #    sprite next to 48 px H3 animations of the same character).
    rgb = np.array(Image.open(face).convert("RGB"))
    from ..pixel import chroma as _chroma
    ys = np.where((_chroma.key(rgb)[..., 3] > 0).any(1))[0]
    size = profile.pixel_size or max(1, round((ys[-1] - ys[0] + 1) / profile.sprite_height_px))
    from . import job_palette
    pal = job_palette.resolve(job, profile)[0]
    params = PixelParams(palette=pal, pixel_size=size, outline=profile.outline, despill=profile.despill)
    res = pixelize([rgb], params)
    if not isinstance(pal, list):
        job_palette.lock_from_clip(job, res.palette, f"{facing}/{action} (flow)")
    target = res.rgba(0)

    # 2. driving clip -> warped art frames
    clip = video.read_frames(m["clip"])
    masks = flowtransfer.masks_of(clip)
    frames = flowtransfer.warp(target, clip, masks=masks)

    # 3. frame selection on the driving clip (same rules as H3 actions)
    d = job.action_dir(facing, action)
    loop = action in CYCLIC if loop is None else loop
    sel = picker.select(picker.analyse(clip), counts=counts, loop=loop)
    report = {"start": sel["start"], "end": sel["end"], "loop": loop, "loop_seam": sel.get("loop_seam"),
              "keys": [{"source": k, "reason": r} for k, r in sel["keys"]],
              "dropped": {str(k): v for k, v in sel["dropped"].items()}, "warnings": sel["warnings"],
              "sets": {str(n): s.as_report() for n, s in sel["sets"].items()},
              "source": {"method": "flow", "motion": motion_name}}
    (d / "selection_report.json").write_text(json.dumps(report, indent=2))
    contact.write(clip, d / "contact_sheet.png")

    # 4. layout + 04_pixel output (same files as `pixel`)
    info = _write_pixel_sets(job, profile, facing, action,
                             {n: ([frames[i] for i in s.indices], s.indices) for n, s in sel["sets"].items()},
                             res.palette, {"grid": {"size": res.grid.size, "source": res.grid.source,
                                                    "resample": res.resample}, "method": "flow", "motion": motion_name})
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
    src = job.root / "04_pixel" / source / action
    rep = json.loads((src / "pixel_report.json").read_text()) if (src / "pixel_report.json").exists() else None
    if rep is None:
        raise FileNotFoundError(f"{action} {source} is not pixelized yet; it is the source for {facing}")
    palette = (np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in rep["palette"]], np.uint8)
               if rep["palette"] else None)                          # None: full-colour style
    sets = {}
    for n, info in rep["sets"].items():
        frames = video.load(video.list_frames(src / f"{n}f" / "frames"))
        frames = [f if f.shape[2] == 4 else np.dstack([f, np.full(f.shape[:2], 255, np.uint8)]) for f in frames]
        sets[n] = ([np.ascontiguousarray(f[:, ::-1]) for f in frames], info["sources"])
    warnings = []
    anchor = job.root / "01_anchor" / "anchor.png"
    if anchor.exists():
        from ..pixel import chroma as _chroma
        asym = layout.asymmetry(_chroma.key(np.array(Image.open(anchor).convert("RGB"))))
        if asym["asymmetric"]:
            warnings.append("anchor is asymmetric: details swap sides in the mirrored facing")
    d = job.action_dir(facing, action)
    sel = job.root / "03_actions" / source / action / "selection_report.json"
    if sel.exists():
        shutil.copyfile(sel, d / "selection_report.json")
    out = _write_pixel_sets(job, profile, facing, action, sets, palette,
                            {"grid": rep.get("grid"), "style": rep.get("style"), "method": "mirror", "source": source},
                            cell=rep.get("cell"))
    (d / "action_report.json").write_text(json.dumps({"mode_used": "mirror", "source": source, "facing": facing,
                                                       "action": action, "warnings": warnings}, indent=2))
    job.set_stage(f"action:{facing}/{action}", "review", mode="mirror", source=source, warnings=warnings)
    return {**out, "warnings": warnings}
