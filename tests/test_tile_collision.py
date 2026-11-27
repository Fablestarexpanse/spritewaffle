"""Audit P2 #7: per-tile collision shapes (slopes, half tiles, polygons, one-way) and properties."""
import json
from base64 import b64encode

import pytest
from fastapi.testclient import TestClient

from spritewaffle.core import tile_collision as tc
from spritewaffle.core import tileset
from spritewaffle.core.job import Job
from spritewaffle.export import godot
from spritewaffle.ui.server import create_app
from test_tileset import atlas_bytes

GRID = {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1}


def test_presets_points_and_validation():
    assert tc.polygon({"shape": "slope_up"}, 16, 16) == [[0, 16], [16, 0], [16, 16]]
    assert tc.polygon(None, 8, 8) == [[0, 0], [8, 0], [8, 8], [0, 8]]
    assert tc.clean_shape({"shape": "full"}, 8, 8) is None                      # the default stays implicit
    assert tc.clean_shape({"shape": "full", "one_way": True}, 8, 8) == {"one_way": True}
    assert tc.clean_shape({"points": [[0, 8], [8, 4], [8, 8]]}, 8, 8) == {"points": [[0, 8], [8, 4], [8, 8]]}
    for bad in ({"shape": "ramp"}, {"points": [[0, 0], [9, 0], [0, 8]]}, {"points": [[0, 0], [1, 1]]},
                {"shape": "slope_up", "points": [[0, 0], [8, 0], [0, 8]]}, {"one_way": "yes"}):
        with pytest.raises(ValueError):
            tc.clean_shape(bad, 8, 8)
    with pytest.raises(ValueError, match="one type"):
        tc.clean_properties({"damage": "high"}, {"3": {"damage": 5}})
    assert tc.parse_text("damage=5, water=true, speed=0.5, step=grass") == {
        "damage": 5, "water": True, "speed": 0.5, "step": "grass"}


def test_http_shapes_properties_export_tiled_godot_and_modules(tmp_path):
    route = "/api/jobs/ground/one/tileset"
    payload = {"data": b64encode(atlas_bytes()).decode("ascii"), "filename": "g.png", "grid": GRID}
    with TestClient(create_app(tmp_path, worker=False)) as c:
        assert c.post("/api/jobs", json={"character": "ground", "job_id": "one", "asset_type": "tileset"}).is_success
        c.post(route + "/import", json=payload).raise_for_status()
        c.post(route + "/collision", json={"tile": 0, "solid": True, "shape": {"shape": "slope_up"}}).raise_for_status()
        r = c.post(route + "/collision", json={"tile": 1, "solid": True, "shape": {"one_way": True}}).json()
        assert r["tileset"]["tile_shapes"] == {"0": {"shape": "slope_up"}, "1": {"one_way": True}}
        r = c.post(route + "/properties", json={"tile": 1, "properties": {"damage": 2, "water": False}}).json()
        assert r["tileset"]["tile_properties"] == {"1": {"damage": 2, "water": False}}
        assert c.post(route + "/properties", json={"tile": 0, "properties": {"damage": "x"}}).status_code == 400
        assert c.post(route + "/collision", json={"tile": 0, "solid": True, "shape": {"shape": "nope"}}).status_code == 400
        c.post(route + "/export").raise_for_status()
    out = tmp_path / "ground" / "one" / "06_export" / "tileset"
    tsj = {t["id"]: t for t in json.loads((out / "tileset.tsj").read_text())["tiles"]}
    assert tsj[0]["objectgroup"]["objects"][0]["polygon"] == [{"x": 0, "y": 9}, {"x": 8, "y": 0}, {"x": 8, "y": 9}]
    assert tsj[1]["objectgroup"]["objects"][0]["properties"][0]["name"] == "one_way"
    assert {"name": "damage", "type": "int", "value": 2} in tsj[1]["properties"]
    native = json.loads((out / "tileset.json").read_text())["tiles"]
    assert native[0]["collision"]["shape"] == "slope_up" and native[1]["properties"]["water"] is False
    tres = (out / "tileset.tres").read_text()
    assert "0:0/0/physics_layer_0/polygon_0/points = PackedVector2Array(-4.0, 4.5, 4.0, -4.5, 4.0, 4.5)" in tres
    assert "1:0/0/physics_layer_0/polygon_0/one_way = true" in tres
    assert 'custom_data_layer_0/name = "damage"' in tres and "custom_data_layer_0/type = 2" in tres
    assert "1:0/0/custom_data_0 = 2" in tres and "1:0/0/custom_data_1 = false" in tres
    # clearing collision drops the shape; re-import of the same sheet keeps shapes and properties
    job = Job.open(tmp_path / "ground" / "one")
    assert "0" not in (tileset.collision(job, 0, False)["tileset"].get("tile_shapes") or {})
    kept = tileset.import_bytes(job, atlas_bytes(), "g.png", GRID)["tileset"]
    assert kept["tile_shapes"] == {"1": {"one_way": True}} and kept["tile_properties"]["1"]["damage"] == 2


def test_old_record_without_shapes_exports_the_same_full_squares():
    rec = {"grid": {"tile_width": 16, "tile_height": 16, "margin": 0, "spacing": 0, "columns": 2, "rows": 1},
           "solid_tiles": [1], "empty_tiles": []}
    assert "1:0/0/physics_layer_0/polygon_0/points = PackedVector2Array(-8.0, -8.0, 8.0, -8.0, 8.0, 8.0, -8.0, 8.0)" in godot.tileset(rec)
    assert "custom_data_layer" not in godot.tileset(rec)


def test_module_export_carries_the_slope_polygon(tmp_path):
    from zipfile import ZipFile

    from spritewaffle.core import tile_module_export
    from test_tile_module_export import packed_atlas
    job, _, _, _ = packed_atlas(tmp_path)
    tileset.collision(job, 3, True, shape={"shape": "slope_up", "one_way": True})
    out = tile_module_export.export(job, "Arch / stone")
    with ZipFile(job.root / out["file"]) as archive:
        spec = json.loads(archive.read("module.json"))
    assert spec["collision"][0] == {"x": 0, "y": 0, "width": 8, "height": 6}          # full tiles unchanged
    assert spec["collision"][1] == {"x": 0, "y": 6, "width": 8, "height": 6, "one_way": True,
                                    "polygon": [[0, 12], [8, 6], [8, 12]]}


def test_tile_weight_exports_as_tiled_probability(tmp_path):
    """Texture variants that share edges can be mixed in a map; Tiled picks among them by weight."""
    import json
    import pytest
    from fastapi.testclient import TestClient
    from spritewaffle.core import tileset
    from spritewaffle.ui.server import create_app
    from test_tileset import atlas_bytes
    job = tileset.create(tmp_path, "ground", "w")
    tileset.import_bytes(job, atlas_bytes(), "g.png", {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1})
    tileset.probability(job, 1, 0.25)
    tileset.probability(job, 0, 3)
    for bad in (-1, 1001, "2", True, float("nan")):
        with pytest.raises(ValueError):
            tileset.probability(job, 1, bad)
    with pytest.raises(ValueError):
        tileset.probability(job, 99, 2)
    out = tileset.export(job)
    tsj = json.loads((job.root / out["files"]["tileset.tsj"]).read_text())
    native = json.loads((job.root / out["files"]["tileset.json"]).read_text())
    assert {t["id"]: t.get("probability") for t in tsj["tiles"]} == {0: 3.0, 1: 0.25}
    assert native["tiles"][1]["probability"] == 0.25
    assert tileset.probability(job, 0, None)["tileset"]["tile_probability"] == {"1": 0.25}   # reset to 1
    tileset.import_bytes(job, atlas_bytes(), "g.png", {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1})
    assert tileset.inspect(job)["tileset"]["tile_probability"] == {"1": 0.25}   # same sheet: kept
    with TestClient(create_app(tmp_path, worker=False)) as client:
        route = "/api/jobs/ground/w/tileset/probability"
        assert client.post(route, json={"tile": 1, "weight": 1}).json()["tileset"].get("tile_probability") is None
        assert client.post(route, json={"tile": 1, "weight": -2}).status_code == 400
    from spritewaffle import cli
    assert cli.main(["tileset", "--job", str(job.root), "--tile", "0", "--weight", "0", "weight"]) in (0, None)
    assert tileset.inspect(job)["tileset"]["tile_probability"] == {"0": 0.0}
