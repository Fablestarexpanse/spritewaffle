"""Terrain transitions: two seamless textures -> the 16-tile corner set (every combination of the
four corners being terrain A or B) as a tileset with its corner terrain rules already filled in,
ready for the terrain map preview and Tiled export (a corner Wang set).

Every tile is A where its mask is low and B where it is high. The mask is the four corners
interpolated across the tile plus a wobble from a noise field that repeats once per tile.
Neighbouring tiles share the two corners of their common edge, the noise continues across the
edge (same field, period = one tile), and A and B are themselves seamless tiles of the same size,
so any arrangement the terrain rules allow fits together pixel for pixel.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# corner order used by the terrain rules (core/terrain.py)
CORNERS = ("NW", "NE", "SE", "SW")


def _noise(size: int, seed: int, octaves: int = 4) -> np.ndarray:
    """A smooth noise field in [-1, 1] that repeats every `size` px in x and y: a sum of waves
    with whole-number frequencies and random phases."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size] + 0.5
    n = np.zeros((size, size))
    for o in range(octaves):
        for _ in range(3):
            fx, fy = rng.integers(-(2 + 2 * o), 3 + 2 * o, 2)
            if fx == 0 and fy == 0:
                fx = 1
            n += (0.55 ** o) * np.sin(2 * np.pi * (fx * x + fy * y) / size + rng.uniform(0, 2 * np.pi))
    return n / max(1e-9, np.abs(n).max())


def masks(size: int, roughness: float = 0.5, seed: int = 0, soft: float = 0.0) -> list[np.ndarray]:
    """16 masks (0 = terrain A, 1 = terrain B), index = NW*8 + NE*4 + SE*2 + SW*1 (corner is B).
    roughness 0..1 bends the border (amplitude kept under 0.45 so all-A / all-B tiles stay pure).
    soft > 0: a blended border that many px wide (painted styles); 0: a hard border (pixel art)."""
    if not 0 <= roughness <= 1:
        raise ValueError("roughness must be 0..1")
    y, x = np.mgrid[0:size, 0:size] + 0.5
    u, v = x / size, y / size
    wobble = 0.42 * roughness * _noise(size, seed)
    out = []
    for i in range(16):
        nw, ne, se, sw = (i >> 3) & 1, (i >> 2) & 1, (i >> 1) & 1, i & 1
        t = nw * (1 - u) * (1 - v) + ne * u * (1 - v) + se * u * v + sw * (1 - u) * v
        if 0 < i < 15:
            t = t + wobble
        if soft > 0:
            w = soft / size
            m = np.clip((t - 0.5) / w + 0.5, 0, 1)
            m = m * m * (3 - 2 * m)
        else:
            m = (t > 0.5).astype(float)
        out.append(m)
    return out


def build(a: np.ndarray, b: np.ndarray, roughness: float = 0.5, seed: int = 0, soft: float = 0.0) -> np.ndarray:
    """The 4 x 4 sheet (tile i at column i % 4, row i // 4) from two seamless tiles of one size."""
    if a.shape != b.shape or a.shape[0] != a.shape[1]:
        raise ValueError(f"both textures need the same square tile size (got {a.shape[:2]} and {b.shape[:2]})")
    size = a.shape[0]
    tiles = [np.rint(a[..., :3] * (1 - m[..., None]) + b[..., :3] * m[..., None]).astype(np.uint8)
             for m in masks(size, roughness, seed, soft)]
    rows = [np.concatenate(tiles[r * 4:(r + 1) * 4], axis=1) for r in range(4)]
    return np.concatenate(rows, axis=0)


def rules(name_a: str, name_b: str) -> dict:
    """Corner terrain rules for the sheet: tile i's corners in NW, NE, SE, SW order."""
    tiles = {}
    for i in range(16):
        bits = ((i >> 3) & 1, (i >> 2) & 1, (i >> 1) & 1, i & 1)
        tiles[str(i)] = [name_b if bit else name_a for bit in bits]
    return {"colors": [name_a, name_b], "tiles": tiles}


def _tile(job, variant: int, size: int) -> np.ndarray:
    """A texture job's seamless master cut at `size` with that job's own style settings."""
    from PIL import Image

    from . import texture
    job.require_approved("texture")
    master = job.root / "02_facings" / f"master_{variant}.png"
    if not master.exists():
        raise FileNotFoundError(f"{job.root.parent.name}/{job.root.name} has no variant {variant + 1}")
    s = {**texture.settings(job), "tile_size": size}
    return texture.tile_from(np.array(Image.open(master).convert("RGB")), s)


def make(a_job, b_job, name: str | None = None, job_id: str | None = None, names: tuple[str, str] | None = None,
         tile_size: int | None = None, roughness: float = 0.5, seed: int = 0, variant_a: int = 0,
         variant_b: int = 0) -> dict:
    """A tileset job holding the 16-tile corner transition between two approved texture jobs,
    with its terrain rules filled in. Re-running it on the same tileset job replaces the sheet."""
    from PIL import Image

    from . import texture, tileset
    from .job import Job
    for j in (a_job, b_job):
        if j.read_meta()["inputs"].get("asset_type") != texture.TYPE:
            raise ValueError(f"{j.root.parent.name}/{j.root.name} is not a seamless texture job")
    sa, sb = texture.settings(a_job), texture.settings(b_job)
    size = int(tile_size or sa["tile_size"])
    if size not in texture.TILE_SIZES:
        raise ValueError(f"tile size must be one of {texture.TILE_SIZES}")
    na, nb = names or (a_job.read_meta()["character"], b_job.read_meta()["character"])
    if not na.strip() or not nb.strip() or na.strip().casefold() == nb.strip().casefold():
        raise ValueError("give the two terrains different names")
    soft = 0.0 if sa["style"] == "pixel" else max(2.0, size / 16)
    sheet = build(_tile(a_job, variant_a, size), _tile(b_job, variant_b, size), roughness, seed, soft)
    base = a_job.root.parent.parent
    name = name or f"{na}_{nb}"
    job_id = job_id or "transition"
    root = base / name / job_id
    ts = Job.open(root) if (root / "job.json").exists() else tileset.create(base, name, job_id)
    if ts.read_meta()["inputs"].get("asset_type") != tileset.TYPE:
        raise ValueError(f"{name}/{job_id} exists and is not a tileset")
    out = ts.stage_dir("06_export") / "transition"
    out.mkdir(parents=True, exist_ok=True)
    sheet_path = out / f"{name}_transition.png"
    Image.fromarray(sheet).save(sheet_path)
    tileset.import_file(ts, sheet_path, {"tile_width": size, "tile_height": size, "margin": 0, "spacing": 0})
    tileset.update_terrain(ts, rules(na.strip(), nb.strip()))
    info = {"a": f"{a_job.root.parent.name}/{a_job.root.name}", "b": f"{b_job.root.parent.name}/{b_job.root.name}",
            "names": [na.strip(), nb.strip()], "tile_size": size, "roughness": roughness, "seed": seed,
            "variants": [variant_a, variant_b], "soft_px": soft}
    ts.update_inputs(transition=info)
    (out / f"{name}_transition.json").write_text(json.dumps(info, indent=2))
    return {"character": name, "job_id": ts.root.name, "tiles": 16, **info}
