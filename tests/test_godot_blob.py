"""Audit P1 fixes: Godot 4 export (SpriteFrames, TileSet) and blob-47 terrain sets."""
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from spritewaffle.core import generate as gen
from spritewaffle.core import terrain, tileset
from spritewaffle.core import texture as tx
from spritewaffle.core import transition as tr
from spritewaffle.core.job import Job
from spritewaffle.export import character, godot
from test_character_export import _anim
from test_texture import FakeComfy, _job


def test_sprite_frames_restore_the_trim_and_timing():
    meta = {"character": "hero", "cell": [16, 16], "pivot": [8.0, 15.0], "pages": [{"image": "hero_atlas_0.png", "w": 40, "h": 20}],
            "animations": [{"name": "walk_E", "fps": 10, "loop": True, "durations_ms": [100, 300], "pivot": [8, 15], "flip_x_of": None,
                            "frames_atlas": [{"page": 0, "x": 1, "y": 1, "w": 6, "h": 8, "ox": 5, "oy": 7},
                                             {"page": 0, "x": 9, "y": 1, "w": 6, "h": 8, "ox": 5, "oy": 7}]},
                           {"name": "walk_W", "fps": 10, "loop": True, "pivot": [8, 15], "flip_x_of": "walk_E", "frames_atlas": []}]}
    text, flips = godot.sprite_frames(meta)
    assert text.startswith('[gd_resource type="SpriteFrames"') and 'path="hero_atlas_0.png"' in text
    assert "region = Rect2(1, 1, 6, 8)" in text and "margin = Rect2(5, 7, 10, 8)" in text     # full 16 x 16 cell again
    assert '"duration": 3.0' in text and '"speed": 10.0' in text and '&"walk_W"' in text
    assert flips == {"walk_W": "walk_E"}
    scene = godot.scene(meta, "hero.tres", flips, pixel=True)
    assert "offset = Vector2(0.0, -7.0)" in scene and "texture_filter = 1" in scene and 'metadata/flip_h = {"walk_W": "walk_E"}' in scene


def test_character_export_writes_godot_files(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    _anim(job, "S", "walk", [(200, 0, 0), (0, 0, 200)])
    out = character.export(job.root, tmp_path / "out", "hero", lambda a: 12)
    assert [Path(p).name for p in out["godot"]] == ["hero.tres", "hero.tscn"]
    assert "walk_S" in (tmp_path / "out" / "hero.tres").read_text()


def test_blob_set_has_47_shapes_and_mixed_rules():
    cfg = tr.blob_configs()
    assert len(cfg) == 47 == len(set(cfg))
    assert all(not ne or (n and e) for n, ne, e, *_ in cfg)                 # a corner needs both edges
    r = tr.blob_rules("grass", "dirt")
    assert r["mode"] == "mixed" and len(r["centers"]) == 48 and len(r["tiles"]) == 47  # the island is centre-only
    norm = terrain.normalize(r, 48)
    assert norm["mode"] == "mixed" and norm["centers"]["1"] == "dirt"
    wang = terrain.tiled_wangset(norm)
    assert wang["type"] == "mixed" and len(wang["wangtiles"]) == 47 and len(wang["wangtiles"][0]["wangid"]) == 8
    with pytest.raises(ValueError, match="blob"):
        terrain.preview(norm, [["grass", "grass"], ["grass", "grass"]])
    with pytest.raises(ValueError):
        terrain.normalize({"colors": ["a"], "tiles": {"0": ["a"] * 4}, "mode": "mixed"}, 4)  # mixed needs 8 entries
    sheet = tr.build(np.full((16, 16, 3), 40, np.uint8), np.full((16, 16, 3), 200, np.uint8), kind="blob", band=1)
    assert sheet.shape == (6 * 16, 8 * 16, 3) and (sheet[:16, :16] < 60).all()      # tile 0 = plain lower terrain


def test_godot_tileset_corner_and_blob(tmp_path):
    rec = {"grid": {"tile_width": 16, "tile_height": 16, "margin": 0, "spacing": 0, "columns": 4, "rows": 4},
           "solid_tiles": [3], "empty_tiles": [], "terrain": terrain.normalize(tr.rules("grass", "dirt"), 16)}
    t = godot.tileset(rec)
    assert "terrain_set_0/mode = 1" in t and "3:0/0/physics_layer_0/polygon_0/points" in t
    assert "0:2/0/terrains_peering_bit/top_left_corner = 1" in t           # tile 8: NW is dirt
    rec_b = {"grid": {"tile_width": 16, "tile_height": 16, "margin": 0, "spacing": 0, "columns": 8, "rows": 6},
             "solid_tiles": [], "empty_tiles": [], "terrain": terrain.normalize(tr.blob_rules("grass", "dirt"), 48)}
    b = godot.tileset(rec_b)
    assert "terrain_set_0/mode = 0" in b and "1:0/0/terrain = 1" in b and "1:0/0/terrains_peering_bit/top_side = 0" in b  # island: dirt centre


def test_palette_snap_and_orphans_keep_the_wrap():
    rng = np.random.default_rng(0)
    tile = np.repeat(np.repeat(rng.integers(0, 255, (8, 8, 3)), 4, 0), 4, 1).astype(np.uint8)
    tile[5, 9] = (255, 0, 255)                                                # an orphan
    out = tx.clean_orphans(tile)
    assert tuple(out[5, 9]) == tuple(tile[5, 8]) and (np.delete(out.reshape(-1, 3), 5 * 32 + 9, 0) == np.delete(tile.reshape(-1, 3), 5 * 32 + 9, 0)).all()
    snapped = tx.snap_palette(tile, ["#000000", "#ffffff", "#ff0000"])
    assert {tuple(c) for c in snapped.reshape(-1, 3)} <= {(0, 0, 0), (255, 255, 255), (255, 0, 0)}


def test_blob_transition_tileset_exports_tiled_and_godot(tmp_path):
    a = _job(tmp_path)
    b = Job.create("dirt", "t1", base=tmp_path, asset_type=tx.TYPE, style="pixel")
    tx.configure(b, description="dry dirt", tile_size=32, variants=1)
    c = FakeComfy()
    tx.generate(a, client=c, seed=1); tx.generate(b, client=c, seed=9)
    gen.approve(a, "texture"); gen.approve(b, "texture")
    r = tr.make(a, b, names=("grass", "dirt"), kind="blob")
    ts = Job.open(tmp_path / r["character"] / r["job_id"])
    assert r["tiles"] == 48
    tileset.export(ts)
    out = ts.root / "06_export" / "tileset"
    tsj = json.loads((out / "tileset.tsj").read_text())
    assert tsj["wangsets"][0]["type"] == "mixed" and tsj["tilecount"] == 48
    assert "terrain_set_0/mode = 0" in (out / "tileset.tres").read_text()


def test_app_page_versions_its_scripts(tmp_path):
    """Browsers kept running an old tileset_terrain.js after an update (no cache headers)."""
    from fastapi.testclient import TestClient

    from spritewaffle.ui.server import create_app
    with TestClient(create_app(tmp_path, worker=False)) as c:
        r = c.get("/")
        assert r.headers["cache-control"] == "no-cache"
        assert '/static/tileset_terrain.js?v=' in r.text and '/static/texture.js?v=' in r.text
        assert c.get("/static/texture.js").headers["cache-control"] == "no-cache"


def test_path_set_tiles_meet_at_every_edge():
    """Edge (path) set: 16 tiles; where two tiles share an edge with the same bit, the path crosses
    at the same rows on both sides; where the bit is 0 the edge is plain ground."""
    from spritewaffle.core import transition as tr2
    for roughness, slack in ((0.0, 0), (0.6, 2)):
        m = tr2.edge_masks(32, roughness=roughness, seed=3)
        assert len(m) == 16 and not m[0].any()                         # tile 0: plain ground
        assert m[15][16, 16] == 1                                      # crossing: path in the middle
        for left in range(16):
            for right in range(16):
                east, west = (left >> 2) & 1, right & 1
                if east != west:
                    continue
                a, b = m[left][:, -1], m[right][:, 0]
                if not east:
                    assert not a.any() and not b.any()                 # no path at that edge, either side
                else:
                    assert a.sum() > 0 and int(np.abs(a - b).sum()) <= slack
    rules = tr2.edge_rules("grass", "path")
    assert rules["mode"] == "edge" and rules["tiles"]["10"] == ["path", "grass", "path", "grass"]   # N+S straight
    assert terrain.tiled_wangset(terrain.normalize(rules, 16))["type"] == "edge"
    sheet = tr2.build(np.full((16, 16, 3), 40, np.uint8), np.full((16, 16, 3), 200, np.uint8), kind="edge")
    assert sheet.shape == (4 * 16, 4 * 16, 3) and (sheet[:16, :16] < 60).all()
