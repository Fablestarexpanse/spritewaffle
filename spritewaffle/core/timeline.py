"""Non-destructive edits to the numbered processed frames of one animation."""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ..frames.video import colour_frames
from ..qa import checks
from . import fsutil

MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_DURATION_MS = 65_535                  # Aseprite stores frame durations as unsigned 16-bit integers.


@dataclass(frozen=True)
class Frame:
    source: Path
    image: Path
    duration_ms: int | None = None
    conflict: bool = False

    @property
    def replaced(self) -> bool:
        return self.image != self.source


def directory(root: Path, facing: str, action: str, frame_set: str) -> Path:
    if any(not name or name in (".", "..") or any(c in name for c in "/\\:\0") for name in (facing, action)):
        raise ValueError("Facing and action must each be a single name.")
    if re.fullmatch(r"[0-9]+f?", frame_set) is None:
        raise ValueError("Choose a numbered frame set such as 12f or 24f.")
    path = root / "04_pixel" / facing / action / frame_set
    if (root / "04_pixel").resolve() not in path.resolve().parents:
        raise ValueError("The frame set must be inside this job.")
    return path


def _edit_directory(root: Path, frame_set: Path) -> Path:
    return root / "edits" / "animations" / frame_set.relative_to(root / "04_pixel")


def replacement_path(root: Path, frame_set: Path, digest: str) -> Path | None:
    if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
        return _edit_directory(root, frame_set) / "replacements" / f"{digest}.png"
    return None


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _edits(path: Path) -> dict:
    try:
        record = json.loads(fsutil.read_text(path))
    except FileNotFoundError:
        return {}
    if not isinstance(record, dict) or record.get("version") != 1 or not isinstance(record.get("frames"), dict):
        raise ValueError("This timeline uses an unsupported edit format.")
    return record["frames"]


def frames(root: Path, frame_set: Path, sources: list[Path] | None = None) -> list[Frame]:
    if sources is None:
        sources = colour_frames(frame_set / "frames")
    edits = _edits(_edit_directory(root, frame_set) / "timeline.json")
    result = []
    for source in sources:
        edit = edits.get(source.name, {})
        replacement = edit.get("replacement")
        image = source
        if replacement:
            path = replacement_path(root, frame_set, replacement["digest"])
            if path and path.is_file() and _digest(source) == replacement["source"] and _digest(path) == replacement["digest"]:
                image = path
        result.append(Frame(source, image, edit.get("duration_ms"), bool(replacement) and image == source))
    return result


def replacements(items: list[Frame]) -> dict[str, str]:
    return {frame.source.name: frame.image.stem for frame in items if frame.replaced}


def pixels(paths: list[Path]) -> np.ndarray:
    cells = []
    for path in paths:
        with Image.open(path) as image:
            cells.append(np.asarray(image.convert("RGBA")))
    return np.stack(cells)


def timings(items: list[Frame], default_ms: int) -> list[int]:
    return [frame.duration_ms if frame.duration_ms is not None else default_ms for frame in items]


def export_settings(items: list[Frame]) -> dict:
    return {f.source.name: {"duration_ms": f.duration_ms, "replacement": f.image.stem if f.replaced else None}
            for f in items if f.duration_ms is not None or f.replaced}


def _png(data: bytes, source: Path) -> bytes:
    if not isinstance(data, bytes) or not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Choose a PNG no larger than 32 MiB.")
    with Image.open(source) as original:
        size = original.size
    buffer = io.BytesIO()
    try:
        with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
            if image.size != size:
                raise ValueError(f"Replacement must be {size[0]} × {size[1]} pixels.")
            if image.n_frames != 1:
                raise ValueError("Choose a single-frame PNG for the replacement.")
            image.convert("RGBA").save(buffer, format="PNG")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("The replacement could not be read as a PNG.") from error
    return buffer.getvalue()


def update(root: Path, frame_set: Path, name: str, operation: str, value=None) -> None:
    from . import manifest
    from .job import Job

    if re.fullmatch(r"[0-9]{3}\.png", name) is None:
        raise ValueError("Choose a numbered source frame such as 000.png.")
    if operation not in ("duration", "replace", "restore"):
        raise ValueError("Choose duration, replace, or restore.")
    source = frame_set / "frames" / name
    if not source.is_file():
        raise FileNotFoundError(f"Processed frame {name} is missing.")
    folder = _edit_directory(root, frame_set)
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / "timeline.json"
    with fsutil.locked(folder / ".timeline.lock", "Another timeline save is in progress. Retry when it finishes."):
        edits = _edits(record)
        edit = edits.get(name, {})
        if operation == "duration":
            if value is None:
                edit.pop("duration_ms", None)
            elif type(value) is not int or not 1 <= value <= MAX_DURATION_MS:
                raise ValueError(f"Frame duration must be a whole number from 1 to {MAX_DURATION_MS} ms.")
            else:
                edit["duration_ms"] = value
        elif operation == "replace":
            source_digest = _digest(source)
            png = _png(value, source)
            if _digest(source) != source_digest:
                raise RuntimeError("The processed frame changed during the save. Open it and try again.")
            digest = hashlib.sha256(png).hexdigest()
            path = replacement_path(root, frame_set, digest)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.is_file() or _digest(path) != digest:
                fsutil.write_bytes(path, png)
            edit["replacement"] = {"digest": digest, "source": source_digest}
        else:
            edit.pop("replacement", None)
        if edit:
            edits[name] = edit
        else:
            edits.pop(name, None)
        fsutil.write_text(record, json.dumps({"version": 1, "frames": edits}, indent=2))
        manifest.refresh(Job(root))


def action_fps(base_fps: int, frame_set: str) -> int:
    count = int(frame_set.rstrip("f"))
    return base_fps if count <= 12 else base_fps * count // 12


def describe(root: Path, frame_set: Path, base_fps: int) -> dict:
    items = frames(root, frame_set)
    if not items:
        raise FileNotFoundError("Pixelize the action to open its timeline.")
    facing, action, name = frame_set.relative_to(root / "04_pixel").parts
    selection = root / "03_actions" / facing / action / "selection_report.json"
    report = checks.read(root / "05_qa" / facing / action / name / "report.json") or {}
    loop = json.loads(fsutil.read_text(selection)).get("loop", True) if selection.is_file() else True
    default_ms = round(1000 / action_fps(base_fps, name))
    with Image.open(items[0].source) as image:
        cell = list(image.size)
    return {"facing": facing, "action": action, "frame_set": name, "cell": cell, "loop": loop,
            "default_ms": default_ms, "max_duration_ms": MAX_DURATION_MS, "max_image_bytes": MAX_IMAGE_BYTES,
            "qa_needs_review": (report.get("timeline_replacements") or {}) != replacements(items),
            "frames": [{"name": f.source.name, "image": f.image.relative_to(root).as_posix(),
                        "duration_ms": t, "timing_edited": f.duration_ms is not None,
                        "replaced": f.replaced, "conflict": f.conflict}
                       for f, t in zip(items, timings(items, default_ms))]}
