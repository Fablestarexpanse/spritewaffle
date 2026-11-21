import json

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
