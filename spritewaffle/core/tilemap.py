"""Named terrain maps owned by a tileset job."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import re
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from . import fsutil, map_objects, tileset
from .job import Job

MAX_MAPS = 64


def _registry(directory: Path) -> Path:
    path = directory / "maps.json"
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Saved maps must stay inside the tileset job.")
    return path


def _read(directory: Path) -> dict:
    try:
        data = json.loads(fsutil.read_text(_registry(directory)))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("maps"), dict):
        raise ValueError("The saved map registry has an unsupported format.")
    for key, record in data["maps"].items():
        _validate_id(key)
        if not isinstance(record, dict) or not isinstance(record.get("name"), str) or "vertices" not in record:
            raise ValueError("The saved map record is invalid.")
    return data["maps"]


def _validate_id(map_id: str) -> None:
    if not isinstance(map_id, str) or not re.fullmatch(r"[0-9a-f]{32}", map_id):
        raise ValueError("Choose a valid saved map ID.")


def _get(maps: dict, map_id: str) -> dict:
    _validate_id(map_id)
    if map_id not in maps:
        raise ValueError("The saved map was not found in this tileset.")
    return maps[map_id]


def _view(map_id: str, record: dict) -> dict:
    return {"id": map_id, **record, "revision": tileset._revision(record)}


def list_maps(job: Job) -> list[dict]:
    maps = _read(tileset._workspace(job))
    return [{"id": key, "name": record["name"]}
            for key, record in sorted(maps.items(), key=lambda item: (item[1]["name"].casefold(), item[0]))]


def load(job: Job, map_id: str) -> dict:
    return _view(map_id, _get(_read(tileset._workspace(job)), map_id))


def _objects(entries: list, layout: dict, record: dict) -> list[dict]:
    grid = record["grid"]
    return map_objects.normalize(entries, layout["width"] * layout["height"], grid["columns"] * grid["rows"],
                                 tileset._atlas_revision(record), tileset.MAX_TILES)


def save(job: Job, name: str, vertices: list, map_id: str | None = None, revision: str | None = None,
         tileset_revision: str | None = None, *, overrides: dict | None = None,
         override_atlas: str | None = None, objects: list | None = None) -> dict:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or len(name.strip().splitlines()) != 1:
        raise ValueError("Enter a map name of 1 to 80 characters on one line.")
    with tileset._locked_record(job) as (directory, record):
        if tileset_revision is not None and tileset_revision != tileset._revision(record):
            raise ValueError("The tileset changed. Reload it before saving the map.")
        maps = _read(directory)
        if map_id is not None:
            current = _get(maps, map_id)
            if revision != tileset._revision(current):
                raise ValueError("The saved map changed. Open it again before saving.")
            if overrides is None:
                overrides, override_atlas = current.get("overrides"), current.get("override_atlas")
            if objects is None:
                objects = current.get("objects")
        else:
            if len(maps) >= MAX_MAPS:
                raise ValueError(f"A tileset can hold up to {MAX_MAPS} saved maps.")
            map_id = uuid4().hex
        layout = tileset._preview(record, vertices, overrides=overrides, override_atlas=override_atlas)
        draft = {"name": name.strip(), "vertices": vertices}
        if overrides:
            draft["overrides"] = overrides
            if any(tile is not None for tile in overrides.values()):
                draft["override_atlas"] = override_atlas or tileset._atlas_revision(record)
        if objects is not None:
            objects = _objects(objects, layout, record)
            if objects:
                draft["objects"] = objects
        maps[map_id] = draft
        fsutil.write_text(_registry(directory), json.dumps({"version": 1, "maps": maps}, ensure_ascii=False))
    return _view(map_id, draft)


def _tiled_map(name: str, preview: dict, grid: dict) -> dict:
    width, height = preview["width"], preview["height"]
    data = [0 if tile is None else tile + 1 for row in preview["tiles"] for tile in row]
    return {"type": "map", "version": "1.10", "tiledversion": tileset.TILED_VERSION,
            "orientation": "orthogonal", "renderorder": "right-down",
            "width": width, "height": height, "tilewidth": grid["tile_width"], "tileheight": grid["tile_height"],
            "infinite": False, "nextlayerid": 2, "nextobjectid": 1,
            "tilesets": [{"firstgid": 1, "source": "tileset.tsj"}],
            "layers": [{"type": "tilelayer", "id": 1, "name": name, "visible": True, "opacity": 1,
                        "x": 0, "y": 0, "width": width, "height": height, "data": data}]}


def export(job: Job, map_id: str, revision: str | None = None, tileset_revision: str | None = None,
           allow_empty: bool = False) -> dict:
    """Write the map ZIP. Unresolved cells refuse the export unless allow_empty: then they are
    left empty (Tiled gid 0) and listed under "empty_cells" in map.json."""
    with tileset._locked_record(job) as (directory, record):
        saved = _get(_read(directory), map_id)
        if revision is not None and revision != tileset._revision(saved):
            raise ValueError("The saved map changed. Open it again before exporting.")
        if tileset_revision is not None and tileset_revision != tileset._revision(record):
            raise ValueError("The tileset changed. Reload it before exporting the map.")
        corners = saved["vertices"]
        resolved = tileset._preview(record, corners, allow_unknown=True, overrides=saved.get("overrides"),
                                    override_atlas=saved.get("override_atlas"))
        objects = _objects(saved.get("objects", []), resolved, record)
        atlas = tileset._atlas_revision(record)
        outdated = next((entry for entry in objects if entry["atlas"] != atlas), None)
        if outdated:
            raise ValueError(f"{outdated['name']} uses a previous atlas. Update its state tiles before exporting.")
        if (missing := resolved["missing"]) and not allow_empty:
            x, y = missing[0]
            raise ValueError(f"The map has {len(missing)} unresolved cells, starting at ({x + 1}, {y + 1}). "
                             "Update its tile placement or terrain before exporting.")
        _, image = tileset._export_image(directory, record)
        native_tiles, tiled_tiles = tileset._export_metadata(record, job.root.parent.name)
        native = {"schema_version": 1, "name": saved["name"], "tileset": "tileset.json", "vertices": corners, **resolved}
        if missing:
            native["empty_cells"] = missing
        if "overrides" in saved:
            native["overrides"] = saved["overrides"]
        tiled = _tiled_map(saved["name"], resolved, record["grid"])
        if objects:
            native["objects"] = objects
            tiled["layers"].append(map_objects.tiled_layer(objects, resolved["width"], record["grid"],
                                                           record["solid_tiles"]))
            tiled["nextlayerid"] = 3
            tiled["nextobjectid"] = len(objects) + 1
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as package:
            for filename, data in (("map.json", native), ("map.tmj", tiled),
                                   ("tileset.json", native_tiles), ("tileset.tsj", tiled_tiles)):
                package.writestr(filename, json.dumps(data, indent=2))
            package.writestr("tiles.png", image)
        output = job.root / "06_export" / "maps" / (map_id + ".zip")
        if not output.resolve().is_relative_to(job.root.resolve()):
            raise ValueError("Map exports must stay inside the tileset job.")
        output.parent.mkdir(parents=True, exist_ok=True)
        fsutil.write_bytes(output, buffer.getvalue())
    return {"id": map_id, "name": saved["name"], "file": output.relative_to(job.root).as_posix(),
            "empty_cells": len(missing)}
