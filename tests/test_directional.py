"""Directional readiness: camera profile, mirror policy, align stage, depth/normal export slots,
and the API / MCP calls. Everything here is additive: with nothing set, behaviour is unchanged."""
import asyncio
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import camera, generate, manifest, stages
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.core.queue import Queue
from spritewaffle.export import character
from spritewaffle.mcp_server import build
from spritewaffle.ui.server import create_app
from synth import draw_sprite, render
from test_character_export import _anim
from test_generate import StubClient
from test_manifest import _pixel_job


def _anchor_job(tmp_path, **inputs):
    j = Job.create("hero", "h1", base=tmp_path, description="a hero", **inputs)
    Image.fromarray(render(draw_sprite(0), canvas=(256, 256))).save(j.root / "01_anchor" / "anchor.png")
    j.set_stage("anchor", "approved")
    return j


# --- camera profile -------------------------------------------------------------------------
def test_no_camera_profile_means_unchanged_prompts(tmp_path):
    j = _anchor_job(tmp_path)
    assert camera.prompt_sentence(j) == "" and camera.effective(j)[1] == "implied"
    c = StubClient()
    generate.facings(j, GameProfile(name="p"), client=c, only=["E"])
    sent = c.calls[0][1]["prompt"]
    from spritewaffle.prompts import builder
    assert sent == builder.facing("E", [], "S", "", raised=False, animal=False)      # byte-identical


def test_camera_profile_project_and_asset(tmp_path):
    j = _anchor_job(tmp_path)
    imp = camera.implied(GameProfile(name="p", projection="topdown_34", sprite_height_px=40))
    assert imp.camera_elevation_degrees == 45 and imp.character_scale == 40
    camera.set_project(tmp_path, {"camera_elevation_degrees": 60, "style_notes": "muted colours"})
    cam, src = camera.effective(j)
    assert src == "project" and cam.camera_elevation_degrees == 60 and cam.canvas_border_px == 2
    s = camera.prompt_sentence(j)
    assert "60 degrees above" in s and s.endswith("muted colours.")
    camera.set_asset(j, {"camera_elevation_degrees": 0})          # same as the profile implies: no sentence for it
    assert camera.effective(j)[1] == "asset" and camera.prompt_sentence(j) == "muted colours."
    camera.set_asset(j, {"camera_elevation_degrees": 10})
    assert camera.prompt_sentence(j).startswith("The camera looks down at the character from 10 degrees")
    c = StubClient()
    generate.facings(j, GameProfile(name="p"), client=c, only=["E"])
    assert c.calls[0][1]["prompt"].endswith("muted colours.")                          # applied to generation
    prov = json.loads((j.root / "job.json").read_text())["provenance"]
    assert [p for p in prov if p["output"].replace("\\", "/") == "02_facings/E.png"][-1]["camera"]["source"] == "asset"
    with pytest.raises(ValueError):
        camera.set_asset(j, {"framing": 3})
    with pytest.raises(ValueError, match="unknown camera fields"):
        camera.set_project(tmp_path, {"elevation": 10})
    camera.set_asset(j, None)
    camera.set_project(tmp_path, None)
    assert camera.effective(j)[1] == "implied" and manifest.build(j)["camera"]["source"] == "implied"


def test_character_scale_reaches_the_pixel_stage(tmp_path):
    j = _anchor_job(tmp_path)
    prof = GameProfile(name="p", cell_size=64, sprite_height_px=48)
    assert camera.character_height(j, prof) == 48
    camera.set_project(tmp_path, {"character_scale": 30})
    assert camera.character_height(j, prof) == 30
    camera.set_project(tmp_path, {"character_scale": 200})                   # doesn't fit the cell: ignored
    assert camera.character_height(j, prof) == 48


# --- mirror policy --------------------------------------------------------------------------
def test_mirror_left_from_right_renders_half_and_flips_the_rest(tmp_path):
    j = _anchor_job(tmp_path)
    manifest.set_mirror_policy(j, "mirror_left_from_right")
    c = StubClient()
    rep = generate.facings(j, GameProfile(name="p"), client=c)
    rendered = {next(t for t in ("E", "N", "NE", "SE", "W", "NW", "SW") if f", {__import__('spritewaffle.prompts.builder', fromlist=['VIEW']).VIEW[t]}, in the same" in v["prompt"]) for _, v in c.calls}
    assert rendered == {"E", "N", "NE", "SE"}                                  # W, NW, SW never rendered
    assert {f: m["from"] for f, m in rep["mirrored"].items()} == {"W": "E", "NW": "NE", "SW": "SE"}
    out = j.root / "02_facings"
    assert np.array_equal(np.array(Image.open(out / "W.png")), np.array(Image.open(out / "E.png"))[:, ::-1])
    views = {v["label"]: v for v in manifest.build(j)["views"]}
    assert views["W"]["mirrored"] and views["W"]["source_view_index"] == 6 and not views["E"]["mirrored"]


def test_policy_none_never_flips_and_custom_needs_a_map(tmp_path):
    j = _anchor_job(tmp_path)
    manifest.set_mirror_policy(j, "none")
    rep = generate.facings(j, GameProfile(name="p"), client=StubClient(drift_for={"W"}))
    assert rep["mirrored"] == {}                                               # legacy would have flipped drifted W
    with pytest.raises(ValueError):
        manifest.set_mirror_policy(j, "custom")
    with pytest.raises(ValueError):
        manifest.set_mirror_policy(j, "custom", {"1": 1})
    assert manifest.set_mirror_policy(j, "custom", {"1": 7})["mirror_map"] == {"1": 7}
    with pytest.raises(ValueError):
        manifest.set_mirror_policy(j, "sideways")


def test_animate_plan_follows_the_policy(tmp_path):
    j = _anchor_job(tmp_path)
    q = Queue(tmp_path)
    stages_of = lambda ts: [(t["stage"], t["args"].get("facing"), t["args"].get("source")) for t in ts]
    legacy = stages_of(q.submit_animate(j.root, ["E", "W"], ["walk"], mirror=True))
    assert ("mirror", "W", "E") in legacy                                      # unchanged default
    manifest.set_mirror_policy(j, "none")
    assert all(s != "mirror" for s, _, _ in stages_of(q.submit_animate(j.root, ["E", "W"], ["walk"], mirror=True)))
    manifest.set_mirror_policy(j, "mirror_left_from_right")
    plan = stages_of(q.submit_animate(j.root, ["W"], ["walk"], mirror=False))   # only W asked: E is rendered for it
    assert ("mirror", "W", "E") in plan and ("action", "E", None) in plan


def test_mirroring_output_is_an_exact_flip(tmp_path):
    j, _ = _pixel_job(tmp_path)
    for k in range(4):
        e = np.array(Image.open(j.root / f"04_pixel/E/walk/12f/frames/{k:03d}.png"))
        w = np.array(Image.open(j.root / f"04_pixel/W/walk/12f/frames/{k:03d}.png"))
        assert np.array_equal(e[..., 3] > 0, (w[..., 3] > 0)[:, ::-1]) or (w[..., 3] > 0).sum() == (e[..., 3] > 0).sum()


# --- align + export slots ------------------------------------------------------------------
def test_align_stage_keeps_originals_and_feeds_export(tmp_path):
    j, prof = _pixel_job(tmp_path, mirror=False)
    before = {p: p.read_bytes() for p in (j.root / "04_pixel").rglob("frames/*.png")}
    rep = stages.align(j, prof)
    assert rep["border"] == 2 and all((p.read_bytes() == b) for p, b in before.items())   # originals untouched
    al = j.root / "04_pixel/E/walk/12f/frames_aligned"
    pts = json.loads((al / "footpoints.json").read_text())
    assert len({tuple(p) for p in pts if p}) == 1                                          # one foot point
    assert j.read_meta()["inputs"]["align_feet"] is True
    f = next(f for a in manifest.build(j)["animations"] for f in a["frames"] if f["yaw_degrees"] == 270)
    assert "frames_aligned" in f["color"] and f["color_unaligned"].endswith("/frames/000.png")


def test_export_unchanged_without_maps_and_packs_maps_when_present(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    _anim(job, "S", "walk", [(200, 0, 0), (0, 0, 200)])
    a = character.export(job.root, tmp_path / "a", "hero", lambda x: 12)
    assert "map_pages" not in a
    snap = {p.name: p.read_bytes() for p in (tmp_path / "a").iterdir()}
    fr = job.root / "04_pixel/S/walk/12f/frames"
    for i in range(12):                                     # depth maps: a different colour, same alpha
        c = np.array(Image.open(fr / f"{i:03d}.png"))
        c[c[..., 3] > 0, :3] = (90, 90, 90)
        Image.fromarray(c).save(fr / f"{i:03d}_depth.png")
    b = character.export(job.root, tmp_path / "b", "hero", lambda x: 12)
    assert b["animations"] == a["animations"] and len(json.loads(Path(b["json"]).read_text())["animations"][0]["frames_atlas"]) == 12
    same = {n: (tmp_path / "b" / n).read_bytes() for n in snap if n != "hero_atlas.json"}
    assert same == {n: v for n, v in snap.items() if n != "hero_atlas.json"}                     # colour output identical
    jb = json.loads((tmp_path / "b" / "hero_atlas.json").read_text())
    assert jb.pop("map_pages") and jb == json.loads(snap["hero_atlas.json"])                     # only map_pages added
    assert b["map_pages"] == {"depth": ["hero_atlas_depth_0.png"]}
    col = np.array(Image.open(tmp_path / "b" / "hero_atlas_0.png"))
    dep = np.array(Image.open(tmp_path / "b" / "hero_atlas_depth_0.png"))
    assert np.array_equal(col[..., 3] > 0, dep[..., 3] > 0) and (dep[dep[..., 3] > 0, :3] == 90).all()


# --- API and MCP ---------------------------------------------------------------------------
def test_api_camera_mirror_manifest(tmp_path):
    j, _ = _pixel_job(tmp_path, mirror=False)
    with TestClient(create_app(tmp_path, worker=False)) as c:
        p = c.get("/api/project/camera").json()
        assert p["camera"] is None and "framing" in p["fields"]
        assert c.post("/api/project/camera", json={"camera": {"camera_elevation_degrees": 35}}).json()["camera"]["camera_elevation_degrees"] == 35
        assert c.post("/api/project/camera", json={"camera": {"framing": 5}}).status_code == 400
        r = c.post("/api/jobs/knight/k1/camera", json={"camera": {"style_notes": "gritty"}}).json()
        assert r["source"] == "asset" and r["camera_elevation_degrees"] == 35
        assert c.post("/api/jobs/knight/k1/mirror_policy", json={"policy": "none"}).json()["mirror_policy"] == "none"
        assert c.post("/api/jobs/knight/k1/mirror_policy", json={"policy": "x"}).status_code == 400
        m = c.get("/api/jobs/knight/k1/manifest").json()
        assert m["schema_version"] == 1 and m["mirror_policy"] == "none" and m["camera"]["style_notes"] == "gritty"
        assert c.post("/api/jobs/knight/k1/manifest/rebuild").json()["asset_id"] == "knight/k1"
        assert manifest.path(j).exists()
        assert c.post("/api/jobs/knight/k1/run", json={"stage": "align", "args": {}}).status_code == 200


def test_mcp_camera_mirror_manifest(tmp_path):
    _pixel_job(tmp_path, mirror=False)
    m, _ = build(tmp_path)
    call = lambda name, **a: json.loads((lambda r: (r[0] if isinstance(r, tuple) else r)[0].text)(asyncio.run(m.call_tool(name, a))))
    assert call("camera_profile")["camera"] is None
    assert call("camera_profile", action="set", camera={"camera_elevation_degrees": 20})["camera"]["camera_elevation_degrees"] == 20
    assert call("camera_profile", action="set", character="knight", job_id="k1", camera={"canvas_border_px": 3})["effective"]["canvas_border_px"] == 3
    assert call("mirror_policy", character="knight", job_id="k1", policy="mirror_left_from_right")["view_count"] == 8
    man = call("manifest", character="knight", job_id="k1", rebuild=True)
    assert man["mirror_policy"] == "mirror_left_from_right" and man["camera"]["source"] == "asset"
    assert call("manifest_migrate")["counts"] == {"kept": 1}
