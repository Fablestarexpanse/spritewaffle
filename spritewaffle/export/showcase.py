"""Showcase GIF for showing a character to people: a turnaround through its facings, then every
saved action with all its facings playing at once in a compass grid, then a SpriteWaffle end card.
One scale and one foot line throughout; pixel art scaled with nearest neighbour, other styles smoothly.

Branded 2026-11-26 (Ronan: "make sure it's branded properly and cleanly"): the app's own colours
(docs/branding: deep purple, purple, gold, cream are fixed), the app icon in the header and in the
centre of every compass grid, a "Made with SpriteWaffle" wordmark, and the horizontal logo on the
end card. The turnaround shows the game sprite (first frame of an animation, idle first) when the
job has animations, so it matches the clips instead of the full-size source painting.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..pixel import chroma

TURN = ("S", "SE", "E", "NE", "N", "NW", "W", "SW")
COMPASS = ("NW", "N", "NE", "W", None, "E", "SW", "S", "SE")
BG = (19, 13, 30)              # app --bg
CELL_BG = (29, 20, 41)         # app --panel
LINE = (73, 57, 86)            # app --line
TEXT = (255, 241, 208)         # brand cream
MUTED = (193, 178, 204)        # app --muted
ACCENT = (255, 203, 66)        # brand gold
BRAND_DEEP = (40, 11, 57)
BRAND_PURPLE = (84, 32, 115)
BRAND = Path(__file__).resolve().parent.parent / "ui" / "static" / "brand"
FONTS = {True: ("segoeuib.ttf", "seguisb.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"),
         False: ("segoeui.ttf", "DejaVuSans.ttf", "Arial.ttf", "arial.ttf")}


def _font(size: int, bold: bool = False):
    """A clean system sans (the app uses system-ui), else Pillow's built-in font."""
    for name in FONTS[bold]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                   # very old Pillow
        return ImageFont.load_default()


def _brand_image(name: str, height: int) -> Image.Image | None:
    try:
        im = Image.open(BRAND / name).convert("RGBA")
    except OSError:
        return None
    return im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)


def _wordmark(d: ImageDraw.ImageDraw, right: int, baseline: int, size: int) -> None:
    """'Made with SpriteWaffle', right-aligned: Sprite in cream, Waffle in gold (the app's wordmark)."""
    f, fb = _font(size), _font(size, bold=True)
    parts = [("Made with ", MUTED, f), ("Sprite", TEXT, fb), ("Waffle", ACCENT, fb)]
    x = right - sum(d.textlength(t, font=ft) for t, _, ft in parts)
    for t, col, ft in parts:
        d.text((x, baseline), t, fill=col, font=ft, anchor="ls")
        x += d.textlength(t, font=ft)


def _trim(rgba: np.ndarray) -> np.ndarray:
    ys, xs = np.where(rgba[..., 3] > 0)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else rgba


def _load_anim(sd: Path) -> list[np.ndarray]:
    from ..frames.video import colour_frames
    return [np.array(Image.open(p).convert("RGBA")) for p in colour_frames(sd / "frames")]


def collect(job_root: Path, frame_set: str = "12f") -> dict:
    """What the job has: facing stills (sprite cut from its canvas) and pixelized animations.
    "sprites": per facing, the game sprite for the turnaround (idle frame 0, else the first action's)."""
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
    sprites = {}
    for action in (["idle"] if "idle" in anims else []) + sorted(a for a in anims if a != "idle"):
        for f, v in anims[action].items():
            sprites.setdefault(f, _trim(v["frames"][0]))
    return {"stills": stills, "anims": anims, "sprites": sprites}


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
          fps: int = 12, turn_hold_ms: int = 350, loops: int = 2, subtitle: str = "",
          end_card_ms: int = 1600) -> dict:
    """Write the showcase GIF. Returns a summary (sections, frame count, duration)."""
    data = collect(Path(job_root), frame_set)
    stills, anims = data["stills"], data["anims"]
    if not stills and not anims:
        raise RuntimeError("nothing to show yet: no facings and no animations")
    k = size / 512                                       # layout drawn for 512 px, scaled
    head, foot = round(48 * k), round(30 * k)            # title bar, footer
    frames: list[Image.Image] = []
    durations: list[int] = []
    sections = []
    icon = _brand_image("app-icon-128.png", round(30 * k))
    centre_icon = _brand_image("app-icon-128.png", round(44 * k))

    def base(caption: str, sub: str = "") -> Image.Image:
        c = Image.new("RGBA", (size, size), BG + (255,))
        d = ImageDraw.Draw(c)
        d.rectangle((0, 0, size, head - 1), fill=BRAND_DEEP)
        d.line((0, head - 1, size, head - 1), fill=BRAND_PURPLE, width=max(1, round(2 * k)))
        x = round(10 * k)
        if icon is not None:
            c.alpha_composite(icon, (x, (head - icon.height) // 2))
            x += icon.width + round(8 * k)
        d.text((x, head // 2), title, fill=TEXT, font=_font(round(20 * k), bold=True), anchor="lm")
        if subtitle:
            tx = x + d.textlength(title, font=_font(round(20 * k), bold=True)) + round(8 * k)
            d.text((tx, head // 2 + round(1 * k)), f"· {subtitle}", fill=MUTED, font=_font(round(14 * k)), anchor="lm")
        d.text((size - round(12 * k), head // 2), caption, fill=ACCENT, font=_font(round(16 * k), bold=True), anchor="rm")
        base_y = size - round(10 * k)
        if sub:
            d.text((round(12 * k), base_y), sub, fill=MUTED, font=_font(round(13 * k)), anchor="ls")
        _wordmark(d, size - round(12 * k), base_y, round(13 * k))
        return c

    # 1. turnaround: the game sprite per facing when there are animations (so it matches the clips),
    #    else the facing stills; large, one scale, one foot line
    turn = data["sprites"] or stills
    if turn:
        tallest = max(s.shape[0] for s in turn.values())
        widest = max(s.shape[1] for s in turn.values())
        area = (20, head + round(10 * k), size - 20, size - foot - round(8 * k))
        scale = min((area[3] - area[1]) / tallest, (area[2] - area[0]) / widest)
        if not smooth and scale >= 1:
            # crisp pixel art: whole-number zoom to about two thirds of the height (a 48 px sprite
            # filling the frame at 8x read as blocks; a fixed 4x left it lost in the frame)
            scale = max(1, min(int(scale), int(0.68 * (area[3] - area[1]) / tallest))) if data["sprites"] else int(scale)
        order = [f for f in TURN if f in turn]
        foot_y = min(area[3], (area[1] + area[3]) // 2 + round(tallest * scale / 2))   # centred, one foot line
        for rnd in range(2):
            for f in order:
                c = base("turnaround", f"facing {f}")
                _paste(c, turn[f], area, scale, smooth, foot_y=foot_y)
                frames.append(c)
                durations.append(turn_hold_ms)
        sections.append({"section": "turnaround", "facings": order})

    # 2. every action: all facings play together in a compass grid, in showcase order (calm to
    #    action: alphabetical opened on "attack")
    first = ("idle", "walk", "run", "jump", "attack")
    for action in sorted(anims, key=lambda a: (first.index(a) if a in first else len(first), a)):
        by_f = anims[action]
        n = max(len(v["frames"]) for v in by_f.values())
        cell = (size - 16) // 3
        grid_top = head + round(4 * k)
        cell_h = (size - grid_top - foot) // 3
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
                for slot, f in enumerate(COMPASS):
                    r, q = divmod(slot, 3)
                    x0, y0 = 8 + q * cell, grid_top + r * cell_h
                    box = (x0 + 3, y0 + 3, x0 + cell - 3, y0 + cell_h - 3)
                    if f is None:                        # centre: the app icon and the action name
                        d.rounded_rectangle(box, round(8 * k), fill=BRAND_DEEP, outline=BRAND_PURPLE, width=max(1, round(k)))
                        mid = (box[0] + box[2]) // 2
                        if centre_icon is not None:
                            c.alpha_composite(centre_icon, (mid - centre_icon.width // 2, (box[1] + box[3]) // 2 - centre_icon.height + round(6 * k)))
                        d.text((mid, (box[1] + box[3]) // 2 + round(20 * k)), action, fill=ACCENT,
                               font=_font(round(15 * k), bold=True), anchor="mm")
                        continue
                    d.rounded_rectangle(box, round(8 * k), fill=CELL_BG, outline=LINE, width=1)
                    d.text((box[0] + round(7 * k), box[1] + round(5 * k)), f, fill=MUTED, font=_font(round(12 * k), bold=True))
                    if f in by_f:
                        fr = by_f[f]["frames"]
                        sprite = fr[i % len(fr)][crop_box[1]:crop_box[3], crop_box[0]:crop_box[2]]
                        _paste(c, sprite, box, scale, smooth, foot_y=box[3] - 6)
                    elif f in data["sprites"] or f in stills:   # facing without this action: standing, dimmed
                        st = (data["sprites"].get(f) if f in data["sprites"] else stills[f]).copy()
                        st[..., 3] = (st[..., 3] * 0.35).astype(np.uint8)
                        s2 = tallest * scale / st.shape[0]          # same drawn height as the animation
                        _paste(c, st, box, s2, smooth, foot_y=box[3] - 6)
                frames.append(c)
                durations.append(round(1000 / fps))
        sections.append({"section": action, "facings": [f for f in TURN if f in by_f], "frames": n})

    # 3. end card: the horizontal logo, the character, the wordmark
    if end_card_ms:
        c = Image.new("RGBA", (size, size), BRAND_DEEP + (255,))
        d = ImageDraw.Draw(c)
        logo = _brand_image("horizontal-logo.png", round(130 * k))
        if logo is not None and logo.width > size - 40:
            logo = logo.resize((size - 40, round(logo.height * (size - 40) / logo.width)), Image.LANCZOS)
        y = round(140 * k)
        if logo is not None:
            c.alpha_composite(logo, ((size - logo.width) // 2, y))
            y += logo.height + round(26 * k)
        d.text((size // 2, y), title, fill=TEXT, font=_font(round(22 * k), bold=True), anchor="mt")
        if subtitle:
            d.text((size // 2, y + round(30 * k)), subtitle, fill=MUTED, font=_font(round(15 * k)), anchor="mt")
        n_act = len(anims)
        if n_act:
            d.text((size // 2, size - round(40 * k)), f"{n_act} animation{'s' if n_act != 1 else ''} · "
                   f"{len(data['sprites']) or len(stills)} directions", fill=ACCENT, font=_font(round(14 * k), bold=True), anchor="ms")
        frames.append(c)
        durations.append(end_card_ms)
        sections.append({"section": "end card"})

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
    inputs = meta.get("inputs") or {}
    subtitle = ""                                            # what makes this job differ from its base
    if inputs.get("item_job"):
        subtitle = "wearing " + Path(str(inputs["item_job"])).parent.name.replace("_", " ")
    elif inputs.get("base_job") and inputs.get("edit"):
        subtitle = str(inputs["edit"])[:40]
    walk_fps = profile.fps("walk")
    out = job.stage_dir("06_export") / "showcase" / f"{meta['character']}_showcase.gif"
    summary = build(job.root, out, title, smooth=smooth, size=size, frame_set=frame_set, fps=walk_fps,
                    subtitle=subtitle)
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
