"""Video reading (OpenCV) and frame folders."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def extract(video: str | Path, out_dir: str | Path) -> dict:
    """Write every frame as RGB PNG (00000.png ...) + extraction_report.json. Returns the report."""
    video, out = Path(video), Path(out_dir)
    if not video.exists():
        raise FileNotFoundError(video)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f"OpenCV cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    n = 0
    size = None
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        size = [rgb.shape[1], rgb.shape[0]]
        Image.fromarray(rgb).save(out / f"{n:05d}.png")
        n += 1
    cap.release()
    if n == 0:
        raise ValueError(f"no frames decoded from {video}")
    report = {"source": str(video), "source_size": size, "fps": fps, "frame_count": n,
              "duration_s": n / fps if fps else None}
    (out / "extraction_report.json").write_text(json.dumps(report, indent=2))
    return report


def read_frames(video: str | Path) -> list[np.ndarray]:
    """All frames of a video as RGB arrays (in memory; for short sprite clips)."""
    cap, out = cv2.VideoCapture(str(video)), []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        out.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()
    if not out:
        raise ValueError(f"no frames decoded from {video}")
    return out


def list_frames(folder: str | Path) -> list[Path]:
    return sorted(Path(folder).glob("*.png"))


def colour_frames(folder: str | Path) -> list[Path]:
    """A pixel set's colour frames (000.png, 001.png...), never the reserved per-frame maps
    (000_depth.png, 000_normal.png) that may sit next to them (docs/MANIFEST.md)."""
    return sorted(Path(folder).glob("[0-9][0-9][0-9].png"))


def load(paths: list[Path]) -> list[np.ndarray]:
    """Load PNGs as RGB, or RGBA when the file has alpha."""
    out = []
    for p in paths:
        im = Image.open(p)
        out.append(np.array(im.convert("RGBA" if im.mode == "RGBA" else "RGB")))
    return out
