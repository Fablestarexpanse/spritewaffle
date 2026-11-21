"""Effects attached to character animations: event, preview, export."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import attach
from spritewaffle.core.job import Job
from spritewaffle.export import character
from spritewaffle.ui.server import create_app


def _effect(tmp_path, name="spark", n=4, size=8, loop=False):
    fj = Job.create(name, "e1", base=tmp_path, asset_type="effect")
    d = fj.root / "06_export" / "effect" / name
    (d / "frames").mkdir(parents=True)
    for i in range(n):
        f = np.zeros((size, size, 4), np.uint8)
        f[2:6, 2:6] = (255, 200, 0, 255)
        Image.fromarray(f).save(d / "frames" / f"{name}_{i:03d}.png")
    (d / f"{name}.json").write_text(json.dumps({"name": name, "fps": 12, "loop": loop}))
    return f"{name}/e1"


def _character(tmp_path, n=6, cell=16):
    j = Job.create("hero", "h1", base=tmp_path)
    sd = j.root / "04_pixel" / "E" / "cast" / "12f"
    (sd / "frames").mkdir(parents=True)
    for i in range(n):
        f = np.zeros((cell, cell, 4), np.uint8)
        f[4:15, 6:10] = (30, 60, 200, 255)
        Image.fromarray(f).save(sd / "frames" / f"{i:03d}.png")
    (sd / "placements.json").write_text(json.dumps([{"scale": 1, "crop": [0, 0, 4, 11], "paste": [6, 4], "pivot": [8.0, 15.0]}] * n))
    (j.root / "03_actions" / "E" / "cast").mkdir(parents=True, exist_ok=True)
    (j.root / "03_actions" / "E" / "cast" / "selection_report.json").write_text(json.dumps({"loop": False}))
    return j


def test_spawn_front_and_behind_and_projectile_moves(tmp_path):
    ej = _effect(tmp_path)
    j = _character(tmp_path)
    att = attach.set_attachment(j, "E", "cast", ej, frame=2, x=8, y=8, layer="front")
    cells = [np.array(Image.open(p).convert("RGBA")) for p in sorted((j.root / "04_pixel/E/cast/12f/frames").glob("*.png"))]
    fx, meta, _ = attach.effect_files(tmp_path / ej)
    out = attach.composite(cells, fx, att, fx_loop=False, loops=1)
    assert len(out) == 6
    assert not (out[1][..., :3] == (255, 200, 0)).all(-1).any()          # nothing before frame 2
    assert (out[2][..., :3] == (255, 200, 0)).all(-1).any()              # effect on top from frame 2
    side = dict(att, point=[11, 8])                                      # half over the body
    front = attach.composite(cells, fx, side, fx_loop=False, loops=1)
    behind = attach.composite(cells, fx, dict(side, layer="behind"), fx_loop=False, loops=1)
    yellow = lambda f: int((f[..., :3] == (255, 200, 0)).all(-1).sum())
    assert 0 < yellow(behind[2]) < yellow(front[2])                     # the body covers part of it
    proj = dict(att, kind="projectile", speed=3.0)
    out = attach.composite(cells, fx, proj, fx_loop=False, loops=1)
    xs = [np.where((f[..., :3] == (255, 200, 0)).all(-1))[1].mean() for f in out[2:5]]
    assert xs[0] < xs[1] < xs[2] and out[0].shape[1] > 16              # flies right (E); canvas grows
    ev = attach.event(proj | {"direction": [1, 0]}, 12)
    assert ev["velocity_px_per_frame"] == [3.0, 0.0] and ev["frame"] == 2


def test_bad_attachments_are_refused(tmp_path):
    j = _character(tmp_path)
    with pytest.raises(FileNotFoundError):
        attach.set_attachment(j, "E", "cast", "nobody/none", 0, 1, 1)
    ej = _effect(tmp_path)
    with pytest.raises(ValueError):
        attach.set_attachment(j, "E", "cast", ej, 0, 1, 1, layer="sideways")


def test_character_export_carries_events_and_effect_files(tmp_path):
    ej = _effect(tmp_path)
    j = _character(tmp_path)
    attach.set_attachment(j, "E", "cast", ej, frame=3, x=12, y=6)
    res = character.export(j.root, j.root / "06_export" / "character", "hero", lambda a: 12, require_pass=False)
    meta = json.loads(open(res["json"]).read())
    ev = meta["animations"][0]["events"][0]
    assert ev["effect"] == "spark" and ev["frame"] == 3 and ev["point"] == [12, 6]
    assert (j.root / "06_export" / "character" / "effects" / "spark" / "spark.json").exists()


def test_attach_api_makes_a_preview(tmp_path):
    ej = _effect(tmp_path)
    _character(tmp_path)
    with TestClient(create_app(tmp_path, worker=False)) as c:
        r = c.post("/api/jobs/hero/h1/attach", json={"facing": "E", "action": "cast", "effect_job": ej, "frame": 1,
                                                    "x": 8, "y": 6, "kind": "projectile", "speed": 2}).json()
        assert r["attachment"]["kind"] == "projectile" and "_with_fx.gif" in r["preview"]
        j = c.get("/api/jobs/hero/h1").json()
        assert j["effect_jobs"] == [ej]
        assert c.post("/api/jobs/hero/h1/attach", json={"facing": "E", "action": "cast", "remove": True}).json() == {"removed": True}
