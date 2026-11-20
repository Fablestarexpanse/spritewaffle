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
    params = PixelParams(palette=profile.palette if isinstance(profile.palette, list) else (palette or profile.palette_size),
                         pixel_size=profile.pixel_size, target_height=profile.sprite_height_px,
                         loop=rep["loop"], outline=profile.outline, despill=profile.despill)
    res = pixelize(frames, params)
    pos = {s: k for k, s in enumerate(union)}
    out = job.stage_dir("04_pixel") / facing / action
    info = {"grid": {"size": res.grid.size, "ox": res.grid.ox, "oy": res.grid.oy, "source": res.grid.source,
                     "score": round(res.grid.score, 3), "resample": res.resample},
            "palette": [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in res.palette.tolist()], "sets": {}}
    for n, idxs in sets.items():
        art = [res.rgba(pos[i]) for i in idxs]
        cells, places = layout.preserve_canvas(art, (profile.cell_size, profile.cell_size))
        ind = np.stack([_rgba_to_index(c, res.palette) for c in cells])
        sd = out / f"{n}f"
        _save_pngs(cells, sd / "frames", [f"{k:03d}" for k in range(len(cells))])
        np.save(sd / "indices.npy", ind)
        (sd / "placements.json").write_text(json.dumps([p.as_dict() for p in places], indent=2))
        prev = np.concatenate(list(cells), axis=1)
        Image.fromarray(prev).resize((prev.shape[1] * 4, prev.shape[0] * 4), Image.NEAREST).save(sd / "preview_4x.png")
        info["sets"][n] = {"frames": len(cells), "sources": idxs}
    (out / "pixel_report.json").write_text(json.dumps(info, indent=2))
    job.set_stage(f"pixelize:{facing}/{action}", "done", grid=info["grid"], palette_size=len(res.palette))
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
    pal_n = len(json.loads((pdir / "pixel_report.json").read_text())["palette"])
    results = {}
    for sd in sorted(p for p in pdir.iterdir() if p.is_dir()):
        cells, places = _load_set(sd)
        r = checks.run(cells, places, "preserve-canvas", palette_size=min(pal_n, profile.palette_size), loop=loop)
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
                    for h in json.loads((pdir / "pixel_report.json").read_text())["palette"]], np.uint8)
    base_fps = profile.fps(action)
    written = {}
    for sd in sorted(p for p in pdir.iterdir() if p.is_dir()):
        n = int(sd.name.rstrip("f"))
        fps = base_fps if n <= 12 else base_fps * n // 12            # same duration for 12f and 24f
        cells, _ = _load_set(sd)
        name = f"{action}_{facing}_{sd.name}"
        out = job.stage_dir("06_export") / facing / action / sd.name
        files = {}
        if fmt in ("png", "both"):
            files.update({k: str(v) for k, v in sheetmod.export_png(out, name, cells, fps, loop=loop).items() if k != "frames"})
        if fmt in ("aseprite", "both"):
            ind = np.load(sd / "indices.npy")
            p = aseprite.write(out / f"{name}.aseprite", ind, pal, [round(1000 / fps)] * len(ind),
                               tags=[(f"{action}_{facing}", 0, len(ind) - 1, "forward")])
            files["aseprite"] = str(p)
        written[sd.name] = files
    job.set_stage(f"export:{facing}/{action}", "done", formats=fmt)
    return written
