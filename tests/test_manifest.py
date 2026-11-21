"""Directional readiness: angles, per-asset manifest (read/write/migration), replayable downscale."""
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from spritewaffle.core import angles, manifest, stages
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.frames import layout
from spritewaffle.pixel.pipeline import PixelParams, pixelize
from synth import draw_sprite, render


def test_angles_any_view_count():
    assert angles.views(4) == [0, 90, 180, 270]
    assert len(angles.views(32)) == 32 and angles.views(16)[1] == 22.5
    assert [angles.yaw_of(f) for f in ("S", "W", "N", "E")] == [0, 90, 180, 270]
    assert angles.label(225) == "NE" and angles.label(22.5) == "22.5°"
    assert angles.mirror_of(270) == 90 and angles.mirror_of(0) == 0 and angles.mirror_of(180) == 180
    assert angles.view_index(270, 8) == 6 and angles.view_index(359.9, 16) == 0
    with pytest.raises(ValueError):
        angles.views(0)


def test_mirror_policies():
    assert angles.mirror_source(90, "mirror_left_from_right") == 270            # W from E
    assert angles.mirror_source(270, "mirror_left_from_right") is None          # E is rendered
    assert angles.mirror_source(0, "mirror_left_from_right") is None
    assert angles.mirror_source(90, "none") is None and angles.mirror_source(90, "legacy") is None
    assert angles.mirror_source(45, "custom", {"1": 7}, n=8) == 315             # SW from SE
    with pytest.raises(ValueError):
        angles.mirror_source(0, "sideways")


def _pixel_job(tmp_path, mirror=True):
    """A job with real pixel-stage output for S, E (+ W mirrored from E) built through stages."""
    j = Job.create("knight", "k1", base=tmp_path, description="knight")
    Image.fromarray(render(draw_sprite(0), canvas=(256, 256))).save(j.root / "01_anchor" / "anchor.png")
    prof = GameProfile(name="p", cell_size=64, sprite_height_px=40)
    for f in ("S", "E"):
        d = j.action_dir(f, "walk")
        frames = [render(draw_sprite(k % 3), canvas=(256, 256), seed=k) for k in range(4)]
        sel = d / "selected_12f"
        sel.mkdir(parents=True, exist_ok=True)
        for k, fr in enumerate(frames):
            Image.fromarray(fr).save(sel / f"{k:03d}_src{k:05d}.png")
        (d / "selection_report.json").write_text(json.dumps({"loop": True, "sets": {}}))
        res = pixelize(frames, PixelParams(palette=8, target_height=40))
        stages._write_pixel_sets(j, prof, f, "walk", {"12": ([res.rgba(i) for i in range(4)], [0, 1, 2, 3])}, res.palette,
                                 {"grid": {"size": res.grid.size, "ox": res.grid.ox, "oy": res.grid.oy,
                                           "source": res.grid.source, "resample": res.resample}})
    if mirror:
        stages.mirror_action(j, prof, "W", "walk")
    return j, prof


def test_manifest_build_write_read_round_trip(tmp_path):
    j, _ = _pixel_job(tmp_path)
    assert not manifest.path(j).exists()
    built = manifest.read(j)                      # migration: no file -> built from what exists
    assert built["schema_version"] == manifest.SCHEMA_VERSION and built["asset_id"] == "knight/k1"
    assert built["project_id"] == tmp_path.name and built["view_count"] == 8 and built["mirror_policy"] == "legacy"
    walk = next(a for a in built["animations"] if a["action"] == "walk" and a["frame_set"] == "12f")
    assert walk["views"] == [0, 2, 6] and len(walk["frames"]) == 12 and walk["loop"] is True
    w = [f for f in walk["frames"] if f["yaw_degrees"] == 90]
    assert all(f["mirrored"] and f["source_view_index"] == 6 for f in w)
    e = next(f for f in walk["frames"] if f["yaw_degrees"] == 270)
    assert not e["mirrored"] and e["master"].startswith("03_actions/E/walk/selected_12f/")
    assert e["color"] == "04_pixel/E/walk/12f/frames/000.png" and e["depth"] is None and e["normal"] is None
    assert e["foot_point"] and e["downscale"]["method"] == "pixelize"
    manifest.write(j, built)
    assert json.loads(manifest.path(j).read_text()) == json.loads(json.dumps(built))
    assert manifest.read(j) == json.loads(json.dumps(built))


def test_manifest_fills_defaults_and_refuses_newer_schema(tmp_path):
    j, _ = _pixel_job(tmp_path, mirror=False)
    manifest.path(j).write_text(json.dumps({"schema_version": 1, "asset_id": "knight/k1",
                                            "animations": [{"action": "walk", "frames": [{"frame": 0}]}]}))
    m = manifest.read(j)
    assert m["mirror_policy"] == "legacy" and m["views"] == []
    assert m["animations"][0]["frames"][0]["depth"] is None and m["animations"][0]["frames"][0]["mirrored"] is False
    manifest.path(j).write_text(json.dumps({"schema_version": 99}))
    with pytest.raises(ValueError, match="newer"):
        manifest.read(j)


def test_manifest_on_an_old_job_without_new_fields(tmp_path):
    j = Job.create("old", "o1", base=tmp_path)                 # nothing but job.json
    m = manifest.read(j)
    assert m["animations"] == [] and len(m["views"]) == 8 and m["camera"]["source"] == "implied"
    assert all(v["facing_image"] is None for v in m["views"])


def test_depth_and_normal_slots_are_picked_up(tmp_path):
    j, _ = _pixel_job(tmp_path, mirror=False)
    frame = j.root / "04_pixel/E/walk/12f/frames/000.png"
    Image.open(frame).save(frame.with_name("000_depth.png"))
    f = next(f for a in manifest.build(j)["animations"] for f in a["frames"] if f["yaw_degrees"] == 270 and f["frame"] == 0)
    assert f["depth"] == "04_pixel/E/walk/12f/frames/000_depth.png" and f["normal"] is None


def test_migrate_streams_and_keeps_existing(tmp_path):
    _pixel_job(tmp_path, mirror=False)
    Job.create("other", "x", base=tmp_path)
    first = [(j.root.name, st) for j, st in manifest.migrate(tmp_path)]
    assert sorted(first) == [("k1", "written"), ("x", "written")]
    assert all(st == "kept" for _, st in manifest.migrate(tmp_path))
    assert all(st == "written" for _, st in manifest.migrate(tmp_path, rebuild=True))


def test_replay_downscale_lines_up_with_the_colour_frame(tmp_path):
    j, _ = _pixel_job(tmp_path)
    for f in manifest.build(j)["animations"][0]["frames"]:
        master = np.array(Image.open(j.root / f["master"]).convert("RGB"))
        out = manifest.replay_downscale(master, f["downscale"])
        ref = np.array(Image.open(j.root / f["color"]).convert("RGBA"))
        assert ((out[..., 3] > 0) == (ref[..., 3] > 0)).all(), (f["yaw_degrees"], f["frame"])   # same pixels lit
        depth = manifest.replay_downscale(np.full_like(master, 128), f["downscale"], alpha_from=master, quantize=False)
        assert ((depth[..., 3] > 0) == (ref[..., 3] > 0)).all()                                 # a map lines up too


def test_foot_point_and_align(tmp_path):
    cell = np.zeros((32, 32, 4), np.uint8)
    cell[10:20, 12:16] = 255
    assert layout.foot_point(cell) == [14.0, 20.0]
    moved = np.zeros_like(cell)
    moved[12:24, 5:9] = 255
    out, pts, warns = layout.align_feet([cell, moved, cell], border=2)
    assert pts[0] == pts[1] == pts[2] and not warns
    assert (out[0] == cell).all()                                               # already on the median: untouched
    left = np.zeros_like(cell)
    left[10:20, 2:6] = 255                                                       # median foot point near the left edge
    wide = np.zeros_like(cell)
    wide[10:20, 10:20] = 255                                                     # wide: can't get its feet there
    out, pts, warns = layout.align_feet([left, left, wide], border=2)
    assert len(warns) == 1 and warns[0].startswith("frame 2: kept 2px border")
    assert np.where(out[2][..., 3] > 0)[1].min() == 2 and (out[0] == left).all()
