import io
import json
from base64 import b64encode
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle import cli
from spritewaffle.core import manifest, stages, timeline
from spritewaffle.core.job import Job
from spritewaffle.core.profile import resolve
from spritewaffle.export import aseprite, character
from spritewaffle.mcp_server import build
from spritewaffle.ui.server import create_app
from test_character_export import _anim
from test_mcp import call, text


@pytest.fixture
def clip(tmp_path):
    job = Job.create("hero", "j", base=tmp_path, facing="S", action="walk")
    _anim(job, "S", "walk", [(70, 20, 180)])
    directory = job.root / "04_pixel" / "S" / "walk" / "12f"
    (directory.parent / "pixel_report.json").write_text('{"palette": [], "sets": {"12": 12}}', encoding="utf-8")
    (directory / "placements.json").write_text("[]", encoding="utf-8")
    return job, directory


def _image(size=(16, 16), color=(190, 60, 104, 128)):
    sprite = Image.new("RGBA", size)
    sprite.paste(color, (4, 4, 10, 12))
    data = io.BytesIO()
    sprite.save(data, format="PNG")
    return data.getvalue()


def test_timeline_keeps_sources_and_disables_conflicting_replacements(clip):
    job, directory = clip
    source = directory / "frames" / "001.png"
    original = source.read_bytes()
    timeline.update(job.root, directory, source.name, "duration", 320)
    timeline.update(job.root, directory, source.name, "replace", _image())
    frame = timeline.frames(job.root, directory)[1]
    assert frame.duration_ms == 320 and frame.image != source
    assert source.read_bytes() == original
    saved = frame.image
    with Image.open(source) as sprite:
        new_source = sprite.copy()
    new_source.putpixel((5, 5), (75, 22, 182, 255))
    new_source.save(source)
    frame = timeline.frames(job.root, directory)[1]
    assert frame.image == source and frame.conflict and frame.duration_ms == 320
    timeline.update(job.root, directory, source.name, "restore")
    assert not timeline.frames(job.root, directory)[1].conflict and saved.is_file()
    with pytest.raises(ValueError, match="16"):
        timeline.update(job.root, directory, source.name, "replace", _image((8, 8)))
    with pytest.raises(ValueError, match="duration"):
        timeline.update(job.root, directory, source.name, "duration", 70000)


def test_timeline_edits_feed_qa_and_both_exporters(clip):
    job, directory = clip
    profile = resolve(None)
    action_out = stages.export(job, profile)
    character_dir = job.root / "06_export" / "character"
    character.export(job.root, character_dir, "hero", profile.fps)
    timeline.update(job.root, directory, "001.png", "duration", 320)
    timeline.update(job.root, directory, "001.png", "replace", _image())
    assert character.export_status(job.root, character_dir, profile.fps)["status"] == "stale"
    assert stages.export_status(job, profile)["formats"]["png"]["status"] == "stale"
    with pytest.raises(RuntimeError, match="QA needs to review"):
        character.export(job.root, character_dir, "hero", profile.fps)
    assert stages.qa(job, profile)["12f"] == "pass"

    revised = stages.export(job, profile)
    assert revised == action_out
    action_doc = aseprite.read(revised["12f"]["aseprite"])
    assert action_doc.durations[1] == 320 and action_doc.depth == 32
    assert np.array_equal(action_doc.frames[1][5, 5], [190, 60, 104, 128])
    meta = json.loads(Path(revised["12f"]["json"]).read_text(encoding="utf-8"))
    assert meta["frames"][1]["duration_ms"] == 320
    for preview in ("apng", "gif"):
        with Image.open(revised["12f"][preview]) as sprite:
            sprite.seek(1)
            assert sprite.info["duration"] == 320
    out = character.export(job.root, character_dir, "hero", profile.fps)
    doc = aseprite.read(out["aseprite"])
    assert doc.durations[1] == 320 and np.array_equal(doc.frames[1][5, 5], [190, 60, 104, 128])
    atlas = json.loads(Path(out["json"]).read_text(encoding="utf-8"))
    assert atlas["animations"][0]["durations_ms"][1] == 320


def test_aligned_character_keeps_other_frames_and_omits_replaced_map(clip):
    job, directory = clip
    stages.align(job, resolve(None))
    source = directory / "frames" / "001.png"
    with Image.open(source) as frame:
        frame.save(source.with_name("001_depth.png"))
        frame.save(source.with_name("000_depth.png"))
    orig_aligned = (directory / "frames_aligned" / "000.png").read_bytes()
    timeline.update(job.root, directory, "001.png", "replace", _image())
    anim = character.collect(job.root, require_pass=False)[0][0]
    with Image.open(io.BytesIO(orig_aligned)) as original:
        assert np.array_equal(anim["cells"][0], np.asarray(original))
    assert np.array_equal(anim["cells"][1][5, 5], [190, 60, 104, 128])
    assert anim["maps"]["depth"][0].any() and not anim["maps"]["depth"][1].any()
    frames = manifest.read(job)["animations"][0]["frames"]
    assert frames[1]["color"].startswith("edits/animations/") and frames[1]["color_source"].endswith("/001.png")
    assert frames[1]["depth"] is None
    assert (directory / "frames_aligned" / "000.png").read_bytes() == orig_aligned


def test_timeline_edits_are_shared_by_http_cli_and_mcp(clip, tmp_path, monkeypatch, capsys):
    job, directory = clip
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    args = ["timeline", "--job", "hero/j", "--facing", "S", "--action", "walk"]
    assert cli.main([*args, "--frame", "001.png", "--duration", "320"]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["frames"][1]["duration_ms"] == 320
    route = "/api/jobs/hero/j/timeline?facing=S&action=walk"
    with TestClient(create_app(tmp_path, worker=False)) as client:
        assert client.get(route).json()["frames"][1]["duration_ms"] == 320
        assert client.post(route, json={"frame": "001.png", "operation": "replace", "png": "invalid!"}).status_code == 400
        response = client.post(route, json={"frame": "001.png", "operation": "replace", "png": b64encode(_image()).decode()})
        assert response.status_code == 200
        item = response.json()["frames"][1]
        assert item["replaced"] and client.get(item["url"]).status_code == 200
        assert response.json()["qa_needs_review"]
    mcp, _ = build(tmp_path)
    result = text(call(mcp, "edit_timeline_frame", character="hero", job_id="j", facing="S",
                       action="walk", frame="001.png", operation="restore"))
    assert result["frames"][1]["image"] == (directory / "frames" / "001.png").relative_to(job.root).as_posix()
    assert result["frames"][1]["duration_ms"] == 320 and not result["frames"][1]["replaced"]
    assert cli.main([*args, "--frame", "001.png", "--use-version", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["frames"][1]["history"][0]["active"]
    with TestClient(create_app(tmp_path, worker=False)) as client:
        assert client.post(route, json={"frame": "001.png", "operation": "restore"}).status_code == 200
        response = client.post(route, json={"frame": "001.png", "operation": "activate", "version": 1})
        version = response.json()["frames"][1]["history"][0]
        assert version["active"] and client.get(version["url"]).status_code == 200
    result = text(call(mcp, "edit_timeline_frame", character="hero", job_id="j", facing="S",
                       action="walk", frame="001.png", operation="activate", version=1))
    assert result["frames"][1]["history"][0]["active"]


def test_replacement_history_survives_restore_and_reuse(clip):
    job, directory = clip
    profile = resolve(None)
    base_fps = profile.fps("walk")
    source = directory / "frames" / "001.png"
    original = source.read_bytes()
    timeline.update(job.root, directory, source.name, "duration", 320)
    timeline.update(job.root, directory, source.name, "replace", _image())
    first = timeline.frames(job.root, directory)[1].image
    stages.qa(job, profile)
    stages.export(job, profile)
    timeline.update(job.root, directory, source.name, "replace", _image(color=(60, 190, 104, 255)))
    second = timeline.frames(job.root, directory)[1].image
    assert timeline.describe(job.root, directory, base_fps)["qa_needs_review"]
    assert stages.export_status(job, profile)["formats"]["png"]["status"] == "stale"
    timeline.update(job.root, directory, source.name, "restore")

    view = timeline.describe(job.root, directory, base_fps)["frames"][1]
    assert [item["version"] for item in view["history"]] == [1, 2]
    assert all(item["available"] and not item["active"] for item in view["history"])
    timeline.update(job.root, directory, source.name, "activate", 1)
    view = timeline.describe(job.root, directory, base_fps)["frames"][1]
    assert timeline.frames(job.root, directory)[1].image == first
    assert view["history"][0]["active"] and view["duration_ms"] == 320
    assert second.is_file() and source.read_bytes() == original
    assert not timeline.describe(job.root, directory, base_fps)["qa_needs_review"]
    assert {item["status"] for item in stages.export_status(job, profile)["formats"].values()} == {"current"}
    with pytest.raises(ValueError, match="version"):
        timeline.update(job.root, directory, source.name, "activate", 3)
    second.unlink()
    assert not timeline.describe(job.root, directory, base_fps)["frames"][1]["history"][1]["available"]
    with pytest.raises(ValueError, match="missing or has changed"):
        timeline.update(job.root, directory, source.name, "activate", 2)
    assert timeline.frames(job.root, directory)[1].image == first


def test_legacy_replacement_can_be_reapplied_to_same_size_source(clip):
    job, directory = clip
    source = directory / "frames" / "001.png"
    timeline.update(job.root, directory, source.name, "replace", _image())
    early = timeline.frames(job.root, directory)[1].image
    sidecar = early.parent.parent / "timeline.json"
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    record["frames"][source.name].pop("history", None)
    sidecar.write_text(json.dumps(record), encoding="utf-8")
    with Image.open(source) as image:
        edited_source = image.copy()
    edited_source.putpixel((5, 5), (80, 20, 180, 255))
    edited_source.save(source)
    view = timeline.describe(job.root, directory, 12)["frames"][1]
    assert view["conflict"] and not view["history"][0]["same_source"]
    timeline.update(job.root, directory, source.name, "activate", 1)
    view = timeline.describe(job.root, directory, 12)["frames"][1]
    assert view["replaced"] and not view["conflict"]
    assert [item["same_source"] for item in view["history"]] == [False, True]
    assert timeline.frames(job.root, directory)[1].image == early

    edited_source.resize((8, 8)).save(source)
    with pytest.raises(ValueError, match="8 × 8"):
        timeline.update(job.root, directory, source.name, "activate", 1)
    assert timeline.frames(job.root, directory)[1].conflict
