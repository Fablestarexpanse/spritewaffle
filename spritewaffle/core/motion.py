"""Motion library (experimental): approved driving clips reused across the cast via TARA.

<base>/_library/motions/<name>/clip.mp4 + motion.json. Clips should come from an identity-neutral
figure (plain grey mannequin): measured 2026-11-20, a costumed driving character leaks its identity
into the transfer, a neutral one does not.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import cv2

from .. import paths
from .job import Job

NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def library(base: str | Path | None = None, *, create: bool = True) -> Path:
    d = (Path(base) if base else paths.jobs()) / "_library" / "motions"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _count_frames(clip: Path) -> int:
    cap = cv2.VideoCapture(str(clip))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return n


def add(name: str, job: Job, facing: str, action: str, base: str | Path | None = None, notes: str = "") -> dict:
    """Copy a job's rendered clip into the library as a motion (status 'review')."""
    if not NAME.match(name):
        raise ValueError("motion name: letters, digits, _ and - only")
    src = job.root / "03_actions" / facing / action / "raw.mp4"
    if not src.exists():
        raise FileNotFoundError(f"no clip at {src}")
    d = library(base) / name
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, d / "clip.mp4")
    meta = {"name": name, "action": action, "facing": facing, "frames": _count_frames(d / "clip.mp4"),
            "source": str(src), "status": "review", "notes": notes, "added": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (d / "motion.json").write_text(json.dumps(meta, indent=2))
    return meta


def get(name: str, base: str | Path | None = None) -> dict:
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("motion name: letters, digits, _ and - only")
    root = library(base, create=False)
    p = root / name / "motion.json"
    clip = p.with_name("clip.mp4")
    if not all(path.resolve().is_relative_to(root.resolve()) for path in (p, clip)):
        raise ValueError("Motion files must stay inside the library.")
    if not p.exists():
        raise KeyError(f"no motion '{name}' in the library")
    meta = json.loads(p.read_text(encoding="utf-8"))
    meta["clip"] = str(clip)
    return meta


def approve(name: str, base: str | Path | None = None) -> dict:
    meta = get(name, base)
    meta["status"] = "approved"
    clip = meta.pop("clip")
    (Path(clip).parent / "motion.json").write_text(json.dumps(meta, indent=2))
    return meta


def list_all(base: str | Path | None = None) -> list[dict]:
    return [get(p.parent.name, base) for p in sorted(library(base).glob("*/motion.json"))]
