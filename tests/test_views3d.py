"""More than 8 views from a 3D model (core/views3d.py). No GPU: H3 and TRELLIS are stubbed."""
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from spritewaffle.core import angles, generate, manifest, views3d
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.core.queue import Queue
from spritewaffle.prompts import builder
from spritewaffle.stack import mesh3d
from synth import draw_sprite, render
from test_generate import StubClient
from test_mesh3d import _cube_glb


class Stub3D(StubClient):
    """H3 as StubClient; TRELLIS returns a cube model."""

    def run_template(self, slot, values, out_dir):
        if slot == "trellis_mesh":
            self.calls.append((slot, values))
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            _cube_glb(Path(out_dir) / "m.glb")
            return {"slot": slot, "files": [str(Path(out_dir) / "m.glb")], "values": values}
        return super().run_template(slot, values, out_dir)

    def free(self):
        pass


@pytest.fixture
def hero(tmp_path):
    j = Job.create("hero", "j", base=tmp_path, description="a small knight")
    a = tmp_path / "a.png"
    Image.fromarray(render(draw_sprite(0), scale=8, offset=(60, 40), canvas=(256, 256))).save(a)
    generate.anchor(j, GameProfile(name="p"), image=a)
    j.set_stage("anchor", "approved")
    for f in angles.LEGACY:
        Image.fromarray(render(draw_sprite(1), scale=8, offset=(60, 40), canvas=(256, 256), seed=3)).save(j.root / "02_facings" / f"{f}.png")
    j.set_stage("facings", "approved")
    return j


def test_body_plan_and_yaws():
    assert views3d.yaws_for(16) == [22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5]
    assert len(views3d.yaws_for(32)) == 24
    with pytest.raises(ValueError):
        views3d.yaws_for(12)
    assert "all four legs" in builder.model_render("animal") and "upright" in builder.model_render("biped")
    assert "seen mostly from behind" in builder.view_words_3d(157.5, "biped")
    assert "shoulder blades" in builder.view_words_3d(202.5, "biped")
    assert "screen right" in builder.view_words_3d(292.5, "biped") and "front" in builder.view_words_3d(22.5, "animal")
    p = builder.view_from_model(157.5, "monster", "a goblin", "six legs")
    assert "a goblin" in p and "six legs" in p and "Add nothing" in p


def test_plan_follows_the_asset_type_and_props_are_refused(tmp_path):
    assert views3d.plan_of(Job.create("c", "a", base=tmp_path, asset_type="animal")) == "animal"
    assert views3d.plan_of(Job.create("c", "b", base=tmp_path, asset_type="creature")) == "monster"
    assert views3d.plan_of(Job.create("c", "c", base=tmp_path, view_plan="animal")) == "animal"
    with pytest.raises(ValueError, match="sprite stack"):
        views3d.model(Job.create("c", "d", base=tmp_path, asset_type="prop"), client=Stub3D())


def test_drop_floor_removes_a_ground_sheet_only():
    """2026-11-27: the goblin's TRELLIS model had a 1 x 1 floor sheet holding half its vertices."""
    body = np.array([[x, y, z] for x in (-.1, .1) for y in (0, .4) for z in (-.1, .1)], float)
    gx, gz = np.meshgrid(np.linspace(-.5, .5, 30), np.linspace(-.5, .5, 30))
    floor = np.stack([gx.ravel(), np.full(gx.size, 0.001), gz.ravel()], 1)
    pos = np.concatenate([body, floor])
    col = np.zeros((len(pos), 3), np.uint8)
    n = 30
    fl = [(8 + i * n + j, 8 + i * n + j + 1, 8 + (i + 1) * n + j) for i in range(n - 1) for j in range(n - 1)]
    faces = np.array([(0, 1, 3), (0, 3, 2), (4, 5, 7), (4, 7, 6), (0, 4, 6), (0, 6, 2)] + fl)
    p2, _, f2, removed = mesh3d.drop_floor(pos, col, faces)
    assert removed == len(fl) and len(f2) == 6 and np.ptp(p2[:, 0]) < 0.3
    _, _, _, none = mesh3d.drop_floor(body, col[:8], faces[:6])
    assert none == 0


def test_view_turns_the_model_by_yaw(tmp_path):
    """yaw 90 faces screen left: a model whose front (+z) is red shows red on the left half."""
    _cube_glb(tmp_path / "c.glb")
    P, C, F = mesh3d.read_glb(tmp_path / "c.glb")
    C = C.copy()
    C[P[:, 2] > 0] = (255, 0, 0)                                       # front face red
    img = mesh3d.view(P, C, F, 0, 0, size=128, frac=0.4)
    assert (img[..., 0] > 150).sum() > 200                              # front view: red
    img = mesh3d.view(P, C, F, 180, 0, size=128, frac=0.4)
    assert (img[..., 0] > 150).sum() < 20                               # back view: no red


def test_model_then_views_left_in_review(hero):
    c = Stub3D()
    with pytest.raises(FileNotFoundError):
        views3d.views(hero, 16, client=c)                               # no model yet
    views3d.model(hero, client=c, plan="biped")
    assert (hero.root / "02_views" / "model.glb").exists() and [s for s, _ in c.calls] == ["facing_multiref", "trellis_mesh"]
    rep = views3d.views(hero, 16, client=c)
    drawn = [y for y, v in rep["views"].items() if v.get("drawn")]
    assert sorted(map(float, drawn)) == [202.5, 247.5, 292.5, 337.5]   # right half drawn, left half mirrored
    for y in views3d.yaws_for(16):
        assert views3d.view_path(hero, y).exists()
    assert rep["views"]["22.5"]["mirrored_from"] == 337.5
    meta = hero.read_meta()
    assert meta["stages"]["views"]["status"] == "review" and meta["inputs"]["view_count"] == 16
    assert meta["stages"]["facings"]["status"] == "approved"           # the eight are untouched
    m = manifest.build(hero)
    v = {x["yaw_degrees"]: x for x in m["views"]}
    assert m["view_count"] == 16 and v[22.5]["facing_image"] == "02_facings/views/22.5.png" and v[22.5]["mirrored"]
    assert v[0.0]["facing_image"] == "02_facings/S.png"
    a = generate._rgba(hero.root / "01_anchor" / "anchor.png")
    w = generate._rgba(views3d.view_path(hero, 292.5))
    ay, wy = (a[..., 3] > 0).nonzero()[0], (w[..., 3] > 0).nonzero()[0]
    assert abs(int(ay.max()) - int(wy.max())) <= 1 and abs((ay.max() - ay.min()) - (wy.max() - wy.min())) <= 2  # anchor size, feet


def test_queue_runs_both_steps_on_the_gpu(hero):
    q = Queue(hero.root.parent.parent)
    t = q.submit(hero.root, "views_model", {"plan": "monster", "note": "six legs"})
    u = q.submit(hero.root, "views", {"count": 24})
    assert t["resource"] == u["resource"] == "gpu"
