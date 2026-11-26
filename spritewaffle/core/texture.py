"""Seamless (tileable) textures: ground, walls, water... that wrap with no visible seam.

Measured 2026-11-26 (cobblestone, seed 7): repainting the wrap seams with H3 image edit (roll by
half, redraw the cross, keep the edges) made it worse: the repainted band came out lighter and
sharper than the rest. So the seam is fixed here in code, by image quilting (Efros & Freeman):
the right edge overlaps the left and the two are joined along the path where they differ least
(a dynamic-programming cut), then the same top/bottom. Wrapping the result joins pixels that were
neighbours in the source, so it tiles by construction; the cut follows natural gaps (mortar,
grass blades) instead of a straight line.
"""
from __future__ import annotations

import numpy as np


def _min_cut(cost: np.ndarray) -> np.ndarray:
    """Column index of the cheapest top-to-bottom path through cost (rows x cols), moving at most
    one column per row."""
    h, w = cost.shape
    acc = cost.astype(float).copy()
    for y in range(1, h):
        prev = acc[y - 1]
        left = np.r_[np.inf, prev[:-1]]
        right = np.r_[prev[1:], np.inf]
        acc[y] += np.minimum(np.minimum(left, prev), right)
    path = np.empty(h, int)
    path[-1] = int(np.argmin(acc[-1]))
    for y in range(h - 2, -1, -1):
        x = path[y + 1]
        lo, hi = max(0, x - 1), min(w, x + 2)
        path[y] = lo + int(np.argmin(acc[y, lo:hi]))
    return path


def _wrap_columns(img: np.ndarray, overlap: int, feather: int = 2) -> np.ndarray:
    """Make the left/right edges wrap: the last `overlap` columns overlap the first ones, joined along
    the minimum-difference cut. Returns width - overlap columns."""
    a = img[:, -overlap:].astype(float)            # right strip (continues into the left edge when wrapped)
    b = img[:, :overlap].astype(float)             # left strip
    cost = ((a - b) ** 2).sum(-1)
    cut = _min_cut(cost)
    xs = np.arange(overlap)[None, :]
    # weight of the right strip: 1 left of the cut, 0 right of it, a short ramp across it
    wgt = np.clip((cut[:, None] - xs) / max(1, feather) + 0.5, 0, 1)[..., None]
    joined = a * wgt + b * (1 - wgt)
    out = img[:, :-overlap].astype(float).copy()
    out[:, :overlap] = joined
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def make_seamless(rgb: np.ndarray, overlap: float = 0.15, feather: int = 2) -> np.ndarray:
    """A tileable version of `rgb` (H x W x 3/4, uint8): left/right, then top/bottom wrapped along
    minimum-difference cuts. The result is smaller by `overlap` of each side."""
    if rgb.ndim != 3:
        raise ValueError("expected an H x W x C image")
    h, w = rgb.shape[:2]
    ox, oy = max(2, int(w * overlap)), max(2, int(h * overlap))
    if ox >= w // 2 or oy >= h // 2:
        raise ValueError("overlap must be under half the image")
    out = _wrap_columns(rgb, ox, feather)
    out = np.ascontiguousarray(_wrap_columns(np.ascontiguousarray(out.transpose(1, 0, 2)), oy, feather).transpose(1, 0, 2))
    return out


def wrap_score(rgb: np.ndarray) -> float:
    """How visible the wrap seam is: the difference across the wrap edges divided by the typical
    difference between neighbouring columns/rows inside the image (median, so an upscaled image's
    alternating smooth pairs don't skew it). About 1 = seamless; 2+ = a visible seam."""
    f = rgb[..., :3].astype(float)
    cols = np.abs(np.diff(f, axis=1)).mean(axis=(0, 2))
    rows = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    edge_c = np.abs(f[:, 0] - f[:, -1]).mean()
    edge_r = np.abs(f[0] - f[-1]).mean()
    return round(float((edge_c / max(np.median(cols), 1e-6) + edge_r / max(np.median(rows), 1e-6)) / 2), 2)


def resize_wrapped(rgb: np.ndarray, size: int, resample: str = "area") -> np.ndarray:
    """Resize a tileable image to size x size so it still tiles: the image is padded with its own
    wrap-around before resampling, then the padding is cut away."""
    import cv2
    h, w = rgb.shape[:2]
    pad = max(4, int(0.05 * max(h, w)))
    big = np.pad(rgb, ((pad, pad), (pad, pad), (0, 0)), mode="wrap")
    k = size / w, size / h
    inter = {"area": cv2.INTER_AREA, "nearest": cv2.INTER_NEAREST, "lanczos": cv2.INTER_LANCZOS4}[resample]
    out = cv2.resize(big, (round(big.shape[1] * k[0]), round(big.shape[0] * k[1])), interpolation=inter)
    px, py = round(pad * k[0]), round(pad * k[1])
    return np.ascontiguousarray(out[py:py + size, px:px + size])


def tiled(rgb: np.ndarray, nx: int = 3, ny: int = 3) -> np.ndarray:
    """The texture repeated nx x ny times: the preview that shows a seam if there is one."""
    return np.tile(rgb, (ny, nx, 1))


# --- the texture job (asset type "texture") ---------------------------------------------------
TYPE = "texture"
TILE_SIZES = (16, 24, 32, 48, 64, 96, 128, 256, 512)
WORK = 1024              # the generated image is seamed at this size, then cut to the tile size
LOOK = {"pixel": "Simple readable shapes, bold forms, a limited palette, crisp detail sized for a small game tile.",
        "painted": "Hand-painted game texture, soft brushwork, readable shapes.",
        "anime": "Clean anime background-art texture, flat cel shading.",
        "comic": "Comic-ink texture, bold ink lines, flat colours."}


def prompt(description: str, style: str = "pixel") -> str:
    """Text-to-image prompt for one texture swatch: seen from straight above with even light so it
    can repeat. The seam itself is fixed in code (make_seamless)."""
    d = description.strip().rstrip(".")
    if not d:
        raise ValueError("describe the texture, e.g. 'mossy cobblestone ground'")
    return (f"Seamless tileable game texture: {d}, seen straight from above. {LOOK.get(style, LOOK['painted'])} "
            "Flat even lighting with no shadows cast from outside, no perspective, no vignette, no border, no text, "
            "no objects cut off at the edges. The pattern fills the whole square image edge to edge with uniform "
            "density and scale, like a texture swatch.")


def auto_zoom(tile_size: int) -> int:
    """How far to zoom into the generated swatch before seaming. Measured 2026-11-26 (cobblestone,
    32 px): the whole 2048 px swatch shrunk to 32 px is mush (dozens of tiny stones per tile);
    cropping a quarter of it first gives a few readable stones per tile."""
    return 4 if tile_size <= 32 else 3 if tile_size <= 64 else 2 if tile_size <= 128 else 1


def settings(job) -> dict:
    i = job.read_meta()["inputs"]
    tile = int(i.get("tile_size") or 32)
    return {"description": i.get("description") or "", "style": i.get("style") or "pixel",
            "tile_size": tile, "variants": int(i.get("variants") or 4),
            "colours": int(i.get("colours") or 16), "overlap": float(i.get("overlap") or 0.15),
            "zoom": int(i.get("zoom") or 0) or auto_zoom(tile), "zoom_auto": not int(i.get("zoom") or 0),
            "palette": _project_palette(job)}


def _project_palette(job) -> list[str] | None:
    """The project's master palette (Project menu), which pixel tiles snap to when set."""
    try:
        from . import project
        return project.palette(job.root.parent.parent) or None
    except Exception:                                             # noqa: BLE001 - no project file is fine
        return None


def configure(job, **values) -> dict:
    """Save texture settings (description, tile_size, variants, colours, overlap, style, zoom;
    zoom 0 = automatic from the tile size)."""
    v = {k: values[k] for k in ("description", "tile_size", "variants", "colours", "overlap", "style", "zoom")
         if values.get(k) is not None}
    if "tile_size" in v and int(v["tile_size"]) not in TILE_SIZES:
        raise ValueError(f"tile size must be one of {TILE_SIZES}")
    if "variants" in v and not 1 <= int(v["variants"]) <= 16:
        raise ValueError("variants must be 1-16")
    if "colours" in v and not 2 <= int(v["colours"]) <= 256:
        raise ValueError("colours must be 2-256")
    if "overlap" in v and not 0.05 <= float(v["overlap"]) <= 0.3:
        raise ValueError("overlap must be 0.05-0.3")
    if "zoom" in v and not 0 <= int(v["zoom"]) <= 8:
        raise ValueError("zoom must be 0 (automatic) to 8")
    job.update_inputs(**v)
    return settings(job)


def _quantize(rgb: np.ndarray, colours: int) -> np.ndarray:
    """Pixel art: fewer colours, mapped pixel by pixel (so a tileable tile stays tileable)."""
    from PIL import Image
    q = Image.fromarray(rgb).quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    return np.array(q.convert("RGB"))


def snap_palette(rgb: np.ndarray, palette, extra_dark: bool = False) -> np.ndarray:
    """Every pixel to its nearest palette colour in OKLab (perceptual; research 2026-11-26: map to
    one shared palette, not per-tile k-means, or neighbouring tiles drift). palette: hex strings or
    an N x 3 array (duplicates fine). extra_dark adds a 70 % shade of each colour (for edge lips)."""
    from ..pixel.color import hex_to_rgb, srgb_to_oklab
    p = np.array([hex_to_rgb(c) if isinstance(c, str) else c for c in palette], np.uint8).reshape(-1, 3)
    p = np.unique(p, axis=0)
    if extra_dark:
        p = np.unique(np.concatenate([p, np.rint(p * 0.7).astype(np.uint8)]), axis=0)
    flat = rgb[..., :3].reshape(-1, 3)
    cols, inv = np.unique(flat, axis=0, return_inverse=True)
    d = ((srgb_to_oklab(cols.astype(float))[:, None] - srgb_to_oklab(p.astype(float))[None]) ** 2).sum(-1)
    return p[d.argmin(1)][inv.reshape(-1)].reshape(rgb.shape[:2] + (3,)).astype(np.uint8)


def clean_orphans(rgb: np.ndarray) -> np.ndarray:
    """Pixel art: a lone pixel whose four neighbours all share one other colour takes that colour
    (research: orphans read as noise and make repetition more visible). Neighbours wrap around, so
    a seamless tile stays seamless."""
    nb = [np.roll(rgb, s, axis=a) for s, a in ((1, 0), (-1, 0), (1, 1), (-1, 1))]
    same = np.all([np.all(n == nb[0], -1) for n in nb[1:]], 0) & ~np.all(rgb == nb[0], -1)
    out = rgb.copy()
    out[same] = nb[0][same]
    return out


def tile_from(master: np.ndarray, s: dict) -> np.ndarray:
    """The game tile from a seamless master. Pixel art: each tile pixel takes the dominant colour of
    its block (pixel/grid.downscale: crisp edges, measured sharper than averaging), then the palette.
    Other styles: an area-averaged resize. Both keep the wrap (blocks line up with the tile edge)."""
    if s["style"] != "pixel":
        return resize_wrapped(master, s["tile_size"], "area")
    from ..pixel import grid
    k = 12
    big = resize_wrapped(master, s["tile_size"] * k, "area")
    t = np.ascontiguousarray(grid.downscale(np.dstack([big, np.full(big.shape[:2], 255, np.uint8)]), k)[..., :3])
    t = snap_palette(t, s["palette"]) if s.get("palette") else _quantize(t, s["colours"])
    return clean_orphans(t)


def _report_path(job):
    return job.root / "02_facings" / "texture_report.json"


def _process(job, k: int, s: dict) -> dict:
    """raw render -> zoomed crop -> seamless master -> tile, for variant k. Scores for the report."""
    from PIL import Image
    raw = np.array(Image.open(job.root / "01_anchor" / f"raw_{k}.png").convert("RGB"))
    h = raw.shape[0]
    c = max(64, h // s["zoom"])
    o = (h - c) // 2
    src = np.array(Image.fromarray(raw[o:o + c, o:o + c]).resize((WORK, WORK), Image.LANCZOS))
    master = make_seamless(src, s["overlap"])
    out = job.root / "02_facings"
    Image.fromarray(master).save(out / f"master_{k}.png")
    tile = tile_from(master, s)
    Image.fromarray(tile).save(out / f"tile_{k}.png")
    return {"wrap_raw": wrap_score(src), "wrap_master": wrap_score(master), "wrap_tile": wrap_score(tile)}


def generate(job, client=None, seed: int | None = None, only: list[int] | None = None) -> dict:
    """Render the variants (or just `only`), make each seamless, cut the tile. Left in review."""
    import json
    import random
    import shutil

    from PIL import Image

    from ..comfy.client import ComfyClient
    from . import takes
    s = settings(job)
    client = client or ComfyClient()
    raw_dir = job.stage_dir("01_anchor")
    job.stage_dir("02_facings")
    text = prompt(s["description"], s["style"])
    rp = _report_path(job)
    rep = json.loads(rp.read_text()) if rp.exists() else {}
    variants = {int(k): v for k, v in (rep.get("variants") or {}).items()}
    base_seed = seed if seed is not None else random.randrange(2**31)
    for k in [k for k in range(s["variants"]) if not only or k in only]:
        sd = base_seed + k
        raw, tmp = raw_dir / f"raw_{k}.png", raw_dir / f".raw_{k}_tmp"
        prov = client.run_template("anchor_still", {"prompt": text, "seed": sd}, tmp)
        takes.stash(job, raw)
        Image.open(prov["files"][0]).convert("RGB").save(raw)
        shutil.rmtree(tmp, ignore_errors=True)
        variants[k] = {"seed": sd, **_process(job, k, s)}
        job.log_provenance(f"01_anchor/raw_{k}.png", template="anchor_still", values={"prompt": text, "seed": sd})
    variants = {k: v for k, v in variants.items() if k < s["variants"]}
    rep = {"settings": s, "prompt": text, "variants": {str(k): variants[k] for k in sorted(variants)}}
    rp.write_text(json.dumps(rep, indent=2))
    job.set_stage("texture", "review", variants=len(variants))
    return rep


def retile(job) -> dict:
    """Seam and cut every variant again from its saved render (new tile size, zoom, colours,
    overlap): no new render, under a second per variant."""
    import json
    s = settings(job)
    rp = _report_path(job)
    if not rp.exists():
        raise FileNotFoundError("generate the texture first")
    rep = json.loads(rp.read_text())
    for k, v in rep["variants"].items():
        v.update(_process(job, int(k), s))
    rep["settings"] = s
    rp.write_text(json.dumps(rep, indent=2))
    job.set_stage("texture", "review", variants=len(rep["variants"]))
    return rep


def export(job) -> dict:
    """06_export/texture/: each tile, a sheet of all variants in a row (a tileset strip), a 3 x 3
    preview of each, and a JSON (tile size, seeds, wrap scores). Needs the texture approved."""
    import json

    from PIL import Image
    job.require_approved("texture")
    s = settings(job)
    src = job.root / "02_facings"
    rep = json.loads(_report_path(job).read_text())
    keys = sorted(rep["variants"], key=int)
    name = job.read_meta()["character"]
    out = job.stage_dir("06_export") / "texture"
    out.mkdir(parents=True, exist_ok=True)
    tiles = [np.array(Image.open(src / f"tile_{k}.png").convert("RGB")) for k in keys]
    if len({t.shape for t in tiles}) != 1:
        raise ValueError("tiles have different sizes: Re-cut tiles first")
    files = []
    for k, t in zip(keys, tiles):
        Image.fromarray(t).save(out / f"{name}_{k}.png")
        prev = tiled(t)
        scale = max(1, 384 // prev.shape[0])
        Image.fromarray(prev).resize((prev.shape[1] * scale, prev.shape[0] * scale), Image.NEAREST).save(out / f"{name}_{k}_preview.png")
        files.append(f"{name}_{k}.png")
    Image.fromarray(np.concatenate(tiles, axis=1)).save(out / f"{name}_sheet.png")
    info = {"texture": name, "tile_size": int(tiles[0].shape[0]), "style": s["style"], "variants": len(tiles),
            "sheet": f"{name}_sheet.png", "tiles": files, "seeds": [rep["variants"][k]["seed"] for k in keys],
            "wrap_scores": [rep["variants"][k]["wrap_tile"] for k in keys]}
    (out / f"{name}.json").write_text(json.dumps(info, indent=2))
    job.set_stage("export:texture", "done", variants=len(tiles), tile_size=info["tile_size"])
    return info


def to_tileset(job, job_id: str | None = None) -> dict:
    """A new tileset job (Tileset workspace: terrain, maps, Tiled export) holding the variants."""
    from . import tileset
    info = export(job)
    sheet = job.root / "06_export" / "texture" / info["sheet"]
    meta = job.read_meta()
    ts = tileset.create(job.root.parent.parent, meta["character"], job_id or f"{meta['job_id']}_tiles")
    tileset.import_file(ts, sheet, {"tile_width": info["tile_size"], "tile_height": info["tile_size"],
                                    "margin": 0, "spacing": 0})
    ts.update_inputs(texture_job=f"{meta['character']}/{meta['job_id']}")
    return {"character": meta["character"], "job_id": ts.root.name, "tiles": info["variants"]}
