"""Generation stages (Phase 2): anchor -> 4 cardinals -> diagonals -> mirror drifting facings.

Every output is written under the job folder with provenance (template, prompt, seed, refs).
"""
from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from ..comfy.client import ComfyClient
from ..frames import layout
from ..pixel import chroma
from ..pixel.color import srgb_to_oklab
from ..prompts import builder
from .job import Job
from .profile import GameProfile

MIRROR_OF = {"W": "E", "E": "W", "NW": "NE", "NE": "NW", "SW": "SE", "SE": "SW"}


def _seed(seed: int | None) -> int:
    return seed if seed is not None else random.randrange(2**31)


def _run(client: ComfyClient, job: Job, slot: str, values: dict, dest: Path) -> dict:
    tmp = dest.parent / f".{dest.stem}_tmp"
    prov = client.run_template(slot, values, tmp)
    src = Path(prov["files"][0])
    dest.parent.mkdir(parents=True, exist_ok=True)
    flatten_background(Image.open(src).convert("RGB"), dest)
    shutil.rmtree(tmp, ignore_errors=True)
    prov["files"] = [str(dest.relative_to(job.root))]
    prov["values"] = {k: (str(v) if isinstance(v, Path) else [str(x) for x in v] if isinstance(v, list) else v)
                      for k, v in prov["values"].items()}
    job.log_provenance(str(dest.relative_to(job.root)), **prov)
    return prov


def flatten_background(img: Image.Image, dest: Path) -> Path:
    """Rule 3: background becomes exact #00FF00. Edit models amplify an off-green background when a
    generated still is fed back as a reference (measured: speckled green noise), so every still is
    keyed and re-composited on pure green before it is saved or reused."""
    a = chroma.key(np.array(img), despill="all")
    out = np.where(a[..., 3:] > 0, a[..., :3], np.array([0, 255, 0], np.uint8)).astype(np.uint8)
    Image.fromarray(out).save(dest)
    return dest


# --- anchor ---------------------------------------------------------------------------------

def anchor(job: Job, profile: GameProfile, client: ComfyClient | None = None, description: str | None = None,
           image: str | Path | None = None, seed: int | None = None) -> Path:
    """Generate the anchor from a description, or import an existing image. Not approved yet."""
    dest = job.stage_dir("01_anchor") / "anchor.png"
    if image:
        flatten_background(Image.open(image).convert("RGB"), dest)
        job.log_provenance(str(dest.relative_to(job.root)), source=str(image))
    else:
        if not description:
            raise ValueError("anchor needs --describe or --image")
        _run(client or ComfyClient(), job, "anchor_still",
             {"prompt": builder.anchor(description, profile), "seed": _seed(seed)}, dest)
    job.update_inputs(description=description)
    job.set_stage("anchor", "review")
    return dest


def approve(job: Job, stage: str) -> None:
    meta = job.read_meta()
    if stage not in meta["stages"]:
        raise ValueError(f"stage {stage} has not run")
    job.set_stage(stage, "approved", **{k: v for k, v in meta["stages"][stage].items() if k not in ("status", "time")})


def _require_approved(job: Job, stage: str) -> None:
    st = job.read_meta()["stages"].get(stage, {}).get("status")
    if st != "approved":
        raise RuntimeError(f"stage '{stage}' is {st or 'missing'}; approve it first (rule 2: one approved anchor)")


# --- facings --------------------------------------------------------------------------------

def _rgba(path: Path) -> np.ndarray:
    return chroma.key(np.array(Image.open(path).convert("RGB")))


def drift(anchor_rgba: np.ndarray, rgba: np.ndarray, bins: int = 6) -> dict:
    """How far a facing strays from the anchor: colour-distribution distance (0..1, Oklab histogram
    of opaque pixels) and silhouette height ratio."""
    def hist(img):
        m = img[..., 3] > 0
        if not m.any():
            return np.zeros(bins ** 3), 0
        lab = srgb_to_oklab(img[m][:, :3].astype(float))
        lo, hi = np.array([0, -0.4, -0.4]), np.array([1, 0.4, 0.4])
        q = np.clip(((lab - lo) / (hi - lo) * bins).astype(int), 0, bins - 1)
        h = np.bincount(q[:, 0] * bins * bins + q[:, 1] * bins + q[:, 2], minlength=bins ** 3).astype(float)
        ys = np.where(m.any(1))[0]
        return h / h.sum(), ys[-1] - ys[0] + 1
    ha, la = hist(anchor_rgba)
    hb, lb = hist(rgba)
    return {"color": round(float(np.abs(ha - hb).sum() / 2), 3), "height_ratio": round(lb / la, 3) if la else 0.0}


def _drifted(d: dict, max_color: float, height_tol: float) -> bool:
    return d["color"] > max_color or abs(d["height_ratio"] - 1) > height_tol


def facings(job: Job, profile: GameProfile, client: ComfyClient | None = None, only: list[str] | None = None,
            seed: int | None = None, mirror: str = "auto", diagonals: str = "nearest",
            max_color: float = 0.35, height_tol: float = 0.12) -> dict:
    """Staged facings (rule 4): cardinals from the anchor, then diagonals from anchor + cardinals,
    then mirror any facing that drifted when its partner did not (code, not prompts)."""
    _require_approved(job, "anchor")
    client = client or ComfyClient()
    a_path = job.root / "01_anchor" / "anchor.png"
    out = job.stage_dir("02_facings")
    flatten_background(Image.open(a_path).convert("RGB"), out / "S.png")   # the approved anchor IS the S facing
    want = [f for f in (builder.CARDINALS + builder.DIAGONALS)[: 4 if profile.directions == 4 else 8]]
    todo = [f for f in want if f != "S" and (not only or f in only)]
    report = {"diagonals": diagonals, "facings": {}, "mirrored": {}, "warnings": []}

    for f in [x for x in todo if x in builder.CARDINALS] + [x for x in todo if x in builder.DIAGONALS]:
        if f in builder.DIAGONALS and diagonals == "nearest":
            first, refs = builder.DIAGONAL_NEAREST[f], []
        else:
            first, refs = "S", list(builder.DIAGONAL_REFS.get(f, ()))
        missing = [r for r in [first] + refs if not (out / f"{r}.png").exists()]
        if missing:
            raise RuntimeError(f"{f} needs cardinals {missing} first")
        imgs = [out / f"{first}.png"] + [out / f"{r}.png" for r in refs]
        _run(client, job, "facing_multiref",
             {"prompt": builder.facing(f, refs, first), "ref_images": imgs, "seed": _seed(seed)}, out / f"{f}.png")

    a = _rgba(a_path)
    asym = layout.asymmetry(a)
    if asym["asymmetric"]:
        report["warnings"].append(f"anchor is asymmetric ({asym}); mirrored facings will flip that detail")
    for f in want:
        p = out / f"{f}.png"
        if p.exists():
            report["facings"][f] = drift(a, _rgba(p))

    if mirror == "auto" and profile.mirror_allowed:
        for f, d in list(report["facings"].items()):
            partner = MIRROR_OF.get(f)
            pd = report["facings"].get(partner)
            if partner and pd and _drifted(d, max_color, height_tol) and not _drifted(pd, max_color, height_tol):
                img = Image.open(out / f"{partner}.png")
                img.transpose(Image.FLIP_LEFT_RIGHT).save(out / f"{f}.png")
                report["mirrored"][f] = {"from": partner, "drift_before": d}
                report["facings"][f] = drift(a, _rgba(out / f"{f}.png"))
                job.log_provenance(f"02_facings/{f}.png", mirrored_from=partner, reason="drift", drift=d)
    for f, d in report["facings"].items():
        if _drifted(d, max_color, height_tol):
            report["warnings"].append(f"{f} still drifts from the anchor {d}: re-roll it")

    (out / "facings_report.json").write_text(json.dumps(report, indent=2))
    sheet = [np.array(Image.open(out / f"{f}.png").convert("RGB")) for f in want if (out / f"{f}.png").exists()]
    from ..frames import contact
    contact.write(sheet, out / "facings_sheet.png", labels=[f for f in want if (out / f"{f}.png").exists()],
                  cols=4, cell=256)
    job.set_stage("facings", "review", mirrored=list(report["mirrored"]), warnings=report["warnings"])
    return report
