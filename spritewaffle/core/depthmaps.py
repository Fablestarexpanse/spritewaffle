"""Depth and normal maps for animation frames (Myth-style lighting test, docs/PLAN_DIRECTIONAL.md).

GPU: Depth Anything V2 (small, controlnet_aux node; Ronan approved the 99 MB download 2026-11-27)
runs on each frame's master (the full-size selected video frame) -> 03_actions/<f>/<a>/selected_<n>f/depth/.
CPU: the depth is cut to the sprite (the master's keyed alpha), scaled to 0..255 over the whole clip
(one range for every frame, so the light does not flicker), and normals come from its slopes. Both
are then put through each frame's recorded downscale (manifest.replay_downscale) so they line up
pixel for pixel with the colour frame, and written next to it as NNN_depth.png / NNN_normal.png
(the reserved slots the manifest and foot alignment already handle).

Conventions: depth bright = near the camera. Normal map OpenGL style (R = +x right, G = +y up,
B = toward the camera), the same as texture.surface_maps.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from . import alignment, manifest
from .job import Job

DEPTH_DIR = "depth"
STRENGTH = 4.0          # slope scale for normals (depth 0..1 over the sprite's height)


def _masters_dir(job: Job, facing: str, action: str, n: int) -> Path:
    return job.root / "03_actions" / facing / action / f"selected_{n}f"


def depth_path(master: Path) -> Path:
    return master.parent / DEPTH_DIR / master.name


def render(job: Job, facing: str, action: str, n: int, client=None, resolution: int = 1024) -> list[Path]:
    """Depth for every master of this frame set that has none yet (GPU). Mirrored views have no
    masters of their own; they use their source view's."""
    from ..comfy.client import ComfyClient
    client = client or ComfyClient()
    masters = sorted(_masters_dir(job, facing, action, n).glob("*.png"))
    if not masters:
        raise FileNotFoundError(f"no selected frames for {facing}/{action} {n}f (mirrored views use their source view)")
    made = []
    for m in masters:
        dest = depth_path(m)
        if dest.exists():
            continue
        dest.parent.mkdir(exist_ok=True)
        prov = client.run_template("depth_map", {"ref_images": [m], "width": resolution}, dest.parent / "_run")
        Image.open(prov["files"][0]).convert("L").resize(Image.open(m).size, Image.BILINEAR).save(dest)
        made.append(dest)
    return made


def _alpha(master: Path) -> np.ndarray:
    from ..pixel.pipeline import _ensure_rgba
    return _ensure_rgba(np.array(Image.open(master).convert("RGB")), 16, "all")[..., 3] > 0


def clip_range(depths: list[np.ndarray], masks: list[np.ndarray]) -> tuple[float, float]:
    """One depth range over every frame of a clip (sprite pixels only; 1st..99th percentile)."""
    vals = np.concatenate([d[m] for d, m in zip(depths, masks) if m.any()]) if any(m.any() for m in masks) else np.zeros(1)
    lo, hi = np.percentile(vals, 1), np.percentile(vals, 99)
    return float(lo), float(max(hi, lo + 1.0))


def maps_from_depth(depth: np.ndarray, mask: np.ndarray, rng: tuple[float, float],
                    strength: float = STRENGTH) -> tuple[np.ndarray, np.ndarray]:
    """(depth L 0..255, normal RGB) at master size; outside the sprite depth 0 and normal flat."""
    import cv2
    lo, hi = rng
    d = np.clip((depth.astype(float) - lo) / (hi - lo), 0, 1) * mask
    # slopes over the sprite only: fill the outside with a blur of the inside so the edge does not
    # read as a cliff, then smooth away the model's fine noise
    m = mask.astype(float)
    k = max(3, (int(0.02 * max(depth.shape)) | 1))
    fill = cv2.GaussianBlur(d, (k * 3 | 1, k * 3 | 1), 0) / np.maximum(cv2.GaussianBlur(m, (k * 3 | 1, k * 3 | 1), 0), 1e-6)
    h = cv2.GaussianBlur(np.where(mask, d, fill), (k, k), 0)
    ys, _ = np.where(mask)
    span = (ys.max() - ys.min() + 1) if len(ys) else depth.shape[0]
    gx = cv2.Sobel(h, cv2.CV_64F, 1, 0, ksize=3) / 8.0 * span
    gy = cv2.Sobel(h, cv2.CV_64F, 0, 1, ksize=3) / 8.0 * span
    # bright = near: nearer to the right -> the surface faces left (-x); image y runs down, so nearer
    # further down the image -> it faces up (+y)
    n = np.dstack([-gx * strength, gy * strength, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    n = np.where(mask[..., None], n, np.array([0.0, 0.0, 1.0]))
    normal = ((n * 0.5 + 0.5) * 255).round().astype(np.uint8)
    return (d * 255).round().astype(np.uint8), normal


def _flip_normals(rgba: np.ndarray) -> np.ndarray:
    out = rgba.copy()
    out[..., 0] = 255 - out[..., 0]
    return out


def _mirrored(rec: dict) -> bool:
    return rec.get("method") == "mirror" or bool(rec.get("flip"))


def build(job: Job, facing: str, action: str, n: int, strength: float = STRENGTH) -> dict:
    """Write NNN_depth.png / NNN_normal.png next to each colour frame of this frame set (CPU).
    Needs the masters' depth (render). Replaced or inserted frames get none (no master)."""
    from . import angles
    man = manifest.build(job)
    anim = next((a for a in man["animations"] if a["action"] == action and a["frame_set"] == f"{n}f"), None)
    if anim is None:
        raise FileNotFoundError(f"no pixel frames for {action} {n}f")
    yaw = angles.yaw_of(facing)
    frames = [f for f in anim["frames"] if f["yaw_degrees"] == yaw and f.get("master") and f.get("downscale")]
    if not frames:
        raise FileNotFoundError(f"no frames with a master for {facing}/{action} {n}f")
    masters = sorted({f["master"] for f in frames})
    depth, mask = {}, {}
    for m in masters:
        mp = job.root / m
        dp = depth_path(mp)
        if not dp.exists():
            raise FileNotFoundError(f"depth not rendered yet for {m} (run the depth render first)")
        depth[m], mask[m] = np.array(Image.open(dp).convert("L")).astype(float), _alpha(mp)
    rng = clip_range([depth[m] for m in masters], [mask[m] for m in masters])
    written, seen = [], set()
    for f in frames:
        colour = job.root / (f.get("color_unaligned") or f["color"])
        if colour in seen:
            continue
        seen.add(colour)
        mp = job.root / f["master"]
        d, nrm = maps_from_depth(depth[f["master"]], mask[f["master"]], rng, strength)
        master_rgb = np.array(Image.open(mp).convert("RGB"))
        rec = f["downscale"]
        dcell = manifest.replay_downscale(np.dstack([d, d, d]), rec, alpha_from=master_rgb, quantize=False)
        ncell = manifest.replay_downscale(nrm, rec, alpha_from=master_rgb, quantize=False)
        if _mirrored(rec):
            ncell = _flip_normals(ncell)
        Image.fromarray(dcell.astype(np.uint8), "RGBA").save(alignment.map_path(colour, "depth"))
        Image.fromarray(ncell.astype(np.uint8), "RGBA").save(alignment.map_path(colour, "normal"))
        written.append(colour.name)
    manifest.refresh(job)
    return {"facing": facing, "action": action, "frame_set": f"{n}f", "frames": len(written),
            "depth_range": [round(rng[0], 1), round(rng[1], 1)]}


def frame_sets(job: Job, facing: str, action: str) -> tuple[str, list[int]]:
    """(view whose masters are used, frame counts) for a pixelized facing/action; mirrored views use
    their source view's masters."""
    import json
    rp = job.root / "04_pixel" / facing / action / "pixel_report.json"
    if not rp.exists():
        raise FileNotFoundError(f"{facing}/{action} is not pixelized yet")
    rep = json.loads(rp.read_text(encoding="utf-8"))
    src = rep.get("source") if rep.get("method") == "mirror" else facing
    return src, sorted(int(n) for n in (rep.get("sets") or {}))


def make(job: Job, facing: str, action: str, client=None, strength: float = STRENGTH) -> dict:
    """Depth on the GPU (only masters without one) and both maps for every frame set of this
    facing/action."""
    src, sets = frame_sets(job, facing, action)
    rendered = sum(len(render(job, src, action, n, client)) for n in sets)
    built = [build(job, facing, action, n, strength) for n in sets]
    return {"facing": facing, "action": action, "rendered": rendered, "sets": built}
