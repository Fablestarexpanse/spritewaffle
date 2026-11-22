"""Rectangular terrain transitions with shared, named corner assignments."""
from __future__ import annotations

MAX_COLORS = 8
MAX_SIDE = 32
SWATCHES = ("#699154", "#5782b0", "#b89459", "#a16d58", "#8b72a5", "#659a90", "#d0b763", "#96a0b0")


def normalize(value: dict, count: int) -> dict:
    if not isinstance(value, dict) or value.keys() - {"colors", "tiles"}:
        raise ValueError("Terrain needs a colors list and tile corner assignments.")
    names, tiles = value.get("colors"), value.get("tiles", {})
    if (not isinstance(names, list) or len(names) > MAX_COLORS
            or any(not isinstance(name, str) or not name.strip() or len(name) > 40 or len(name.splitlines()) != 1
                   for name in names)):
        raise ValueError("Enter up to eight terrain names of 1 to 40 characters.")
    names = [name.strip() for name in names]
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Terrain names must be distinct.")
    if not isinstance(tiles, dict) or len(tiles) > count:
        raise ValueError("Assign corners to tile IDs in the current grid.")
    valid = set(names)
    assigned = {}
    for key, corners in tiles.items():
        if not isinstance(key, str) or not key.isascii() or not key.isdecimal() or len(key) > len(str(count)):
            raise ValueError("Terrain assignments use zero-based tile IDs.")
        i = int(key)
        if str(i) != key or not 0 <= i < count:
            raise ValueError(f"Tile {key} is outside the grid.")
        if not isinstance(corners, list) or len(corners) != 4:
            raise ValueError(f"Tile {i} needs four corners in NW, NE, SE, SW order.")
        for name in corners:
            if name is not None and (not isinstance(name, str) or name not in valid):
                raise ValueError(f"Tile {i} has an unknown terrain {name!r}. Clear its corners before removing a terrain.")
        if any(name is not None for name in corners):
            assigned[key] = corners
    return {"colors": names, "tiles": assigned}


def _matches(rules: dict) -> dict[tuple, int]:
    matches = {}
    for key in sorted(rules["tiles"], key=int):
        matches.setdefault(tuple(rules["tiles"][key]), int(key))
    return matches


def preview(rules: dict, vertices: list) -> dict:
    if (not isinstance(vertices, list) or not 2 <= len(vertices) <= MAX_SIDE + 1
            or not isinstance(vertices[0], list) or not 2 <= len(vertices[0]) <= MAX_SIDE + 1
            or any(not isinstance(row, list) or len(row) != len(vertices[0]) for row in vertices)):
        raise ValueError("Give a rectangular corner grid for a map of 1 to 32 tiles per side.")
    valid = set(rules["colors"])
    if any(name is not None and (not isinstance(name, str) or name not in valid) for row in vertices for name in row):
        raise ValueError("The preview uses terrain names from the tileset or null for an unpainted corner.")
    matches = _matches(rules)
    width, height = len(vertices[0]) - 1, len(vertices) - 1
    cells, missing = [], []
    for y in range(height):
        row = []
        for x in range(width):
            corners = (vertices[y][x], vertices[y][x+1], vertices[y+1][x+1], vertices[y+1][x])
            tile = matches.get(corners)
            row.append(tile)
            if tile is None and any(name is not None for name in corners):
                missing.append([x, y])
        cells.append(row)
    return {"width": width, "height": height, "tiles": cells, "missing": missing}


def tiled_wangset(rules: dict) -> dict:
    colors = {name: i + 1 for i, name in enumerate(rules["colors"])}
    matches = _matches(rules)
    wangtiles = []
    for key in sorted(rules["tiles"], key=int):
        nw, ne, se, sw = (colors.get(name, 0) for name in rules["tiles"][key])
        wangtiles.append({"tileid": int(key), "wangid": [0, ne, 0, se, 0, sw, 0, nw]})
    return {"name": "Terrain", "type": "corner", "tile": -1,
            "colors": [{"name": name, "color": swatch, "probability": 1, "tile": matches.get((name,) * 4, -1)}
                       for name, swatch in zip(colors, SWATCHES)], "wangtiles": wangtiles}
