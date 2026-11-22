import io
import json
from base64 import b64decode, b64encode
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle import cli
from spritewaffle.core import attach, job_palette, manifest, stages, timeline
from spritewaffle.core.job import Job
from spritewaffle.core.profile import resolve
from spritewaffle.export import aseprite, character
from spritewaffle.frames.video import colour_frames
from spritewaffle.mcp_server import build
from spritewaffle.ui.server import create_app
from test_attach import _effect
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


def test_pixel_save_edits_only_changed_rgba_on_selected_copy(clip):
    job, directory = clip
    profile = resolve(None)
    timeline.update(job.root, directory, "001.png", "replace", _image(color=(170, 30, 200, 1)))
    copy = timeline.update(job.root, directory, "001.png", "duplicate")
    timeline.update(job.root, directory, copy, "duration", 320)
    stages.qa(job, profile)
    stages.export(job, profile)
    original, source_copy = timeline.frames(job.root, directory)[1:3]
    source = original.source.read_bytes()
    job_palette.save(job, ["#b25648"], "test palette")

    view = timeline.describe_pixels(job.root, directory, copy)
    assert (view["width"], view["height"], view["palette"]) == (16, 16, ["#b25648"])
    pixel = (5 * 16 + 5) * 4
    assert b64decode(view["rgba"])[pixel:pixel + 4] == bytes((170, 30, 200, 1))
    patch = {"fingerprint": view["fingerprint"], "pixels": [[4, 4, 15, 20, 25, 100], [6, 6, 0, 0, 0, 0]]}
    assert timeline.update(job.root, directory, copy, "paint", patch) == copy
    kept, painted = timeline.frames(job.root, directory)[1:3]
    assert kept == original and painted.duration_ms == 320 and painted.image != source_copy.image
    with Image.open(source_copy.image) as result:
        expected = result.convert("RGBA")
    expected.putpixel((4, 4), (15, 20, 25, 100))
    expected.putpixel((6, 6), (0, 0, 0, 0))
    with Image.open(painted.image) as result:
        assert result.tobytes() == expected.tobytes()
    state = timeline.describe(job.root, directory, profile.fps("walk"))
    assert state["qa_needs_review"] and len(state["frames"][2]["history"]) == 2
    assert stages.export_status(job, profile)["formats"]["png"]["status"] == "stale"
    stages.qa(job, profile)
    out = aseprite.read(stages.export(job, profile)["12f"]["aseprite"])
    assert np.array_equal(out.frames[2], np.asarray(expected))
    timeline.update(job.root, directory, copy, "activate", 1)
    assert timeline.frames(job.root, directory)[2] == source_copy
    assert original.source.read_bytes() == source


def test_pixel_save_rejects_stale_and_malformed_patches_without_mutation(clip):
    job, directory = clip
    frame = "001.png"
    timeline.update(job.root, directory, frame, "replace", _image())
    view = timeline.describe_pixels(job.root, directory, frame)
    folder = timeline._edit_directory(job.root, directory)
    state = (folder / "timeline.json").read_bytes()
    saved = set((folder / "replacements").iterdir())
    valid = [4, 4, 40, 22, 30, 90]
    for invalid in ([16, 4, 0, 0, 0, 0], [4, 3, False, 0, 0, 0], [4, 4, 0, 0, 0, 0], [1, 1, 0, 0, 0, 256]):
        with pytest.raises(ValueError, match="pixel"):
            timeline.update(job.root, directory, frame, "paint", {"fingerprint": view["fingerprint"], "pixels": [valid, invalid]})
    assert (folder / "timeline.json").read_bytes() == state
    assert set((folder / "replacements").iterdir()) == saved
    timeline.update(job.root, directory, frame, "paint", {"fingerprint": view["fingerprint"], "pixels": [[4, 4, 190, 60, 104, 128]]})
    assert (folder / "timeline.json").read_bytes() == state
    assert set((folder / "replacements").iterdir()) == saved

    for change in ("restore", "source"):
        if change == "restore":
            timeline.update(job.root, directory, frame, "restore")
        else:
            (directory / "frames" / frame).write_bytes(_image(color=(3, 4, 5, 255)))
        with pytest.raises(RuntimeError, match="changed.*reopen"):
            timeline.update(job.root, directory, frame, "paint", {"fingerprint": view["fingerprint"], "pixels": [valid]})
        view = timeline.describe_pixels(job.root, directory, frame)
    assert set((folder / "replacements").iterdir()) == saved


def test_pixels_are_shared_by_http_cli_and_mcp(clip, tmp_path, monkeypatch, capsys):
    job, directory = clip
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    route = "/api/jobs/hero/j/timeline"
    query = "?facing=S&action=walk"
    args = ["timeline", "--job", "hero/j", "--facing", "S", "--action", "walk", "--frame", "001.png"]
    with TestClient(create_app(worker=False)) as client:
        view = client.get(route + "/pixels" + query + "&frame=001.png").json()
        assert view["width"] == 16
        assert cli.main([*args, "--pixels"]) == 0
        assert view == json.loads(capsys.readouterr().out)
        mcp_args = dict(character="hero", job_id="j", facing="S", action="walk", frame="001.png")
        mcp, _ = build(tmp_path)
        mcp_view = text(call(mcp, "timeline_pixels", **mcp_args))
        assert "rgba" not in mcp_view and mcp_view["fingerprint"] == view["fingerprint"]
        patch = {"fingerprint": view["fingerprint"], "pixels": [[5, 5, 20, 30, 40, 50]]}
        resp = client.post(route + query, json={"operation": "paint", "frame": "001.png", **patch})
        assert resp.status_code == 200 and resp.json()["frames"][1]["replaced"]
        assert client.post(route + query, json={"operation": "paint", "frame": "001.png", **patch}).status_code == 400
        patch["fingerprint"] = client.get(route + "/pixels" + query + "&frame=001.png").json()["fingerprint"]
        patch["pixels"][0][-1] = 51
        path = tmp_path / "patch.json"
        path.write_text(json.dumps(patch), encoding="utf-8")
        assert cli.main([*args, "--paint", str(path)]) == 0
        assert len(json.loads(capsys.readouterr().out)["frames"][1]["history"]) == 2
        patch["fingerprint"] = timeline.describe_pixels(job.root, directory, "001.png")["fingerprint"]
        patch["pixels"][0][-1] = 52
        edited = text(call(mcp, "edit_timeline_frame", **mcp_args, operation="paint", **patch))
        assert len(edited["frames"][1]["history"]) == 3


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


def test_duplicate_and_move_preserve_edits_and_support_order_undo(clip):
    job, directory = clip
    source = directory / "frames" / "001.png"
    original = source.read_bytes()
    timeline.update(job.root, directory, source.name, "duration", 320)
    timeline.update(job.root, directory, source.name, "replace", _image())
    copy = timeline.update(job.root, directory, source.name, "duplicate")
    assert copy and copy != source.name
    items = timeline.frames(job.root, directory)
    assert items[1].image == items[2].image and items[2].duration_ms == 320
    timeline.update(job.root, directory, copy, "duration", 181)
    timeline.update(job.root, directory, copy, "move", 0)
    assert timeline.frames(job.root, directory)[0].id == copy
    timeline.update(job.root, directory, None, "undo")
    assert timeline.frames(job.root, directory)[2].id == copy
    timeline.update(job.root, directory, None, "undo")
    assert len(timeline.frames(job.root, directory)) == 12
    timeline.update(job.root, directory, None, "redo")
    timeline.update(job.root, directory, None, "redo")
    items = timeline.frames(job.root, directory)
    assert items[0].id == copy and items[0].duration_ms == 181
    assert next(f for f in items if f.id == source.name).duration_ms == 320
    timeline.update(job.root, directory, copy, "restore")
    items = timeline.frames(job.root, directory)
    assert not items[0].replaced and next(f for f in items if f.id == source.name).replaced
    assert source.read_bytes() == original


def test_order_updates_qa_and_both_exports_without_copying_events(clip, tmp_path):
    job, directory = clip
    profile = resolve(None)
    sources = colour_frames(directory / "frames")
    # Numbered colours are identical but the two silhouettes alternate, so index order is observable.
    palette = {"palette": ["#4614b4"], "sets": {"12": 12}}
    (directory.parent / "pixel_report.json").write_text(json.dumps(palette), encoding="utf-8")
    pixels = timeline.pixels(sources)
    np.save(directory / "indices.npy", np.where(pixels[..., 3] > 0, 0, -1))
    attach.set_attachment(job, "S", "walk", _effect(tmp_path), frame=1, x=8, y=8)
    stages.export(job, profile)
    copy = timeline.update(job.root, directory, "001.png", "duplicate")
    timeline.update(job.root, directory, "001.png", "move", 0)
    timeline.update(job.root, directory, copy, "duration", 157)
    assert stages.export_status(job, profile)["formats"]["aseprite"]["status"] == "stale"
    assert timeline.describe(job.root, directory, 12)["qa_needs_review"]
    out_dir = job.root / "06_export" / "character"
    with pytest.raises(RuntimeError, match="QA needs to review"):
        character.export(job.root, out_dir, "hero", profile.fps)
    stages.qa(job, profile)
    assert not timeline.describe(job.root, directory, 12)["qa_needs_review"]
    result = stages.export(job, profile)["12f"]
    doc = aseprite.read(result["aseprite"])
    assert doc.depth == 8 and len(doc.frames) == 13 and doc.durations[2] == 157
    assert np.array_equal(doc.frames[0] > 0, pixels[1, ..., 3] > 0)
    sheet = json.loads(Path(result["json"]).read_text(encoding="utf-8"))
    assert [ev["frame"] for ev in sheet["events"]] == [0]
    assert [frame["frame_id"] for frame in sheet["frames"][:3]] == ["001.png", "000.png", copy]
    result = character.export(job.root, out_dir, "hero", profile.fps)
    entry = json.loads(Path(result["json"]).read_text(encoding="utf-8"))["animations"][0]
    assert entry["frames"] == 13 and entry["durations_ms"][2] == 157
    assert [ev["frame"] for ev in entry["events"]] == [0]
    frames = manifest.read(job)["animations"][0]["frames"]
    assert [frame["frame_id"] for frame in frames[:3]] == ["001.png", "000.png", copy]
    assert frames[0]["color"] == frames[2]["color"]

    exported_frames = job.root / "06_export" / "S" / "walk" / "12f" / "frames"
    extra = exported_frames / "walk_S_12f_012.png"
    assert extra.is_file()
    keep = exported_frames / "reference.png"
    keep.write_bytes(sources[0].read_bytes())
    timeline.update(job.root, directory, None, "undo")
    timeline.update(job.root, directory, None, "undo")
    stages.export(job, profile)
    assert not extra.exists() and keep.is_file()
    timeline.update(job.root, directory, "001.png", "duplicate")
    stages.export(job, profile)
    edited_export = _image()
    extra.write_bytes(edited_export)
    timeline.update(job.root, directory, None, "undo")
    stages.export(job, profile)
    assert extra.read_bytes() == edited_export


def test_order_operations_are_shared_by_http_cli_and_mcp(clip, tmp_path, monkeypatch, capsys):
    job, _ = clip
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    args = ["timeline", "--job", "hero/j", "--facing", "S", "--action", "walk"]
    assert cli.main([*args, "--frame", "001.png", "--duplicate"]) == 0
    copy = json.loads(capsys.readouterr().out)["selected_frame"]
    route = "/api/jobs/hero/j/timeline?facing=S&action=walk"
    with TestClient(create_app(tmp_path, worker=False)) as client:
        response = client.post(route, json={"frame": copy, "operation": "move", "position": 0})
        assert response.status_code == 200 and response.json()["frames"][0]["id"] == copy
        response = client.post(route, json={"frame": copy, "operation": "move", "position": 99})
        assert response.status_code == 400
    mcp, _ = build(tmp_path)
    undo = text(call(mcp, "edit_timeline_frame", character="hero", job_id="j", facing="S", action="walk", operation="undo"))
    assert undo["can_redo"] and undo["frames"][2]["id"] == copy
    assert cli.main([*args, "--redo-order"]) == 0
    redo = json.loads(capsys.readouterr().out)
    assert not redo["can_redo"] and redo["frames"][0]["id"] == copy


def test_order_keeps_missing_source_positions_and_discards_redo_branch(clip):
    job, directory = clip
    source = directory / "frames" / "001.png"
    original = source.read_bytes()
    first = timeline.update(job.root, directory, source.name, "duplicate")
    source.unlink()
    timeline.update(job.root, directory, "002.png", "move", 0)
    source.write_bytes(original)
    assert [f.id for f in timeline.frames(job.root, directory)[:4]] == ["002.png", "001.png", first, "000.png"]
    timeline.update(job.root, directory, None, "undo")
    timeline.update(job.root, directory, None, "undo")
    second = timeline.update(job.root, directory, source.name, "duplicate")
    assert second != first
    assert not timeline.describe(job.root, directory, 12)["can_redo"]


def test_duplicates_extend_playback_without_switching_character_fps(clip):
    job, directory = clip
    profile = resolve(None)
    for _ in range(12):
        timeline.update(job.root, directory, "001.png", "duplicate")
    files = character.export(job.root, job.root / "06_export" / "character", "hero", profile.fps, require_pass=False)
    doc = aseprite.read(files["aseprite"])
    assert len(doc.frames) == 24
    assert all(ms == round(1000 / profile.fps("walk")) for ms in doc.durations)


def test_saved_qa_links_to_the_replacement_on_a_copied_frame(clip, tmp_path):
    job, directory = clip
    copy = timeline.update(job.root, directory, "001.png", "duplicate")
    with Image.open(io.BytesIO(_image())) as image:
        image.putpixel((0, 0), (255, 0, 0, 255))
        replacement = io.BytesIO()
        image.save(replacement, format="PNG")
    timeline.update(job.root, directory, copy, "replace", replacement.getvalue())
    assert stages.qa(job, resolve(None))["12f"] == "fail"
    timeline.update(job.root, directory, copy, "move", 0)
    with TestClient(create_app(tmp_path, worker=False)) as client:
        report = client.get("/api/jobs/hero/j").json()["actions"][0]["sets"]["12f"]["qa"]
        border = next(finding for finding in report["frame_findings"]
                      if any(issue["code"] == "border" for issue in finding["issues"]))
        assert border["frame_id"] == copy and border["frame"] == 2
        assert "/edits/animations/" in border["preview"] and client.get(border["preview"]).status_code == 200
