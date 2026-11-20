"""Synthetic sprites/clips: a known pixel-art character, upscaled with blur + noise on #00FF00."""
from __future__ import annotations

import numpy as np
import cv2

PALETTE = [
    (24, 20, 37),     # 0 outline
    (232, 183, 150),  # 1 skin
    (44, 92, 196),    # 2 shirt
    (110, 70, 40),    # 3 pants
    (220, 30, 40),    # 4 red hat (small salient detail)
    (250, 250, 250),  # 5 eye (single pixel)
]


def draw_sprite(step: int = 0) -> np.ndarray:
    """16x24 label image, -1 = transparent. `step` swings the legs (0..3)."""
    L = np.full((24, 16), -1, int)
    L[2:4, 5:11] = 4                 # hat
    L[4:9, 5:11] = 1                 # head
    L[6, 9] = 5                      # eye
    L[9:16, 4:12] = 2                # torso
    L[9:14, 2:4] = 1; L[9:14, 12:14] = 1   # arms
    sw = [0, 1, 0, -1][step % 4]
    L[16:22, 5 + sw:8 + sw] = 3      # left leg
    L[16:22, 8 - sw:11 - sw] = 3     # right leg
    # 1px dark outline around everything
    opaque = L >= 0
    ring = cv2.dilate(opaque.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & ~opaque
    L[ring] = 0
    return L


def render(labels: np.ndarray, scale: int = 8, offset=(3, 5), canvas=(256, 256),
           blur: float = 1.0, noise: float = 4.0, seed: int = 0, bg=(0, 255, 0)) -> np.ndarray:
    """Upscale labels by `scale`, paste at (x, y) offset on a flat bg, blur, add noise -> RGB uint8."""
    h, w = labels.shape
    img = np.zeros((canvas[1], canvas[0], 3), np.float32)
    img[:] = bg
    big = np.repeat(np.repeat(labels, scale, 0), scale, 1)
    pal = np.array(PALETTE, np.float32)
    ox, oy = offset
    region = img[oy:oy + h * scale, ox:ox + w * scale]
    m = big >= 0
    region[m] = pal[big[m]]
    if blur > 0:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    rng = np.random.default_rng(seed)
    img += rng.normal(0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


def write_clip(path, frames: int = 48, fps: int = 24, scale: int = 8, canvas=(320, 320)) -> None:
    """Synthetic 'H3-like' clip: walking-in-place character, locked camera, green bg, mp4."""
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, canvas)
    for i in range(frames):
        lab = draw_sprite(step=i // 3)
        rgb = render(lab, scale=scale, offset=(96, 64), canvas=canvas, seed=i)
        vw.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    vw.release()
