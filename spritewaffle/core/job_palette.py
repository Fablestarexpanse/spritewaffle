"""One palette per job, so a character keeps its colours in every facing and action.

Measured before this existed (knight p2_002): walk_E, walk_N and idle_S were quantized separately,
16 colours each, sharing none; median nearest-colour distance E->S 13 RGB, max 35 — the tunic
changed colour when the character turned, and the character export merged them into 48 colours
against a 16-colour profile.

Where the palette comes from, first match wins:
1. the profile's own locked palette (a hex list in the profile JSON);
2. `04_pixel/palette.json`, once it exists: set from a file (.gpl/.hex/.txt/.png) or fitted;
3. the project palette captured in job.json when this job was created;
4. built from the anchor + every facing still (all sides of the character, so colours only seen
   from the back are in it), or, for a job with no stills, locked from its first pixelized clip.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

from . import fsutil
from .job import Job

MAX_COLOURS = 256


def path(job: Job) -> Path:
    return job.root / "04_pixel" / "palette.json"


def get(job: Job) -> dict | None:
    p = path(job)
    try:
        return json.loads(fsutil.read_text(p))
    except FileNotFoundError:
        return None


def _hex(rgb) -> list[str]:
    return [f"#{int(r):02x}{int(g):02x}{int(b):02x}" for r, g, b in np.asarray(rgb).reshape(-1, 3).tolist()]


def clean_colours(colours: list[str]) -> list[str]:
    if not isinstance(colours, list) or any(not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colours):
        raise ValueError("Provide an array of colours in #RRGGBB format")
    colours = list(dict.fromkeys(c.lower() for c in colours))
    if not colours:
        raise ValueError("palette is empty")
    if len(colours) > MAX_COLOURS:
        raise ValueError(f"palette has {len(colours)} colours; the limit is {MAX_COLOURS}")
    return colours


def save(job: Job, colours: list[str], source: str) -> dict:
    colours = clean_colours(colours)
    data = {"colours": colours, "source": source}
    path(job).parent.mkdir(parents=True, exist_ok=True)
    fsutil.write_text(path(job), json.dumps(data, indent=2))
    job.log_provenance("04_pixel/palette.json", method="job palette", source=source, colours=len(colours))
    return data


def clear(job: Job) -> None:
    path(job).unlink(missing_ok=True)


def load_file(file: str | Path) -> list[str]:
    """.gpl (GIMP/Aseprite/Lospec), .hex/.txt (one hex per line), or an image (.png/.gif: its colours)."""
    file = Path(file)
    if not file.exists():
        raise FileNotFoundError(file)
    if file.suffix.lower() in (".png", ".gif", ".bmp"):
        im = np.array(Image.open(file).convert("RGBA"))
        px = im[im[..., 3] > 0][:, :3]
        colours = _hex(np.unique(px, axis=0))
    else:
        colours = []
        for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith(("#!", ";", "GIMP", "Name:", "Columns:")) or line == "#":
                continue
            m = re.fullmatch(r"#?([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?", line.split()[0])
            if m and file.suffix.lower() != ".gpl":
                colours.append("#" + m.group(1))
                continue
            nums = re.match(r"(\d+)\s+(\d+)\s+(\d+)", line)
            if nums:
                colours.append("#%02x%02x%02x" % tuple(min(255, int(v)) for v in nums.groups()))
    if not colours:
        raise ValueError(f"no colours found in {file}")
    return colours


def stills(job: Job) -> list[np.ndarray]:
    """Anchor + every facing still (RGB, green background)."""
    facings = ("S", "SE", "E", "NE", "N", "NW", "W", "SW")
    files = [job.root / "01_anchor" / "anchor.png"] + [job.root / "02_facings" / f"{f}.png" for f in facings]
    return [np.array(Image.open(p).convert("RGB")) for p in files if p.exists()]


def from_stills(job: Job, profile) -> list[str] | None:
    """Fit profile.palette_size colours on the anchor and all facings, at the profile's sprite
    height (the same scale the clips are pixelized at). None when the job has no stills."""
    from ..pixel import chroma
    from ..pixel.pipeline import PixelParams, pixelize
    imgs = stills(job)
    if not imgs:
        return None
    ys = np.where((chroma.key(imgs[0])[..., 3] > 0).any(1))[0]
    if not len(ys):
        return None
    size = profile.pixel_size or max(1, round((ys[-1] - ys[0] + 1) / profile.sprite_height_px))
    res = pixelize(imgs, PixelParams(palette=profile.palette_size, pixel_size=size, outline=profile.outline,
                                     despill=profile.despill))
    return _hex(res.palette)


def rebuild(job: Job, profile) -> dict:
    colours = from_stills(job, profile)
    if not colours:
        raise FileNotFoundError("no anchor or facing stills to build from")
    return save(job, colours, f"anchor + facings ({len(stills(job))} stills)")


def current(job: Job, profile) -> dict | None:
    """Return the effective fixed palette without fitting or writing any artwork."""
    if profile.locked_palette is not None:
        return {"colours": profile.locked_palette, "origin": "profile", "source": f"game profile {profile.name}"}
    if have := get(job):
        return have | {"origin": "job"}
    if colours := job.read_meta()["inputs"].get("project_palette"):
        return {"colours": colours, "origin": "project", "source": "project snapshot"}
    return None


def resolve(job: Job, profile) -> tuple[list[str] | int, bool]:
    """(palette for PixelParams, locked_now). A list = fixed palette; an int = fit per clip, and the
    caller locks the result with `lock_from_clip` (job with no stills)."""
    have = current(job, profile)
    if have:
        return have["colours"], False
    built = from_stills(job, profile)
    if built:
        return save(job, built, f"anchor + facings ({len(stills(job))} stills)")["colours"], True
    return profile.palette_size, False


def lock_from_clip(job: Job, palette_rgb, clip: str) -> None:
    if get(job) is None:
        save(job, _hex(palette_rgb), f"first pixelized clip ({clip})")


def clips(job: Job) -> list[dict]:
    """Every pixelized clip and how it was made (render / mirror / flow), for re-applying a palette."""
    out = []
    for rep in sorted((job.root / "04_pixel").glob("*/*/pixel_report.json")):
        info = json.loads(rep.read_text())
        out.append({"facing": rep.parent.parent.name, "action": rep.parent.name,
                    "method": info.get("method", "render"), "source": info.get("source"),
                    "motion": info.get("motion"), "colours": len(info.get("palette", []))})
    return out
