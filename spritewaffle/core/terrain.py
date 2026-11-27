"""Rectangular terrain transitions with shared, named corner assignments.

Two rule modes: "corner" (default; each tile lists NW, NE, SE, SW) and "mixed" (blob / 47-tile
sets: each tile lists N, NE, E, SE, S, SW, W, NW, Tiled's mixed Wang order). SpriteWaffle's map
preview paints corners, so it resolves corner sets; mixed sets are painted in Tiled or Godot
(audit 2026-11-26 P1 #3), and both exports carry them.
"""
from __future__ import annotations

MAX_COLORS = 8
MAX_SIDE = 64                 # tiles per map side (was 32; raised 2026-11-26 with a Size control in the map panel)
SWATCHES = ("#699154", "#5782b0", "#b89459", "#a16d58", "#8b72a5", "#659a90", "#d0b763", "#96a0b0")


def normalize(value: dict, count: int) -> dict:
    if not isinstance(value, dict) or value.keys() - {"colors", "tiles", "mode", "centers"}:
        raise ValueError("Terrain needs a colors list and tile corner assignments.")
    mode = value.get("mode") or "corner"
    if mode not in ("corner", "mixed"):
        raise ValueError("Terrain mode must be corner or mixed.")
    slots = 4 if mode == "corner" else 8
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
        if not isinstance(corners, list) or len(corners) != slots:
            raise ValueError(f"Tile {i} needs four corners in NW, NE, SE, SW order." if slots == 4 else
                             f"Tile {i} needs eight entries in N, NE, E, SE, S, SW, W, NW order.")
        for name in corners:
            if name is not None and (not isinstance(name, str) or name not in valid):
                raise ValueError(f"Tile {i} has an unknown terrain {name!r}. Clear its corners before removing a terrain.")
        if any(name is not None for name in corners):
            assigned[key] = corners
    centers = value.get("centers") or {}
    if not isinstance(centers, dict) or any(not str(k).isdecimal() or not 0 <= int(k) < count or n not in valid
                                            for k, n in centers.items()):
        raise ValueError("Tile centres must map tile IDs in the grid to terrain names.")
    return {"colors": names, "tiles": assigned, **({"mode": "mixed"} if mode == "mixed" else {}),
            **({"centers": {str(int(k)): n for k, n in centers.items()}} if centers else {})}


def _matches(rules: dict) -> dict[tuple, int]:
    """First tile for each assignment (pure tiles: the whole tuple is one terrain)."""
    matches = {}
    for key in sorted(rules["tiles"], key=int):
        matches.setdefault(tuple(rules["tiles"][key]), int(key))
    return matches


def _all_matches(rules: dict) -> dict[tuple, list[int]]:
    """Every tile for each assignment (variants share one), in tile order."""
    matches: dict[tuple, list[int]] = {}
    for key in sorted(rules["tiles"], key=int):
        matches.setdefault(tuple(rules["tiles"][key]), []).append(int(key))
    return matches


def _pick(tiles: list[int], weights: dict[int, float], x: int, y: int) -> int:
    """One of the variants for cell (x, y), by tile weight (default 1; 0 = only if nothing else).
    The same cell always gets the same tile for the same weights, so saving and exporting agree."""
    from hashlib import sha256
    live = [(t, weights.get(t, 1.0)) for t in tiles if weights.get(t, 1.0) > 0]
    if len(live) <= 1:
        return live[0][0] if live else tiles[0]
    u = int.from_bytes(sha256(f"{x},{y}".encode()).digest()[:8], "big") / 2 ** 64 * sum(w for _, w in live)
    for tile, w in live:
        u -= w
        if u < 0:
            return tile
    return live[-1][0]


def preview(rules: dict, vertices: list, *, allow_unknown: bool = False, weights: dict[int, float] | None = None) -> dict:
    """weights: mix variants (tiles with the same corners) by tile weight, per cell; None keeps the
    first tile for every corner pattern (maps saved before mixing look the same)."""
    if rules.get("mode") == "mixed":
        raise ValueError("This tileset uses a blob (mixed) terrain set: paint maps with it in Tiled or Godot. "
                         "SpriteWaffle's map preview paints corner sets.")
    if (not isinstance(vertices, list) or not 2 <= len(vertices) <= MAX_SIDE + 1
            or not isinstance(vertices[0], list) or not 2 <= len(vertices[0]) <= MAX_SIDE + 1
            or any(not isinstance(row, list) or len(row) != len(vertices[0]) for row in vertices)):
        raise ValueError(f"Give a rectangular corner grid for a map of 1 to {MAX_SIDE} tiles per side.")
    valid = set(rules["colors"])
    if any(name is not None and (not isinstance(name, str) or not name.strip() or len(name) > 40
                                 or len(name.splitlines()) != 1 or (not allow_unknown and name not in valid))
           for row in vertices for name in row):
        raise ValueError("The preview uses terrain names from the tileset or null for an unpainted corner.")
    matches = _matches(rules)
    variants = _all_matches(rules) if weights is not None else {}
    width, height = len(vertices[0]) - 1, len(vertices) - 1
    cells, missing = [], []
    for y in range(height):
        row = []
        for x in range(width):
            corners = (vertices[y][x], vertices[y][x+1], vertices[y+1][x+1], vertices[y+1][x])
            tile = _pick(variants[corners], weights, x, y) if corners in variants else matches.get(corners)
            row.append(tile)
            if tile is None and any(name is not None for name in corners):
                missing.append([x, y])
        cells.append(row)
    return {"width": width, "height": height, "tiles": cells, "missing": missing}


def tiled_wangset(rules: dict) -> dict:
    colors = {name: i + 1 for i, name in enumerate(rules["colors"])}
    matches = _matches(rules)
    wangtiles = []
    mixed = rules.get("mode") == "mixed"
    for key in sorted(rules["tiles"], key=int):
        if mixed:                                               # already Tiled's order: N NE E SE S SW W NW
            wangtiles.append({"tileid": int(key), "wangid": [colors.get(name, 0) for name in rules["tiles"][key]]})
            continue
        nw, ne, se, sw = (colors.get(name, 0) for name in rules["tiles"][key])
        wangtiles.append({"tileid": int(key), "wangid": [0, ne, 0, se, 0, sw, 0, nw]})
    icons = [matches.get((name,) * (8 if mixed else 4), -1) for name in colors]
    return {"name": "Terrain", "type": "mixed" if mixed else "corner",
            "tile": next((t for t in icons if t >= 0), -1),           # the set's icon in Tiled's terrain panel
            "colors": [{"name": name, "color": swatch, "probability": 1, "tile": icon}
                       for name, swatch, icon in zip(colors, SWATCHES, icons)], "wangtiles": wangtiles}
