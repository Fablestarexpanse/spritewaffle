"""Showcase GIF for showing a character to people: a turnaround through its facings, then every
saved action with all its facings playing at once in a compass grid. One scale and one foot line
throughout; pixel art scaled with nearest neighbour, other styles smoothly.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..pixel import chroma

TURN = ("S", "SE", "E", "NE", "N", "NW", "W", "SW")
COMPASS = ("NW", "N", "NE", "W", None, "E", "SW", "S", "SE")
BG = (21, 22, 34)
CELL_BG = (31, 33, 48)
TEXT = (235, 235, 240)
MUTED = (150, 154, 170)
ACCENT = (242, 179, 61)


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                   # very old Pillow
        return ImageFont.load_default()


def _trim(rgba: np.ndarray) -> np.ndarray:
    ys, xs = np.where(rgba[..., 3] > 0)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else rgba


def _load_anim(sd: Path) -> list[np.ndarray]:
    from ..frames.video import colour_frames
    return [np.array(Image.open(p).convert("RGBA")) for p in colour_frames(sd / "frames")]


def collect(job_root: Path, frame_set: str = "12f") -> dict:
    """What the job has: facing stills (sprite cut from its canvas) and pixelized animations."""
    stills = {}
    for f in TURN:
        p = job_root / "02_facings" / f"{f}.png"
        if p.exists():
            stills[f] = _trim(chroma.crop_sprite(np.array(Image.open(p).convert("RGB"))))
    anims: dict[str, dict[str, dict]] = {}
    for sd in sorted((job_root / "04_pixel").glob(f"*/*/{frame_set}")):
        facing, action = sd.parent.parent.name, sd.parent.name
        frames = _load_anim(sd)
        if frames:
            anims.setdefault(action, {})[facing] = {"frames": frames}
    return {"stills": stills, "anims": anims}


def _scaler(smooth: bool):
    return Image.LANCZOS if smooth else Image.NEAREST


def _paste(canvas: Image.Image, sprite: np.ndarray, box: tuple[int, int, int, int], scale: float, smooth: bool,
           foot_y: int | None = None) -> None:
    """Draw a sprite (RGBA, already trimmed or a full cell) centred in box, feet on foot_y."""
    im = Image.fromarray(sprite, "RGBA")
    w, h = max(1, round(im.width * scale)), max(1, round(im.height * scale))
    im = im.resize((w, h), _scaler(smooth))
    x0, y0, x1, y1 = box
    x = x0 + (x1 - x0 - w) // 2
    y = (foot_y - h) if foot_y is not None else y0 + (y1 - y0 - h) // 2
    canvas.alpha_composite(im, (x, y))


def build(job_root: Path, out: Path, title: str, smooth: bool, size: int = 512, frame_set: str = "12f",
          fps: int = 12, turn_hold_ms: int = 350, loops: int = 2) -> dict:
    """Write the showcase GIF. Returns a summary (sections, frame count, duration)."""
    data = collect(Path(job_root), frame_set)
    stills, anims = data["stills"], data["anims"]
    if not stills and not anims:
        raise RuntimeError("nothing to show yet: no facings and no animations")
    head = 44                                            # title bar
    frames: list[Image.Image] = []
    durations: list[int] = []
    sections = []

    def base(caption: str, sub: str = "") -> Image.Image:
        c = Image.new("RGBA", (size, size), BG + (255,))
        d = ImageDraw.Draw(c)
        d.text((14, 10), title, fill=TEXT, font=_font(20))
        d.text((size - 14, 14), caption, fill=ACCENT, font=_font(16), anchor="ra")
        if sub:
            d.text((size // 2, size - 12), sub, fill=MUTED, font=_font(14), anchor="ms")
        return c

    # 1. turnaround: facing stills, large, one scale, one foot line
    if stills:
        tallest = max(s.shape[0] for s in stills.values())
        widest = max(s.shape[1] for s in stills.values())
        area = (20, head + 6, size - 20, size - 30)
        scale = min((area[3] - area[1]) / tallest, (area[2] - area[0]) / widest)
        if not smooth and scale >= 1:
            scale = int(scale)                           # crisp pixel art: whole-number zoom
        order = [f for f in TURN if f in stills]
        for rnd in range(2):
            for f in order:
                c = base("turnaround", f"facing {f}")
                _paste(c, stills[f], area, scale, smooth, foot_y=area[3])
                frames.append(c)
                durations.append(turn_hold_ms)
        sections.append({"section": "turnaround", "facings": order})

    # 2. every action: all facings play together in a compass grid
    for action in sorted(anims):
        by_f = anims[action]
        n = max(len(v["frames"]) for v in by_f.values())
        cell = (size - 16) // 3
        grid_top = head + 2
        cell_h = (size - grid_top - 22) // 3
        trimmed = [_trim(fr) for v in by_f.values() for fr in v["frames"]]
        tallest = max(t.shape[0] for t in trimmed)
        widest = max(t.shape[1] for t in trimmed)
        scale = min((cell_h - 18) / tallest, (cell - 10) / widest)
        if not smooth and scale >= 1:
            scale = int(scale)
        crop_box = _union_box([fr for v in by_f.values() for fr in v["frames"]])
        for loop in range(loops):
            for i in range(n):
                c = base(action, f"{len(by_f)} facing{'s' if len(by_f) != 1 else ''} · {n} frames")
                d = ImageDraw.Draw(c)
                for k, f in enumerate(COMPASS):
                    r, q = divmod(k, 3)
                    x0, y0 = 8 + q * cell, grid_top + r * cell_h
                    box = (x0 + 3, y0 + 3, x0 + cell - 3, y0 + cell_h - 3)
                    d.rounded_rectangle(box, 6, fill=CELL_BG)
                    if f is None:
                        d.text(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2), action, fill=MUTED,
                               font=_font(14), anchor="mm")
                        continue
                    d.text((box[0] + 6, box[1] + 4), f, fill=MUTED, font=_font(12))
                    if f in by_f:
                        fr = by_f[f]["frames"]
                        sprite = fr[i % len(fr)][crop_box[1]:crop_box[3], crop_box[0]:crop_box[2]]
                        _paste(c, sprite, box, scale, smooth, foot_y=box[3] - 6)
                    elif f in stills:                    # facing without this action: show it standing, dimmed
                        st = stills[f].copy()
                        st[..., 3] = (st[..., 3] * 0.35).astype(np.uint8)
                        s2 = tallest * scale / st.shape[0]          # same drawn height as the animation
                        _paste(c, st, box, s2, smooth, foot_y=box[3] - 6)
                frames.append(c)
                durations.append(round(1000 / fps))
        sections.append({"section": action, "facings": [f for f in TURN if f in by_f], "frames": n})

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rgb = [f.convert("RGB") for f in frames]
    pal = [im.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE if not smooth
                       else Image.Dither.FLOYDSTEINBERG) for im in rgb]
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=False, disposal=1)
    summary = {"file": str(out), "size": size, "frames": len(frames), "seconds": round(sum(durations) / 1000, 1),
               "sections": sections}
    out.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    return summary


def for_job(job, profile, size: int = 512, frame_set: str = "12f") -> dict:
    """Build <job>/06_export/showcase/<character>_showcase.gif with the job's title, style and fps."""
    from ..prompts import styles
    meta = job.read_meta()
    smooth = styles.get(styles.of_job(job))["post"] != "pixel"
    title = meta["character"].replace("_", " ").title()
    walk_fps = profile.fps("walk")
    out = job.stage_dir("06_export") / "showcase" / f"{meta['character']}_showcase.gif"
    summary = build(job.root, out, title, smooth=smooth, size=size, frame_set=frame_set, fps=walk_fps)
    job.set_stage("export:showcase", "done", frames=summary["frames"], seconds=summary["seconds"])
    return summary


def _union_box(frames: list[np.ndarray]) -> tuple[int, int, int, int]:
    """One crop for every frame of an action (cells are laid out with preserve-canvas already)."""
    m = np.zeros(frames[0].shape[:2], bool)
    for f in frames:
        if f.shape[:2] == m.shape:
            m |= f[..., 3] > 0
    ys, xs = np.where(m)
    if not len(ys):
        return 0, 0, m.shape[1], m.shape[0]
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
