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
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from ..comfy.client import ComfyClient
from ..export import receipt
from ..prompts import builder, styles
from .job import Job
from .profile import GameProfile

VIEWS = ("S", "N")          # front, back


def is_item(job: Job) -> bool:
    return job.read_meta()["inputs"].get("asset_type") == "item"


def reference_palette(path: Path) -> list[str]:
    """Sample colour cues without passing the reference's subject to the renderer."""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
    image.thumbnail((256, 256), Image.Resampling.NEAREST)
    rgba = np.asarray(image)
    rgb = rgba[..., :3]
    visible = rgba[..., 3] > 127
    if visible.all():
        # Saved SpriteWaffle anchors use an exact green matte. Keep other greens as artwork.
        green = (rgb == (0, 255, 0)).all(axis=2)
        border = np.concatenate((green[0], green[-1], green[1:-1, 0], green[1:-1, -1]))
        if border.mean() > .5:
            visible = ~green
    colours = rgb[visible]
    if len(colours) == 0:
        raise ValueError("The item style reference has no visible colours. Choose another reference.")
    indexed = Image.fromarray(colours.reshape(1, -1, 3)).quantize(colors=6)
    palette = indexed.getpalette()
    return ["#{:02x}{:02x}{:02x}".format(*palette[index * 3:index * 3 + 3])
            for _, index in sorted(indexed.getcolors(), key=lambda entry: (-entry[0], entry[1]))]


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


def _export_inputs(job: Job, profile: GameProfile) -> dict:
    meta = job.read_meta()
    inputs = meta["inputs"]
    if inputs.get("asset_type") != "item":
        raise ValueError(f"{job.root.name} is not an item job")
    style = styles.get(inputs.get("style") or "pixel")
    settings = {"name": meta["character"], "style": style["name"], "fits": inputs.get("fits") or [],
                "facings_approved": meta["stages"].get("facings", {}).get("status") == "approved",
                "despill": profile.despill}
    if style["post"] == "pixel":
        settings.update(palette=profile.palette, pixel_size=profile.pixel_size or None, outline=profile.outline)
    if style["post"] == "smooth" or not profile.pixel_size:
        settings["sprite_height_px"] = profile.sprite_height_px
    return receipt.snapshot(job.root, (job.root / "02_facings" / f"{v}.png" for v in VIEWS), settings)


def export_status(job: Job, profile: GameProfile) -> dict:
    """Check the last completed item bundle against the current views and export settings."""
    if not is_item(job):
        raise ValueError(f"{job.root.name} is not an item job")
    out = job.root / "06_export" / "item"
    path = out.with_name(".item.receipt")
    record = receipt.load(path)
    if record is None:
        return {"status": "untracked" if path.exists() or any(out.glob("*.png")) or any(out.glob("*_item.json")) else "missing"}
    if record.get("incomplete"):
        return {"status": "incomplete"}
    return receipt.compare(record, out, _export_inputs(job, profile))


def export(job: Job, profile: GameProfile) -> dict:
    """Export game-ready front and back sprites and the fit list as one tracked bundle."""
    out = job.root / "06_export" / "item"
    out.parent.mkdir(parents=True, exist_ok=True)
    path = out.with_name(".item.receipt")
    with receipt.locked(out):
        inputs = _export_inputs(job, profile)
        job.require_approved("facings")
        info, files = _write_export(job, profile, out, path, inputs["settings"])
        if inputs != _export_inputs(job, profile):
            raise RuntimeError("Item export inputs changed during export. Wait for processing to finish, then export again.")
        receipt.save(path, out, inputs, files)
        job.set_stage("export:item", "done", colours=info["colours"], sizes={k: v["size"] for k, v in info["views"].items()})
    return info


def _write_export(job: Job, profile: GameProfile, out: Path, receipt_path: Path, settings: dict) -> tuple[dict, list[Path]]:
    import numpy as np

    from ..pixel import chroma
    from ..pixel.pipeline import PixelParams, pixelize
    f = job.root / "02_facings"
    rgbs = [np.array(Image.open(f / f"{v}.png").convert("RGB")) for v in VIEWS]
    st = styles.get(settings["style"])
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
    receipt.incomplete(receipt_path)
    out.mkdir(parents=True, exist_ok=True)
    name = settings["name"]
    views, files = {}, []
    for label, art in zip(("front", "back"), arts):
        ys, xs = np.where(art[..., 3] > 0)
        crop = art[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else art
        p = out / f"{name}_{label}.png"
        Image.fromarray(crop).save(p)
        views[label] = {"file": p.name, "size": [int(crop.shape[1]), int(crop.shape[0])]}
        files.append(p)
    info = {"item": name, "style": st["name"], "colours": colours, "views": views, "fits": settings["fits"]}
    meta = out / f"{name}_item.json"
    meta.write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info, [*files, meta]
