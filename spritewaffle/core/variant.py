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


def create(base: Job, instruction: str, job_id: str | None = None) -> Job:
    """New job next to the base (same character name), linked to it. The base must have approved
    facings: the variant copies their poses."""
    instruction = (instruction or "").strip().rstrip(".")
    if not instruction:
        raise ValueError("describe the change, e.g. 'add a long green cape'")
    base.require_approved("facings")
    bm = base.read_meta()
    job_id = job_id or f"{bm['job_id']}_{_slug(instruction)}"
    root = base.root.parent / job_id
    if root.exists():
        raise FileExistsError(f"job {bm['character']}/{job_id} already exists")
    keep = {k: v for k, v in bm["inputs"].items() if k in ("profile", "style", "asset_type", "prompt_writer", "facing_notes")}
    desc = bm["inputs"].get("description") or ""
    job = Job.create(bm["character"], job_id, base=base.root.parent.parent, **keep,
                     description=f"{desc}; {instruction}" if desc else instruction,
                     base_job=str(base.root), edit=instruction)
    job.log_provenance("variant", base=f"{bm['character']}/{bm['job_id']}", edit=instruction)
    return job


def base_of(job: Job) -> Job | None:
    b = job.read_meta()["inputs"].get("base_job")
    return Job.open(b) if b and (Path(b) / "job.json").exists() else None


def anchor(job: Job, profile: GameProfile, client: ComfyClient | None = None, seed: int | None = None) -> Path:
    """The base anchor with the change applied. Left in review."""
    from . import generate
    base = base_of(job)
    if base is None:
        raise FileNotFoundError("this job is not a variant, or its base job is gone")
    styles.use(styles.of_job(job))
    client = client or ComfyClient()
    edit = job.read_meta()["inputs"]["edit"]
    dest = job.stage_dir("01_anchor") / "anchor.png"
    generate._run(client, job, "facing_multiref",
                  {"prompt": builder.edit_anchor(edit), "ref_images": [base.root / "01_anchor" / "anchor.png"],
                   "seed": generate._seed(seed)}, dest)
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
    edit = job.read_meta()["inputs"]["edit"]
    out = job.stage_dir("02_facings")
    a_path = job.root / "01_anchor" / "anchor.png"
    generate.flatten_background(Image.open(a_path).convert("RGB"), out / "S.png")
    raised = profile.projection != "side"
    done = []
    for f in [x for x in builder.CARDINALS + builder.DIAGONALS if x != "S" and (not only or x in only)]:
        src = base.root / "02_facings" / f"{f}.png"
        if not src.exists():
            continue
        generate._run(client, job, "facing_multiref",
                      {"prompt": builder.edit_facing(f, edit, raised), "ref_images": [src],
                       "seed": generate._seed(seed)}, out / f"{f}.png")
        done.append(f)
    a = generate._rgba(a_path)
    report = {"variant_of": str(base.root), "edit": edit, "facings": {}, "mirrored": {}, "warnings": [],
              "diagonals": "from base"}
    for f in done:
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
