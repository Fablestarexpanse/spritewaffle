"""Non-destructive edits to the numbered processed frames of one animation."""
from __future__ import annotations

import hashlib
import io
import json
import re
from base64 import b64encode
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ..frames.video import colour_frames
from ..qa import checks
from . import fsutil

MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_DURATION_MS = 65_535                  # Aseprite stores frame durations as unsigned 16-bit integers.
ORDER_OPERATIONS = ("duplicate", "move", "undo", "redo")
PLAYBACK_MODES = ("source", "loop", "once")
STALE_PIXELS = "The frame changed after the editor opened. Close and reopen the editor to load the current frame."


@dataclass(frozen=True)
class Frame:
    id: str
    source: Path
    image: Path
    duration_ms: int | None = None
    conflict: bool = False

    @property
    def replaced(self) -> bool:
        return self.image != self.source


@dataclass(frozen=True)
class Playback:
    mode: str
    loop: bool
    start: int
    end: int
    start_frame: str | None = None
    end_frame: str | None = None
    error: str | None = None

    @property
    def frame_range(self) -> list[int] | None:
        return [self.start, self.end] if self.start_frame and not self.error else None

    def signature(self) -> dict:
        return asdict(self) if self.mode != "source" or self.start_frame is not None else {}

    def require_valid(self) -> None:
        if self.error:
            raise ValueError(self.error)


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


def _state(path: Path) -> dict:
    try:
        record = json.loads(fsutil.read_text(path))
    except FileNotFoundError:
        return {"version": 1, "frames": {}}
    if not isinstance(record, dict) or record.get("version") != 1 or not isinstance(record.get("frames"), dict):
        raise ValueError("This timeline uses an unsupported edit format.")
    return record


def _history(edit: dict) -> list[dict]:
    versions = list(edit.get("history", []))
    if (active := edit.get("replacement")) and active not in versions:
        versions.append(active)
    return versions


def _order(sources: list[Path], state: dict) -> list[str]:
    saved = state.get("order") or []
    known = set(saved)
    return [*saved, *(p.name for p in sources if p.name not in known)]


def _active_path(root: Path, frame_set: Path, replacement: dict | None, source_digest: str) -> Path | None:
    if replacement and replacement["source"] == source_digest:
        path = replacement_path(root, frame_set, replacement["digest"])
        if path and path.is_file() and _digest(path) == replacement["digest"]:
            return path
    return None


def _source_for(sources: list[Path], state: dict, name: str | None) -> Path:
    if name not in _order(sources, state):
        raise FileNotFoundError(f"Frame {name or '(unspecified)'} is unavailable in this timeline.")
    source_name = (state.get("copies") or {}).get(name, name)
    for source in sources:
        if source.name == source_name:
            return source
    raise FileNotFoundError(f"Frame {name} is unavailable in this timeline.")


def _frames(root: Path, frame_set: Path, sources: list[Path], state: dict) -> list[Frame]:
    by_name = {p.name: p for p in sources}
    copies = state.get("copies") or {}
    result = []
    for frame_id in _order(sources, state):
        source = by_name.get(copies.get(frame_id, frame_id))
        if source is None:
            continue
        edit = state["frames"].get(frame_id, {})
        replacement = edit.get("replacement")
        active = _active_path(root, frame_set, replacement, _digest(source)) if replacement else None
        result.append(Frame(frame_id, source, active or source, edit.get("duration_ms"), bool(replacement) and active is None))
    return result


def frames(root: Path, frame_set: Path, sources: list[Path] | None = None) -> list[Frame]:
    if sources is None:
        sources = colour_frames(frame_set / "frames")
    return _frames(root, frame_set, sources, _state(_edit_directory(root, frame_set) / "timeline.json"))


def _playback(root: Path, frame_set: Path, items: list[Frame], settings: dict, source_loop: bool | None) -> Playback:
    mode = settings.get("mode", "source")
    if source_loop is None and mode == "source":
        facing, action, _ = frame_set.relative_to(root / "04_pixel").parts
        report = root / "03_actions" / facing / action / "selection_report.json"
        source_loop = bool(json.loads(fsutil.read_text(report)).get("loop", True)) if report.is_file() else True
    loop = bool(source_loop) if mode == "source" else mode == "loop"
    first, last = settings.get("start_frame"), settings.get("end_frame")
    if first is None and last is None:
        return Playback(mode, loop, 0, len(items) - 1)
    indices = {frame.id: i for i, frame in enumerate(items)}
    if first not in indices or last not in indices:
        error = "A playback range endpoint is missing. Choose available frames or clear the range."
    elif indices[first] > indices[last]:
        error = "The playback range start must be before or at the end. Adjust the range or undo the move."
    else:
        return Playback(mode, loop, indices[first], indices[last], first, last)
    return Playback(mode, loop, 0, len(items) - 1, first, last, error)


def read_clip(root: Path, frame_set: Path, sources: list[Path] | None = None, *,
              source_loop: bool | None = None) -> tuple[list[Frame], Playback]:
    """Read the effective frames and playback from the same timeline snapshot."""
    state = _state(_edit_directory(root, frame_set) / "timeline.json")
    sources = colour_frames(frame_set / "frames") if sources is None else sources
    items = _frames(root, frame_set, sources, state)
    return items, _playback(root, frame_set, items, state.get("playback", {}), source_loop)


def replacements(items: list[Frame]) -> dict[str, str]:
    return {frame.id: frame.image.stem for frame in items if frame.replaced}


def order_signature(items: list[Frame]) -> list[str]:
    order = [f.id for f in items]
    return order if order != sorted({f.source.name for f in items}) else []


def qa_needs_review(report: dict, items: list[Frame], playback: Playback) -> bool:
    return ((report.get("timeline_replacements") or {}) != replacements(items) or
            (report.get("timeline_order") or []) != order_signature(items) or
            (report.get("timeline_playback") or {}) != playback.signature())


def pixels(paths: list[Path]) -> np.ndarray:
    cells = []
    for path in paths:
        with Image.open(path) as image:
            cells.append(np.asarray(image.convert("RGBA")))
    return np.stack(cells)


def timings(items: list[Frame], default_ms: int) -> list[int]:
    return [frame.duration_ms if frame.duration_ms is not None else default_ms for frame in items]


def export_settings(items: list[Frame]) -> dict:
    return {f.id: {"duration_ms": f.duration_ms, "replacement": f.image.stem if f.replaced else None}
            for f in items if f.duration_ms is not None or f.replaced}


def _check_png(image: Image.Image, source: Path) -> None:
    with Image.open(source) as original:
        size = original.size
    if image.size != size:
        raise ValueError(f"Replacement must be {size[0]} × {size[1]} pixels.")
    if image.n_frames != 1:
        raise ValueError("Choose a single-frame PNG for the replacement.")


def _png(data: bytes, source: Path) -> bytes:
    if not isinstance(data, bytes) or not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Choose a PNG no larger than 32 MiB.")
    buffer = io.BytesIO()
    try:
        with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
            _check_png(image, source)
            image.convert("RGBA").save(buffer, format="PNG")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("The replacement could not be read as a PNG.") from error
    return buffer.getvalue()


def _store_png(root: Path, frame_set: Path, png: bytes) -> str:
    digest = hashlib.sha256(png).hexdigest()
    path = replacement_path(root, frame_set, digest)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or _digest(path) != digest:
        fsutil.write_bytes(path, png)
    return digest


def _select_replacement(root: Path, frame_set: Path, source: Path, history: list[dict], operation: str, value) -> dict:
    source_digest = _digest(source)
    if operation == "activate":
        if type(value) is not int or not 1 <= value <= len(history):
            raise ValueError("Choose a saved replacement version for this frame.")
        digest = history[value - 1]["digest"]
        path = replacement_path(root, frame_set, digest)
        if not path or not path.is_file() or _digest(path) != digest:
            raise ValueError("The saved replacement PNG is missing or has changed.")
        with Image.open(path, formats=["PNG"]) as image:
            _check_png(image, source)
    else:
        digest = _store_png(root, frame_set, _png(value, source))
    if _digest(source) != source_digest:
        raise RuntimeError("The processed frame changed during the save. Open it and try again.")
    return {"digest": digest, "source": source_digest}


def _pixel_snapshot(root: Path, frame_set: Path, source: Path, edit: dict) -> tuple[Image.Image, str, str]:
    source_bytes = source.read_bytes()
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    replacement = edit.get("replacement")
    active = _active_path(root, frame_set, replacement, source_digest)
    data = active.read_bytes() if active else source_bytes
    image_digest = hashlib.sha256(data).hexdigest() if active else source_digest
    if active and image_digest != replacement["digest"]:
        raise RuntimeError(STALE_PIXELS)
    fingerprint = hashlib.sha256(bytes.fromhex(source_digest + image_digest)).hexdigest()
    with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
        return image.convert("RGBA"), source_digest, fingerprint


def describe_pixels(root: Path, frame_set: Path, frame: str, *, include_pixels: bool = True) -> dict:
    """Read a draft source and the fingerprint required to save changes to it."""
    from . import job_palette
    from .job import Job

    state = _state(_edit_directory(root, frame_set) / "timeline.json")
    source = _source_for(colour_frames(frame_set / "frames"), state, frame)
    image, _, fingerprint = _pixel_snapshot(root, frame_set, source, state["frames"].get(frame, {}))
    palette = (job_palette.get(Job(root)) or {}).get("colours", [])
    view = {"width": image.width, "height": image.height, "fingerprint": fingerprint, "palette": palette}
    if include_pixels:
        view["rgba"] = b64encode(image.tobytes()).decode("ascii")
    return view


def _paint(root: Path, frame_set: Path, source: Path, edit: dict, patch) -> dict | None:
    if not isinstance(patch, dict) or not isinstance(patch.get("fingerprint"), str):
        raise ValueError("Load the frame fingerprint before saving pixels.")
    image, source_digest, fingerprint = _pixel_snapshot(root, frame_set, source, edit)
    if patch["fingerprint"] != fingerprint:
        raise RuntimeError(STALE_PIXELS)
    changes = patch.get("pixels")
    if not isinstance(changes, list) or not 0 < len(changes) <= image.width * image.height:
        raise ValueError("Provide one change per edited pixel.")
    seen = set()
    changed = False
    for row in changes:
        if not isinstance(row, list) or len(row) != 6 or any(type(n) is not int for n in row):
            raise ValueError("Each pixel must be six integers [x, y, r, g, b, a].")
        x, y, *channels = row
        if not (0 <= x < image.width and 0 <= y < image.height and all(0 <= n <= 255 for n in channels)):
            raise ValueError("Each pixel must be inside the frame with RGBA channels from 0 to 255.")
        position = (x, y)
        if position in seen:
            raise ValueError("Each pixel must appear only once in a save.")
        seen.add(position)
        if image.getpixel(position) != tuple(channels):
            image.putpixel(position, tuple(channels))
            changed = True
    if not changed:
        return None
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    if _digest(source) != source_digest:
        raise RuntimeError(STALE_PIXELS)
    digest = _store_png(root, frame_set, buffer.getvalue())
    if _digest(source) != source_digest:
        raise RuntimeError(STALE_PIXELS)
    return {"digest": digest, "source": source_digest}


def _edit_order(state: dict, sources: list[Path], name: str | None, operation: str, value) -> str | None:
    if operation in ("undo", "redo"):
        steps = state.get(operation) or []
        if not steps:
            raise ValueError(f"There is no frame order change to {operation}.")
        other = "redo" if operation == "undo" else "undo"
        state.setdefault(other, []).append(state.get("order"))
        state["order"] = steps.pop()
        return None

    copies = state.setdefault("copies", {})
    order = _order(sources, state)
    names = {p.name for p in sources}
    visible = [key for key in order if copies.get(key, key) in names]
    if name not in visible:
        raise ValueError("Choose a frame in this timeline.")
    state.setdefault("undo", []).append(state.get("order"))
    state["redo"] = []
    if operation == "duplicate":
        if len(visible) >= 65_535:    # The Aseprite frame count is an unsigned 16-bit field.
            raise ValueError("This frame set is already at the Aseprite frame limit.")
        new_id = f"copy-{len(copies) + 1}"
        copies[new_id] = copies.get(name, name)
        order.insert(order.index(name) + 1, new_id)
        if name in state["frames"]:
            state["frames"][new_id] = deepcopy(state["frames"][name])
        state["order"] = order
        return new_id

    if type(value) is not int or not 0 <= value < len(visible) or visible[value] == name:
        raise ValueError("Choose a different frame position within this timeline.")
    visible.remove(name)
    visible.insert(value, name)
    available = set(visible)
    moved = iter(visible)
    # Unavailable source frames retain their saved positions if they return later.
    state["order"] = [next(moved) if key in available else key for key in order]
    return name


def _edit_frame(root: Path, frame_set: Path, state: dict, sources: list[Path], name: str | None, operation: str, value) -> bool:
    source = _source_for(sources, state, name)
    edits = state["frames"]
    edit = edits.get(name, {})
    history = _history(edit)
    if operation == "duration":
        if value is None:
            edit.pop("duration_ms", None)
        elif type(value) is not int or not 1 <= value <= MAX_DURATION_MS:
            raise ValueError(f"Frame duration must be a whole number from 1 to {MAX_DURATION_MS} ms.")
        else:
            edit["duration_ms"] = value
    elif operation == "restore":
        edit.pop("replacement", None)
    else:
        active = (_paint(root, frame_set, source, edit, value) if operation == "paint" else
                  _select_replacement(root, frame_set, source, history, operation, value))
        if active is None:
            return False
        edit["replacement"] = active
        if active not in history:
            history.append(active)
    if history:
        edit["history"] = history
    if edit:
        edits[name] = edit
    else:
        edits.pop(name, None)
    return True


def _edit_playback(root: Path, frame_set: Path, state: dict, sources: list[Path], value) -> None:
    if not isinstance(value, dict) or value.get("mode") not in PLAYBACK_MODES:
        raise ValueError("Playback mode must be source, loop, or once.")
    first, last = value.get("start_frame"), value.get("end_frame")
    if (first is not None or last is not None) and not (isinstance(first, str) and isinstance(last, str)):
        raise ValueError("Choose both playback range endpoints, or clear both.")
    if not sources:
        raise FileNotFoundError("Pixelize the action before saving playback settings.")
    settings = {"mode": value["mode"]}
    if first is not None:
        settings.update(start_frame=first, end_frame=last)
    _playback(root, frame_set, _frames(root, frame_set, sources, state), settings, None).require_valid()
    if first is None and settings["mode"] == "source":
        state.pop("playback", None)
    else:
        state["playback"] = settings


def update(root: Path, frame_set: Path, name: str | None, operation: str, value=None) -> str | None:
    from . import manifest
    from .job import Job

    if operation not in (*ORDER_OPERATIONS, "duration", "replace", "restore", "activate", "paint", "playback"):
        raise ValueError("Unknown timeline operation.")
    if operation not in ("undo", "redo", "playback") and (
        not isinstance(name, str) or re.fullmatch(r"(?:[0-9]{3}\.png|copy-[1-9][0-9]*)", name) is None
    ):
        raise ValueError("Choose a frame ID from this timeline.")
    folder = _edit_directory(root, frame_set)
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / "timeline.json"
    with fsutil.locked(folder / ".timeline.lock", "Another timeline save is in progress. Retry when it finishes."):
        state = _state(record)
        sources = colour_frames(frame_set / "frames")
        selected = name
        if operation in ORDER_OPERATIONS:
            selected = _edit_order(state, sources, name, operation, value)
        elif operation == "playback":
            _edit_playback(root, frame_set, state, sources, value)
        elif not _edit_frame(root, frame_set, state, sources, name, operation, value):
            return selected
        fsutil.write_text(record, json.dumps(state, indent=2))
        manifest.refresh(Job(root))
        return selected


def action_fps(base_fps: int, frame_set: str) -> int:
    count = int(frame_set.rstrip("f"))
    return base_fps if count <= 12 else base_fps * count // 12


def _history_view(root: Path, frame_set: Path, frame: Frame, edit: dict) -> list[dict]:
    versions = _history(edit)
    if not versions:
        return []
    source_digest = _digest(frame.source)
    view = []
    for number, version in enumerate(versions, 1):
        path = replacement_path(root, frame_set, version["digest"])
        available = path is not None and path.is_file()
        view.append({"version": number, "image": path.relative_to(root).as_posix() if available else None,
                     "available": available, "same_source": version["source"] == source_digest,
                     "active": frame.replaced and version == edit.get("replacement")})
    return view


def describe(root: Path, frame_set: Path, base_fps: int) -> dict:
    state = _state(_edit_directory(root, frame_set) / "timeline.json")
    items = _frames(root, frame_set, colour_frames(frame_set / "frames"), state)
    if not items:
        raise FileNotFoundError("Pixelize the action to open its timeline.")
    facing, action, name = frame_set.relative_to(root / "04_pixel").parts
    report = checks.read(root / "05_qa" / facing / action / name / "report.json") or {}
    playback = _playback(root, frame_set, items, state.get("playback", {}), None)
    default_ms = round(1000 / action_fps(base_fps, name))
    with Image.open(items[0].source) as image:
        cell = list(image.size)
    return {"facing": facing, "action": action, "frame_set": name, "cell": cell, "loop": playback.loop,
            "playback": asdict(playback),
            "default_ms": default_ms, "max_duration_ms": MAX_DURATION_MS, "max_image_bytes": MAX_IMAGE_BYTES,
            "qa_needs_review": qa_needs_review(report, items, playback),
            "can_undo": bool(state.get("undo")), "can_redo": bool(state.get("redo")),
            "frames": [{"id": f.id, "name": f.source.name, "image": f.image.relative_to(root).as_posix(),
                        "duration_ms": t, "timing_edited": f.duration_ms is not None,
                        "replaced": f.replaced, "conflict": f.conflict,
                        "history": _history_view(root, frame_set, f, state["frames"].get(f.id, {}))}
                       for f, t in zip(items, timings(items, default_ms))]}
