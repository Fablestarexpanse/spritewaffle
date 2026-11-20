"""Sprite-stack stages: orthographic views (ComfyUI image edits) and the stack build (CPU).

job folder: 02_ortho/{front,back,right,top}.png -> 06_export/stack/<name>_slices.png + .json,
<name>_turntable.gif, <name>_rotations.png + .json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from ..comfy.client import ComfyClient
from ..core import generate
from ..core.job import Job
from ..core.profile import GameProfile
from ..pixel import chroma
from ..pixel.pipeline import PixelParams, pixelize
from ..prompts.builder import FRAMING
from . import carve

VIEWS = {
    "back": "a flat orthographic back view, seen straight from behind with no perspective",
    "right": ("a flat orthographic side view of its right side, seen exactly side-on with no perspective; "
              "the front of the object points to the LEFT edge of the image"),
    "top": ("a flat orthographic top-down plan view, looking straight down from directly above with no "
            "perspective; the front of the object points to the BOTTOM edge of the image"),
}


def ortho_prompt(view: str) -> str:
    return ("<Picture 1> shows a game prop seen straight from the front. "
            f"Draw this exact same object as {VIEWS[view]}. Keep the identical shape, proportions, colours, "
            "pixel-art style, outline and scale as <Picture 1>; it is one rigid object. " + FRAMING)


def ortho(job: Job, client: ComfyClient | None = None, seed: int | None = None, only: list[str] | None = None) -> dict:
    """Front = the approved anchor; back/right/top from image edits of it."""
    generate._require_approved(job, "anchor")
    client = client or ComfyClient()
    out = job.stage_dir("02_ortho")
    anchor = job.root / "01_anchor" / "anchor.png"
    generate.flatten_background(Image.open(anchor).convert("RGB"), out / "front.png")
    for v in VIEWS:
        if only and v not in only:
            continue
        generate._run(client, job, "facing_multiref",
                      {"prompt": ortho_prompt(v), "ref_images": [anchor], "seed": generate._seed(seed)}, out / f"{v}.png")
    job.set_stage("ortho", "review")
    return {v: str(out / f"{v}.png") for v in ("front", *VIEWS)}


def build(job: Job, profile: GameProfile, stack_height: int = 24, layer_px: int = 1, steps: int = 16,
          name: str | None = None) -> dict:
    """Pixelize the four views as one batch (shared palette + pixel size), carve, export."""
    src = job.root / "02_ortho"
    missing = [v for v in ("front", *VIEWS) if not (src / f"{v}.png").exists()]
    if missing:
        raise FileNotFoundError(f"orthographic views missing: {missing}")
    imgs = [np.array(Image.open(src / f"{v}.png").convert("RGB")) for v in ("front", "back", "right", "top")]
    ys = np.where((chroma.key(imgs[0])[..., 3] > 0).any(1))[0]
    size = max(1, round((ys[-1] - ys[0] + 1) / stack_height))
    params = PixelParams(palette=profile.palette if isinstance(profile.palette, list) else profile.palette_size,
                         pixel_size=size, despill=profile.despill, outline="none")
    res = pixelize(imgs, params)
    front, back, right, top = (res.rgba(i) for i in range(4))
    occ, col = carve.carve(carve.Views(front=front, right=right, top=top, back=back))
    sl = carve.slices(occ, col)
    H, D, W = occ.shape
    name = name or job.read_meta()["character"]
    out = job.stage_dir("06_export") / "stack"
    out.mkdir(parents=True, exist_ok=True)
    strip = np.concatenate(list(sl), axis=1)                       # bottom slice first
    Image.fromarray(strip, "RGBA").save(out / f"{name}_slices.png")
    (out / f"{name}_slices.json").write_text(json.dumps({
        "name": name, "slices": H, "slice_size": [W, D], "order": "bottom_to_top", "layer_px": layer_px,
        "front": "bottom edge of each slice", "voxels": int(occ.sum()),
        "rects": [[z * W, 0, W, D] for z in range(H)],
        "palette": [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in res.palette.tolist()]}, indent=2))
    frames = carve.turntable(sl, steps, layer_px)
    big = [Image.fromarray(f, "RGBA").resize((f.shape[1] * 4, f.shape[0] * 4), Image.NEAREST) for f in frames]
    big[0].save(out / f"{name}_turntable.gif", save_all=True, append_images=big[1:], duration=90, loop=0,
                disposal=2)
    rots = [carve.render(sl, a, layer_px) for a in range(0, 360, 45)]
    h, w = rots[0].shape[:2]
    Image.fromarray(np.concatenate(rots, axis=1), "RGBA").save(out / f"{name}_rotations.png")
    (out / f"{name}_rotations.json").write_text(json.dumps({
        "angles": list(range(0, 360, 45)), "cell": [w, h], "rects": [[i * w, 0, w, h] for i in range(8)]}, indent=2))
    job.set_stage("stack", "done", slices=H, size=[W, D], voxels=int(occ.sum()))
    return {"slices": H, "slice_size": [W, D], "voxels": int(occ.sum()), "dir": str(out)}
