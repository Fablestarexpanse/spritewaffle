"""Audit P3: Tiled version and terrain icons, map export with empty cells."""
import json
from io import BytesIO
from zipfile import ZipFile

from spritewaffle.core import terrain, tilemap
from spritewaffle.core import transition as tr
from test_tilemap import meadow


def test_map_export_can_leave_unresolved_cells_empty(tmp_path):
    job = meadow(tmp_path)
    saved = tilemap.save(job, "Edge", [["Grass", "Grass", None, None]] * 2)
    out = tilemap.export(job, saved["id"], allow_empty=True)
    assert out["empty_cells"] == 1
    with ZipFile(job.root / out["file"]) as z:
        native, tiled = json.loads(z.read("map.json")), json.loads(z.read("map.tmj"))
        tsj = json.loads(z.read("tileset.tsj"))
    assert native["empty_cells"] == [[1, 0]] and tiled["layers"][0]["data"][1] == 0
    assert tiled["tiledversion"] == tsj["tiledversion"] == "1.10.2"


def test_wangset_has_an_icon_tile():
    w = terrain.tiled_wangset(terrain.normalize(tr.rules("grass", "dirt"), 16))
    assert w["tile"] == w["colors"][0]["tile"] >= 0
