"""Atlas pages: trimmed, deduped, within the page limit, every frame rebuilds exactly."""
import json

import numpy as np
import pytest
from PIL import Image

from spritewaffle.export import atlas


def _anim(name, facing, action, n=4, size=64, seed=0, x=20):
    rng = np.random.default_rng(seed)
    cells = np.zeros((n, size, size, 4), np.uint8)
    for i in range(n):
        cells[i, 10:60, x + i:x + i + 20, :3] = rng.integers(0, 255, 3)
        cells[i, 10:60, x + i:x + i + 20, 3] = 255
    return {"name": name, "facing": facing, "action": action, "cells": cells}


def _rebuild(pages, f, size):
    cell = np.zeros((size, size, 4), np.uint8)
    cell[f["oy"]:f["oy"] + f["h"], f["ox"]:f["ox"] + f["w"]] = pages[f["page"]][f["y"]:f["y"] + f["h"], f["x"]:f["x"] + f["w"]]
    return cell


def test_every_frame_rebuilds_exactly_and_pages_respect_the_limit():
    anims = [_anim(f"walk_{k}", k, "walk", n=12, seed=k) for k in range(30)]
    pages, lay = atlas.pack(anims, max_size=512)
    assert len(pages) > 1 and all(max(p.shape[:2]) <= 512 for p in pages)
    for a in anims:
        for i, f in enumerate(lay[a["name"]]["frames"]):
            assert np.array_equal(_rebuild(pages, f, 64), a["cells"][i])
    area = sum(p.shape[0] * p.shape[1] for p in pages)
    assert area < 30 * 12 * 64 * 64 / 2                 # trimmed: far smaller than untrimmed cells


def test_identical_frames_are_stored_once():
    a = _anim("idle_S", "S", "idle", n=4)
    a["cells"][:] = a["cells"][0]                       # a still idle: 4 identical frames
    pages, lay = atlas.pack([a])
    fr = lay["idle_S"]["frames"]
    assert len({(f["x"], f["y"]) for f in fr}) == 1


def test_flip_only_for_exact_mirrors():
    e = _anim("walk_E", "E", "walk", seed=1)
    w = dict(e, name="walk_W", facing="W", cells=np.ascontiguousarray(e["cells"][:, :, ::-1]))
    ne = _anim("walk_NE", "NE", "walk", seed=2)
    nw = _anim("walk_NW", "NW", "walk", seed=3)          # rendered separately: not a mirror
    pages, lay = atlas.pack([e, w, ne, nw], mirror="flip")
    assert lay["walk_W"]["flip_x_of"] == "walk_E" and lay["walk_W"]["frames"] == lay["walk_E"]["frames"]
    assert lay["walk_NW"]["flip_x_of"] is None
    _, packed = atlas.pack([e, w, ne, nw], mirror="pack")
    assert packed["walk_W"]["flip_x_of"] is None


def test_flip_keeps_distinct_auxiliary_maps():
    east = _anim("idle_E", "E", "idle", n=1)
    west = dict(east, name="idle_W", facing="W", cells=np.ascontiguousarray(east["cells"][:, :, ::-1]))
    west["maps"] = {"normal": west["cells"].copy()}
    _, layout = atlas.pack([east, west], mirror="flip")
    assert layout["idle_W"]["flip_x_of"] is None


def test_frame_larger_than_page_is_refused():
    with pytest.raises(ValueError, match="page limit"):
        atlas.pack([_anim("x_S", "S", "x", size=64)], max_size=32)


def test_texturepacker_json(tmp_path):
    anims = [_anim(f"walk_{k}", k, "walk", n=12, seed=k) for k in range(30)]
    pages, lay = atlas.pack(anims, max_size=512)
    files = atlas.save_pages(tmp_path, "hero_atlas", pages)
    js = atlas.write_texturepacker(tmp_path, "hero_atlas", pages, lay, (64, 64), {a["name"]: [32.0, 63.0] for a in anims})
    names = set()
    for i, p in enumerate(js):
        d = json.loads(p.read_text())
        assert d["meta"]["image"] == files[i].name and Image.open(files[i]).size == (d["meta"]["size"]["w"], d["meta"]["size"]["h"])
        assert len(d["meta"]["related_multi_packs"]) == len(js) - 1
        for n, f in d["frames"].items():
            assert f["sourceSize"] == {"w": 64, "h": 64} and f["pivot"] == {"x": 0.5, "y": round(63 / 64, 6)}
        names |= set(d["frames"])
    assert len(names) == 30 * 12
