"""Texture variants that share edges: any variant fits next to any other."""
import json

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import texture as tx
from test_texture import FakeComfy, _job, _noise


def _tiles(j):
    d = j.root / "02_facings"
    rep = json.loads((d / "texture_report.json").read_text())
    return rep, [np.array(Image.open(d / f"tile_{k}.png").convert("RGB")) for k in sorted(rep["variants"], key=int)]


def test_share_edges_keeps_the_base_border_and_the_variant_middle():
    base, other = tx.make_seamless(_noise(300, 1)), tx.make_seamless(_noise(300, 2))
    out = tx.share_edges(base, other, 0.15)
    k = max(2, int(out.shape[1] * 0.15) // 4)
    assert (out[:k] == base[:k]).all() and (out[:, -k:] == base[:, -k:]).all()      # outer edge = base
    c = out.shape[0] // 2
    assert (out[c - 10:c + 10, c - 10:c + 10] == other[c - 10:c + 10, c - 10:c + 10]).all()  # middle = variant


def test_pixel_variants_share_edges_exactly_and_fit_side_by_side(tmp_path):
    j = _job(tmp_path)
    tx.generate(j, client=FakeComfy(), seed=3)
    before, _ = _tiles(j)
    tx.configure(j, shared_edges=True)
    tx.retile(j)
    rep, tiles = _tiles(j)
    for t in tiles[1:]:
        assert (t[0] == tiles[0][0]).all() and (t[:, -1] == tiles[0][:, -1]).all()
        assert not (t == tiles[0]).all()                                              # still its own tile
    assert len({tuple(c) for t in tiles for c in t.reshape(-1, 3)}) <= 16              # one shared palette
    assert rep["cross_score"] < before["cross_score"]
    assert rep["settings"]["shared_edges"] is True
    only = tx.generate(j, client=FakeComfy(), seed=9, only=[0])                        # re-rolling the base re-shares all
    _, again = _tiles(j)
    assert all((t[0] == again[0][0]).all() for t in again) and only["cross_score"] is not None


def test_shared_edges_off_by_default_and_through_http(tmp_path):
    j = _job(tmp_path)
    assert tx.settings(j)["shared_edges"] is False
    from spritewaffle.ui.server import create_app
    with TestClient(create_app(tmp_path, worker=False)) as c:
        r = c.post("/api/jobs/cobble/t1/texture", json={"shared_edges": True}).raise_for_status().json()
        assert r["shared_edges"] is True
        assert "cross_score" in c.get("/api/jobs/cobble/t1").json()["texture"]
