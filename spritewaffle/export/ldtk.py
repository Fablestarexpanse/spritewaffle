"""LDtk 1.5 project for one saved terrain map (written into the map ZIP as map.ldtk).

Layout follows a project saved by LDtk 1.5.3 itself (its bundled samples): one level with a
"Tiles" layer (each cell's tile from tiles.png) under a "Collision" IntGrid layer (1 = solid,
2 = one-way). LDtk has no collision polygons, so each tile's exact polygon, one-way flag and
properties go into the tileset's per-tile custom data as JSON, where a game reads them.
Map objects become entities on an "Objects" layer: one entity definition per object kind, drawn
with the tile of the object's current state, with fields name, state, states (JSON), solid and
spritewaffle_id (+ spritewaffle_template). Field layout copied from LDtk 1.5.3's Entities sample.

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


_FIELDS = (("name", "String"), ("state", "String"), ("states", "String"), ("solid", "Bool"),
           ("spritewaffle_id", "String"), ("spritewaffle_template", "String"))


def _field_def(identifier: str, kind: str, uid: int) -> dict:
    return {"identifier": identifier, "doc": None, "__type": kind, "uid": uid, "type": f"F_{kind}",
            "isArray": False, "canBeNull": kind != "Bool", "arrayMinLength": None, "arrayMaxLength": None,
            "editorDisplayMode": "Hidden", "editorDisplayScale": 1, "editorDisplayPos": "Above",
            "editorLinkStyle": "CurvedArrow", "editorDisplayColor": None, "editorAlwaysShow": False,
            "editorShowInWorld": True, "editorCutLongValues": True, "editorTextSuffix": None,
            "editorTextPrefix": None, "useForSmartColor": False, "exportToToc": False, "searchable": False,
            "min": None, "max": None, "regex": None, "acceptFileTypes": None,
            "defaultOverride": {"id": "V_Bool", "params": [False]} if kind == "Bool" else None,
            "textLanguageMode": None, "symmetricalRef": False, "autoChainRef": False,
            "allowOutOfLevelRef": True, "allowedRefs": "OnlySame", "allowedRefsEntityUid": None,
            "allowedRefTags": [], "tilesetUid": None}


def _entities(objects: list[dict], by_id: dict, width: int, size: int, tileset_uid: int, name: str,
              first_uid: int) -> tuple[list[dict], list[dict], int]:
    """(entity definitions, entity instances, next uid) for SpriteWaffle map objects."""
    defs, instances, uid = {}, [], first_uid
    for entry in objects:
        kind = "".join(c if c.isalnum() else "_" for c in entry["kind"]).strip("_") or "Object"
        kind = kind[0].upper() + kind[1:] if not kind[0].isdigit() else "Object_" + kind
        state = next(s for s in entry["states"] if s["name"] == entry["state"])
        rect = by_id.get(state["tile"], {}).get("rect", [0, 0, size, size])
        tile = {"tilesetUid": tileset_uid, "x": rect[0], "y": rect[1], "w": size, "h": size}
        if kind not in defs:
            fields = [_field_def(ident, typ, uid + 1 + i) for i, (ident, typ) in enumerate(_FIELDS)]
            defs[kind] = {"identifier": kind, "uid": uid, "tags": [], "exportToToc": False, "allowOutOfBounds": False,
                          "doc": None, "width": size, "height": size, "resizableX": False, "resizableY": False,
                          "minWidth": None, "maxWidth": None, "minHeight": None, "maxHeight": None,
                          "keepAspectRatio": False, "tileOpacity": 1, "fillOpacity": 0.08, "lineOpacity": 0,
                          "hollow": False, "color": "#BE4A2F", "renderMode": "Tile", "showName": True,
                          "tilesetId": tileset_uid, "tileRenderMode": "FitInside", "tileRect": tile,
                          "uiTileRect": None, "nineSliceBorders": [], "maxCount": 0, "limitScope": "PerLevel",
                          "limitBehavior": "MoveLastOne", "pivotX": 0, "pivotY": 0, "fieldDefs": fields}
            uid += 1 + len(_FIELDS)
        d = defs[kind]
        values = {"name": entry["name"], "state": entry["state"],
                  "states": json.dumps(entry["states"], ensure_ascii=False, separators=(",", ":")),
                  "solid": bool(by_id.get(state["tile"], {}).get("solid")), "spritewaffle_id": entry["id"],
                  "spritewaffle_template": entry.get("template_id")}
        fields = []
        for f in d["fieldDefs"]:
            v = values[f["identifier"]]
            real = [] if v is None else [{"id": "V_Bool", "params": [v]} if f["__type"] == "Bool" else {"id": "V_String", "params": [v]}]
            fields.append({"__identifier": f["identifier"], "__type": f["__type"], "__value": v, "__tile": None,
                           "defUid": f["uid"], "realEditorValues": real})
        y, x = divmod(entry["cell"], width)
        instances.append({"__identifier": kind, "__grid": [x, y], "__pivot": [0, 0], "__tags": [], "__tile": tile,
                          "__smartColor": "#BE4A2F", "iid": _iid(name, "object", entry["id"]), "width": size,
                          "height": size, "defUid": d["uid"], "px": [x * size, y * size], "fieldInstances": fields,
                          "__worldX": x * size, "__worldY": y * size})
    return list(defs.values()), instances, uid


def project(name: str, resolved: dict, tiles: list[dict], grid: dict, objects: list[dict] | None = None,
            layers: list[dict] | None = None) -> dict:
    """resolved: the map preview (width, height, tiles rows of tile id or None). tiles: the native
    tileset entries (id, rect, solid, collision, properties). objects: the map's objects. layers:
    extra hand-placed tile layers above the terrain ([{name, tiles: {cell: tile}}], bottom first)."""
    size = grid["tile_width"]
    width, height = resolved["width"], resolved["height"]
    by_id = {t["id"]: t for t in tiles}
    tileset_uid, tiles_uid, collision_uid, objects_uid, level_uid = 1, 2, 3, 4, 0
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
    entity_defs, entities, next_uid = _entities(objects or [], by_id, width, size, tileset_uid, name, 10)
    extra = []                                       # (identifier, uid, gridTiles), bottom first; uids 5-8
    for n, layer in enumerate(layers or []):
        ident = "".join(c if c.isalnum() else "_" for c in layer["name"]).strip("_") or f"Layer_{n + 2}"
        ident = ("Layer_" + ident) if ident[0].isdigit() or ident in ("Objects", "Collision", "Tiles") else ident
        while ident in {e[0] for e in extra}:          # "Decor" and "Decor!" must not share an identifier
            ident += "_2"
        placed = []
        for key, tile in sorted(layer["tiles"].items(), key=lambda kv: int(kv[0])):
            y, x = divmod(int(key), width)
            rect = by_id.get(tile, {}).get("rect", [0, 0])
            placed.append({"px": [x * size, y * size], "src": [rect[0], rect[1]], "f": 0, "t": tile,
                           "d": [int(key)], "a": 1})
        extra.append((ident, 5 + n, placed))
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
        "iid": _iid(name, width, height), "jsonVersion": JSON_VERSION, "appBuildId": 0, "nextUid": max(next_uid, 10),
        "identifierStyle": "Capitalize", "toc": [], "worldLayout": "Free", "worldGridWidth": width * size,
        "worldGridHeight": height * size, "defaultLevelWidth": width * size, "defaultLevelHeight": height * size,
        "defaultPivotX": 0, "defaultPivotY": 0, "defaultGridSize": size, "defaultEntityWidth": size,
        "defaultEntityHeight": size, "bgColor": "#40465B", "defaultLevelBgColor": "#696A79", "minifyJson": False,
        "externalLevels": False, "exportTiled": False, "simplifiedExport": False, "imageExportMode": "None",
        "exportLevelBg": True, "pngFilePattern": None, "backupOnSave": False, "backupLimit": 10,
        "backupRelPath": None, "levelNamePattern": "Level_%idx", "tutorialDesc": None, "customCommands": [],
        "flags": [], "worlds": [], "dummyWorldIid": _iid(name, "world"),
        "defs": {
            "layers": ([_layer_def("Objects", "Entities", objects_uid, size, None, [])] if entities else [])
                      + [_layer_def("Collision", "IntGrid", collision_uid, size, None, values)]
                      + [_layer_def(ident, "Tiles", uid, size, tileset_uid, []) for ident, uid, _ in reversed(extra)]
                      + [_layer_def("Tiles", "Tiles", tiles_uid, size, tileset_uid, [])],
            "entities": entity_defs, "enums": [], "externalEnums": [], "levelFields": [],
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
                    "layerInstances": ([layer_inst("Objects", "Entities", objects_uid, {"entityInstances": entities})]
                                       if entities else [])
                    + [layer_inst("Collision", "IntGrid", collision_uid, {"intGridCsv": int_grid})]
                    + [layer_inst(ident, "Tiles", uid, {"gridTiles": placed}) for ident, uid, placed in reversed(extra)]
                    + [layer_inst("Tiles", "Tiles", tiles_uid, {"gridTiles": grid_tiles})]}],
    }
