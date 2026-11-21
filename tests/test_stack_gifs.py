"""Sprite stack show-off GIFs: spin and build-up, drawn like the in-app viewer."""
import json

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core.job import Job
from spritewaffle.stack import gifs
from spritewaffle.ui.server import create_app


def _stack(d, name="crate", H=6, W=8, D=8):
    d.mkdir(parents=True, exist_ok=True)
    strip = np.zeros((D, W * H, 4), np.uint8)
    for z in range(H):
        strip[1:7, z * W + 1:z * W + 7] = (40 * z, 100, 200, 255)
    Image.fromarray(strip, "RGBA").save(d / f"{name}_slices.png")
    (d / f"{name}_slices.json").write_text(json.dumps({"slices": H, "slice_size": [W, D]}))


def test_build_up_adds_one_slice_per_frame_then_spins(tmp_path):
    _stack(tmp_path)
    sl = gifs.load(tmp_path, "crate")
    assert sl.shape == (6, 8, 8, 4)
    a1 = (gifs.render(sl, 30, count=1)[..., 3] > 0).sum()
    a6 = (gifs.render(sl, 30, count=6)[..., 3] > 0).sum()
    assert 0 < a1 < a6
    flat = gifs.render(sl, 0, tilt=1.0)
    squashed = gifs.render(sl, 0, tilt=0.5)
    assert squashed.shape[0] < flat.shape[0]                    # tilt squashes the camera view
    out = gifs.build_up(sl, tmp_path / "b.gif", steps=8, scale=2)
    assert out["frames"] == 6 + 8 and Image.open(out["file"]).n_frames == 14
    out = gifs.spin(sl, tmp_path / "s.gif", steps=8, scale=2)
    assert Image.open(out["file"]).n_frames == 8


def test_stack_gif_api(tmp_path):
    job = Job.create("crate", "c1", base=tmp_path, asset_type="prop")
    with TestClient(create_app(tmp_path, worker=False)) as c:
        assert c.post("/api/jobs/crate/c1/stack_gif", json={"kind": "spin"}).status_code == 400   # no stack yet
        _stack(job.root / "06_export" / "stack")
        r = c.post("/api/jobs/crate/c1/stack_gif", json={"kind": "build", "tilt": 0.5, "steps": 8}).json()
        assert r["frames"] == 6 + 8 and r["url"].startswith("/files/crate/c1/06_export/stack/crate_build.gif")
        assert c.post("/api/jobs/crate/c1/stack_gif", json={"kind": "wobble"}).status_code == 400
        st = c.get("/api/jobs/crate/c1").json()["stack"]
        assert st["build_gif"] and st["slices"]
