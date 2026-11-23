"""Reusable map object definitions scoped to a tileset job."""
from __future__ import annotations

import json
from pathlib import Path
import re
from uuid import uuid4

from . import fsutil, map_objects, terrain, tileset
from .job import Job

MAX_TEMPLATES = 64


def _path(directory: Path) -> Path:
    target = directory / "object_templates.json"
    if not target.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Object templates must stay inside the tileset job.")
    return target


def _read(directory: Path) -> list[dict]:
    try:
        library = json.loads(fsutil.read_text(_path(directory)))
    except FileNotFoundError:
        return []
    if (not isinstance(library, dict) or library.get("version") != 1
            or not isinstance(library.get("templates"), list)
            or any(not isinstance(entry, dict) or not isinstance(entry.get("name"), str)
                   for entry in library["templates"])):
        raise ValueError("The object template library has an unsupported format.")
    return library["templates"]


def list_templates(job: Job) -> list[dict]:
    return sorted(_read(tileset._workspace(job)), key=lambda template: template["name"].casefold())


def save(job: Job, draft: dict) -> dict:
    if not isinstance(draft, dict) or draft.keys() - {"name", "kind", "state", "states", "atlas"}:
        raise ValueError("An object template needs a name and named atlas states.")
    with tileset._locked_record(job) as (directory, record):
        library = _read(directory)
        if len(library) >= MAX_TEMPLATES:
            raise ValueError(f"A tileset can hold up to {MAX_TEMPLATES} object templates.")
        grid = record["grid"]
        atlas = tileset._atlas_revision(record)
        definition = map_objects.definition(draft, grid["rows"] * grid["columns"], atlas, tileset.MAX_TILES)
        if definition["atlas"] != atlas:
            raise ValueError("This object uses a previous atlas. Update its state tiles before saving a template.")
        if any(entry["name"].casefold() == definition["name"].casefold() for entry in library):
            raise ValueError("An object template already has that name.")
        template = {"id": uuid4().hex, **definition}
        library.append(template)
        fsutil.write_text(_path(directory), json.dumps({"version": 1, "templates": library}, ensure_ascii=False))
    return template


def instantiate(job: Job, template_id: str, cell: int, state: str | None = None) -> dict:
    if not isinstance(template_id, str) or not re.fullmatch(r"[0-9a-f]{32}", template_id):
        raise ValueError("Choose a valid object template ID.")
    with tileset._locked_record(job) as (directory, record):
        source = next((entry for entry in _read(directory) if entry.get("id") == template_id), None)
        if source is None:
            raise ValueError("The object template was not found in this tileset.")
        atlas = tileset._atlas_revision(record)
        if source.get("atlas") != atlas:
            raise ValueError("This template uses a previous atlas. Create a template from tiles on the current atlas.")
        grid = record["grid"]
        instance = {**source, "id": uuid4().hex, "cell": cell, "template_id": template_id}
        if state is not None:
            instance["state"] = state
        placed, = map_objects.normalize([instance], terrain.MAX_SIDE**2, grid["columns"] * grid["rows"],
                                        atlas, tileset.MAX_TILES)
    return placed
