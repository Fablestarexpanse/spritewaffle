"""Visual effects as their own sprites: spells, fire, explosions, impacts, auras.

Measured 2026-11-20 (H3, seed 7, 48 frames): on a pure black background H3 keeps the background
black (99.9th percentile of the border = 0) and draws clean pixel-art effects; a fireball loops,
an explosion goes spark -> burst -> smoke -> empty black, healing sparkles twinkle.

Two backgrounds:
- black (default; glowing things): alpha from brightness. The result works with normal alpha
  blending and, because empty areas stay black, with additive blending too.
- green (effects with dark parts: smoke, dust, debris): dark smoke can't be told apart from a black
  background, so it is keyed like a character instead.

Frames: one-shots keep the whole active part (first to last frame with content); loops skip the
start (the clip settling in from the still) and use the window whose last frame best matches its
first. One scale for the whole effect: its largest frame fits the requested size.
"""
from __future__ import annotations

import json
import math

import cv2
import numpy as np
from PIL import Image

from ..comfy.client import ComfyClient
from ..frames import video
from ..pixel import chroma
from ..prompts import effects as fx
from ..prompts import styles
from .job import Job

H3_FPS = 24


def spec(job: Job) -> dict:
    """The effect's settings from the job (preset values filled in)."""
    i = job.read_meta()["inputs"]
    p = fx.PRESETS.get((i.get("preset") or "").lower(), {})
    return {"name": i.get("effect_name") or i.get("preset") or job.read_meta()["character"],
            "still": i.get("still") or p.get("still") or i.get("description") or "",
            "motion": i.get("motion") or p.get("motion") or "",
            "sound": i.get("sound") or p.get("sound", ""),
            "loop": bool(i["loop"]) if i.get("loop") is not None else p.get("loop", True),
            "start_small": bool(i.get("start_small", p.get("start_small", False))),
            "bg": i.get("bg") or ("green" if p.get("green") else "black"),
            "seconds": float(i.get("seconds") or 2.0),
            "size": int(i.get("size") or 64), "frames": int(i.get("frame_count") or (12 if p.get("loop", True) else 16)),
            "fps": int(i.get("fps") or 12), "colours": int(i.get("colours") or 16)}


# --- render (GPU) ------------------------------------------------------------------------------
def render(job: Job, client: ComfyClient | None = None, seed: int | None = None) -> dict:
    """First frame (H3 Image) then the clip (H3 image-to-video), both on the chosen background."""
    from . import generate
    styles.use(styles.of_job(job))
    s = spec(job)
    if not s["still"] or not s["motion"]:
        raise ValueError("describe the effect (first frame) and what it does (motion), or pick a preset")
    client = client or ComfyClient()
    still_text = (fx.still_green if s["bg"] == "green" else fx.still)(s["still"], s["start_small"])
    dest = job.stage_dir("01_anchor") / "anchor.png"
    seed = generate._seed(seed)
    prov = client.run_template("anchor_still", {"prompt": still_text, "seed": seed}, dest.parent / ".still_tmp")
    from . import takes
    takes.stash(job, dest)
    Image.open(prov["files"][0]).convert("RGB").save(dest)
    job.log_provenance("01_anchor/anchor.png", template="anchor_still", values={"prompt": still_text, "seed": seed})
    clip = job.action_dir("S", "effect") / "raw.mp4"
    vtext = fx.video(s["motion"], s["sound"], s["seconds"])
    if s["bg"] == "green":
        vtext = vtext.replace("The flat pure black #000000 background", "The flat #00FF00 background")
    generate._run_video(client, job, "h3_action_i2v",
                        {"prompt": vtext, "first_frame": dest, "frames": round(s["seconds"] * H3_FPS), "seed": seed}, clip)
    job.set_stage("effect:render", "done", seed=seed)
    return {"still": str(dest), "clip": str(clip), "seed": seed}


# --- process (CPU) -----------------------------------------------------------------------------
def luma_key(rgb: np.ndarray, lo: int = 10, soft: bool = True) -> np.ndarray:
    """RGB on black -> RGBA. alpha from the brightest channel; colours un-premultiplied for soft
    alpha (so normal blending reproduces the look), kept as-is for hard alpha."""
    v = rgb.max(-1).astype(np.float32)
    a = np.clip((v - lo) / (255 - lo), 0, 1)
    if soft:
        col = np.where(a[..., None] > 0, np.clip(rgb.astype(np.float32) / np.maximum(v[..., None], 1) * 255, 0, 255), 0)
        return np.dstack([col.astype(np.uint8), (a * 255).astype(np.uint8)])
    return np.dstack([rgb, np.where(v > lo * 4, 255, 0).astype(np.uint8)])


def detect_bg(frame: np.ndarray) -> str:
    """What the clip's background really is: the median of the frame border. Measured 2026-11-21:
    a 'spinning shield' asked for on green came out on black (glow wording pulls toward black), and
    keying it as green left an opaque black box around every frame."""
    b = np.concatenate([frame[:8].reshape(-1, 3), frame[-8:].reshape(-1, 3), frame[:, :8].reshape(-1, 3),
                        frame[:, -8:].reshape(-1, 3)])
    r, g, bl = np.median(b, 0)
    if g > 150 and r < 120 and bl < 120:
        return "green"
    if max(r, g, bl) < 40:
        # H3 sometimes draws the asked-for green as a flat card on a black frame (measured: the
        # spinning shield) -> key both
        pure = (frame[..., 1] > 200) & (frame[..., 0] < 80) & (frame[..., 2] < 80)
        return "black+green" if pure.mean() > 0.05 else "black"
    raise ValueError(f"the clip's background is neither black nor green (border median {int(r)},{int(g)},{int(bl)}); re-render")


def key_frames(frames: list[np.ndarray], bg: str, soft: bool) -> list[np.ndarray]:
    if bg == "green":
        return [chroma.remove_specks(chroma.key(f, despill="all"), 16) for f in frames]
    if bg == "black+green":
        out = []
        for f in frames:
            g = chroma.key(f, despill="all")                        # green card -> transparent
            lk = luma_key(f, soft=soft)                             # black frame -> transparent
            a = np.minimum(g[..., 3], lk[..., 3])
            out.append(chroma.remove_specks(np.dstack([g[..., :3], a]), 16))
        return out
    return [luma_key(f, soft=soft) for f in frames]


def pick(rgba: list[np.ndarray], loop: bool, count: int) -> tuple[list[int], dict]:
    """Indices of the frames to keep."""
    mass = np.array([float((f[..., 3] > 32).sum()) for f in rgba])
    live = np.where(mass > 0.02 * max(mass.max(), 1))[0]
    if not len(live):
        raise ValueError("the clip is empty: nothing visible on the background")
    if not loop:
        a, b = int(live[0]), int(live[-1])
        return list(np.linspace(a, b, count).round().astype(int)), {"start": a, "end": b, "kind": "one-shot"}
    n = len(rgba)
    lo = max(int(live[0]), n // 6)                              # skip the still settling into motion
    small = [cv2.resize(f, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32) for f in rgba]
    # a loop shorter than ~1 s barely moves on slow effects (measured: magic circle picked a 12-frame
    # window, 0.5 s, and looked static), so windows are at least 24 source frames when the clip allows
    min_len = min(24, max(8, n - lo - 1))
    best = None
    for i in range(lo, n - min_len):
        for j in range(i + min_len, n):
            d = float(np.abs(small[i] - small[j]).mean()) - 0.02 * (j - i)     # prefer longer windows a little
            if best is None or d < best[0]:
                best = (d, i, j)
    _, i, j = best
    idx = list(np.linspace(i, j, count, endpoint=False).round().astype(int))
    return idx, {"start": i, "end": j, "kind": "loop", "seam": round(float(np.abs(small[i] - small[j]).mean()), 2)}


def _union_box(rgba: list[np.ndarray]) -> tuple[int, int, int, int]:
    m = np.zeros(rgba[0].shape[:2], bool)
    for f in rgba:
        m |= f[..., 3] > 32
    ys, xs = np.where(m)
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def process(job: Job, profile=None) -> dict:
    """Clip -> keyed, picked, scaled frames -> 06_export/effect/<name>/."""
    styles.use(styles.of_job(job))
    st = styles.get(styles.of_job(job))
    pixel = st["post"] == "pixel"
    s = spec(job)
    clip = job.action_dir("S", "effect") / "raw.mp4"
    if not clip.exists():
        raise FileNotFoundError("render the effect first")
    frames = video.read_frames(clip)
    bg = detect_bg(frames[0])                                    # key what was drawn, not what was asked
    rgba = key_frames(frames, bg, soft=not pixel)
    idx, info = pick(rgba, s["loop"], s["frames"])
    chosen = [rgba[i] for i in idx]
    x0, y0, x1, y1 = _union_box(chosen)
    pad = 2
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(chosen[0].shape[1], x1 + pad), min(chosen[0].shape[0], y1 + pad)
    crop = [f[y0:y1, x0:x1] for f in chosen]
    size = s["size"] * (1 if pixel else st.get("scale", 4))
    k = size / max(y1 - y0, x1 - x0)                              # the largest frame fits `size`
    if pixel:
        from ..pixel.pipeline import PixelParams, pixelize
        res = pixelize(crop, PixelParams(palette=s["colours"], pixel_size=max(1, round(1 / k)), outline="none",
                                         loop=s["loop"], despill="all"))
        out_frames = [res.rgba(i) for i in range(len(crop))]
        palette = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in res.palette.tolist()]
    else:
        w, h = max(1, round(crop[0].shape[1] * k)), max(1, round(crop[0].shape[0] * k))
        out_frames = []
        for f in crop:
            a = f[..., 3:].astype(np.float32) / 255
            pm = cv2.resize(np.dstack([f[..., :3] * a, a * 255]).astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)
            al = pm[..., 3:] / 255
            col = np.where(al > 0, pm[..., :3] / np.maximum(al, 1e-6), 0)
            out_frames.append(np.dstack([np.clip(col, 0, 255), np.clip(pm[..., 3:], 0, 255)]).astype(np.uint8))
        palette = []
    s = s | {"bg": bg}
    return export(job, s, out_frames, info | {"source_frames": [int(i) for i in idx], "background_detected": bg,
                                              "background_asked": spec(job)["bg"]}, pixel, palette)


def export(job: Job, s: dict, frames: list[np.ndarray], info: dict, pixel: bool, palette: list[str]) -> dict:
    from ..export import aseprite
    name = s["name"].replace(" ", "_")
    out = job.stage_dir("06_export") / "effect" / name
    (out / "frames").mkdir(parents=True, exist_ok=True)
    for old in (out / "frames").glob("*.png"):
        old.unlink()
    h, w = frames[0].shape[:2]
    for i, f in enumerate(frames):
        Image.fromarray(f, "RGBA").save(out / "frames" / f"{name}_{i:03d}.png")
    Image.fromarray(np.concatenate(frames, 1), "RGBA").save(out / f"{name}.png")
    cols = math.ceil(math.sqrt(len(frames)))
    rows = math.ceil(len(frames) / cols)
    sheet = np.zeros((rows * h, cols * w, 4), np.uint8)
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        sheet[r * h:(r + 1) * h, c * w:(c + 1) * w] = f
    Image.fromarray(sheet, "RGBA").save(out / f"{name}_sheet.png")
    dur = round(1000 / s["fps"])
    aseprite.write_rgba(out / f"{name}.aseprite", np.stack(frames), [dur] * len(frames),
                        tags=[(name, 0, len(frames) - 1, "forward", 0 if s["loop"] else 1)])
    scale = 4 if pixel else 1
    gif = []
    for f in frames:
        bg = np.zeros((h, w, 3), np.float32) + (18, 18, 26)
        a = f[..., 3:].astype(np.float32) / 255
        comp = (f[..., :3] * a + bg * (1 - a)).astype(np.uint8)
        gif.append(Image.fromarray(comp).resize((w * scale, h * scale), Image.NEAREST if pixel else Image.LANCZOS))
    gif[0].save(out / f"{name}_preview.gif", save_all=True, append_images=gif[1:], duration=dur, loop=0)
    meta = {"name": name, "frames": len(frames), "fps": s["fps"], "loop": s["loop"], "cell": [w, h],
            "sheet": {"image": f"{name}_sheet.png", "cols": cols, "rows": rows},
            "strip": f"{name}.png", "background": s["bg"],
            "blend": "alpha or additive" if s["bg"] == "black" else "alpha",
            "palette": palette, "pick": info}
    (out / f"{name}.json").write_text(json.dumps(meta, indent=2))
    job.set_stage("effect:export", "done", frames=len(frames), cell=[w, h], loop=s["loop"])
    return meta | {"dir": str(out)}
