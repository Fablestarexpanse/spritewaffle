"""Attach an effect (or a thrown object) to a character animation.

The character and the effect stay separate sprites, as games use them: the export carries an
event ("at frame 6 spawn `fireball` at (40, 22), in front, moving +3 px/frame") and the effect's own
files; a preview GIF shows them together. The effect is drawn at its own pixel size (set it on the
effect's tab), its centre on the chosen point.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from .job import Job

DIRECTION = {"E": (1, 0), "W": (-1, 0), "S": (0, 1), "N": (0, -1),
             "SE": (0.7071, 0.7071), "SW": (-0.7071, 0.7071), "NE": (0.7071, -0.7071), "NW": (-0.7071, -0.7071)}


def _key(facing: str, action: str) -> str:
    return f"{action}_{facing}"


def get(job: Job, facing: str, action: str) -> dict | None:
    return (job.read_meta()["inputs"].get("attachments") or {}).get(_key(facing, action))


def effect_files(effect_root: Path) -> tuple[list[np.ndarray], dict, Path]:
    """Frames (RGBA), meta and folder of an effect job's export."""
    d = next((p for p in sorted((Path(effect_root) / "06_export" / "effect").glob("*")) if p.is_dir()), None)
    if d is None:
        raise FileNotFoundError(f"{effect_root} has no exported effect yet (render it on its Effect tab)")
    meta = json.loads((d / f"{d.name}.json").read_text())
    frames = [np.array(Image.open(p).convert("RGBA")) for p in sorted((d / "frames").glob("*.png"))]
    return frames, meta, d


def set_attachment(job: Job, facing: str, action: str, effect_job: str, frame: int, x: int, y: int,
                   layer: str = "front", kind: str = "spawn", speed: float = 0.0) -> dict:
    """effect_job: '<character>/<job_id>' of an effect job in the same jobs folder."""
    if layer not in ("front", "behind") or kind not in ("spawn", "projectile"):
        raise ValueError("layer is front or behind; kind is spawn or projectile")
    root = job.root.parent.parent / effect_job
    if not (root / "job.json").exists():
        raise FileNotFoundError(f"no effect job {effect_job}")
    _, meta, _ = effect_files(root)
    att = {"effect_job": effect_job, "effect": meta["name"], "frame": int(frame), "point": [int(x), int(y)],
           "layer": layer, "kind": kind, "speed": float(speed) if kind == "projectile" else 0.0,
           "direction": list(DIRECTION.get(facing, (1, 0)))}
    with job.mutate() as m:
        m["inputs"].setdefault("attachments", {})[_key(facing, action)] = att
    return att


def remove(job: Job, facing: str, action: str) -> None:
    with job.mutate() as m:
        (m["inputs"].get("attachments") or {}).pop(_key(facing, action), None)


def event(att: dict, fps_effect: int) -> dict:
    """The export JSON event for one attachment."""
    return {"frame": att["frame"], "name": "spawn_" + att["effect"], "effect": att["effect"], "point": att["point"],
            "layer": att["layer"], "kind": att["kind"],
            **({"velocity_px_per_frame": [round(att["direction"][0] * att["speed"], 3),
                                          round(att["direction"][1] * att["speed"], 3)]} if att["kind"] == "projectile" else {}),
            "effect_fps": fps_effect}


def composite(cells: list[np.ndarray], fx: list[np.ndarray], att: dict, fx_loop: bool, loops: int = 2) -> list[np.ndarray]:
    """Character frames with the effect drawn on top/behind, played from att['frame'].
    The canvas grows to fit the effect (and a projectile's path)."""
    ch, cw = cells[0].shape[:2]
    fh, fw = fx[0].shape[:2]
    n = len(cells)
    total = n * loops
    life = total - att["frame"] if fx_loop or att["kind"] == "projectile" else min(len(fx), total - att["frame"])
    dx, dy = att["direction"]
    travel = att["speed"] * max(life, 0)
    px, py = att["point"]
    xs = [px - fw / 2, px + fw / 2, px + dx * travel - fw / 2, px + dx * travel + fw / 2, 0, cw]
    ys = [py - fh / 2, py + fh / 2, py + dy * travel - fh / 2, py + dy * travel + fh / 2, 0, ch]
    x0, y0 = int(np.floor(min(xs))), int(np.floor(min(ys)))
    W, H = int(np.ceil(max(xs))) - x0 + 2, int(np.ceil(max(ys))) - y0 + 2
    out = []
    for t in range(total):
        canvas = np.zeros((H, W, 4), np.uint8)
        k = t - att["frame"]
        fxf = None
        if 0 <= k < life:
            fxf = fx[k % len(fx)] if (fx_loop or att["kind"] == "projectile") else fx[k]
            fx_x = int(round(px + dx * att["speed"] * k - fw / 2)) - x0
            fx_y = int(round(py + dy * att["speed"] * k - fh / 2)) - y0
        def put(img, x, y):                            # clipped to the canvas
            ys, xs = max(0, -y), max(0, -x)
            ye, xe = min(img.shape[0], H - y), min(img.shape[1], W - x)
            if ye <= ys or xe <= xs:
                return
            src = img[ys:ye, xs:xe]
            a = src[..., 3] > 0
            region = canvas[y + ys:y + ye, x + xs:x + xe]
            region[a] = src[a]
        if fxf is not None and att["layer"] == "behind":
            put(fxf, fx_x, fx_y)
        put(cells[t % n], -x0, -y0)
        if fxf is not None and att["layer"] == "front":
            put(fxf, fx_x, fx_y)
        out.append(canvas)
    return out


def preview(job: Job, facing: str, action: str, frame_set: str = "12f", fps: int = 12) -> Path:
    """<job>/06_export/<facing>/<action>/<set>/<action>_<facing>_<set>_with_fx.gif"""
    att = get(job, facing, action)
    if not att:
        raise FileNotFoundError("no effect attached to this animation")
    sd = job.root / "04_pixel" / facing / action / frame_set
    from ..frames.video import colour_frames
    cells = [np.array(Image.open(p).convert("RGBA")) for p in colour_frames(sd / "frames")]
    if not cells:
        raise FileNotFoundError(f"{action} {facing} has no {frame_set} frames yet")
    fx, meta, _ = effect_files(job.root.parent.parent / att["effect_job"])
    frames = composite(cells, fx, att, meta["loop"])
    from ..prompts import styles
    scale = 4 if styles.get(styles.of_job(job))["post"] == "pixel" else 1
    imgs = []
    for f in frames:
        bg = np.zeros(f.shape[:2] + (3,), np.uint8) + np.array((28, 30, 42), np.uint8)
        a = f[..., 3:] > 0
        comp = np.where(a, f[..., :3], bg)
        imgs.append(Image.fromarray(comp).resize((f.shape[1] * scale, f.shape[0] * scale), Image.NEAREST))
    out = job.root / "06_export" / facing / action / frame_set / f"{action}_{facing}_{frame_set}_with_fx.gif"
    out.parent.mkdir(parents=True, exist_ok=True)
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=round(1000 / fps), loop=0)
    return out
