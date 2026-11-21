"""Sprite-stack stages: orthographic views (ComfyUI image edits) and the stack build (CPU).

Two ways to the voxels:
- method "3d" (default): the anchor redrawn as a lit 3D render (H3 Image edit), TRELLIS.2 on
  ComfyUI turns it into a vertex-coloured mesh (02_ortho/model.glb), stack/mesh3d.py voxelizes it.
  Measured 2026-11-21: fed the flat pixel-art anchor directly, TRELLIS built a flat card (depth
  +-0.0008); fed the 3D-look render it built the whole tree. Keeps overhangs, gaps and
  non-mirrored sides.
- method "carve": front/back/right/top outlines intersected (02_ortho/{front,back,right,top}.png).
  Rigid boxy props only: hollows come out solid, overhangs become a solid cone.

-> 06_export/stack/<name>_slices.png + .json, <name>_turntable.gif, <name>_rotations.png + .json.
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
    job.require_approved("anchor")
    from ..prompts import styles
    styles.use(styles.of_job(job))
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


RENDER3D = ("<Picture 1> shows a pixel-art game prop. Draw the exact same object as a solid 3D rendered model: "
            "smooth realistic volume and depth, soft studio lighting with clear shading and shadows on the form, seen "
            "from a three-quarter view slightly from above so its depth and all its parts are visible, the same shape, "
            "proportions and colors. Not pixel art, not flat. The whole object is visible, centered, on a flat plain "
            "light grey background, no floor, no shadow on the ground, no text.")


def model3d(job: Job, client: ComfyClient | None = None, seed: int | None = None) -> dict:
    """Anchor -> 3D-look render (02_ortho/render3d.png) -> TRELLIS.2 mesh (02_ortho/model.glb)."""
    import shutil
    job.require_approved("anchor")
    client = client or ComfyClient()
    out = job.stage_dir("02_ortho")
    anchor = job.root / "01_anchor" / "anchor.png"
    seed = generate._seed(seed)
    r = client.run_template("facing_multiref", {"prompt": RENDER3D, "ref_images": [anchor], "seed": seed}, out / ".r3d")
    shutil.copyfile(r["files"][0], out / "render3d.png")
    job.log_provenance("02_ortho/render3d.png", template="facing_multiref", values={"prompt": RENDER3D, "seed": seed})
    client.free()                                    # H3 Image still holds ~20 GB of VRAM
    m = client.run_template("trellis_mesh", {"ref_images": [out / "render3d.png"], "seed": seed}, out / ".glb")
    glb = next((f for f in m["files"] if f.endswith(".glb")), None)
    if not glb:
        raise RuntimeError(f"TRELLIS produced no GLB: {m['files']}")
    shutil.copyfile(glb, out / "model.glb")
    shutil.rmtree(out / ".r3d", ignore_errors=True)
    shutil.rmtree(out / ".glb", ignore_errors=True)
    job.log_provenance("02_ortho/model.glb", template="trellis_mesh", seed=seed)
    job.set_stage("model3d", "done", seed=seed)
    return {"render": str(out / "render3d.png"), "model": str(out / "model.glb")}


def build(job: Job, profile: GameProfile, stack_height: int = 24, layer_px: int = 1, steps: int = 16,
          name: str | None = None, method: str = "3d") -> dict:
    """Voxels from the 3D model (method '3d') or carved from the four views ('carve'), then export."""
    from ..prompts import styles
    if styles.get(styles.of_job(job))["post"] != "pixel":
        raise RuntimeError(f"sprite stacking is pixel art only; this job's style is '{styles.of_job(job)}'")
    if method == "3d":
        from . import mesh3d
        glb = job.root / "02_ortho" / "model.glb"
        if not glb.exists():
            raise FileNotFoundError("no 3D model yet: run the 3D model step first")
        occ, col = mesh3d.voxelize(*mesh3d.read_glb(glb), stack_height)
        from ..core import job_palette
        jp = job_palette.get(job)
        fixed = profile.palette if isinstance(profile.palette, list) else (jp["colours"] if jp else None)
        col, pal = mesh3d.quantize(occ, col, profile.palette_size, fixed)
        return _export(job, carve.slices(occ, col), occ, pal, layer_px, steps, name, method)
    if method != "carve":
        raise ValueError("method must be '3d' or 'carve'")
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
    return _export(job, carve.slices(occ, col), occ, res.palette, layer_px, steps, name, method)


def _export(job: Job, sl: np.ndarray, occ: np.ndarray, palette, layer_px: int, steps: int, name: str | None,
            method: str) -> dict:
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
        "method": method,
        "palette": [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in np.asarray(palette).tolist()]}, indent=2))
    frames = carve.turntable(sl, steps, layer_px)
    big = [Image.fromarray(f, "RGBA").resize((f.shape[1] * 4, f.shape[0] * 4), Image.NEAREST) for f in frames]
    big[0].save(out / f"{name}_turntable.gif", save_all=True, append_images=big[1:], duration=90, loop=0,
                disposal=2)
    rots = [carve.render(sl, a, layer_px) for a in range(0, 360, 45)]
    h, w = rots[0].shape[:2]
    Image.fromarray(np.concatenate(rots, axis=1), "RGBA").save(out / f"{name}_rotations.png")
    (out / f"{name}_rotations.json").write_text(json.dumps({
        "angles": list(range(0, 360, 45)), "cell": [w, h], "rects": [[i * w, 0, w, h] for i in range(8)]}, indent=2))
    job.set_stage("stack", "done", slices=H, size=[W, D], voxels=int(occ.sum()), method=method)
    return {"slices": H, "slice_size": [W, D], "voxels": int(occ.sum()), "dir": str(out), "method": method}
