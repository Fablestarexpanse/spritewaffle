import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from spritewaffle.core.job import Job
from spritewaffle.export import aseprite, character


def _anim(job, facing, action, colours, n=12, status="pass", size=16):
    sd = job.root / "04_pixel" / facing / action / "12f" / "frames"
    sd.mkdir(parents=True)
    for i in range(n):
        f = np.zeros((size, size, 4), np.uint8)
        f[4:12, 4 + i % 2:10 + i % 2] = (*colours[i % len(colours)], 255)
        Image.fromarray(f).save(sd / f"{i:03d}.png")
    q = job.root / "05_qa" / facing / action / "12f"
    q.mkdir(parents=True)
    (q / "report.json").write_text(json.dumps({"status": status}))
    a = job.root / "03_actions" / facing / action
    a.mkdir(parents=True)
    (a / "selection_report.json").write_text(json.dumps({"loop": action != "attack"}))


def test_character_export_tags_palette_and_skips(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    _anim(job, "S", "walk", [(200, 0, 0), (0, 0, 200)])
    _anim(job, "E", "idle", [(0, 200, 0)], n=12)
    _anim(job, "N", "attack", [(9, 9, 9)], status="fail")
    out = character.export(job.root, tmp_path / "out", "hero", lambda a: {"walk": 12, "idle": 8}.get(a, 12))
    assert out["animations"] == ["idle_E", "walk_S"] and out["mode"] == "indexed"
    assert out["skipped"] == ["attack_N: QA failed"] and out["colours"] == 3
    doc = aseprite.read(out["aseprite"])
    assert doc.tags == [("idle_E", 0, 11, "forward"), ("walk_S", 12, 23, "forward")]
    assert len(doc.frames) == 24 and doc.durations[0] == 125 and doc.durations[12] == 83
    # palette exact (index 0 = transparent), pixels round-trip
    assert {tuple(c) for c in doc.palette[1:, :3].tolist()} == {(200, 0, 0), (0, 0, 200), (0, 200, 0)}
    meta = json.loads(open(out["json"]).read())
    assert len(meta["pages"]) == 1 and meta["animations"][0]["loop"] is True
    page = np.array(Image.open(out["atlas"]).convert("RGBA"))
    f = meta["animations"][1]["frames_atlas"][0]                       # rebuild walk_S frame 0 from the atlas
    cell = np.zeros((16, 16, 4), np.uint8)
    cell[f["oy"]:f["oy"] + f["h"], f["ox"]:f["ox"] + f["w"]] = page[f["y"]:f["y"] + f["h"], f["x"]:f["x"] + f["w"]]
    src = {a["name"]: a["cells"] for a in character.collect(job.root)[0]}["walk_S"][0]
    assert np.array_equal(cell, src)


def test_character_export_refuses_mixed_cell_sizes_and_empty(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    with pytest.raises(RuntimeError, match="nothing to export"):
        character.export(job.root, tmp_path / "o", "hero", lambda a: 12)
    _anim(job, "S", "walk", [(1, 2, 3)], size=16)
    _anim(job, "E", "walk", [(1, 2, 3)], size=32)
    with pytest.raises(ValueError, match="cell sizes"):
        character.export(job.root, tmp_path / "o", "hero", lambda a: 12)


def test_character_export_freshness_tracks_inputs_and_bundle_files(tmp_path):
    job = Job.create("hero", "j", base=tmp_path)
    out_dir = job.root / "06_export" / "character"
    fps = lambda action: 12
    check = lambda: character.export_status(job.root, out_dir, fps)
    assert check()["status"] == "missing"
    out_dir.mkdir()
    (out_dir / "hero.aseprite").write_bytes(b"legacy")
    assert check()["status"] == "untracked"

    _anim(job, "S", "walk", [(1, 2, 3)])
    out = character.export(job.root, out_dir, "hero", fps)
    assert check()["status"] == "current"
    raw = job.root / "03_actions/S/walk/raw.mp4"
    raw.write_bytes(b"new AI source")
    assert check()["status"] == "current"
    assert character.export_status(job.root, out_dir, lambda action: 15)["settings_changed"] == ["fps"]

    frame = job.root / "04_pixel/S/walk/12f/frames/000.png"
    with Image.open(frame) as image:
        changed = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    changed.save(frame)
    assert check()["changed_inputs"] == ["04_pixel/S/walk/12f/frames/000.png"]
    Path(out["atlas"]).unlink()
    assert check()["changed_outputs"] == [Path(out["atlas"]).name]
    character.export(job.root, out_dir, "hero", fps)
    assert check()["status"] == "current"

    _anim(job, "N", "attack", [(9, 9, 9)], status="fail")
    assert check()["status"] == "stale"
    character.export(job.root, out_dir, "hero", fps)
    assert check()["status"] == "current"
    report = job.root / "05_qa/N/attack/12f/report.json"
    report.write_text('{"status": "pass"}', encoding="utf-8")
    assert "05_qa/N/attack/12f/report.json" in check()["changed_inputs"]
    assert "04_pixel/N/attack/12f/frames/000.png" in check()["changed_inputs"]


def test_character_export_reports_interrupted_bundle_and_can_retry(tmp_path, monkeypatch):
    job = Job.create("hero", "j", base=tmp_path)
    _anim(job, "S", "walk", [(1, 2, 3)])
    out_dir = tmp_path / "out"
    fps = lambda action: 12
    character.export(job.root, out_dir, "hero", fps)

    def interrupted(*args, **kwargs):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(aseprite, "write", interrupted)
        with pytest.raises(OSError, match="disk full"):
            character.export(job.root, out_dir, "hero", fps)
    assert character.export_status(job.root, out_dir, fps)["status"] == "incomplete"
    character.export(job.root, out_dir, "hero", fps)
    assert character.export_status(job.root, out_dir, fps)["status"] == "current"


def test_character_export_refuses_concurrent_writer_and_changed_inputs(tmp_path, monkeypatch):
    job = Job.create("hero", "j", base=tmp_path)
    _anim(job, "S", "walk", [(1, 2, 3)])
    out_dir = tmp_path / "out"
    write = aseprite.write

    def change_inputs(*args, **kwargs):
        with pytest.raises(RuntimeError, match="already running"):
            character.export(job.root, out_dir, "hero", lambda action: 12)
        selection = job.root / "03_actions/S/walk/selection_report.json"
        selection.write_text('{"loop": false}', encoding="utf-8")
        return write(*args, **kwargs)

    monkeypatch.setattr(aseprite, "write", change_inputs)
    with pytest.raises(RuntimeError, match="inputs changed"):
        character.export(job.root, out_dir, "hero", lambda action: 12)
    assert character.export_status(job.root, out_dir, lambda action: 12)["status"] == "incomplete"


def test_rgba_export_writes_no_palette_list(tmp_path):
    """Audit P2 #5: a painted character wrote a 345,331-entry 'palette' (5.6 MB) into the JSON."""
    job = Job.create("hero", "j", base=tmp_path)
    _anim(job, "S", "walk", [(c, 255 - c, c // 2) for c in range(0, 256, 1)], n=12)
    sd = job.root / "04_pixel" / "S" / "walk" / "12f" / "frames"
    for i in range(12):                                # > 255 colours: RGBA mode
        f = np.zeros((32, 32, 4), np.uint8)
        f[..., :3] = np.arange(32 * 32 * 3).reshape(32, 32, 3) % 251 + i
        f[..., 3] = 255
        Image.fromarray(f).save(sd / f"{i:03d}.png")
    out = character.export(job.root, tmp_path / "out", "hero", lambda a: 12)
    meta = json.loads(Path(out["json"]).read_text())
    assert out["mode"] == "rgba" and "palette" not in meta
    small = Job.create("hero", "k", base=tmp_path)
    _anim(small, "S", "walk", [(200, 0, 0)])
    out = character.export(small.root, tmp_path / "out2", "hero", lambda a: 12)
    assert json.loads(Path(out["json"]).read_text())["palette"] == ["#c80000"]
