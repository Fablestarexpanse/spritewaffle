"""Edge-only terrain sets (paths, fences, roads): rules list N, E, S, W; Tiled edge wangset;
Godot Match Sides terrain set."""
import io
import json
import subprocess
import sys

import pytest
from PIL import Image

from spritewaffle.core import terrain, tileset
from spritewaffle.export import godot

PATH = {"colors": ["Grass", "Path"], "mode": "edge",
        "tiles": {"0": ["Grass"] * 4,                                    # plain grass
                  "1": ["Path", "Grass", "Path", "Grass"],               # straight north-south path
                  "2": ["Grass", "Path", "Grass", "Path"],               # straight east-west path
                  "3": ["Path", "Path", "Grass", "Grass"]}}              # bend: north and east


def path_job(base):
    image = Image.new("RGBA", (64, 16), "#67b652")
    data = io.BytesIO()
    image.save(data, format="PNG")
    job = tileset.create(base, "paths", "e")
    tileset.import_bytes(job, data.getvalue(), "p.png", {"tile_width": 16, "tile_height": 16, "margin": 0, "spacing": 0})
    tileset.update_terrain(job, PATH)
    return job


def test_edge_rules_export_as_tiled_edge_wangset_and_godot_match_sides(tmp_path):
    rules = terrain.normalize(PATH, 4)
    assert rules["mode"] == "edge"
    with pytest.raises(ValueError, match="N, E, S, W"):
        terrain.normalize({**PATH, "tiles": {"0": ["Grass"] * 8}}, 4)
    wang = terrain.tiled_wangset(rules)
    assert wang["type"] == "edge"
    by_tile = {t["tileid"]: t["wangid"] for t in wang["wangtiles"]}
    assert by_tile[1] == [2, 0, 1, 0, 2, 0, 1, 0]                       # N=Path E=Grass S=Path W=Grass
    assert by_tile[3] == [2, 0, 2, 0, 1, 0, 1, 0]
    job = path_job(tmp_path)
    out = tileset.export(job)
    tsj = json.loads((job.root / out["files"]["tileset.tsj"]).read_text())
    assert tsj["wangsets"][0]["type"] == "edge"
    tres = godot.tileset(tileset.inspect(job)["tileset"])
    assert "terrain_set_0/mode = 2" in tres                             # Godot TileSet.TERRAIN_MODE_MATCH_SIDES
    assert "1:0/0/terrains_peering_bit/top_side = 1" in tres and "1:0/0/terrains_peering_bit/right_side = 0" in tres
    assert "1:0/0/terrain = 1" in tres                                  # two path + two grass sides: a path tile
    assert "corner" not in tres.split("terrain_set_0/mode")[0].split("1:0/0 = 0")[1].split("2:0/0")[0]


def test_corner_preview_refuses_edge_sets(tmp_path):
    job = path_job(tmp_path)
    with pytest.raises(ValueError, match="edge"):
        tileset.preview(job, [["Grass", "Grass"], ["Grass", "Grass"]])


def test_tied_centre_terrain_is_the_same_every_run(tmp_path):
    """The centre of a tile with a 2:2 tie came from a Python set, whose order changes per process."""
    job = path_job(tmp_path)
    tileset.update_terrain(job, {"colors": ["Grass", "Water"],
                                 "tiles": {"0": ["Grass", "Water", "Water", "Grass"]}})   # corner set, 2:2
    code = ("import sys; sys.path.insert(0, 'tests'); from pathlib import Path; from spritewaffle.core import tileset;"
            "from spritewaffle.core.job import Job; from spritewaffle.export import godot;"
            f"r = tileset.inspect(Job.open(Path(r'{job.root}')))['tileset'];"
            "print([l for l in godot.tileset(r).splitlines() if l.startswith('0:0/0/terrain =')][0])")
    seen = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={"PYTHONHASHSEED": str(seed),
                                                                                             **{k: v for k, v in __import__("os").environ.items() if k != "PYTHONHASHSEED"}}).stdout.strip()
            for seed in range(6)}
    assert seen == {"0:0/0/terrain = 1"}                                 # the later terrain, every time
