"""LDtk 1.5 project for one saved terrain map (written into the map ZIP as map.ldtk).

Layout follows a project saved by LDtk 1.5.3 itself (its bundled samples): one level with a
"Tiles" layer (each cell's tile from tiles.png) under a "Collision" IntGrid layer (1 = solid,
2 = one-way). LDtk has no collision polygons, so each tile's exact polygon, one-way flag and
properties go into the tileset's per-tile custom data as JSON, where a game reads them.
Map objects stay in the Tiled map (map.tmj); LDtk entities are not written.

IDs are derived from the map name and size (uuid5), so the same map exports the same file.
"""
from __future__ import annotations

import json
import uuid

JSON_VERSION = "1.5.3"
SOLID, ONE_WAY = 1, 2
_NS = uuid.UUID("6f1c2a4e-5b7d-4e8a-9c3f-2d1e0b9a8c7d")


def supported(grid: dict) -> str | None:
    """None when LDtk can hold this tileset, else the reason it cannot."""
    if grid["tile_width"] != grid["tile_height"]:
        return f"LDtk needs square tiles; these are {grid['tile_width']} x {grid['tile_height']} px"
    return None


def _iid(*parts) -> str:
    return str(uuid.uuid5(_NS, "/".join(str(p) for p in parts)))


def _layer_def(identifier: str, kind: str, uid: int, size: int, tileset_uid: int | None, values: list) -> dict:
    return {"__type": kind, "identifier": identifier, "type": kind, "uid": uid, "doc": None,
            "uiColor": None, "gridSize": size, "guideGridWid": 0, "guideGridHei": 0,
            "displayOpacity": 0.4 if kind == "IntGrid" else 1, "inactiveOpacity": 0.4 if kind == "IntGrid" else 1,
            "hideInList": False, "hideFieldsWhenInactive": True, "canSelectWhenInactive": True,
            "renderInWorldView": True, "pxOffsetX": 0, "pxOffsetY": 0, "parallaxFactorX": 0,
            "parallaxFactorY": 0, "parallaxScaling": True, "requiredTags": [], "excludedTags": [],
            "autoTilesKilledByOtherLayerUid": None, "uiFilterTags": [], "useAsyncRender": False,
            "intGridValues": values, "intGridValuesGroups": [], "autoRuleGroups": [],
            "autoSourceLayerDefUid": None, "tilesetDefUid": tileset_uid, "tilePivotX": 0, "tilePivotY": 0,
            "biomeFieldUid": None}


def project(name: str, resolved: dict, tiles: list[dict], grid: dict) -> dict:
    """resolved: the map preview (width, height, tiles rows of tile id or None). tiles: the native
    tileset entries (id, rect, solid, collision, properties)."""
    size = grid["tile_width"]
    width, height = resolved["width"], resolved["height"]
    by_id = {t["id"]: t for t in tiles}
    tileset_uid, tiles_uid, collision_uid, level_uid = 1, 2, 3, 0
    ident = "".join(c if c.isalnum() else "_" for c in name).strip("_") or "Map"
    if ident[0].isdigit():
        ident = "Map_" + ident
    grid_tiles, int_grid = [], []
    for y, row in enumerate(resolved["tiles"]):
        for x, tile in enumerate(row):
            entry = by_id.get(tile) if tile is not None else None
            if entry is None:
                int_grid.append(0)
                continue
            rx, ry = entry["rect"][0], entry["rect"][1]
            grid_tiles.append({"px": [x * size, y * size], "src": [rx, ry], "f": 0, "t": tile,
                               "d": [y * width + x], "a": 1})
            one_way = bool((entry.get("collision") or {}).get("one_way"))
            int_grid.append(ONE_WAY if entry.get("solid") and one_way else SOLID if entry.get("solid") else 0)
    custom = []
    for t in tiles:
        data = {}
        if t.get("solid"):
            col = t.get("collision") or {}
            data["collision"] = col.get("polygon") or [[0, 0], [size, 0], [size, size], [0, size]]
            if col.get("one_way"):
                data["one_way"] = True
        if t.get("properties"):
            data["properties"] = t["properties"]
        if data:
            custom.append({"tileId": t["id"], "data": json.dumps(data, separators=(",", ":"))})
    values = [{"value": SOLID, "identifier": "solid", "color": "#E03C3C", "tile": None, "groupUid": 0},
              {"value": ONE_WAY, "identifier": "one_way", "color": "#3CA0E0", "tile": None, "groupUid": 0}]
    layer_inst = lambda ident_, kind, uid, extra: {   # noqa: E731
        "__identifier": ident_, "__type": kind, "__cWid": width, "__cHei": height, "__gridSize": size,
        "__opacity": 1, "__pxTotalOffsetX": 0, "__pxTotalOffsetY": 0,
        "__tilesetDefUid": tileset_uid if kind == "Tiles" else None,
        "__tilesetRelPath": "tiles.png" if kind == "Tiles" else None,
        "iid": _iid(name, width, height, ident_), "levelId": level_uid, "layerDefUid": uid,
        "pxOffsetX": 0, "pxOffsetY": 0, "visible": True, "optionalRules": [],
        "intGridCsv": [], "autoLayerTiles": [], "seed": 0, "overrideTilesetUid": None,
        "gridTiles": [], "entityInstances": [], **extra}
    return {
        "__header__": {"fileType": "LDtk Project JSON", "app": "LDtk", "doc": "https://ldtk.io/json",
                       "schema": "https://ldtk.io/files/JSON_SCHEMA.json", "appAuthor": "Sebastien 'deepnight' Benard",
                       "appVersion": JSON_VERSION, "url": "https://ldtk.io"},
        "iid": _iid(name, width, height), "jsonVersion": JSON_VERSION, "appBuildId": 0, "nextUid": 4,
        "identifierStyle": "Capitalize", "toc": [], "worldLayout": "Free", "worldGridWidth": width * size,
        "worldGridHeight": height * size, "defaultLevelWidth": width * size, "defaultLevelHeight": height * size,
        "defaultPivotX": 0, "defaultPivotY": 0, "defaultGridSize": size, "defaultEntityWidth": size,
        "defaultEntityHeight": size, "bgColor": "#40465B", "defaultLevelBgColor": "#696A79", "minifyJson": False,
        "externalLevels": False, "exportTiled": False, "simplifiedExport": False, "imageExportMode": "None",
        "exportLevelBg": True, "pngFilePattern": None, "backupOnSave": False, "backupLimit": 10,
        "backupRelPath": None, "levelNamePattern": "Level_%idx", "tutorialDesc": None, "customCommands": [],
        "flags": [], "worlds": [], "dummyWorldIid": _iid(name, "world"),
        "defs": {
            "layers": [_layer_def("Collision", "IntGrid", collision_uid, size, None, values),
                       _layer_def("Tiles", "Tiles", tiles_uid, size, tileset_uid, [])],
            "entities": [], "enums": [], "externalEnums": [], "levelFields": [],
            "tilesets": [{"__cWid": grid["columns"], "__cHei": grid["rows"], "identifier": "Tiles",
                          "uid": tileset_uid, "relPath": "tiles.png", "embedAtlas": None,
                          "pxWid": grid["width"], "pxHei": grid["height"], "tileGridSize": size,
                          "spacing": grid["spacing"], "padding": grid["margin"], "tags": [],
                          "tagsSourceEnumUid": None, "enumTags": [], "customData": custom,
                          "savedSelections": [], "cachedPixelData": None}]},
        "levels": [{"identifier": ident, "iid": _iid(name, width, height, "level"), "uid": level_uid,
                    "worldX": 0, "worldY": 0, "worldDepth": 0, "pxWid": width * size, "pxHei": height * size,
                    "__bgColor": "#696A79", "bgColor": None, "useAutoIdentifier": False, "bgRelPath": None,
                    "bgPos": None, "bgPivotX": 0.5, "bgPivotY": 0.5, "__smartColor": "#ADADB5", "__bgPos": None,
                    "externalRelPath": None, "fieldInstances": [], "__neighbours": [],
                    "layerInstances": [layer_inst("Collision", "IntGrid", collision_uid, {"intGridCsv": int_grid}),
                                       layer_inst("Tiles", "Tiles", tiles_uid, {"gridTiles": grid_tiles})]}],
    }
