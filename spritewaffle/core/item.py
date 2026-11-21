"""Equipment items for paper-doll games (Ronan 2026-11-21: "we would generate item separately ...
we add it to base but we still have our original item"; "front and back").

An item is its own job (asset type "item"): the anchor is its front (S), the facings stage draws
its back (N) from the front with H3 Image edit. Fitting it onto a base character makes a variant of
that base (core/variant.py) with the item front as <Picture 2> for front and side views and the item
back for back views (words for N). The worn variant is the result; the item job stays the
original. Any number of bases (races, bodies) can wear the same item; the item job lists them in inputs.fits.
"""
from __future__ import annotations

import json

from PIL import Image

from ..comfy.client import ComfyClient
from ..prompts import builder, styles
from .job import Job
from .profile import GameProfile

VIEWS = ("S", "N")          # front, back


def is_item(job: Job) -> bool:
    return job.read_meta()["inputs"].get("asset_type") == "item"


def facings(job: Job, profile: GameProfile, client: ComfyClient | None = None, seed: int | None = None) -> dict:
    """Front = the approved anchor; back drawn from it. Left in review."""
    from . import generate
    job.require_approved("anchor")
    styles.use(styles.of_job(job))
    client = client or ComfyClient()
    out = job.stage_dir("02_facings")
    a_path = job.root / "01_anchor" / "anchor.png"
    generate.flatten_background(Image.open(a_path).convert("RGB"), out / "S.png")
    inputs = job.read_meta()["inputs"]
    desc = inputs.get("visual_description") or inputs.get("description") or ""
    generate._run(client, job, "facing_multiref",
                  {"prompt": builder.item_back(desc), "ref_images": [out / "S.png"], "seed": generate._seed(seed)},
                  out / "N.png")
    a = generate._rgba(a_path)
    t = round(generate.turned_from(generate._rgba(out / "N.png"), a), 1)
    report = {"item": True, "facings": {"N": generate.drift(a, generate._rgba(out / "N.png"))}, "mirrored": {},
              "turned": {"N": t}, "warnings": []}
    if t < generate.COPY_DIFF:
        report["warnings"].append(f"the back looks like a copy of the front (difference {t}): re-roll it")
    (out / "facings_report.json").write_text(json.dumps(report, indent=2))
    job.set_stage("facings", "review", rendered=["N"])
    return report


def fit(item_job: Job, base: Job, how: str = "wearing this", job_id: str | None = None,
        client: ComfyClient | None = None) -> Job:
    """A variant of `base` wearing/holding this item. The item needs approved front and back."""
    from . import variant
    if not is_item(item_job):
        raise ValueError(f"{item_job.root.name} is not an item job (asset type 'item')")
    item_job.require_approved("facings")
    im = item_job.read_meta()
    f = item_job.root / "02_facings"
    desc = im["inputs"].get("visual_description") or im["inputs"].get("description")
    v = variant.create(base, how or "wearing this", job_id or f"{base.root.name}_{im['character']}",
                       item=f / "S.png", item_back=f / "N.png", item_description=desc, client=client,
                       extra={"item_job": str(item_job.root)})
    with item_job.mutate() as meta:
        fits = meta["inputs"].setdefault("fits", [])
        fits.append({"character": v.read_meta()["character"], "job_id": v.root.name, "base": base.root.name})
    return v


def export(job: Job, profile: GameProfile) -> dict:
    """The original item as game sprites: 06_export/item/<name>_front.png and _back.png, made like a
    facing (pixel art at the profile's sprite height, one palette for both; smooth styles scaled)."""
    import numpy as np

    from ..pixel import chroma
    from ..pixel.pipeline import PixelParams, pixelize
    if not is_item(job):
        raise ValueError(f"{job.root.name} is not an item job")
    job.require_approved("facings")
    f = job.root / "02_facings"
    rgbs = [np.array(Image.open(f / f"{v}.png").convert("RGB")) for v in VIEWS]
    st = styles.get(styles.of_job(job))
    if st["post"] == "smooth":
        from ..pixel import smooth
        arts, _ = smooth.process(rgbs, profile.sprite_height_px * st["scale"], despill=profile.despill)
        colours = None
    else:
        ys = np.where((chroma.key(rgbs[0])[..., 3] > 0).any(1))[0]
        size = profile.pixel_size or max(1, round((ys[-1] - ys[0] + 1) / profile.sprite_height_px))
        res = pixelize(rgbs, PixelParams(palette=profile.palette if isinstance(profile.palette, list) else profile.palette_size,
                                         pixel_size=size, outline=profile.outline, despill=profile.despill))
        arts, colours = [res.rgba(i) for i in range(len(VIEWS))], len(res.palette)
    out = job.stage_dir("06_export") / "item"
    out.mkdir(parents=True, exist_ok=True)
    name = job.read_meta()["character"]
    files = {}
    for v, label, art in zip(VIEWS, ("front", "back"), arts):
        ys, xs = np.where(art[..., 3] > 0)
        crop = art[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else art
        p = out / f"{name}_{label}.png"
        Image.fromarray(crop).save(p)
        files[label] = {"file": p.name, "size": [int(crop.shape[1]), int(crop.shape[0])]}
    info = {"item": name, "style": st["name"], "colours": colours, "views": files,
            "fits": job.read_meta()["inputs"].get("fits") or []}
    (out / f"{name}_item.json").write_text(json.dumps(info, indent=2))
    job.set_stage("export:item", "done", colours=colours, sizes={k: v["size"] for k, v in files.items()})
    return info
