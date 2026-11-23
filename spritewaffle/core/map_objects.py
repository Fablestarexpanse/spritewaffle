"""Cell-aligned map objects with named atlas states."""
from __future__ import annotations

import json
import re

MAX_OBJECTS = 64
MAX_STATES = 8


def _label(value: str, limit: int, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit or len(value.strip().splitlines()) != 1:
        raise ValueError(f"Enter {label} of 1 to {limit} characters on one line.")
    return value.strip()


def definition(entry: dict, tile_count: int, atlas: str, max_tiles: int) -> dict:
    name = _label(entry.get("name"), 80, "an object name")
    kind = _label(entry.get("kind", "object"), 40, "an object type")
    bound = entry.get("atlas", atlas)
    if not isinstance(bound, str) or not re.fullmatch(r"[0-9a-f]{64}", bound):
        raise ValueError(f"{name} has an invalid atlas revision.")
    count = tile_count if bound == atlas else max_tiles
    states = entry.get("states")
    if not isinstance(states, list) or not 2 <= len(states) <= MAX_STATES:
        raise ValueError(f"{name} needs 2 to {MAX_STATES} states.")
    names = set()
    options = []
    for state in states:
        if not isinstance(state, dict) or set(state) != {"name", "tile"}:
            raise ValueError("Each object state needs a name and an atlas tile ID.")
        label = _label(state["name"], 40, "a state name")
        if label.casefold() in names:
            raise ValueError(f"{name} has duplicate state names.")
        names.add(label.casefold())
        tile = state["tile"]
        if type(tile) is not int or not 0 <= tile < count:
            raise ValueError(f"{name}: state {label} needs a tile ID within the atlas.")
        options.append({"name": label, "tile": tile})
    active = _label(entry.get("state"), 40, "an active state name")
    if all(option["name"] != active for option in options):
        raise ValueError(f"{name}: select one of its defined states as active.")
    return {"name": name, "kind": kind, "state": active, "states": options, "atlas": bound}


def normalize(objects: list, cell_count: int, tile_count: int, atlas: str, max_tiles: int) -> list[dict]:
    if not isinstance(objects, list) or len(objects) > MAX_OBJECTS:
        raise ValueError(f"Use a list of up to {MAX_OBJECTS} map objects.")
    ids, cells = set(), set()
    result = []
    for entry in objects:
        if not isinstance(entry, dict) or entry.keys() - {"id", "name", "kind", "cell", "state", "states", "atlas", "template_id"}:
            raise ValueError("Each object needs an ID, name, cell, and named states.")
        key, cell = entry.get("id"), entry.get("cell")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key) or key in ids:
            raise ValueError("Object IDs must be unique and use lowercase letters, numbers, hyphens, or underscores.")
        if type(cell) is not int or not 0 <= cell < cell_count or cell in cells:
            raise ValueError("Place each object in a different cell within the map.")
        ids.add(key)
        cells.add(cell)
        fields = definition(entry, tile_count, atlas, max_tiles)
        instance = {"id": key, "name": fields["name"], "kind": fields["kind"], "cell": cell,
                    "state": fields["state"], "states": fields["states"], "atlas": fields["atlas"]}
        if "template_id" in entry:
            template_id = entry["template_id"]
            if not isinstance(template_id, str) or not re.fullmatch(r"[0-9a-f]{32}", template_id):
                raise ValueError("Object template IDs must be 32 lowercase hexadecimal digits.")
            instance["template_id"] = template_id
        result.append(instance)
    return result


def tiled_layer(objects: list[dict], width: int, grid: dict, solid_tiles: list[int]) -> dict:
    w, h = grid["tile_width"], grid["tile_height"]
    solids = set(solid_tiles)
    instances = []
    for number, entry in enumerate(objects, start=1):
        row, column = divmod(entry["cell"], width)
        tile = next(state["tile"] for state in entry["states"] if state["name"] == entry["state"])
        properties = [
            {"name": "spritewaffle_id", "type": "string", "value": entry["id"]},
            {"name": "state", "type": "string", "value": entry["state"]},
            {"name": "states", "type": "string", "value": json.dumps(entry["states"], ensure_ascii=False)},
            {"name": "solid", "type": "bool", "value": tile in solids},
        ]
        if "template_id" in entry:
            properties.append({"name": "spritewaffle_template", "type": "string", "value": entry["template_id"]})
        instances.append({"id": number, "name": entry["name"], "type": entry["kind"], "gid": tile + 1,
                          "x": column * w, "y": (row + 1) * h, "width": w, "height": h,
                          "rotation": 0, "visible": True, "properties": properties})
    return {"id": 2, "name": "Objects", "type": "objectgroup", "draworder": "index", "opacity": 1,
            "visible": True, "x": 0, "y": 0, "objects": instances}
