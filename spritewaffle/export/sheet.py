"""PNG strip + per-frame PNGs + sheet.json + GIF/APNG previews for one animation."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


def feet_pivot(frames: np.ndarray) -> list[int]:
    """Bottom-centre of the union opaque bbox across all frames: [x, y] in cell pixels."""
    a = (frames[..., 3] > 0).any(0)
    if not a.any():
        h, w = a.shape
        return [w // 2, h]
    ys, xs = np.where(a)
    return [int((xs.min() + xs.max() + 1) // 2), int(ys.max() + 1)]


def _preview(frames: np.ndarray, scale: int) -> list[Image.Image]:
    return [Image.fromarray(f, "RGBA").resize((f.shape[1] * scale, f.shape[0] * scale), Image.NEAREST)
            for f in frames]


def export_png(out_dir, name: str, frames: np.ndarray, fps: int, loop: bool = True,
               events: list | dict | None = None, hitboxes: dict | None = None, preview_scale: int = 4,
               pivot=None, durations_ms: list[int] | None = None, frame_ids: list[str] | None = None,
               *, playback_range: list[int] | None = None, preview_once: bool = False) -> dict:
    """frames (F,h,w,4) uint8 cells -> files. Returns {'strip','json','gif','apng','frames'} paths."""
    out = Path(out_dir)
    (out / "frames").mkdir(parents=True, exist_ok=True)
    n, h, w = frames.shape[:3]
    strip = np.concatenate(list(frames), axis=1)
    paths = {"strip": out / f"{name}.png", "json": out / f"{name}.json",
             "gif": out / f"{name}_preview.gif", "apng": out / f"{name}_preview.png"}
    Image.fromarray(strip, "RGBA").save(paths["strip"])
    frame_paths = []
    for i, f in enumerate(frames):
        p = out / "frames" / f"{name}_{i:03d}.png"
        Image.fromarray(f, "RGBA").save(p)
        frame_paths.append(p)
    paths["frames"] = frame_paths

    dur = round(1000 / fps)
    durations = durations_ms if durations_ms is not None else [dur] * n
    meta = {
        "name": name, "cell": [w, h], "frame_count": n, "fps": fps, "loop": loop,
        "pivot": list(pivot) if pivot is not None else feet_pivot(frames), "pivot_norm": None,
        "frames": [{"index": i, "rect": [i * w, 0, w, h], "duration_ms": durations[i],
                    **({"frame_id": frame_ids[i]} if frame_ids else {}),
                    **({"hitbox": hitboxes[i]} if hitboxes and i in hitboxes else {})} for i in range(n)],
        "events": events or [],
    }
    meta["pivot_norm"] = [meta["pivot"][0] / w, 1 - meta["pivot"][1] / h]   # Unity: origin bottom-left
    if playback_range is not None:
        meta["playback_range"] = playback_range
    paths["json"].write_text(json.dumps(meta, indent=2), encoding="utf-8")

    start, end = playback_range if playback_range is not None else (0, n - 1)
    imgs = _preview(frames[start:end + 1], preview_scale)
    preview_duration = dur if durations_ms is None else durations[start:end + 1]
    imgs[0].save(paths["apng"], save_all=True, append_images=imgs[1:], duration=preview_duration,
                 loop=1 if preview_once else 0, disposal=1)
    gif_frames = [_gif_frame(im) for im in imgs]
    gif_loop = {} if preview_once else {"loop": 0}
    gif_frames[0].save(paths["gif"], save_all=True, append_images=gif_frames[1:], duration=preview_duration,
                       disposal=2, transparency=255, optimize=False, **gif_loop)
    return paths


def _gif_frame(im: Image.Image) -> Image.Image:
    """RGBA -> P with index 255 reserved for transparency (exact colours for <=255-colour art)."""
    a = np.array(im)
    p = im.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    idx = np.array(p)
    idx[a[..., 3] == 0] = 255
    out = Image.fromarray(idx, "P")
    pal = p.getpalette()[:765] + [0, 0, 0]
    out.putpalette(pal)
    out.info["transparency"] = 255
    return out
