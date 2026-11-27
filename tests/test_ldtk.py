"""LDtk 1.5 project written next to the Tiled map in the map ZIP (export/ldtk.py)."""
import io
import json
from zipfile import ZipFile

from PIL import Image

from spritewaffle.core import tileset, tilemap
from spritewaffle.export import ldtk


def square_meadow(base):
    """Three 8 x 8 tiles: grass (solid slope with properties), water (one-way half), plain."""
    image = Image.new("RGBA", (24, 8))
    image.paste("#67b652", (0, 0, 8, 8))
    image.paste("#3d7af0", (8, 0, 16, 8))
    image.paste("#c8b27a", (16, 0, 24, 8))
    data = io.BytesIO()
    image.save(data, format="PNG")
    job = tileset.create(base, "meadow", "sq")
    tileset.import_bytes(job, data.getvalue(), "meadow.png", {"tile_width": 8, "tile_height": 8, "margin": 0, "spacing": 0})
    tileset.update_terrain(job, {"colors": ["Grass", "Water"],
                                 "tiles": {"0": ["Grass"] * 4, "1": ["Water"] * 4}})
    tileset.collision(job, 0, True, shape={"shape": "slope_up"})
    tileset.collision(job, 1, True, shape={"shape": "half_top", "one_way": True})
    tileset.properties(job, 0, {"damage": 3, "footstep": "grass"})
    return job


def test_map_zip_has_an_ldtk_project_with_tiles_and_collision(tmp_path):
    job = square_meadow(tmp_path)
    saved = tilemap.save(job, "South meadow", [["Grass", "Grass", "Water", "Water"]] * 2)   # grass, mixed, water
    out = tilemap.export(job, saved["id"], allow_empty=True)
    assert "ldtk_skipped" not in out
    with ZipFile(job.root / out["file"]) as z:
        project = json.loads(z.read("map.ldtk"))
        again = z.read("map.ldtk")
    assert project["jsonVersion"] == ldtk.JSON_VERSION
    tset, = project["defs"]["tilesets"]
    assert tset["relPath"] == "tiles.png" and tset["tileGridSize"] == 8 and tset["__cWid"] == 3
    level, = project["levels"]
    assert level["identifier"] == "South_meadow" and (level["pxWid"], level["pxHei"]) == (24, 8)
    collision, tiles = level["layerInstances"]
    assert [d["identifier"] for d in project["defs"]["layers"]] == ["Collision", "Tiles"]
    assert collision["intGridCsv"] == [1, 0, 2]             # grass solid, empty middle cell, water one-way
    assert [(t["px"], t["src"], t["t"], t["d"]) for t in tiles["gridTiles"]] == [([0, 0], [0, 0], 0, [0]),
                                                                              ([16, 0], [8, 0], 1, [2])]
    custom = {c["tileId"]: json.loads(c["data"]) for c in tset["customData"]}
    assert custom[0] == {"collision": [[0, 8], [8, 0], [8, 8]], "properties": {"damage": 3, "footstep": "grass"}}
    assert custom[1] == {"collision": [[0, 0], [8, 0], [8, 4], [0, 4]], "one_way": True}
    assert 2 not in custom                                   # plain tile: nothing to say
    # the same map exports the same file (ids from the map, not random)
    with ZipFile(job.root / tilemap.export(job, saved["id"], allow_empty=True)["file"]) as z:
        assert z.read("map.ldtk") == again


def test_non_square_tiles_skip_ldtk_and_say_why(tmp_path):
    from test_tilemap import meadow                          # 8 x 9 tiles
    job = meadow(tmp_path)
    saved = tilemap.save(job, "Edge", [["Grass", "Grass"], ["Grass", "Grass"]])
    out = tilemap.export(job, saved["id"])
    assert "square tiles" in out["ldtk_skipped"]
    with ZipFile(job.root / out["file"]) as z:
        assert "map.ldtk" not in z.namelist() and "map.tmj" in z.namelist()


def test_map_objects_become_ldtk_entities(tmp_path):
    job = square_meadow(tmp_path)
    chest = {"id": "chest1", "name": "Old chest", "kind": "chest", "cell": 2, "state": "open",
             "states": [{"name": "closed", "tile": 0}, {"name": "open", "tile": 1}]}
    door = {"id": "door1", "name": "Door", "kind": "door", "cell": 0, "state": "closed",
            "states": [{"name": "closed", "tile": 0}, {"name": "open", "tile": 2}]}
    saved = tilemap.save(job, "Camp", [["Grass", "Grass", "Water", "Water"]] * 2, objects=[chest, door])
    out = tilemap.export(job, saved["id"], allow_empty=True)
    with ZipFile(job.root / out["file"]) as z:
        project = json.loads(z.read("map.ldtk"))
    assert [d["identifier"] for d in project["defs"]["layers"]] == ["Objects", "Collision", "Tiles"]
    assert [e["identifier"] for e in project["defs"]["entities"]] == ["Chest", "Door"]
    objects_layer = project["levels"][0]["layerInstances"][0]
    assert objects_layer["__type"] == "Entities"
    first, second = objects_layer["entityInstances"]
    assert first["__identifier"] == "Chest" and first["__grid"] == [2, 0] and first["px"] == [16, 0]
    assert first["__tile"] == {"tilesetUid": 1, "x": 8, "y": 0, "w": 8, "h": 8}          # state "open" = tile 1
    fields = {f["__identifier"]: f["__value"] for f in first["fieldInstances"]}
    assert fields["name"] == "Old chest" and fields["state"] == "open" and fields["solid"] is True
    assert json.loads(fields["states"]) == chest["states"] and fields["spritewaffle_id"] == "chest1"
    assert fields["spritewaffle_template"] is None
    assert second["__identifier"] == "Door" and second["__grid"] == [0, 0]
    uids = [project["defs"]["entities"][0]["uid"]] + [f["uid"] for e in project["defs"]["entities"] for f in e["fieldDefs"]]
    assert len(set(uids)) == len(uids) and project["nextUid"] > max(uids + [e["uid"] for e in project["defs"]["entities"]])
