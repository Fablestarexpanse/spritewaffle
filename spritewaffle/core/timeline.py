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
from unicodedata import normalize
from uuid import uuid4

import numpy as np
from PIL import Image

from ..frames.video import colour_frames
from ..qa import checks
from . import fsutil

MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_DURATION_MS = 65_535                  # Aseprite stores frame durations as unsigned 16-bit integers.
ORDER_OPERATIONS = ("duplicate", "move", "insert", "insert_blank", "remove", "undo", "redo")
TAG_OPERATIONS = ("save_tag", "remove_tag")
PLAYBACK_MODES = ("source", "loop", "once")
STALE_PIXELS = "The frame changed after the editor opened. Close and reopen the editor to load the current frame."


@dataclass(frozen=True)
class Frame:
    id: str
    source: Path
    image: Path
    duration_ms: int | None = None
    conflict: bool = False
    insertion_id: str | None = None

    @property
    def replaced(self) -> bool:
        return self.image != self.source

    @property
    def inserted(self) -> bool:
        return self.insertion_id is not None

    @property
    def source_id(self) -> str:
        return self.insertion_id or self.source.name


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


@dataclass(frozen=True)
class Tag:
    id: str
    name: str
    start_frame: str
    end_frame: str
    loop: bool
    start: int | None
    end: int | None
    error: str | None


@dataclass(frozen=True)
class Clip:
    items: list[Frame]
    sources: list[Path]
    playback: Playback
    unavailable: dict[str, str]
    tags: list[Tag]

    @property
    def order(self) -> list[str]:
        order = [frame.id for frame in self.items]
        return order if order != [source.name for source in self.sources] else []

    @property
    def error(self) -> str | None:
        if self.unavailable:
            return "Restore or remove unavailable inserted frames: " + ", ".join(self.unavailable) + "."
        if self.playback.error:
            return self.playback.error
        for tag in self.tags:
            if tag.error:
                return f"Repair or remove animation tag {tag.name!r}. {tag.error}"
        return None

    def describe_tags(self) -> list[dict]:
        return [asdict(tag) for tag in self.tags]

    def export_tags(self, animation: str) -> list[dict]:
        return [{"name": tag.name, "start": tag.start, "end": tag.end, "loop": tag.loop,
                 "aseprite_tag": f"{animation} [{tag.name}]"} for tag in self.tags]

    def require_valid(self) -> None:
        if error := self.error:
            raise ValueError(error)


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


def _insertion_path(root: Path, frame_set: Path, digest: str, size: tuple[int, int] | None) -> tuple[Path | None, str]:
    path = replacement_path(root, frame_set, digest)
    if not path or not path.is_file():
        return None, "Saved PNG is missing."
    if _digest(path) != digest:
        return None, "Saved PNG has changed."
    with Image.open(path, formats=["PNG"]) as image:
        if size is not None and image.size != size:
            return None, f"Saved PNG no longer fits the {size[0]} × {size[1]} cell."
    return path, ""


def _frames(root: Path, frame_set: Path, sources: list[Path], state: dict) -> tuple[list[Frame], dict[str, str]]:
    by_name = {p.name: p for p in sources}
    copies = state.get("copies") or {}
    removed = set(state.get("removed") or [])
    insertions = state.get("insertions") or {}
    imports = {}
    size = None
    unavailable = {}
    result = []
    for frame_id in _order(sources, state):
        if frame_id in removed:
            continue
        source_id = copies.get(frame_id, frame_id)
        insertion_id = source_id if source_id in insertions else None
        if insertion_id:
            if not imports and sources:
                with Image.open(sources[0]) as original:
                    size = original.size
            if insertion_id not in imports:
                imports[insertion_id] = _insertion_path(root, frame_set, insertions[insertion_id], size)
            source, error = imports[insertion_id]
            if error:
                unavailable[frame_id] = error
                continue
        else:
            source = by_name.get(source_id)
        if source is None:
            continue
        edit = state["frames"].get(frame_id, {})
        replacement = edit.get("replacement")
        active = _active_path(root, frame_set, replacement, _digest(source)) if replacement else None
        result.append(Frame(frame_id, source, active or source, edit.get("duration_ms"),
                            bool(replacement) and active is None, insertion_id))
    return result, unavailable


def _selected_frame(root: Path, frame_set: Path, sources: list[Path], state: dict, name: str | None) -> Frame:
    items, unavailable = _frames(root, frame_set, sources, state)
    for frame in items:
        if frame.id == name:
            return frame
    raise FileNotFoundError(unavailable.get(name, f"Frame {name or '(unspecified)'} is unavailable in this timeline."))


def frames(root: Path, frame_set: Path, sources: list[Path] | None = None) -> list[Frame]:
    if sources is None:
        sources = colour_frames(frame_set / "frames")
    return _frames(root, frame_set, sources, _state(_edit_directory(root, frame_set) / "timeline.json"))[0]


def _range_positions(indices: dict[str, int], first: str, last: str) -> tuple[int | None, int | None, str | None]:
    if first not in indices or last not in indices:
        return None, None, "A range endpoint is missing. Choose available first and last frames."
    if indices[first] > indices[last]:
        return None, None, "The range start must be before or at the end. Adjust the range or undo the move."
    return indices[first], indices[last], None


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
    start, end, error = _range_positions(indices, first, last)
    if error:
        return Playback(mode, loop, 0, len(items) - 1, first, last, f"Playback needs repair. {error}")
    return Playback(mode, loop, start, end, first, last)


def _tags(items: list[Frame], records: list[dict]) -> list[Tag]:
    if not records:
        return []
    indices = {frame.id: i for i, frame in enumerate(items)}
    tags = []
    for tag in records:
        start, end, error = _range_positions(indices, tag["start_frame"], tag["end_frame"])
        tags.append(Tag(**tag, start=start, end=end, error=error))
    return tags


def _clip(root: Path, frame_set: Path, sources: list[Path], state: dict, source_loop: bool | None = None) -> Clip:
    items, unavailable = _frames(root, frame_set, sources, state)
    playback = _playback(root, frame_set, items, state.get("playback", {}), source_loop)
    return Clip(items, sources, playback, unavailable, _tags(items, state.get("tags", [])))


def read_clip(root: Path, frame_set: Path, sources: list[Path] | None = None, *, source_loop: bool | None = None) -> Clip:
    """Read the effective frames and playback from the same timeline snapshot."""
    state = _state(_edit_directory(root, frame_set) / "timeline.json")
    sources = colour_frames(frame_set / "frames") if sources is None else sources
    return _clip(root, frame_set, sources, state, source_loop)


def alternate_images(items: list[Frame]) -> dict[str, str]:
    return {frame.id: frame.image.stem for frame in items if frame.replaced or frame.inserted}


def qa_needs_review(report: dict, clip: Clip) -> bool:
    return (bool(clip.error) or (report.get("timeline_replacements") or {}) != alternate_images(clip.items) or
            (report.get("timeline_order") or []) != clip.order or
            (report.get("timeline_playback") or {}) != clip.playback.signature() or
            (report.get("timeline_tags") or []) != clip.describe_tags())


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
        raise ValueError(f"PNG must be {size[0]} × {size[1]} pixels.")
    if image.n_frames != 1:
        raise ValueError("Choose a single-frame PNG.")


def _png(data: bytes, source: Path) -> bytes:
    if not isinstance(data, bytes) or not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Choose a PNG no larger than 32 MiB.")
    buffer = io.BytesIO()
    try:
        with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
            _check_png(image, source)
            image.convert("RGBA").save(buffer, format="PNG")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("The artwork could not be read as a PNG.") from error
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


def frame_artwork(root: Path, frame_set: Path, frame: str) -> tuple[Frame, Image.Image, str, str]:
    """Read a frame's effective image, source digest, and current image fingerprint."""
    state = _state(_edit_directory(root, frame_set) / "timeline.json")
    selected = _selected_frame(root, frame_set, colour_frames(frame_set / "frames"), state, frame)
    image, source_digest, fingerprint = _pixel_snapshot(root, frame_set, selected.source, state["frames"].get(frame, {}))
    return selected, image, source_digest, fingerprint


def describe_pixels(root: Path, frame_set: Path, frame: str, *, include_pixels: bool = True) -> dict:
    """Read a draft source and the fingerprint required to save changes to it."""
    from . import job_palette
    from .job import Job

    _, image, _, fingerprint = frame_artwork(root, frame_set, frame)
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


def _order_checkpoint(state: dict) -> list | dict | None:
    if removed := state.get("removed"):
        return {"order": state.get("order"), "removed": removed}
    return state.get("order")


def _edit_order(root: Path, frame_set: Path, state: dict, sources: list[Path], name: str | None,
                operation: str, value) -> str | None:
    if operation in ("undo", "redo"):
        steps = state.get(operation) or []
        if not steps:
            raise ValueError(f"There is no frame order change to {operation}.")
        other = "redo" if operation == "undo" else "undo"
        state.setdefault(other, []).append(_order_checkpoint(state))
        checkpoint = steps.pop()
        # Older timelines saved just the order list, without any hidden frame IDs.
        if isinstance(checkpoint, dict):
            state.update(checkpoint)
        else:
            state["order"] = checkpoint
            state.pop("removed", None)
        return None

    order = _order(sources, state)
    items, unavailable = _frames(root, frame_set, sources, state)
    visible = [frame.id for frame in items]
    if name not in visible and not (operation == "remove" and name in unavailable):
        raise ValueError("Choose a frame in this timeline.")
    state.setdefault("undo", []).append(_order_checkpoint(state))
    state["redo"] = []
    if operation == "remove":
        if name in visible and len(visible) == 1:
            raise ValueError("Cannot remove the last available frame in this timeline.")
        state["removed"] = [*(state.get("removed") or []), name]
        if name not in visible:
            return None
        position = visible.index(name)
        visible.pop(position)
        return visible[min(position, len(visible) - 1)]

    if operation in ("duplicate", "insert", "insert_blank") and len(visible) + len(unavailable) >= 65_535:
        raise ValueError("This frame set is already at the Aseprite frame limit.")
    if operation in ("insert", "insert_blank"):
        source = items[visible.index(name)].source
        if operation == "insert":
            png = _png(value, source)
        else:
            buffer = io.BytesIO()
            with Image.open(source) as cell:
                Image.new("RGBA", cell.size).save(buffer, format="PNG")
            png = buffer.getvalue()
        insertions = state.setdefault("insertions", {})
        new_id = f"insert-{len(insertions) + 1}"
        insertions[new_id] = _store_png(root, frame_set, png)
        order.insert(order.index(name) + 1, new_id)
        state["order"] = order
        return new_id

    if operation == "duplicate":
        copies = state.setdefault("copies", {})
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
    # Hidden or unavailable frames retain their saved positions if they return later.
    state["order"] = [next(moved) if key in available else key for key in order]
    return name


def _edit_frame(root: Path, frame_set: Path, state: dict, sources: list[Path], name: str | None, operation: str, value) -> bool:
    source = _selected_frame(root, frame_set, sources, state, name).source
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
        if operation == "paint":
            active = _paint(root, frame_set, source, edit, value)
        elif operation == "reprocess":
            from . import frame_repair

            if not isinstance(value, dict) or not isinstance(value.get("fingerprint"), str):
                raise ValueError("Compare the reprocessed frame before applying it.")
            draft = frame_repair.prepare(root, frame_set, name, value.get("despill", "profile"))
            if value["fingerprint"] != draft.fingerprint:
                raise RuntimeError(frame_repair.STALE)
            if not draft.changed_pixels:
                return False
            draft.require_current_inputs()
            digest = _store_png(root, frame_set, draft.candidate)
            draft.require_current_inputs()
            active = {"digest": digest, "source": draft.source_digest}
        else:
            active = _select_replacement(root, frame_set, source, history, operation, value)
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
    playback = _playback(root, frame_set, _frames(root, frame_set, sources, state)[0], settings, None)
    if playback.error:
        raise ValueError(playback.error)
    if first is None and settings["mode"] == "source":
        state.pop("playback", None)
    else:
        state["playback"] = settings


def _edit_tag(root: Path, frame_set: Path, state: dict, sources: list[Path], tag_id: str | None,
              operation: str, value) -> str | None:
    tags = state.get("tags", [])
    index = next((i for i, tag in enumerate(tags) if tag["id"] == tag_id), None)
    if (tag_id is not None or operation == "remove_tag") and index is None:
        raise ValueError("Choose an existing animation tag.")
    if operation == "remove_tag":
        tags.pop(index)
        if not tags:
            state.pop("tags", None)
        return None

    if not isinstance(value, dict) or not isinstance(value.get("name"), str):
        raise ValueError("Enter a name for the animation tag.")
    name = normalize("NFC", value["name"].strip())
    if not name or not name.isprintable() or "[" in name or "]" in name:
        raise ValueError("Enter a printable animation tag name without square brackets.")
    facing, action, _ = frame_set.relative_to(root / "04_pixel").parts
    if len(f"{action}_{facing} [{name}]".encode("utf-8")) > 65_535:
        raise ValueError("The exported animation tag name exceeds the Aseprite file format limit.")
    if any(tag["name"].casefold() == name.casefold() and tag["id"] != tag_id for tag in tags):
        raise ValueError("An animation tag with that name already exists in this frame set.")
    first, last, loop = value.get("start_frame"), value.get("end_frame"), value.get("loop")
    if not isinstance(first, str) or not isinstance(last, str) or type(loop) is not bool:
        raise ValueError("Choose both tag endpoints and whether the tag loops.")
    items, _ = _frames(root, frame_set, sources, state)
    _, _, error = _range_positions({frame.id: i for i, frame in enumerate(items)}, first, last)
    if error:
        raise ValueError(error)
    tag_id = uuid4().hex if tag_id is None else tag_id
    tag = {"id": tag_id, "name": name, "start_frame": first, "end_frame": last, "loop": loop}
    if index is None:
        # One slot remains for the ordinary Aseprite animation tag.
        if len(tags) >= 65_534:
            raise ValueError("This clip is already at the Aseprite tag limit.")
        tags.append(tag)
    else:
        tags[index] = tag
    state["tags"] = tags
    return tag_id


def selected_result(operation: str, selected: str | None) -> dict:
    if operation in TAG_OPERATIONS:
        return {"selected_frame": None, "selected_tag": selected}
    return {"selected_frame": selected}


def update(root: Path, frame_set: Path, name: str | None, operation: str, value=None) -> str | None:
    from . import manifest
    from .job import Job

    if operation not in (*ORDER_OPERATIONS, *TAG_OPERATIONS, "duration", "replace", "restore", "activate", "paint", "playback", "reprocess"):
        raise ValueError("Unknown timeline operation.")
    if operation not in (*TAG_OPERATIONS, "undo", "redo", "playback") and (
        not isinstance(name, str) or re.fullmatch(r"(?:[0-9]{3}\.png|(?:copy|insert)-[1-9][0-9]*)", name) is None
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
            selected = _edit_order(root, frame_set, state, sources, name, operation, value)
        elif operation in TAG_OPERATIONS:
            selected = _edit_tag(root, frame_set, state, sources, name, operation, value)
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
    clip = _clip(root, frame_set, colour_frames(frame_set / "frames"), state)
    items, playback = clip.items, clip.playback
    if not items and not clip.unavailable:
        raise FileNotFoundError("Pixelize the action to open its timeline.")
    facing, action, name = frame_set.relative_to(root / "04_pixel").parts
    report = checks.read(root / "05_qa" / facing / action / name / "report.json") or {}
    default_ms = round(1000 / action_fps(base_fps, name))
    cell = None
    if items or clip.sources:
        with Image.open(items[0].source if items else clip.sources[0]) as image:
            cell = list(image.size)
    return {"facing": facing, "action": action, "frame_set": name, "cell": cell, "loop": playback.loop,
            "playback": asdict(playback), "tags": clip.describe_tags(),
            "default_ms": default_ms, "max_duration_ms": MAX_DURATION_MS, "max_image_bytes": MAX_IMAGE_BYTES,
            "qa_needs_review": qa_needs_review(report, clip), "unavailable": clip.unavailable,
            "can_undo": bool(state.get("undo")), "can_redo": bool(state.get("redo")),
            "frames": [{"id": f.id, "name": f.source_id, "image": f.image.relative_to(root).as_posix(),
                        "inserted": f.inserted,
                        "duration_ms": t, "timing_edited": f.duration_ms is not None,
                        "replaced": f.replaced, "conflict": f.conflict,
                        "history": _history_view(root, frame_set, f, state["frames"].get(f.id, {}))}
                       for f, t in zip(items, timings(items, default_ms))]}
