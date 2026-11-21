"""Show-off GIFs for a sprite stack: a spin, and a build-up (slices stacking one by one, then a
spin). Same drawing as the in-app viewer: each slice rotated, optionally squashed vertically
("tilt": 1 = seen from straight above, ~0.5 = a typical sprite-stack game camera), stacked upward
by `layer_px`. Nearest-neighbour throughout, so pixel art stays crisp.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

BG = (21, 22, 34)


def load(stack_dir: Path, name: str) -> np.ndarray:
    """Slices (H, D, W, 4), bottom first, from <name>_slices.png + .json."""
    meta = json.loads((stack_dir / f"{name}_slices.json").read_text())
    strip = np.array(Image.open(stack_dir / f"{name}_slices.png").convert("RGBA"))
    W, D = meta["slice_size"]
    return np.stack([strip[:D, z * W:(z + 1) * W] for z in range(meta["slices"])])


def render(sl: np.ndarray, angle: float, layer_px: int = 1, tilt: float = 1.0, count: int | None = None,
           canvas: tuple[int, int] | None = None) -> np.ndarray:
    """One frame: the first `count` slices (all by default) at `angle` degrees."""
    H, D, W = sl.shape[:3]
    side = int(np.ceil(np.hypot(D, W))) + 2
    sq = max(1, round(side * tilt))
    cw, ch = canvas or (side, sq + H * layer_px + 2)
    out = np.zeros((ch, cw, 4), np.uint8)
    M = cv2.getRotationMatrix2D((W / 2, D / 2), angle, 1.0)
    M[:, 2] += (side / 2 - W / 2, side / 2 - D / 2)
    x0 = (cw - side) // 2
    for z in range(H if count is None else min(count, H)):
        rot = cv2.warpAffine(sl[z], M, (side, side), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(0, 0, 0, 0))
        if sq != side:
            rot = cv2.resize(rot, (side, sq), interpolation=cv2.INTER_NEAREST)
        y0 = ch - sq - z * layer_px - 1
        m = rot[..., 3] > 0
        region = out[y0:y0 + sq, x0:x0 + side]
        region[m] = rot[m]
    return out


def _save(frames: list[np.ndarray], path: Path, scale: int, ms: list[int]) -> Path:
    imgs = []
    for f in frames:
        bg = np.zeros_like(f)
        bg[..., :3] = BG
        bg[..., 3] = 255
        a = f[..., 3:] > 0
        comp = np.where(a, f, bg)[..., :3]
        im = Image.fromarray(np.ascontiguousarray(comp), "RGB").resize((f.shape[1] * scale, f.shape[0] * scale), Image.NEAREST)
        imgs.append(im.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    path.parent.mkdir(parents=True, exist_ok=True)
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms, loop=0, optimize=False, disposal=1)
    return path


def spin(sl: np.ndarray, path: Path, steps: int = 32, layer_px: int = 1, tilt: float = 0.6, scale: int = 4,
         ms: int = 60) -> dict:
    H, D, W = sl.shape[:3]
    side = int(np.ceil(np.hypot(D, W))) + 2
    canvas = (side + 8, max(1, round(side * tilt)) + H * layer_px + 8)
    frames = [render(sl, 360 * i / steps, layer_px, tilt, canvas=canvas) for i in range(steps)]
    _save(frames, path, scale, [ms] * steps)
    return {"file": str(path), "frames": steps, "seconds": round(steps * ms / 1000, 1)}


def build_up(sl: np.ndarray, path: Path, angle: float = 30, steps: int = 32, layer_px: int = 1, tilt: float = 0.6,
             scale: int = 4, ms: int = 60, hold_ms: int = 500) -> dict:
    """Slices land one by one at `angle`, a short hold, then one full spin."""
    H, D, W = sl.shape[:3]
    side = int(np.ceil(np.hypot(D, W))) + 2
    canvas = (side + 8, max(1, round(side * tilt)) + H * layer_px + 8)
    per = max(30, min(90, round(2400 / H)))                     # the build takes ~2.4 s whatever the height
    frames = [render(sl, angle, layer_px, tilt, count=k, canvas=canvas) for k in range(1, H + 1)]
    durs = [per] * H
    durs[-1] = hold_ms
    spin_frames = [render(sl, angle + 360 * i / steps, layer_px, tilt, canvas=canvas) for i in range(1, steps + 1)]
    frames += spin_frames
    durs += [ms] * steps
    durs[-1] = hold_ms
    _save(frames, path, scale, durs)
    return {"file": str(path), "frames": len(frames), "seconds": round(sum(durs) / 1000, 1)}
