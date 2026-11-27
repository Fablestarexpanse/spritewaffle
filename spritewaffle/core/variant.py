"""Variants: an approved character with a change ("add a long green cape", "swap the club for a
sword"), as a new job linked to its base (Ronan: "edit model to make changes", "test default
character adding items, clothing").

Anchor: the base anchor edited with the instruction (H3 Image edit). Facings: each one is drawn
from the BASE facing for that direction (pose, angle, position), with the edited anchor as the
reference for what changed. The variant therefore lines up with the base frame for frame, instead
of drifting the way freshly generated facings can.
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from ..comfy.client import ComfyClient
from ..prompts import builder, styles
from .job import Job
from .profile import GameProfile


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return "_".join(s.split("_")[:4])[:32] or "variant"


STYLE_WORDS = re.compile(r"\b(pixel[- ]art|pixelated|sprite|8-bit|16-bit)\s*", re.I)


def item_edit(instruction: str, description: str) -> str:
    """'wearing this' + 'a golden breastplate…' -> 'wearing a golden breastplate…'. Without 'this'
    the description is appended."""
    d = STYLE_WORDS.sub("", description).strip().rstrip(".")
    d = d[0].lower() + d[1:] if d else d
    instruction = (instruction or "wearing this").strip().rstrip(".")
    if re.search(r"\bthis\b", instruction):
        return re.sub(r"\bthis\b", d, instruction, count=1)
    return f"{instruction} {d}"


# Details that wrap round or hang behind, so a back view still shows them; and words that mark a detail
# as front-only even when it also names one of those.
BACK_SEEN = re.compile(r"\b(?:trim\w*|edg\w*|hem\w*|border\w*|lin(?:ed|ing)|hood\w*|fur|collar|belt\w*|sash\w*|"
                       r"strap\w*|shoulder\w*|pattern\w*|stripe\w*|reach\w*|knee\w*|ankle\w*|floor|waist\w*|"
                       r"length|long|short|tattered|frayed|torn)\b", re.I)
FRONT_ONLY = re.compile(r"\b(?:front|clasp\w*|buckle\w*|gem\w*|jewel\w*|emblem\w*|crest\w*|badge\w*|brooch\w*|"
                        r"button\w*|lac(?:e|ed|es|ing)|chest|central|centre|center|face|pommel\w*|open)\b", re.I)


def item_core(description: str) -> str:
    """The item without its front details, for back views ('a long red velvet cape with a gold clasp at
    the neck and gold trim along the edges' -> 'a long red velvet cape with gold trim along the edges').
    Measured 2026-11-21: with the full description every back view showed the gem on the back, even
    when told front details are hidden. 2026-11-27: cutting at the first 'with' also lost the trim, hood
    and length on N, so later details naming something that shows from behind (BACK_SEEN) are kept
    unless they name a front-only part (FRONT_ONLY)."""
    joins = r"(?:featuring|with|detailed with|decorated with|adorned with|that|which|and)"
    parts = re.split(rf",\s*(?:{joins}\s+)?|\s+{joins}\s+", description.strip().rstrip("."))
    head, rest = parts[0].strip(), [p.strip() for p in parts[1:] if p and p.strip()]
    kept = [p for p in rest if BACK_SEEN.search(p) and not FRONT_ONLY.search(p)]
    if not kept:
        return head
    return head + " with " + (kept[0] if len(kept) == 1 else ", ".join(kept[:-1]) + " and " + kept[-1])


def item_reference(item: Path, dest: Path, size: int = 1024, frac: float = 0.35) -> Path:
    """The item shrunk to about a third of a light grey card: the second reference picture. Measured
    2026-11-21: the item picture at full size was read as the canvas (huge armor, tiny knight)."""
    import numpy as np
    from ..pixel import chroma
    im = Image.open(item)
    if im.mode == "RGBA" and np.array(im)[..., 3].min() < 255:
        a = np.array(im)
        ys, xs = np.where(a[..., 3] > 0)
        cut = Image.fromarray(a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]) if len(ys) else im
    else:
        cut = Image.fromarray(chroma.crop_sprite(np.array(im.convert("RGB"))))
    cut = cut.convert("RGBA")
    cut.thumbnail((int(size * frac), int(size * frac)), Image.NEAREST if max(cut.size) < size * frac else Image.LANCZOS)
    card = Image.new("RGBA", (size, size), (205, 205, 210, 255))
    card.alpha_composite(cut, ((size - cut.width) // 2, (size - cut.height) // 2))
    card.convert("RGB").save(dest)
    return dest


def create(base: Job, instruction: str, job_id: str | None = None, item: str | Path | None = None,
           client: ComfyClient | None = None, item_back: str | Path | None = None,
           item_description: str | None = None, extra: dict | None = None) -> Job:
    """New job next to the base (same character name), linked to it. The base must have approved
    facings: the variant copies their poses.

    item: a picture of an item (armor, weapon, hat); `instruction` says how it is used ("wearing
    this", "holding this in the right hand"). It goes to H3 Image edit as <Picture 2> (a small copy on
    a grey card, 01_anchor/item_ref.png) with a Subject caption (builder.item_reference). The local
    prompt writer (Qwen3-VL 4B) names the item and, when the base has no description, the character:
    the caption needs both in words.

    item_back: the item's own back view (item jobs, core/item.py): back facings use it as <Picture 2>.
    item_description: skips the writer when the item is already described (item jobs)."""
    instruction = (instruction or "").strip().rstrip(".")
    item_desc = None
    if item:
        item = Path(item)
        if not item.exists():
            raise FileNotFoundError(f"item picture {item} not found")
        from ..prompts import writer
        item_desc = item_description or writer.describe_item(item, client=client)
        character = (base.read_meta()["inputs"].get("description")
                     or writer.describe("", image=base.root / "01_anchor" / "anchor.png", client=client))
        item_how = instruction or "wearing this"
        instruction = item_edit(item_how, item_desc)
    if not instruction:
        raise ValueError("describe the change, e.g. 'add a long green cape'")
    base.require_approved("facings")
    bm = base.read_meta()
    job_id = job_id or f"{bm['job_id']}_{_slug(instruction)}"
    root = base.root.parent / job_id
    if root.exists():
        raise FileExistsError(f"job {bm['character']}/{job_id} already exists")
    keep = {k: v for k, v in bm["inputs"].items()
            if k in ("profile", "style", "style_guide", "project_palette", "asset_type", "prompt_writer", "facing_notes")}
    desc = bm["inputs"].get("description") or ""
    job = Job.create(bm["character"], job_id, base=base.root.parent.parent, **keep,
                     description=f"{desc}; {instruction}" if desc else instruction,
                     base_job=str(base.root), edit=instruction, **({"item_description": item_desc, "item_how": item_how, "character_description": character}
                        if item_desc else {}), **(extra or {}))
    if item:
        import shutil
        shutil.copyfile(item, job.stage_dir("01_anchor") / "item.png")
        item_reference(item, job.stage_dir("01_anchor") / "item_ref.png")
        if item_back:
            item_reference(Path(item_back), job.stage_dir("01_anchor") / "item_ref_back.png")
    job.log_provenance("variant", base=f"{bm['character']}/{bm['job_id']}", edit=instruction,
                       **({"item": str(item), "item_description": item_desc} if item else {}))
    return job


def layers(job: Job) -> tuple[str, list[str]]:
    """(top item, clothes under it) for a fitted variant, walking the base_job chain: each fitted item
    by its name ('the brown leather armor vest'), and a base body's plain wear last. Only for layered
    fits (an item fitted over another fitted item, the measured case): ("", []) otherwise."""
    inputs = job.read_meta()["inputs"]
    if not inputs.get("item_description"):
        return "", []

    def name(d: str) -> str:
        head = re.split(r"\s+(?:featuring|with|detailed|decorated|adorned|that|which)\b|,", d, maxsplit=1)[0]
        return re.sub(r"^(?:a|an|the)\s+", "", head.strip(), flags=re.I)

    top, under, seen = name(inputs["item_description"]), [], {str(job.root)}
    b = base_of(job)
    while b is not None and str(b.root) not in seen:
        seen.add(str(b.root))
        bi = b.read_meta()["inputs"]
        if bi.get("item_description"):
            under.append("the " + name(bi["item_description"]))
        elif bi.get("asset_type") == "base_body":
            under.append(builder.BASE_BODY_WEAR.split(", bare head")[0].removeprefix("dressed in "))
            break
        b = base_of(b)
    return (top, under) if under and under[0].startswith("the ") else ("", [])


def base_of(job: Job) -> Job | None:
    b = job.read_meta()["inputs"].get("base_job")
    return Job.open(b) if b and (Path(b) / "job.json").exists() else None


def _edit_values(job: Job, inputs: dict, f: str, src: Path, raised: bool) -> dict:
    """Prompt + reference pictures for one variant view. With an item picture: base view + item card
    and the Subject caption; otherwise base view + the change in words."""
    ref = job.root / "01_anchor" / "item_ref.png"
    # N goes by words: measured 2026-11-21 (red cape on knight/p2_002) with the item back as Picture 2
    # the knight's belt was drawn across the cape in 5 of 5 rolls; in words, 0 of 2. NE/NW kept the
    # reference fine (3 of 4).
    if ref.exists() and inputs.get("item_description") and f != "N":
        back_ref = job.root / "01_anchor" / "item_ref_back.png"
        use_back = f in builder.BACK and back_ref.exists()
        return {"prompt": builder.item_reference(f, inputs.get("character_description") or "character",
                                                 inputs["item_description"], inputs.get("item_how") or "wearing this",
                                                 back_item=item_core(inputs["item_description"]), raised=raised,
                                                 back_ref=use_back),
                "ref_images": [src, back_ref if use_back else ref]}
    edit = inputs["edit"]
    if f == "S":
        return {"prompt": builder.edit_anchor(edit), "ref_images": [src]}
    back_edit = (item_edit(inputs["item_how"], item_core(inputs["item_description"]))
                 if inputs.get("item_description") and inputs.get("item_how") else edit)
    return {"prompt": builder.edit_facing(f, back_edit if f in builder.BACK else edit, raised), "ref_images": [src]}


def anchor(job: Job, profile: GameProfile, client: ComfyClient | None = None, seed: int | None = None) -> Path:
    """The base anchor with the change applied. Left in review."""
    from . import generate
    base = base_of(job)
    if base is None:
        raise FileNotFoundError("this job is not a variant, or its base job is gone")
    styles.use(styles.of_job(job))
    client = client or ComfyClient()
    inputs = job.read_meta()["inputs"]
    dest = job.stage_dir("01_anchor") / "anchor.png"
    src = base.root / "01_anchor" / "anchor.png"
    generate._run(client, job, "facing_multiref", {**_edit_values(job, inputs, "S", src, False),
                                                   "seed": generate._seed(seed)}, dest)
    if "project_reference_id" in inputs:
        with job.mutate() as meta:
            meta["inputs"].pop("project_reference_id", None)
    job.set_stage("anchor", "review", variant_of=base.root.name)
    return dest


def facings(job: Job, profile: GameProfile, client: ComfyClient | None = None, only: list[str] | None = None,
            seed: int | None = None) -> dict:
    """Every base facing redrawn with the change: Picture 1 = base facing (pose/view), the change in
    words. S is the approved variant anchor itself."""
    from . import generate
    job.require_approved("anchor")
    base = base_of(job)
    if base is None:
        raise FileNotFoundError("this job is not a variant, or its base job is gone")
    styles.use(styles.of_job(job))
    client = client or ComfyClient()
    inputs = job.read_meta()["inputs"]
    edit = inputs["edit"]
    out = job.stage_dir("02_facings")
    a_path = job.root / "01_anchor" / "anchor.png"
    generate.flatten_background(Image.open(a_path).convert("RGB"), out / "S.png")
    raised = profile.projection != "side"
    done = []
    for f in [x for x in builder.CARDINALS + builder.DIAGONALS if x != "S" and (not only or x in only)]:
        src = base.root / "02_facings" / f"{f}.png"
        if not src.exists():
            continue
        generate._run(client, job, "facing_multiref", {**_edit_values(job, inputs, f, src, raised),
                                                       "seed": generate._seed(seed)}, out / f"{f}.png")
        done.append(f)
    a = generate._rgba(a_path)
    report = {"variant_of": str(base.root), "edit": edit, "facings": {}, "mirrored": {}, "warnings": [],
              "diagonals": "from base"}
    # every view on disk, not just the ones drawn now: re-rolling one view used to drop the other
    # views' drift and warnings from the report (seen 2026-11-26 re-rolling N of a fitted vest)
    present = [f for f in builder.CARDINALS + builder.DIAGONALS
               if f != "S" and (out / f"{f}.png").exists() and (base.root / "02_facings" / f"{f}.png").exists()]
    for f in present:
        report["facings"][f] = generate.drift(a, generate._rgba(out / f"{f}.png"))
        t = round(generate.turned_from(generate._rgba(out / f"{f}.png"), generate._rgba(base.root / "02_facings" / f"{f}.png")), 1)
        report.setdefault("changed", {})[f] = t
        if t < 4:
            report["warnings"].append(f"{f} looks unchanged from the base (difference {t}): the edit may be missing; re-roll it")
        s = round(generate.turned_from(generate._rgba(out / f"{f}.png"), a), 1)   # came out as the front view?
        report.setdefault("turned", {})[f] = s
        if s < generate.COPY_DIFF:
            report["warnings"].append(f"{f} looks like a copy of the front view (difference {s}): it lost the base pose; re-roll it")
    import json
    (out / "facings_report.json").write_text(json.dumps(report, indent=2))
    job.set_stage("facings", "review", variant_of=base.root.name, rendered=done)
    return report
