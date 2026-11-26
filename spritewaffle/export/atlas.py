"""Atlas pages a game engine can load: frames trimmed to their pixels, identical frames stored once,
shelf-packed into pages no larger than `max_size` (default 4096: Unity's default max texture size
is 2048, its limit 8192, many mobile GPUs 4096). Measured before this existed: the hare at a 384 px
cell was one 4608x15360 PNG, one row per animation, untrimmed.

Each frame keeps where it sits in its cell (`ox`, `oy`), so the cell-space pivot still holds.
mirror="flip": a W/NW/SW animation that is an exact horizontal flip of its E/NE/SE partner is not
packed; it is listed with `flip_x` and the partner's frames (engines flip at runtime). That is
checked pixel by pixel, never assumed.

Two JSON files: ours (animations, fps, loop, pivot, per-frame page + rect + offset) and, per page,
TexturePacker "JSON hash" (frames + animations + meta.related_multi_packs), which Phaser, PixiJS,
Godot importers and others read.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

MIRROR_OF = {"W": "E", "NW": "NE", "SW": "SE"}
PAD = 1                                     # transparent gap between sprites (no bleeding when filtered)


def _trim(cell: np.ndarray) -> tuple[np.ndarray, int, int]:
    ys, xs = np.where(cell[..., 3] > 0)
    if not len(ys):
        return cell[:1, :1], 0, 0
    return cell[ys.min():ys.max() + 1, xs.min():xs.max() + 1], int(xs.min()), int(ys.min())


def _key(a: np.ndarray) -> str:
    return hashlib.sha1(a.shape.__repr__().encode() + np.ascontiguousarray(a).tobytes()).hexdigest()


def flips(anims: list[dict]) -> dict[str, str]:
    """{W-side animation name: its E-side partner} for exact mirrors without auxiliary maps."""
    by = {(a["facing"], a["action"]): a for a in anims}
    out = {}
    for a in anims:
        src = by.get((MIRROR_OF.get(a["facing"]), a["action"]))
        if (src is not None and not (src.get("maps") or a.get("maps")) and len(src["cells"]) == len(a["cells"])
                and np.array_equal(src["cells"][:, :, ::-1], a["cells"])):
            out[a["name"]] = src["name"]
    return out


def _pow2(n: int) -> int:
    return 1 << max(0, int(n - 1).bit_length())

def pack(anims: list[dict], max_size: int = 4096, mirror: str = "pack", pot: bool = False,
         extrude: int = 0) -> tuple[list[np.ndarray], dict]:
    """anims: [{name, facing, action, cells (F,h,w,4)}]. Returns (pages, layout) where layout maps
    animation name -> {"frames": [{page, x, y, w, h, ox, oy}], "flip_x_of": name | None}.
    pot: page sizes rounded up to powers of two (older GPUs, mip maps). extrude: each sprite's edge
    pixels repeated this many px outward, so bilinear filtering or mip maps don't pull in the
    neighbour; the frame rects stay the sprite itself."""
    if mirror not in ("pack", "flip"):
        raise ValueError("mirror must be 'pack' or 'flip'")
    if pot and max_size & (max_size - 1):
        raise ValueError("a power-of-two atlas needs a power-of-two page limit (2048, 4096, 8192)")
    e = int(extrude)
    if not 0 <= e <= 4:
        raise ValueError("extrude must be 0-4 px")
    flipped = flips(anims) if mirror == "flip" else {}
    uniq: dict[str, dict] = {}                  # key -> {"img", "ox", "oy"}
    refs: dict[str, list[str]] = {}
    for a in anims:
        if a["name"] in flipped:
            continue
        keys = []
        maps = sorted((a.get("maps") or {}).items())
        for index, cell in enumerate(a["cells"]):
            img, ox, oy = _trim(cell)
            k = _key(img) + f":{ox},{oy}"
            for kind, cells in maps:
                auxiliary = cells[index, oy:oy + img.shape[0], ox:ox + img.shape[1]]
                if auxiliary.any():
                    k += f":{kind}:{_key(auxiliary)}"
            uniq.setdefault(k, {"img": img, "ox": ox, "oy": oy})
            keys.append(k)
        refs[a["name"]] = keys
    big = [k for k, u in uniq.items() if max(u["img"].shape[:2]) + 2 * PAD + 2 * e > max_size]
    if big:
        h, w = uniq[big[0]]["img"].shape[:2]
        raise ValueError(f"a frame is {w}x{h} px, larger than the {max_size} px page limit")

    # shelf packing: tallest first, rows left to right, new page when a page is full
    order = sorted(uniq, key=lambda k: (-uniq[k]["img"].shape[0], -uniq[k]["img"].shape[1]))
    pages_used: list[list[tuple[str, int, int]]] = [[]]
    x = y = row_h = 0
    for k in order:
        h, w = uniq[k]["img"].shape[:2]
        h, w = h + 2 * e, w + 2 * e             # the extruded footprint
        if x + w + PAD > max_size:              # next row
            x, y, row_h = 0, y + row_h, 0
        if y + h + PAD > max_size:              # next page
            pages_used.append([])
            x = y = row_h = 0
        pages_used[-1].append((k, x + PAD + e, y + PAD + e))
        uniq[k].update(page=len(pages_used) - 1, x=x + PAD + e, y=y + PAD + e)
        x += w + PAD
        row_h = max(row_h, h + PAD)

    pages = []
    for used in pages_used:
        W = max(uniq[k]["x"] + uniq[k]["img"].shape[1] for k, _, _ in used) + e + PAD
        H = max(uniq[k]["y"] + uniq[k]["img"].shape[0] for k, _, _ in used) + e + PAD
        if pot:
            W, H = _pow2(W), _pow2(H)
        page = np.zeros((H, W, 4), np.uint8)
        for k, px, py in used:
            img = _extrude(uniq[k]["img"], e)
            page[py - e:py - e + img.shape[0], px - e:px - e + img.shape[1]] = img
        pages.append(page)

    def frame(k):
        u = uniq[k]
        return {"page": u["page"], "x": u["x"], "y": u["y"], "w": int(u["img"].shape[1]), "h": int(u["img"].shape[0]),
                "ox": u["ox"], "oy": u["oy"]}

    layout = {}
    for a in anims:
        if a["name"] in flipped:
            layout[a["name"]] = {"frames": [frame(k) for k in refs[flipped[a["name"]]]], "flip_x_of": flipped[a["name"]]}
        else:
            layout[a["name"]] = {"frames": [frame(k) for k in refs[a["name"]]], "flip_x_of": None}
    return pages, layout


def _extrude(img: np.ndarray, e: int) -> np.ndarray:
    return np.pad(img, ((e, e), (e, e), (0, 0)), mode="edge") if e else img


def write_texturepacker(out_dir: Path, base: str, pages: list[np.ndarray], layout: dict, cell: tuple[int, int],
                        pivots: dict[str, list[float]], timing: dict[str, dict] | None = None) -> list[Path]:
    """One TexturePacker JSON-hash file per page. Frame names: <animation>_<index:03d>, each with
    its "duration" in ms. The format has no flip and no fps, so every page's meta also carries
    "animations": {name: {fps, loop, flip_x_of}}; a flip-only animation (mirror="flip") is listed
    there with the animation whose frames it flips, instead of vanishing from the file.
    timing: {name: {"fps", "loop", "durations_ms"?}}."""
    timing = timing or {}
    w, h = cell
    files = [out_dir / f"{base}_{i}.json" for i in range(len(pages))]
    per_page = [{"frames": {}, "animations": {}} for _ in pages]
    for name, lay in layout.items():
        if lay["flip_x_of"]:
            continue
        t = timing.get(name) or {}
        durs = t.get("durations_ms") or [round(1000 / t["fps"])] * len(lay["frames"]) if t.get("fps") else None
        for i, f in enumerate(lay["frames"]):
            fn = f"{name}_{i:03d}"
            pv = pivots.get(name) or [w / 2, h]
            per_page[f["page"]]["frames"][fn] = {**({"duration": int(durs[i])} if durs else {}),
                "frame": {"x": f["x"], "y": f["y"], "w": f["w"], "h": f["h"]}, "rotated": False,
                "trimmed": (f["w"], f["h"]) != (w, h),
                "spriteSourceSize": {"x": f["ox"], "y": f["oy"], "w": f["w"], "h": f["h"]},
                "sourceSize": {"w": w, "h": h}, "pivot": {"x": round(pv[0] / w, 6), "y": round(pv[1] / h, 6)}}
            per_page[f["page"]]["animations"].setdefault(name, []).append(fn)
    info = {name: {"fps": (timing.get(name) or {}).get("fps"), "loop": (timing.get(name) or {}).get("loop"),
                   "flip_x_of": lay["flip_x_of"]} for name, lay in layout.items()}
    for i, (p, d) in enumerate(zip(files, per_page)):
        d["meta"] = {"app": "SpriteWaffle", "image": f"{base}_{i}.png", "format": "RGBA8888",
                     "size": {"w": int(pages[i].shape[1]), "h": int(pages[i].shape[0])}, "scale": "1",
                     "related_multi_packs": [f.name for f in files if f != p], "animations": info}
        p.write_text(json.dumps(d, indent=2))
    return files


def save_pages(out_dir: Path, base: str, pages: list[np.ndarray]) -> list[Path]:
    out = []
    for old in out_dir.glob(f"{base}_*.png"):               # a re-export may need fewer pages
        if old.stem[len(base) + 1:].isdigit():
            old.unlink()
    for old in out_dir.glob(f"{base}_*.json"):
        if old.stem[len(base) + 1:].isdigit():
            old.unlink()
    for i, page in enumerate(pages):
        p = out_dir / f"{base}_{i}.png"
        Image.fromarray(page, "RGBA").save(p)
        out.append(p)
    return out


def map_pages(pages: list[np.ndarray], layout: dict, anims: list[dict], kind: str, extrude: int = 0) -> list[np.ndarray]:
    """Pages for a per-frame map (depth, normal) laid out exactly like the colour pages: each
    frame's map is cut with the colour frame's trim and put in the colour frame's rectangle, so an
    engine samples colour and map with the same UVs. Frames without the map stay empty."""
    out = [np.zeros_like(p) for p in pages]
    for a in anims:
        lay = layout.get(a["name"]) or {}
        maps = (a.get("maps") or {}).get(kind)
        if maps is None or lay.get("flip_x_of"):
            continue
        for f, m in zip(lay["frames"], maps):
            e = extrude
            out[f["page"]][f["y"] - e:f["y"] + f["h"] + e, f["x"] - e:f["x"] + f["w"] + e] = \
                _extrude(m[f["oy"]:f["oy"] + f["h"], f["ox"]:f["ox"] + f["w"]], e)
    return out


def save_map_pages(out_dir: Path, base: str, pages: list[np.ndarray]) -> list[Path]:
    out = []
    for i, p in enumerate(pages):
        f = out_dir / f"{base}_{i}.png"
        Image.fromarray(p).save(f)
        out.append(f)
    return out
