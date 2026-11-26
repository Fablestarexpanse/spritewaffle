"""Seamless textures: the seam fix, tile cutting, the texture job, and its API / MCP / CLI."""
import asyncio
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import generate as gen
from spritewaffle.core import texture as tx
from spritewaffle.core.job import Job
from spritewaffle.mcp_server import build
from spritewaffle.ui.server import create_app


def _noise(size=256, seed=0):
    """A non-tileable texture: blotchy noise plus a left-to-right ramp (so the wrap edges differ)."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, (size // 8, size // 8, 3)).astype(np.uint8)
    img = np.array(Image.fromarray(small).resize((size, size), Image.BICUBIC)).astype(int)
    img += np.linspace(0, 90, size).astype(int)[None, :, None]
    return np.clip(img, 0, 255).astype(np.uint8)


def test_make_seamless_wraps_and_resize_keeps_it():
    src = _noise()
    assert tx.wrap_score(src) > 2.5                            # the ramp makes a hard seam
    out = tx.make_seamless(src, 0.15)
    assert out.shape[0] == out.shape[1] == 256 - int(256 * 0.15)
    assert tx.wrap_score(out) < 1.5
    t = tx.resize_wrapped(out, 32)
    assert t.shape == (32, 32, 3) and tx.wrap_score(t) < 1.6
    assert tx.tiled(t, 3, 2).shape == (64, 96, 3)
    with pytest.raises(ValueError):
        tx.make_seamless(src, 0.6)


def test_pixel_tiles_use_few_colours():
    t = tx.tile_from(tx.make_seamless(_noise()), {"tile_size": 16, "style": "pixel", "colours": 8})
    assert t.shape == (16, 16, 3) and len({tuple(c) for c in t.reshape(-1, 3)}) <= 8


class FakeComfy:
    def __init__(self):
        self.calls = []

    def run_template(self, slot, values, out_dir):
        self.calls.append((slot, values))
        out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "o.png"
        Image.fromarray(_noise(512, values["seed"] % 7)).save(p)
        return {"files": [str(p)], "values": values}


def _job(tmp_path, **settings):
    j = Job.create("cobble", "t1", base=tmp_path, asset_type=tx.TYPE, style="pixel")
    tx.configure(j, description="mossy cobblestone ground", tile_size=32, variants=3, **settings)
    return j


def test_texture_job_generate_retile_export_tileset(tmp_path):
    j = _job(tmp_path)
    c = FakeComfy()
    rep = tx.generate(j, client=c, seed=10)
    assert len(c.calls) == 3 and "Seamless tileable game texture: mossy cobblestone ground" in c.calls[0][1]["prompt"]
    assert [v["seed"] for v in rep["variants"].values()] == [10, 11, 12]
    assert all(v["wrap_tile"] < 1.6 < v["wrap_raw"] for v in rep["variants"].values())
    assert Image.open(j.root / "02_facings" / "tile_0.png").size == (32, 32)
    assert j.read_meta()["stages"]["texture"]["status"] == "review"
    tx.generate(j, client=c, only=[1])                        # re-roll one variant
    assert len(c.calls) == 4 and len(json.loads((j.root / "02_facings/texture_report.json").read_text())["variants"]) == 3
    tx.configure(j, tile_size=64)
    tx.retile(j)                                              # no render
    assert len(c.calls) == 4 and Image.open(j.root / "02_facings" / "tile_2.png").size == (64, 64)
    with pytest.raises(RuntimeError):
        tx.export(j)                                          # a human approves first
    gen.approve(j, "texture")
    info = tx.export(j)
    out = j.root / "06_export" / "texture"
    assert info["tile_size"] == 64 and Image.open(out / "cobble_sheet.png").size == (192, 64)
    assert (out / "cobble_0_preview.png").exists() and json.loads((out / "cobble.json").read_text())["variants"] == 3
    ts = tx.to_tileset(j)
    tj = json.loads((tmp_path / "cobble" / ts["job_id"] / "job.json").read_text())
    assert ts["tiles"] == 3 and tj["inputs"]["asset_type"] == "tileset" and tj["inputs"]["texture_job"] == "cobble/t1"


def test_settings_are_validated(tmp_path):
    j = _job(tmp_path)
    for bad in ({"tile_size": 33}, {"variants": 0}, {"colours": 1}, {"overlap": 0.6}):
        with pytest.raises(ValueError):
            tx.configure(j, **bad)
    with pytest.raises(ValueError):
        tx.prompt("  ")


def test_texture_api(tmp_path):
    with TestClient(create_app(tmp_path, worker=False)) as c:
        assert "texture" in c.get("/api/status").json()["asset_types"]
        r = c.post("/api/jobs", json={"character": "sand", "asset_type": "texture", "style": "painted"}).json()
        path = f"/api/jobs/sand/{r['job_id']}"
        assert c.post(path + "/texture", json={"description": "dry desert sand", "tile_size": 128}).json()["tile_size"] == 128
        assert c.post(path + "/texture", json={"tile_size": 7}).status_code == 400
        j = c.get(path).json()
        assert j["asset_type"] == "texture" and j["texture"]["settings"]["style"] == "painted" and j["texture"]["variants"] == []
        assert c.post(path + "/run", json={"stage": "texture", "args": {}}).status_code == 200
        assert c.post(path + "/texture/export").status_code == 400


def test_texture_mcp(tmp_path):
    m, q = build(tmp_path)
    call = lambda **a: json.loads((lambda r: (r[0] if isinstance(r, tuple) else r)[0].text)(asyncio.run(m.call_tool("texture", a))))
    s = call(character="water", action="setup", description="shallow ocean water", tile_size=64)
    assert s["settings"]["tile_size"] == 64 and s["variants"] == {}
    r = call(character="water", action="generate", only=[2])
    assert q.get(r["queued"])["stage"] == "texture" and q.get(r["queued"])["args"] == {"only": [1]}
