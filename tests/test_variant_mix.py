"""Terrain variants (tiles with the same corners) mixed per cell by tile weight (opt-in per map)."""
import io
import json
from zipfile import ZipFile

from PIL import Image

from spritewaffle.core import terrain, tileset, tilemap


def grass_variants(base):
    """Four 8 x 8 tiles: three grass variants and water."""
    image = Image.new("RGBA", (32, 8))
    for i, colour in enumerate(("#67b652", "#5fa84b", "#74c25e", "#3d7af0")):
        image.paste(colour, (i * 8, 0, i * 8 + 8, 8))
    data = io.BytesIO()
    image.save(data, format="PNG")
    job = tileset.create(base, "meadow", "mix")
    tileset.import_bytes(job, data.getvalue(), "m.png", {"tile_width": 8, "tile_height": 8, "margin": 0, "spacing": 0})
    tileset.update_terrain(job, {"colors": ["Grass", "Water"], "tiles": {"0": ["Grass"] * 4, "1": ["Grass"] * 4,
                                                                         "2": ["Grass"] * 4, "3": ["Water"] * 4}})
    tileset.probability(job, 1, 0)        # never at random
    tileset.probability(job, 2, 3)        # three times as often as tile 0
    return job


def test_mix_picks_variants_by_weight_and_stays_off_by_default(tmp_path):
    job = grass_variants(tmp_path)
    field = [["Grass"] * 33 for _ in range(33)]                 # 32 x 32 grass cells
    plain = tilemap.save(job, "Plain", field)
    assert {t for row in tilemap.load(job, plain["id"])["vertices"] for t in row} == {"Grass"}
    off = tileset.preview(job, field)
    assert {t for row in off["tiles"] for t in row} == {0}      # first tile everywhere, as before mixing
    on = tileset.preview(job, field, mix=True)
    counts = {t: sum(row.count(t) for row in on["tiles"]) for t in (0, 1, 2)}
    assert counts[1] == 0                                       # weight 0: never
    assert 2.4 < counts[2] / counts[0] < 3.8, counts            # weight 3 vs 1, 1024 cells
    assert tileset.preview(job, field, mix=True)["tiles"] == on["tiles"]   # same cells, same tiles

    mixed = tilemap.save(job, "Mixed", field, mix=True)
    assert mixed["mix"] is True
    again = tilemap.save(job, "Mixed", field, mixed["id"], mixed["revision"])   # mix omitted: kept
    assert again["mix"] is True
    out = tilemap.export(job, again["id"])
    with ZipFile(job.root / out["file"]) as z:
        native, tiled = json.loads(z.read("map.json")), json.loads(z.read("map.tmj"))
    assert native["mix_variants"] is True and native["tiles"] == on["tiles"]
    assert tiled["layers"][0]["data"][:32] == [t + 1 for t in on["tiles"][0]]
    with ZipFile(job.root / tilemap.export(job, plain["id"])["file"]) as z:
        assert "mix_variants" not in json.loads(z.read("map.json"))


def test_pick_ignores_zero_weights_unless_nothing_else():
    assert terrain._pick([4, 5], {4: 0, 5: 0}, 0, 0) == 4
    assert {terrain._pick([4, 5], {4: 0}, x, 0) for x in range(20)} == {5}
