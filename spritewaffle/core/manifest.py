"""Per-asset manifest (docs/MANIFEST.md): every frame's angle, foot point, colour / depth / normal /
master files and the downscale that made it, plus the camera profile and mirror policy.

The manifest is derived from the files a job already has, so `build` is also the migration for
assets made before manifests existed; `read` never fails on an old job (it builds one with
defaults). Nothing here writes frames: only manifest.json and the footpoints.json caches.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from ..frames import layout
from ..frames.video import colour_frames
from . import alignment, angles, camera, timeline
from .job import Job
from .profile import GameProfile, resolve

SCHEMA_VERSION = 1
CYCLIC = {"idle", "walk", "run"}
SINGLE_VIEW = {"effect": 1, "prop": 1}


def path(job: Job) -> Path:
    return job.root / "manifest.json"


def _profile(inputs: dict) -> GameProfile:
    try:
        return resolve(inputs.get("profile"))
    except (FileNotFoundError, ValueError):
        return GameProfile(name="default")


def view_count(job: Job, profile: GameProfile | None = None) -> int:
    inputs = job.read_meta()["inputs"]
    if inputs.get("view_count"):
        return int(inputs["view_count"])
    t = inputs.get("asset_type", "character")
    if t == "item":
        return 2                                    # front (yaw 0) and back (yaw 180)
    return SINGLE_VIEW.get(t, (profile or _profile(inputs)).directions)


def _rel(job: Job, p: Path | None) -> str | None:
    return p.relative_to(job.root).as_posix() if p is not None and p.exists() else None


def _maps(job: Job, color: Path) -> dict:
    """Reserved slots next to a colour frame: <frame>_depth.png, <frame>_normal.png (null if absent)."""
    return {"depth": _rel(job, color.with_name(color.stem + "_depth.png")),
            "normal": _rel(job, color.with_name(color.stem + "_normal.png"))}


def _footpoints(folder: Path, frames: list[Path]) -> list:
    """Cached per frame set in footpoints.json (written by the pixel stage; measured once here for
    older sets). Rebuilt when the frame count no longer matches."""
    cache = folder / "footpoints.json"
    if cache.exists():
        pts = json.loads(cache.read_text())
        if len(pts) == len(frames):
            return pts
    pts = [layout.foot_point(np.array(Image.open(f).convert("RGBA"))) for f in frames]
    cache.write_text(json.dumps(pts))
    return pts


def _facing_mirrors(job: Job) -> dict[str, str]:
    """facing -> the facing it was flipped from (facings stage records both forms)."""
    meta = job.read_meta()
    out = {}
    rep = job.root / "02_facings" / "facings_report.json"
    if rep.exists():
        for f, v in (json.loads(rep.read_text()).get("mirrored") or {}).items():
            out[f] = (v or {}).get("from") or angles.label(angles.mirror_of(angles.yaw_of(f)))
    for f in (meta["stages"].get("facings") or {}).get("mirrored") or []:
        out.setdefault(f, angles.label(angles.mirror_of(angles.yaw_of(f))))
    return out


def downscale_record(rep: dict, placement: dict | None, profile: GameProfile, mirrored_from: str | None = None) -> dict:
    method = rep.get("method") or ("smooth" if rep.get("style") and rep.get("style") != "pixel" and not rep.get("grid") else "pixelize")
    return {"method": method, "flip": bool(mirrored_from), "grid": rep.get("grid"), "scale": rep.get("scale"),
            "style": rep.get("style") or "pixel", "palette": rep.get("palette") or [], "cell": rep.get("cell"),
            "placement": placement, "outline": profile.outline, "despill": profile.despill,
            "target_height": profile.sprite_height_px, "alpha_threshold": 0.5}


def _mirror_record(source: dict, placement: dict | None, cell) -> dict:
    """A mirrored frame = the source frame's downscale, its cell flipped left-right, laid out again
    with this frame's placement (core/stages.mirror_action)."""
    return {"method": "mirror", "flip": True, "source": source, "placement": placement, "cell": cell,
            "palette": source.get("palette") or []}


def _frame_set(job: Job, facing: str, action: str, n: str, rep: dict, vc: int, elev: float, profile: GameProfile,
               align: bool, source_loop: bool) -> tuple[list[dict], timeline.Clip]:
    sd = job.root / "04_pixel" / facing / action / f"{n}f"
    frames = colour_frames(sd / "frames")
    clip = timeline.read_clip(job.root, sd, frames, source_loop=source_loop)
    if not clip.items:
        return [], clip
    aligned = alignment.frames(sd, frames) if align else []
    use = aligned or frames
    reordered = bool(clip.order)
    source_indices = {frame: index for index, frame in enumerate(frames)}
    pts = _footpoints(sd / ("frames_aligned" if use is aligned and aligned else "frames"), use)
    places = json.loads((sd / "placements.json").read_text()) if (sd / "placements.json").exists() else []
    src_facing = rep.get("source") if rep.get("method") == "mirror" else None
    masters = sorted((job.root / "03_actions" / (src_facing or facing) / action / f"selected_{n}f").glob("*.png"))
    src_rep, src_places = {}, []
    if src_facing:                       # mirrored clip: the source's finished cells, flipped, then laid out again
        sp = job.root / "04_pixel" / src_facing / action
        src_rep = json.loads((sp / "pixel_report.json").read_text()) if (sp / "pixel_report.json").exists() else {}
        pf = sp / f"{n}f" / "placements.json"
        src_places = json.loads(pf.read_text()) if pf.exists() else []
    yaw = angles.yaw_of(facing)
    out = []
    for position, edit in enumerate(clip.items):
        k = source_indices.get(edit.source)
        f = use[k] if k is not None else edit.source
        foot = pts[k] if k is not None and k < len(pts) else None
        maps = {"depth": None, "normal": None}
        if edit.replaced or edit.inserted:
            foot = layout.foot_point(timeline.pixels([edit.image])[0])
        elif k is not None:
            maps = _maps(job, frames[k])
        mirrored = bool(src_facing and not (edit.replaced or edit.inserted))
        downscale = None
        if k is not None:
            place = places[k] if k < len(places) else None
            downscale = (_mirror_record(downscale_record(src_rep, src_places[k] if k < len(src_places) else None, profile),
                                        place, rep.get("cell"))
                         if src_facing else downscale_record(rep, place, profile))
        out.append({"view_index": angles.view_index(yaw, vc), "frame": position, "yaw_degrees": yaw,
                    **({"frame_id": edit.id, "source_frame": edit.source_id} if reordered or edit.pose_markers else {}),
                    **({"pose_markers": list(edit.pose_markers)} if edit.pose_markers else {}),
                    **({"inserted": True} if edit.inserted else {}),
                    "camera_elevation_degrees": elev, "view_count": vc,
                    "mirrored": mirrored,
                    "source_view_index": angles.view_index(angles.yaw_of(src_facing), vc) if mirrored else None,
                    "foot_point": foot,
                    "color": _rel(job, edit.image if edit.replaced else f),
                    "color_unaligned": _rel(job, frames[k]) if k is not None and use is aligned and not edit.replaced else None,
                    **maps,
                    **({"duration_ms": edit.duration_ms} if edit.duration_ms is not None else {}),
                    **({"color_source": _rel(job, f)} if edit.replaced else {}),
                    "master": _rel(job, masters[k]) if k is not None and k < len(masters) else None,
                    "downscale": downscale})
    return out, clip


def build(job: Job) -> dict:
    meta = job.read_meta()
    inputs = meta["inputs"]
    profile = _profile(inputs)
    base = job.root.parent.parent
    cam = camera.snapshot(job, profile)
    vc = view_count(job, profile)
    elev = cam["camera_elevation_degrees"]
    policy = inputs.get("mirror_policy") or "legacy"
    mirrors = _facing_mirrors(job)
    views = []
    for i, yaw in enumerate(angles.views(vc)):
        lab = angles.label(yaw)
        img = job.root / "02_facings" / f"{lab}.png"
        src = mirrors.get(lab)
        views.append({"view_index": i, "yaw_degrees": yaw, "label": lab,
                      "facing_image": _rel(job, img) if lab in angles.LEGACY else None,
                      "mirrored": bool(src), "source_view_index": angles.view_index(angles.yaw_of(src), vc) if src else None})
    anims = {}
    pix = job.root / "04_pixel"
    for rp in sorted(pix.glob("*/*/pixel_report.json")) if pix.is_dir() else []:
        facing, action = rp.parent.parent.name, rp.parent.name
        if facing not in angles.LEGACY:
            continue
        rep = json.loads(rp.read_text())
        sel = job.root / "03_actions" / facing / action / "selection_report.json"
        loop = json.loads(sel.read_text()).get("loop") if sel.exists() else action in CYCLIC
        for n in sorted(rep.get("sets") or {}, key=int):
            a = anims.setdefault((action, f"{n}f"), {"action": action, "frame_set": f"{n}f", "fps": profile.fps(action),
                                                     "loop": bool(loop), "frames": []})
            view = str(angles.view_index(angles.yaw_of(facing), vc))
            align = bool(inputs.get("align_feet"))
            if align:
                check = alignment.status(job.root, rp.parent / f"{n}f", cam["canvas_border_px"])
                if check["status"] in ("stale", "incomplete"):
                    a.setdefault("alignment_by_view", {})[view] = check["status"]
                    align = False
            frames, clip = _frame_set(job, facing, action, n, rep, vc, elev, profile, align, bool(loop))
            a["frames"] += frames
            if saved := clip.playback.signature():
                a.setdefault("playback_by_view", {})[view] = saved
            if clip.unavailable:
                a.setdefault("unavailable_frames_by_view", {})[view] = clip.unavailable
            if clip.tags:
                a.setdefault("tags_by_view", {})[view] = clip.describe_tags()
    for a in anims.values():
        a["frames"].sort(key=lambda f: (f["yaw_degrees"], f["frame"]))
        a["views"] = sorted({f["view_index"] for f in a["frames"]})
    cell = next((f["downscale"]["cell"] for a in anims.values() for f in a["frames"] if (f["downscale"] or {}).get("cell")), profile.cell_size)
    return {"schema_version": SCHEMA_VERSION,
            "asset_id": f"{meta['character']}/{meta['job_id']}", "project_id": camera.project(base)["id"],
            "asset_type": inputs.get("asset_type", "character"), "style": inputs.get("style") or "pixel",
            **({"style_guide": inputs["style_guide"]} if inputs.get("style_guide") else {}),
            **({"project_palette": inputs["project_palette"]} if inputs.get("project_palette") else {}),
            **({"project_reference_id": inputs["project_reference_id"]} if inputs.get("project_reference_id") else {}),
            "profile": profile.name, "camera": cam, "mirror_policy": policy, "mirror_map": inputs.get("mirror_map"),
            "view_count": vc, "canvas": [cell, cell], "align_feet": bool(inputs.get("align_feet")),
            "base_job": Path(inputs["base_job"]).name if inputs.get("base_job") else None,
            "views": views, "animations": sorted(anims.values(), key=lambda a: (a["action"], a["frame_set"]))}


DEFAULTS = {"schema_version": SCHEMA_VERSION, "mirror_policy": "legacy", "mirror_map": None, "align_feet": False,
            "views": [], "animations": [], "base_job": None}
FRAME_DEFAULTS = {"mirrored": False, "source_view_index": None, "foot_point": None, "depth": None, "normal": None,
                  "master": None, "downscale": None, "color_unaligned": None}


def read(job: Job) -> dict:
    """The stored manifest with defaults for any missing field, or a freshly built one (old job)."""
    p = path(job)
    if not p.exists():
        return build(job)
    m = json.loads(p.read_text(encoding="utf-8"))
    if int(m.get("schema_version", 0)) > SCHEMA_VERSION:
        raise ValueError(f"{p}: schema_version {m['schema_version']} is newer than this SpriteWaffle ({SCHEMA_VERSION})")
    m = DEFAULTS | m
    for a in m["animations"]:
        a["frames"] = [FRAME_DEFAULTS | f for f in a.get("frames", [])]
    return m


def write(job: Job, m: dict | None = None) -> Path:
    m = m or build(job)
    path(job).write_text(json.dumps(m, indent=1), encoding="utf-8")
    return path(job)


def refresh(job: Job) -> Path | None:
    """Rebuild after a stage finishes. Never breaks the stage: a failure is logged, not raised."""
    try:
        return write(job)
    except Exception as e:                                           # noqa: BLE001 - bookkeeping only
        job.log_provenance("manifest", error=f"{type(e).__name__}: {e}")
        return None


def migrate(base: Path, rebuild: bool = False):
    """Write a manifest for every job under `base` that has none (or all, with rebuild). Streams
    (job, status) so thousands of jobs don't sit in memory."""
    for jf in sorted(Path(base).glob("*/*/job.json")):
        if jf.parts[-3].startswith("_"):
            continue
        job = Job.open(jf.parent)
        if path(job).exists() and not rebuild:
            yield job, "kept"
            continue
        try:
            write(job)
            yield job, "written"
        except Exception as e:                                       # noqa: BLE001 - report and go on
            yield job, f"failed: {type(e).__name__}: {e}"


def replay_downscale(image: np.ndarray, record: dict, alpha_from: np.ndarray | None = None,
                     quantize: bool = True) -> np.ndarray:
    """Re-run a frame's recorded downscale (pixel/pipeline.pixelize's steps with the recorded grid,
    resample, palette and placement) on `image`, which has the master's size. For a future depth or
    normal map pass the colour master as `alpha_from` (its keyed alpha is used; a map has no green
    background) and quantize=False (keep the map's values). Returns the cell-sized RGBA, aligned
    pixel for pixel with the colour frame."""
    import cv2

    from ..pixel import grid as gridmod
    from ..pixel.pipeline import _ensure_rgba
    rec = record or {}
    if rec.get("method") == "mirror":
        src = replay_downscale(image, rec["source"], alpha_from, quantize)
        pl = rec.get("placement")
        flipped = np.ascontiguousarray(src[:, ::-1])
        if not pl:
            return flipped
        cell = int(rec.get("cell") or src.shape[1])
        return layout._place(flipped, layout.Placement(float(pl["scale"]), tuple(pl["crop"]), tuple(pl["paste"])), (cell, cell))
    if alpha_from is not None:
        keyed = _ensure_rgba(np.asarray(alpha_from)[..., :3], 16, rec.get("despill") or "all")
        rgba = np.dstack([np.asarray(image)[..., :3], keyed[..., 3]]).astype(np.uint8)
    else:
        rgba = _ensure_rgba(np.asarray(image), 16, rec.get("despill") or "all")
    if rec.get("flip"):
        rgba = np.ascontiguousarray(rgba[:, ::-1])
    cell = int(rec.get("cell") or 64)
    g = rec.get("grid") or {}
    if rec.get("method") == "smooth" or not g:
        k = float(rec.get("scale") or 1.0)
        art = cv2.resize(rgba, (max(1, round(rgba.shape[1] * k)), max(1, round(rgba.shape[0] * k))), interpolation=cv2.INTER_AREA)
    else:
        r = float(g.get("resample") or 1.0)
        if abs(r - 1.0) > 0.01:
            rgba = cv2.resize(rgba, (max(1, round(rgba.shape[1] * r)), max(1, round(rgba.shape[0] * r))), interpolation=cv2.INTER_NEAREST)
        art = gridmod.downscale(rgba, int(g["size"]), int(g.get("ox", 0)), int(g.get("oy", 0)),
                                float(rec.get("alpha_threshold", 0.5)))
        pal = rec.get("palette") or []
        if quantize and pal:
            from ..pixel.color import hex_to_rgb, srgb_to_oklab
            prgb = np.array([hex_to_rgb(h) for h in pal], np.uint8)
            lab, plab = srgb_to_oklab(art[..., :3].astype(float)), srgb_to_oklab(prgb.astype(float))
            idx = ((lab[:, :, None, :] - plab[None, None]) ** 2).sum(-1).argmin(-1)
            art = np.dstack([prgb[idx], np.where(art[..., 3] > 0, 255, 0).astype(np.uint8)])
    pl = rec.get("placement")
    if pl:
        return layout._place(art, layout.Placement(float(pl["scale"]), tuple(pl["crop"]), tuple(pl["paste"])), (cell, cell))
    return art


def set_mirror_policy(job: Job, policy: str, mirror_map: dict | None = None) -> dict:
    """Per-asset mirror policy (docs/MANIFEST.md). legacy = today's per-run choices; none = never
    flip; mirror_left_from_right = render S, N and the right-facing half, flip the left half;
    custom = mirror_map {"<view_index>": <source view_index>}."""
    if policy not in angles.POLICIES:
        raise ValueError(f"mirror_policy must be one of {angles.POLICIES}")
    n = view_count(job)
    clean_map = None
    if policy == "custom":
        if not mirror_map:
            raise ValueError("custom needs mirror_map, e.g. {\"1\": 7} = view 1 (SW) flipped from view 7 (SE)")
        clean_map = {}
        for k, v in mirror_map.items():
            if not (str(k).isdigit() and 0 <= int(k) < n and 0 <= int(v) < n and int(k) != int(v)):
                raise ValueError(f"mirror_map entries must be two different view indices 0..{n - 1}: {k}->{v}")
            clean_map[str(int(k))] = int(v)
    with job.mutate() as meta:
        meta["inputs"]["mirror_policy"] = policy
        if clean_map is None:
            meta["inputs"].pop("mirror_map", None)
        else:
            meta["inputs"]["mirror_map"] = clean_map
    refresh(job)
    return {"mirror_policy": policy, "mirror_map": clean_map, "view_count": n}
