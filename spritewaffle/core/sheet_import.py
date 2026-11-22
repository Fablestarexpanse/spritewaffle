"""Import your own character sheet (several views side by side, any background) as a job's anchor
and facings, instead of generating them.

SAM 3 (ComfyUI, `sam3_mask` template) segments the figures — measured on a hand-drawn sheet on
parchment: colour keying ate the beige bandages and kept the parchment between the legs, SAM 3 cut
every view cleanly. Views are split left to right, scaled by ONE factor (relative sizes kept), and
placed on exact #00FF00 2048² canvases with a common foot line at ~45% of the height (rule 3).
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..comfy.client import ComfyClient
from .job import Job

CANVAS = 2048
MIRROR = {"W": "E", "SW": "SE", "NW": "NE", "E": "W", "SE": "SW", "NE": "NW"}


def segment(sheet: Path, n: int, subject: str, client: ComfyClient, work: Path) -> np.ndarray:
    """Union mask (H, W) bool of the n figures on the sheet."""
    prov = client.run_template("sam3_mask", {"prompt": f"{subject}:{n}", "ref_images": [Path(sheet)]}, work)
    return np.array(Image.open(prov["files"][0]).convert("L")) > 127


def split(img: np.ndarray, mask: np.ndarray, n: int) -> list[np.ndarray]:
    """The n largest mask regions, left to right, as RGBA crops (soft 1-px edge)."""
    k, lab, st, cen = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if k - 1 < n:
        raise ValueError(f"found {k - 1} figures on the sheet, expected {n}")
    big = sorted(range(1, k), key=lambda i: -st[i, cv2.CC_STAT_AREA])[:n]
    big.sort(key=lambda i: cen[i][0])
    alpha_full = cv2.GaussianBlur(mask.astype(np.float32), (3, 3), 0.6)
    out = []
    for i in big:
        x, y, w, h = (int(st[i, j]) for j in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
        own = (lab[y:y + h, x:x + w] == i)
        own = cv2.dilate(own.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        a = np.where(own, alpha_full[y:y + h, x:x + w], 0)
        out.append(np.dstack([img[y:y + h, x:x + w], (a * 255).astype(np.uint8)]))
    return out


def place_all(views: list[np.ndarray], height_frac: float = 0.45) -> list[np.ndarray]:
    """Same scale for every view; centred; common foot line. Returns RGB canvases on #00FF00."""
    k = CANVAS * height_frac / max(v.shape[0] for v in views)
    foot = int(CANVAS * (0.5 + height_frac / 2))
    out = []
    for v in views:
        w, h = max(1, round(v.shape[1] * k)), max(1, round(v.shape[0] * k))
        v = cv2.resize(v, (w, h), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LANCZOS4)
        canvas = np.zeros((CANVAS, CANVAS, 3), np.float32)
        canvas[:] = (0, 255, 0)
        x0, y0 = (CANVAS - w) // 2, foot - h
        a = v[..., 3:4].astype(np.float32) / 255
        region = canvas[y0:y0 + h, x0:x0 + w]
        region[:] = region * (1 - a) + v[..., :3].astype(np.float32) * a
        out.append(np.clip(canvas, 0, 255).astype(np.uint8))
    return out


def import_sheet(job: Job, sheet: str | Path, views: list[str], subject: str = "character",
                 client: ComfyClient | None = None, mirror: bool = True) -> dict:
    """views: facing of each figure left to right, e.g. ["S", "SE", "E", "N"]. "S" becomes the
    anchor. With mirror=True, missing W/SW/NW are flipped from E/SE/NE. Stages are left in
    'review' for the human to approve."""
    from ..prompts.builder import VIEW
    bad = [v for v in views if v not in VIEW]
    if bad or len(set(views)) != len(views):
        raise ValueError(f"views must be distinct facings from {list(VIEW)}; got {views}")
    if "S" not in views:
        raise ValueError("one of the views must be the front (S): it becomes the anchor")
    sheet = Path(sheet)
    if not sheet.exists():
        raise FileNotFoundError(sheet)
    client = client or ComfyClient()
    work = job.stage_dir("01_anchor") / "sheet"
    work.mkdir(parents=True, exist_ok=True)
    img = np.array(Image.open(sheet).convert("RGB"))
    Image.fromarray(img).save(work / "source.png")
    mask = segment(work / "source.png", len(views), subject, client, work / "sam3")
    Image.fromarray((mask * 255).astype(np.uint8)).save(work / "mask.png")
    placed = dict(zip(views, place_all(split(img, mask, len(views)))))
    if mirror:
        for target, src in MIRROR.items():
            if target not in placed and src in placed and target in ("W", "SW", "NW"):
                placed[target] = np.ascontiguousarray(placed[src][:, ::-1])
    from . import takes
    takes.stash(job, job.stage_dir("01_anchor") / "anchor.png")
    Image.fromarray(placed["S"]).save(job.stage_dir("01_anchor") / "anchor.png")
    fdir = job.stage_dir("02_facings")
    for f, im in placed.items():
        takes.stash(job, fdir / f"{f}.png")
        Image.fromarray(im).save(fdir / f"{f}.png")
    mirrored = sorted(set(placed) - set(views))
    missing = [f for f in VIEW if f not in placed]
    (fdir / "facings_report.json").write_text(json.dumps(
        {"source": "sheet", "facings": {}, "mirrored": {f: {"from": MIRROR[f]} for f in mirrored},
         "warnings": [], "diagonals": "sheet"}, indent=2))
    with job.mutate() as meta:
        meta["inputs"].update(sheet=str(sheet), sheet_views=views)
        meta["inputs"].pop("project_reference_id", None)
    job.log_provenance("01_anchor/anchor.png", source=str(sheet), method="sheet import (SAM 3)", views=views,
                       mirrored=mirrored)
    job.set_stage("anchor", "review", source="sheet")
    job.set_stage("facings", "review", source="sheet", from_sheet=views, mirrored=mirrored, missing=missing)
    return {"views": views, "mirrored": mirrored, "missing": missing, "mask_coverage": round(float(mask.mean()), 3)}
