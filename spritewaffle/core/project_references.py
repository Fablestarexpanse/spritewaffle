"""Portable, source-preserving image references for a jobs folder."""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from . import fsutil, project

MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_PIXELS = 16 * 1024 * 1024
THUMBNAIL_SIZE = 192
FORMATS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
TEXT_LIMITS = {"name": 120, "collection": 80, "notes": 4096}
REFERENCE_ID = re.compile(r"[0-9a-f]{32}")


def _catalog(record: dict) -> dict:
    entries = record.get("references", {})
    if not isinstance(entries, dict):
        raise ValueError("Project references must be a JSON object")
    return entries


def _image_path(base: Path, reference_id: str, suffix: str) -> Path:
    if not REFERENCE_ID.fullmatch(reference_id):
        raise ValueError("Invalid project reference ID")
    path = Path(base).resolve() / "_references" / f"{reference_id}{suffix}"
    if path.resolve() != path:
        raise ValueError("Project reference files must be stored directly in the jobs folder's _references directory")
    return path


def _view(base: Path, reference_id: str, entry: dict) -> dict:
    original = _image_path(base, reference_id, FORMATS[entry["format"]])
    return {**entry, "id": reference_id, "available": original.is_file()}


def list_all(base: Path, include_archived: bool = False) -> list[dict]:
    entries = _catalog(project.read(base))
    return [_view(base, ref_id, entry) for ref_id, entry in entries.items() if include_archived or not entry["archived"]]


def _get(entries: dict, reference_id: str) -> dict:
    if not isinstance(reference_id, str) or not REFERENCE_ID.fullmatch(reference_id):
        raise ValueError("Invalid project reference ID")
    if reference_id not in entries:
        raise FileNotFoundError(f"No project reference with ID {reference_id}")
    return entries[reference_id]


def image(base: Path, reference_id: str, thumbnail: bool = False, *, active_only: bool = False) -> Path:
    entry = _get(_catalog(project.read(base)), reference_id)
    if active_only and entry["archived"]:
        raise ValueError("This project reference is archived. Restore it or choose another image.")
    original = _image_path(base, reference_id, FORMATS[entry["format"]])
    if not original.is_file():
        raise FileNotFoundError(f"Image for project reference {reference_id} is missing")
    if thumbnail:
        preview = _image_path(base, reference_id, ".thumb.png")
        if preview.is_file():
            return preview
    return original


def _clean_fields(changes: dict) -> dict:
    if not isinstance(changes, dict):
        raise ValueError("Reference details must be a JSON object")
    if unknown := changes.keys() - (TEXT_LIMITS.keys() | {"archived"}):
        raise ValueError(f"Unknown reference fields: {', '.join(sorted(unknown))}")
    clean = {}
    for field, value in changes.items():
        if field == "archived":
            if not isinstance(value, bool):
                raise ValueError("Archived must be true or false")
            clean[field] = value
        else:
            if not isinstance(value, str) or len(value.strip()) > TEXT_LIMITS[field] or "\x00" in value:
                raise ValueError(f"{field.capitalize()} must be text up to {TEXT_LIMITS[field]} characters")
            value = value.strip()
            if field == "name" and not value:
                raise ValueError("Give the reference a name")
            clean[field] = "General" if field == "collection" and not value else value
    return clean


def _inspect_image(data: bytes) -> tuple[str, tuple[int, int], bytes]:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Choose an image no larger than 16 MiB")
    try:
        with Image.open(BytesIO(data), formats=list(FORMATS)) as source:
            fmt = source.format
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("Reference images must have at most 16,777,216 pixels")
            if getattr(source, "is_animated", False):
                raise ValueError("Choose a single still image for the reference library")
            source.verify()
        with Image.open(BytesIO(data), formats=[fmt]) as source:
            preview = ImageOps.exif_transpose(source).convert("RGBA")
        dimensions = preview.size
        preview.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE), Image.Resampling.LANCZOS)
        result = BytesIO()
        preview.save(result, "PNG")
        return fmt, dimensions, result.getvalue()
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError("Choose a valid PNG, JPEG, or WebP reference image") from error


def add(base: Path, data: bytes, filename: str, *, name: str = "", collection: str = "", notes: str = "") -> dict:
    if not isinstance(filename, str) or "\x00" in filename:
        raise ValueError("An original image filename is required")
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not filename or len(filename) > 255:
        raise ValueError("An original image filename is required (max 255 characters)")
    if isinstance(name, str) and not name.strip():
        name = Path(filename).stem[:TEXT_LIMITS["name"]]
    details = _clean_fields({"name": name, "collection": collection, "notes": notes, "archived": False})
    fmt, (width, height), thumbnail = _inspect_image(data)
    ref_id = uuid4().hex
    entry = {**details, "filename": filename, "format": fmt, "width": width, "height": height}
    stored = []
    try:
        with project.edit(base) as record:
            entries = _catalog(record)
            original = _image_path(base, ref_id, FORMATS[fmt])
            preview = _image_path(base, ref_id, ".thumb.png")
            original.parent.mkdir(exist_ok=True)
            for path, contents in ((original, data), (preview, thumbnail)):
                fsutil.write_bytes(path, contents)
                stored.append(path)
            entries[ref_id] = entry
            record["references"] = entries
    except Exception:
        for path in stored:
            path.unlink(missing_ok=True)
        raise
    return _view(base, ref_id, entry)


def import_file(base: Path, path: Path, **details) -> dict:
    path = Path(path)
    with path.open("rb") as stream:
        return add(base, stream.read(MAX_IMAGE_BYTES + 1), path.name, **details)


def update(base: Path, ref_id: str, changes: dict) -> dict:
    clean = _clean_fields(changes)
    _get(_catalog(project.read(base)), ref_id)
    with project.edit(base) as record:
        entries = _catalog(record)
        entry = _get(entries, ref_id) | clean
        result = _view(base, ref_id, entry)
        entries[ref_id] = entry
        return result
