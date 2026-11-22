import io
import json
from base64 import b64decode, b64encode
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle import cli
from spritewaffle.core import attach, frame_repair, job_palette, manifest, stages, timeline
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


def test_reposition_preserves_rgba_and_saves_only_the_selected_frame(clip):
    job, directory = clip
    profile = resolve(None)
    frame = "001.png"
    timeline.update(job.root, directory, frame, "replace", _image())
    timeline.update(job.root, directory, frame, "duration", 140)
    old = timeline.frames(job.root, directory)[1]
    stages.qa(job, profile)
    stages.export(job, profile)
    files = {path: path.read_bytes() for path in job.root.rglob("*") if path.is_file()}
    result = frame_repair.preview_reposition(job.root, directory, frame, dx=-2, dy=3)
    with Image.open(old.image) as source:
        expected = Image.new("RGBA", source.size)
        expected.paste(source, (-2, 3))
    with Image.open(io.BytesIO(b64decode(result["after_png"]))) as after:
        assert after.tobytes() == expected.tobytes()
        assert after.getpixel((3, 8)) == (190, 60, 104, 128)
        assert after.getpixel((7, 2)) == (0, 0, 0, 0)
    assert result["foot_before"] == [7.0, 12.0] and result["foot_after"] == [5.0, 15.0]
    assert {path: path.read_bytes() for path in job.root.rglob("*") if path.is_file()} == files
    options = {"fingerprint": result["fingerprint"], "dx": -2, "dy": 3}
    timeline.update(job.root, directory, frame, "reposition", options)
    assert old.source.read_bytes() == files[old.source] and old.image.read_bytes() == files[old.image]
    assert timeline.describe(job.root, directory, 12)["qa_needs_review"]
    assert stages.export_status(job, profile)["formats"]["png"]["status"] == "stale"
    stages.qa(job, profile)
    actual = aseprite.read(stages.export(job, profile)["12f"]["aseprite"])
    assert actual.durations[1] == 140 and np.array_equal(actual.frames[1], np.asarray(expected))
    version = timeline.describe(job.root, directory, 12)["frames"][1]["history"]
    assert len(version) == 2 and version[1]["active"]
    timeline.update(job.root, directory, frame, "activate", 1)
    assert timeline.frames(job.root, directory)[1] == old


def test_foot_alignment_defaults_to_vertical_and_binds_the_reference(clip):
    job, directory = clip
    reference = "002.png"
    edited = Image.new("RGBA", (16, 16))
    edited.paste((70, 20, 180, 255), (8, 3, 14, 9))
    buffer = io.BytesIO()
    edited.save(buffer, format="PNG")
    timeline.update(job.root, directory, reference, "replace", buffer.getvalue())
    vertical = frame_repair.preview_reposition(job.root, directory, "000.png", reference=reference)
    both = frame_repair.preview_reposition(job.root, directory, "000.png", reference=reference, axes="both")
    assert vertical["foot_reference"] == [11.0, 9.0]
    assert [vertical["dx"], vertical["dy"]] == [0, -3] and vertical["foot_after"] == [7.0, 9.0]
    assert [both["dx"], both["dy"]] == [4, -3] and both["foot_after"] == [11.0, 9.0]
    assert vertical["fingerprint"] != both["fingerprint"]
    timeline.update(job.root, directory, reference, "restore")
    with pytest.raises(RuntimeError, match="compare again"):
        timeline.update(job.root, directory, "000.png", "reposition",
                        {"reference": reference, "fingerprint": vertical["fingerprint"]})
    assert not timeline.frames(job.root, directory)[0].replaced
    timeline.update(job.root, directory, reference, "activate", 1)
    timeline.update(job.root, directory, "000.png", "reposition",
                    {"reference": reference, "axes": "both", "fingerprint": both["fingerprint"]})
    item = manifest.read(job)["animations"][0]["frames"][0]
    assert item["foot_point"] == [11.0, 9.0]


def test_reposition_refuses_clipping_invalid_offsets_and_empty_reference(clip):
    job, directory = clip
    frame = "000.png"
    for options, message in (({"dx": -5}, "clip"), ({"dy": 5}, "clip"), ({"dx": True}, "whole"),
                             ({"reference": frame}, "different"), ({"reference": "005.png", "dx": 1}, "offsets or")):
        with pytest.raises(ValueError, match=message):
            frame_repair.preview_reposition(job.root, directory, frame, **options)
    blank = timeline.update(job.root, directory, frame, "insert_blank")
    with pytest.raises(ValueError, match="no visible"):
        frame_repair.preview_reposition(job.root, directory, frame, reference=blank)
    zero = frame_repair.preview_reposition(job.root, directory, frame, include_png=False)
    assert zero["changed_pixels"] == 0 and "after_png" not in zero
    timeline.update(job.root, directory, frame, "reposition", {"fingerprint": zero["fingerprint"]})
    assert not timeline.describe(job.root, directory, 12)["frames"][0]["history"]


def test_reposition_is_available_through_http_cli_and_mcp(clip, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    endpoint = "/api/jobs/hero/j/timeline"
    query = "?facing=S&action=walk"
    frame = "002.png"
    args = ["timeline", "--job", "hero/j", "--facing", "S", "--action", "walk", "--frame", frame]
    with TestClient(create_app(worker=False)) as client:
        response = client.get(endpoint + "/reposition" + query + "&frame=" + frame + "&dx=2")
        assert response.status_code == 200
        view = response.json()
        assert client.post(endpoint + query, json={"operation": "reposition", "frame": frame,
                                                  "fingerprint": view["fingerprint"], "dx": 3}).status_code == 400
    assert cli.main([*args, "--preview-reposition", "--dx", "2"]) == 0
    assert json.loads(capsys.readouterr().out) == view
    mcp, _ = build(tmp_path)
    target = {"character": "hero", "job_id": "j", "facing": "S", "action": "walk", "frame": frame, "dx": 2}
    compared = text(call(mcp, "preview_frame_reposition", **target))
    assert compared["fingerprint"] == view["fingerprint"] and "after_png" not in compared
    saved = text(call(mcp, "edit_timeline_frame", **target, operation="reposition", fingerprint=view["fingerprint"]))
    assert saved["frames"][2]["replaced"]
    assert cli.main([*args, "--restore"]) == 0
    capsys.readouterr()
    assert cli.main([*args, "--apply-reposition", view["fingerprint"], "--dx", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["frames"][2]["replaced"]


@pytest.fixture
def retained_frame(clip):
    job, directory = clip
    master = job.root / "03_actions/S/walk/selected_12f/002_src00006.png"
    master.parent.mkdir()
    rgba = Image.new("RGB", (16, 16), (0, 255, 0))
    rgba.paste((32, 165, 48), (4, 4, 12, 12))
    rgba.save(master)
    report = {"style": "painted", "scale": 1.0, "palette": [], "cell": 16,
              "sets": {"12": {"frames": 12, "sources": list(range(0, 36, 3))}}}
    (directory.parent / "pixel_report.json").write_text(json.dumps(report), encoding="utf-8")
    places = [{"scale": 1.0, "crop": [0, 0, 16, 16], "paste": [0, 0]}] * 12
    (directory / "placements.json").write_text(json.dumps(places), encoding="utf-8")
    return job, directory, master


def test_reprocess_preview_is_read_only_and_apply_saves_a_copy_version(retained_frame):
    job, directory, master = retained_frame
    profile = resolve(None)
    copy = timeline.update(job.root, directory, "002.png", "duplicate")
    timeline.update(job.root, directory, copy, "duration", 140)
    stages.qa(job, profile)
    stages.export(job, profile)
    files = {path: path.read_bytes() for path in job.root.rglob("*") if path.is_file()}

    before = frame_repair.preview(job.root, directory, copy)
    preferred = frame_repair.preview(job.root, directory, copy, despill="edge")
    assert preferred["source"] == master.relative_to(job.root).as_posix()
    assert preferred["changed_pixels"] > 0 and [preferred["width"], preferred["height"]] == [16, 16]
    assert preferred["fingerprint"] != before["fingerprint"]
    with Image.open(io.BytesIO(b64decode(preferred["before_png"]))) as current:
        assert current.getpixel((7, 7)) == (70, 20, 180, 255)
        original_pixels = np.asarray(current).copy()
    with Image.open(io.BytesIO(b64decode(preferred["after_png"]))) as candidate:
        assert candidate.getpixel((7, 7)) == (32, 165, 48, 255)
        different = np.any(np.asarray(candidate) != original_pixels, axis=2)
    with Image.open(io.BytesIO(b64decode(preferred["change_mask_png"]))) as mask:
        assert np.array_equal(np.asarray(mask)[..., 3] > 0, different)
    assert preferred["changed_pixels"] == np.count_nonzero(different)
    assert {path: path.read_bytes() for path in job.root.rglob("*") if path.is_file()} == files

    patch = {"fingerprint": preferred["fingerprint"], "despill": "edge"}
    timeline.update(job.root, directory, copy, "reprocess", patch)
    current, repaired = timeline.frames(job.root, directory)[2:4]
    assert not current.replaced and repaired.replaced and repaired.duration_ms == 140
    assert master.read_bytes() == files[master] and current.source.read_bytes() == files[current.source]
    assert timeline.describe(job.root, directory, 12)["qa_needs_review"]
    assert stages.export_status(job, profile)["formats"]["png"]["status"] == "stale"
    stages.qa(job, profile)
    exported = aseprite.read(stages.export(job, profile)["12f"]["aseprite"])
    assert exported.frames[3][7, 7].tolist() == [32, 165, 48, 255] and exported.durations[3] == 140
    again = frame_repair.preview(job.root, directory, copy, despill="edge", include_png=False)
    assert again["changed_pixels"] == 0 and "after_png" not in again
    timeline.update(job.root, directory, copy, "reprocess", patch | {"fingerprint": again["fingerprint"]})
    assert len(timeline.describe(job.root, directory, 12)["frames"][3]["history"]) == 1


def test_reprocess_rejects_stale_comparison_and_missing_provenance(retained_frame):
    job, directory, master = retained_frame
    frame = "002.png"
    current = frame_repair.preview(job.root, directory, frame)
    timeline.update(job.root, directory, frame, "replace", _image())
    with pytest.raises(RuntimeError, match="compare again"):
        timeline.update(job.root, directory, frame, "reprocess", {"fingerprint": current["fingerprint"]})
    current = frame_repair.preview(job.root, directory, frame)
    raw = master.read_bytes()
    with Image.open(io.BytesIO(raw)) as source:
        source.putpixel((7, 7), (200, 45, 130))
        source.save(master)
    with pytest.raises(RuntimeError, match="compare again"):
        timeline.update(job.root, directory, frame, "reprocess", {"fingerprint": current["fingerprint"]})
    assert len(timeline.describe(job.root, directory, 12)["frames"][2]["history"]) == 1
    with pytest.raises(FileNotFoundError, match="retained"):
        frame_repair.preview(job.root, directory, "001.png")
    inserted = timeline.update(job.root, directory, frame, "insert", _image())
    with pytest.raises(ValueError, match="inserted"):
        frame_repair.preview(job.root, directory, inserted)
    report_path = directory.parent / "pixel_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["method"] = "mirror"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="mirror"):
        frame_repair.preview(job.root, directory, frame)


def test_reprocess_pixel_candidate_uses_report_palette_and_locked_grid(retained_frame):
    job, directory, _ = retained_frame
    report_path = directory.parent / "pixel_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.pop("scale")
    report.update(style="pixel", palette=["#203030", "#20a530"], grid={"size": 1, "ox": 0, "oy": 0, "resample": 1.0})
    report_path.write_text(json.dumps(report), encoding="utf-8")
    for despill, expected in (("all", (32, 48, 48, 255)), ("edge", (32, 165, 48, 255))):
        result = frame_repair.preview(job.root, directory, "002.png", despill=despill)
        with Image.open(io.BytesIO(b64decode(result["after_png"]))) as candidate:
            assert candidate.getpixel((7, 7)) == expected


def test_reprocess_is_available_in_http_cli_and_mcp(retained_frame, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    endpoint = "/api/jobs/hero/j/timeline"
    query = "?facing=S&action=walk"
    frame = "002.png"
    args = ["timeline", "--job", "hero/j", "--facing", "S", "--action", "walk", "--frame", frame]
    with TestClient(create_app(worker=False)) as client:
        response = client.get(endpoint + "/reprocess" + query + "&frame=" + frame + "&despill=edge")
        assert response.status_code == 200
        view = response.json()
        body = {"operation": "reprocess", "frame": frame, "fingerprint": view["fingerprint"], "despill": "all"}
        assert client.post(endpoint + query, json=body).status_code == 400
    assert cli.main([*args, "--preview-reprocess", "--despill", "edge"]) == 0
    assert json.loads(capsys.readouterr().out) == view
    mcp, _ = build(tmp_path)
    options = {"character": "hero", "job_id": "j", "facing": "S", "action": "walk", "frame": frame, "despill": "edge"}
    mcp_view = text(call(mcp, "preview_frame_reprocess", **options))
    assert mcp_view["fingerprint"] == view["fingerprint"] and "after_png" not in mcp_view
    result = text(call(mcp, "edit_timeline_frame", **options, operation="reprocess", fingerprint=view["fingerprint"]))
    assert result["frames"][2]["replaced"]
    assert cli.main([*args, "--restore"]) == 0
    capsys.readouterr()
    assert cli.main([*args, "--apply-reprocess", view["fingerprint"], "--despill", "edge"]) == 0
    assert json.loads(capsys.readouterr().out)["frames"][2]["replaced"]


def test_named_tags_are_additive_in_both_exporters_and_the_manifest(clip):
    job, directory = clip
    profile = resolve(None)
    _anim(job, "E", "idle", [(20, 90, 140)])
    bundle_dir = job.root / "06_export/character"
    stages.export(job, profile)
    character.export(job.root, bundle_dir, "hero", profile.fps)
    view = timeline.describe(job.root, directory, profile.fps("walk"))
    recover = {"name": "Récupération", "start_frame": "005.png", "end_frame": "009.png", "loop": False}
    coast = {"name": "Coast", "start_frame": "001.png", "end_frame": "006.png", "loop": True}
    tag_id = timeline.update(job.root, directory, None, "save_tag", recover)
    timeline.update(job.root, directory, None, "save_tag", coast)
    updated = timeline.describe(job.root, directory, profile.fps("walk"))
    assert [tag["name"] for tag in updated["tags"]] == [recover["name"], coast["name"]]
    assert updated["tags"][0] == recover | {"id": tag_id, "start": 5, "end": 9, "error": None}
    assert updated["playback"] == view["playback"] and updated["qa_needs_review"]
    assert {item["status"] for item in stages.export_status(job, profile)["formats"].values()} == {"stale"}
    assert character.export_status(job.root, bundle_dir, profile.fps)["status"] == "stale"

    assert stages.qa(job, profile)["12f"] == "pass"
    assert not timeline.describe(job.root, directory, profile.fps("walk"))["qa_needs_review"]
    manifest_anim = manifest.read(job)["animations"][0]
    assert manifest_anim["tags_by_view"][str(manifest_anim["views"][0])] == updated["tags"]
    action = stages.export(job, profile)["12f"]
    character_out = character.export(job.root, bundle_dir, "hero", profile.fps)
    doc = aseprite.read(action["aseprite"])
    tags = [("walk_S", 0, 11, "forward"), ("walk_S [Récupération]", 5, 9, "forward"), ("walk_S [Coast]", 1, 6, "forward")]
    assert len(doc.frames) == 12 and doc.tags == tags and doc.repeats == [0, 1, 0]
    packed = aseprite.read(character_out["aseprite"])
    assert len(packed.frames) == 24
    assert packed.tags == [("idle_E", 0, 11, "forward"), *[(name, a + 12, b + 12, direction) for name, a, b, direction in tags]]
    assert packed.repeats == [0, 0, 1, 0]
    action_meta = json.loads(Path(action["json"]).read_text(encoding="utf-8"))
    char_meta = json.loads(Path(character_out["json"]).read_text(encoding="utf-8"))["animations"]
    assert "tags" not in char_meta[0]
    assert action_meta["tags"] == char_meta[1]["tags"] == [
        {"name": "Récupération", "start": 5, "end": 9, "loop": False, "aseprite_tag": "walk_S [Récupération]"},
        {"name": "Coast", "start": 1, "end": 6, "loop": True, "aseprite_tag": "walk_S [Coast]"},
    ]


def test_named_tags_follow_frame_ids_and_reject_invalid_edits(clip):
    job, directory = clip
    profile = resolve(None)
    copy = timeline.update(job.root, directory, "001.png", "duplicate")
    tag = {"name": "Loop", "start_frame": copy, "end_frame": "004.png", "loop": True}
    tag_id = timeline.update(job.root, directory, None, "save_tag", tag)
    with pytest.raises(ValueError, match="already"):
        timeline.update(job.root, directory, None, "save_tag", tag | {"name": " loop "})
    for change in ({"name": "bad[tag]"}, {"name": ""}, {"loop": "true"}, {"start_frame": "0000.png"}):
        with pytest.raises(ValueError):
            timeline.update(job.root, directory, None, "save_tag", tag | change)
    timeline.update(job.root, directory, "000.png", "move", 3)
    view = timeline.describe(job.root, directory, 12)["tags"][0]
    assert view["start"] == 1 and view["end"] == 5 and view["id"] == tag_id
    timeline.update(job.root, directory, copy, "move", 8)
    assert "before" in timeline.describe(job.root, directory, 12)["tags"][0]["error"]
    with pytest.raises(ValueError, match="Loop.*before"):
        stages.export(job, profile)
    timeline.update(job.root, directory, None, "undo")
    timeline.update(job.root, directory, copy, "remove")
    assert "missing" in timeline.describe(job.root, directory, 12)["tags"][0]["error"]
    with pytest.raises(RuntimeError, match="Loop.*missing"):
        character.export(job.root, job.root / "06_export/character", "hero", profile.fps, require_pass=False)
    timeline.update(job.root, directory, None, "undo")
    assert timeline.describe(job.root, directory, 12)["tags"][0] == view
    renamed = timeline.update(job.root, directory, tag_id, "save_tag", tag | {"name": "Motion"})
    assert renamed == tag_id
    timeline.update(job.root, directory, tag_id, "remove_tag")
    assert timeline.describe(job.root, directory, 12)["tags"] == []
    with pytest.raises(ValueError, match="tag"):
        timeline.update(job.root, directory, tag_id, "save_tag", tag)


def test_named_loop_seam_finding_points_to_tag_endpoints(clip):
    job, directory = clip
    for i, x in enumerate([3, 2, 3, 4, 5, 6, 7, 8, 9, 8, 6, 3]):
        frame = Image.new("RGBA", (20, 16))
        frame.paste((70, 20, 180, 255), (x, 4, x + 8, 12))
        frame.save(directory / "frames" / f"{i:03}.png")
    tag = {"name": "March", "start_frame": "001.png", "end_frame": "006.png", "loop": True}
    timeline.update(job.root, directory, None, "save_tag", tag)
    timeline.update(job.root, directory, None, "save_tag", tag | {"name": "Once", "loop": False})
    assert stages.qa(job, resolve(None))["12f"] == "pass"
    review = stages.qa_review(job)["12f"]
    assert any("March" in warning for warning in review["warnings"]) and not any("Once" in warning for warning in review["warnings"])
    assert [(entry["frame"], entry["file"]) for entry in review["frame_findings"]
            if any(issue["code"] == "tag-loop-seam" for issue in entry["issues"])] == [(1, "001.png"), (6, "006.png")]


def test_named_tags_share_state_between_http_cli_and_mcp(clip, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    route = "/api/jobs/hero/j/timeline?facing=S&action=walk"
    args = ["timeline", "--job", "hero/j", "--facing", "S", "--action", "walk"]
    tag = {"name": "Land", "start_frame": "001.png", "end_frame": "005.png", "loop": False}
    path = tmp_path / "tag.json"
    path.write_text(json.dumps(tag), encoding="utf-8")
    assert cli.main([*args, "--save-tag", str(path)]) == 0
    view = json.loads(capsys.readouterr().out)
    tag_id = view["selected_tag"]
    with TestClient(create_app(worker=False)) as client:
        assert client.get(route).json()["tags"] == view["tags"]
        response = client.post(route, json={"operation": "save_tag", "tag_id": tag_id, "tag": tag | {"name": "Impact"}})
        assert response.status_code == 200 and response.json()["selected_tag"] == tag_id
        assert response.json()["tags"][0]["name"] == "Impact"
    mcp, _ = build(tmp_path)
    result = text(call(mcp, "edit_timeline_frame", character="hero", job_id="j", facing="S", action="walk",
                       operation="remove_tag", tag_id=tag_id))
    assert result["tags"] == []


def test_inserted_frames_export_with_exact_rgba_and_can_be_undone(clip):
    job, directory = clip
    profile = resolve(None)
    stages.align(job, profile)
    processed = {p.name: p.read_bytes() for p in colour_frames(directory / "frames")}
    aligned = (directory / "frames_aligned/003.png").read_bytes()
    (directory / "frames/003_depth.png").write_bytes(_image())
    stages.export(job, profile)
    output = job.root / "06_export/S/walk"
    before = {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    character_dir = job.root / "06_export/character"
    character.export(job.root, character_dir, "hero", profile.fps)

    inserted = timeline.update(job.root, directory, "001.png", "insert", _image(color=(19, 71, 203, 121)))
    view = timeline.describe(job.root, directory, profile.fps("walk"))
    assert inserted == "insert-1" and len(view["frames"]) == 13
    assert view["frames"][2]["id"] == inserted and view["frames"][2]["inserted"]
    path = job.root / view["frames"][2]["image"]
    assert path.is_file() and path.is_relative_to(job.root / "edits")
    assert view["qa_needs_review"]
    assert stages.export_status(job, profile)["formats"]["png"]["status"] == "stale"
    assert character.export_status(job.root, character_dir, profile.fps)["status"] == "stale"
    assert timeline.update(job.root, directory, "002.png", "remove") == "003.png"
    stages.qa(job, profile)
    result = stages.export(job, profile)["12f"]
    bundle = character.export(job.root, character_dir, "hero", profile.fps)
    for product in (result, bundle):
        document = aseprite.read(product["aseprite"])
        assert document.depth == 32 and len(document.frames) == 12
        assert document.durations[2] == round(1000 / profile.fps("walk"))
        assert document.frames[2][5, 5].tolist() == [19, 71, 203, 121]
    packed = character.collect(job.root)[0][0]
    assert packed["maps"]["depth"][3].any() and not packed["maps"]["depth"][2].any()
    with Image.open(io.BytesIO(aligned)) as original:
        assert np.array_equal(packed["cells"][3], np.asarray(original))
    data = manifest.read(job)["animations"][0]["frames"]
    assert data[2]["inserted"] and data[2]["frame_id"] == inserted and data[2]["downscale"] is None
    assert data[2]["depth"] is None and data[3]["source_frame"] == "003.png"
    assert timeline.update(job.root, directory, None, "undo") is None
    assert timeline.update(job.root, directory, None, "undo") is None
    stages.qa(job, profile)
    stages.export(job, profile)
    assert {p.relative_to(output): p.read_bytes() for p in output.rglob("*") if p.is_file()} == before
    assert path.is_file() and {p.name: p.read_bytes() for p in colour_frames(directory / "frames")} == processed
    timeline.update(job.root, directory, None, "redo")
    assert timeline.frames(job.root, directory)[2].source == path


def test_removal_keeps_playback_endpoints_and_does_not_retarget_legacy_attachment(clip):
    job, directory = clip
    profile = resolve(None)
    effect = _effect(job.root.parent.parent)
    attach.set_attachment(job, "S", "walk", effect, 2, 8, 8)
    with job.mutate() as meta:
        del meta["inputs"]["attachments"]["walk_S"]["source_frame"]
    timeline.update(job.root, directory, None, "playback", {"mode": "once", "start_frame": "000.png", "end_frame": "003.png"})
    timeline.update(job.root, directory, "002.png", "remove")
    stages.qa(job, profile)
    output = stages.export(job, profile)["12f"]
    metadata = json.loads(Path(output["json"]).read_text(encoding="utf-8"))
    assert metadata["events"] == [] and metadata["playback_range"] == [0, 2]
    assert [frame["frame_id"] for frame in metadata["frames"][:3]] == ["000.png", "001.png", "003.png"]
    timeline.update(job.root, directory, "003.png", "remove")
    assert "missing" in timeline.describe(job.root, directory, profile.fps("walk"))["playback"]["error"]
    with pytest.raises(ValueError, match="missing"):
        stages.export(job, profile)
    timeline.update(job.root, directory, None, "undo")
    timeline.update(job.root, directory, None, "undo")
    stages.qa(job, profile)
    metadata = json.loads(Path(stages.export(job, profile)["12f"]["json"]).read_text(encoding="utf-8"))
    assert metadata["events"][0]["frame"] == 2 and metadata["playback_range"] == [0, 3]


def test_insert_validation_and_last_frame_removal_preserve_the_timeline(clip):
    job, directory = clip
    with pytest.raises(ValueError, match="16"):
        timeline.update(job.root, directory, "000.png", "insert", _image((8, 8)))
    assert len(timeline.frames(job.root, directory)) == 12
    for source in colour_frames(directory / "frames")[1:]:
        timeline.update(job.root, directory, source.name, "remove")
    with pytest.raises(ValueError, match="last"):
        timeline.update(job.root, directory, "000.png", "remove")
    view = timeline.describe(job.root, directory, 12)
    assert [frame["id"] for frame in view["frames"]] == ["000.png"]
    imported = timeline.update(job.root, directory, "000.png", "insert_blank")
    snapshot = timeline.describe_pixels(job.root, directory, imported)
    assert not any(b64decode(snapshot["rgba"]))
    assert stages.qa(job, resolve(None))["12f"] == "fail"
    patch = {"fingerprint": snapshot["fingerprint"], "pixels": [[5, 5, 19, 71, 203, 121]]}
    timeline.update(job.root, directory, imported, "paint", patch)
    copied = timeline.update(job.root, directory, imported, "duplicate")
    assert timeline.frames(job.root, directory)[2].insertion_id == imported
    timeline.update(job.root, directory, imported, "remove")
    assert timeline.frames(job.root, directory)[1].id == copied
    timeline.update(job.root, directory, None, "undo")
    assert timeline.frames(job.root, directory)[1].id == imported
    assert timeline.describe_pixels(job.root, directory, imported) == timeline.describe_pixels(job.root, directory, copied)


def test_unavailable_insertions_block_qa_and_export_until_repaired_or_removed(clip):
    job, directory = clip
    profile = resolve(None)
    inserted = timeline.update(job.root, directory, "000.png", "insert_blank")
    path = timeline.frames(job.root, directory)[1].source
    original = path.read_bytes()
    path.write_bytes(_image())
    view = timeline.describe(job.root, directory, profile.fps("walk"))
    assert view["unavailable"] == {inserted: "Saved PNG has changed."}
    assert view["qa_needs_review"]
    with pytest.raises(ValueError, match="unavailable.*insert-1"):
        stages.export(job, profile)
    with pytest.raises(ValueError, match="unavailable.*insert-1"):
        stages.qa(job, profile)
    with pytest.raises(RuntimeError, match="unavailable.*insert-1"):
        character.export(job.root, job.root / "06_export/character", "hero", profile.fps, require_pass=False)
    timeline.update(job.root, directory, inserted, "remove")
    assert timeline.describe(job.root, directory, 12)["unavailable"] == {}
    stages.export(job, profile)
    timeline.update(job.root, directory, None, "undo")
    path.write_bytes(original)
    assert timeline.frames(job.root, directory)[1].id == inserted
    for source in colour_frames(directory / "frames"):
        source.write_bytes(_image((8, 8)))
    assert timeline.describe(job.root, directory, 12)["unavailable"] == {inserted: "Saved PNG no longer fits the 8 × 8 cell."}


def test_insertion_and_removal_are_shared_by_http_cli_and_mcp(clip, tmp_path, monkeypatch, capsys):
    job, directory = clip
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    route = "/api/jobs/hero/j/timeline?facing=S&action=walk"
    args = ["timeline", "--job", "hero/j", "--facing", "S", "--action", "walk"]
    png = tmp_path / "insert.png"
    png.write_bytes(_image())
    assert cli.main([*args, "--frame", "001.png", "--insert", str(png)]) == 0
    inserted = json.loads(capsys.readouterr().out)["selected_frame"]
    with TestClient(create_app(worker=False)) as client:
        data = client.post(route, json={"frame": inserted, "operation": "remove"}).json()
        assert data["selected_frame"] == "002.png"
        assert len(data["frames"]) == 12
        assert client.post(route, json={"frame": "000.png", "operation": "insert", "png": "invalid"}).status_code == 400
    mcp, _ = build(tmp_path)
    result = text(call(mcp, "edit_timeline_frame", character="hero", job_id="j", facing="S", action="walk",
                       operation="undo"))
    assert result["frames"][2]["id"] == inserted
    assert timeline.frames(job.root, directory)[2].inserted


def test_saved_playback_range_reaches_qa_manifest_and_both_exporters(clip):
    job, directory = clip
    profile = resolve(None)
    output = job.root / "06_export" / "character"
    source = job.root / "03_actions" / "S" / "walk" / "selection_report.json"
    original = source.read_bytes()
    stages.export(job, profile)
    character.export(job.root, output, "hero", profile.fps)
    timeline.update(job.root, directory, "001.png", "duration", 320)
    playback = {"mode": "once", "start_frame": "001.png", "end_frame": "003.png"}
    timeline.update(job.root, directory, None, "playback", playback)
    view = timeline.describe(job.root, directory, profile.fps("walk"))
    assert not view["loop"] and view["playback"] == playback | {"loop": False, "start": 1, "end": 3, "error": None}
    assert view["qa_needs_review"] and view["frames"][1]["duration_ms"] == 320
    assert source.read_bytes() == original
    assert character.export_status(job.root, output, profile.fps)["status"] == "stale"
    assert {v["status"] for v in stages.export_status(job, profile)["formats"].values()} == {"stale"}
    with pytest.raises(RuntimeError, match="QA needs to review"):
        character.export(job.root, output, "hero", profile.fps)
    assert stages.qa(job, profile)["12f"] == "pass"
    qa = json.loads((job.root / "05_qa/S/walk/12f/report.json").read_text(encoding="utf-8"))
    assert qa["loop"] is False and qa["playback_range"] == [1, 3]
    assert not timeline.describe(job.root, directory, profile.fps("walk"))["qa_needs_review"]
    anim = manifest.read(job)["animations"][0]
    assert anim["playback_by_view"][str(anim["views"][0])] == view["playback"]

    action = stages.export(job, profile)["12f"]
    char = character.export(job.root, output, "hero", profile.fps)
    for product in (action, char):
        doc = aseprite.read(product["aseprite"])
        assert len(doc.frames) == 12 and doc.durations[1] == 320
        assert doc.tags == [("walk_S", 1, 3, "forward")] and doc.repeats == [1]
    action_meta = json.loads(Path(action["json"]).read_text(encoding="utf-8"))
    char_meta = json.loads(Path(char["json"]).read_text(encoding="utf-8"))["animations"][0]
    assert len(action_meta["frames"]) == 12 and char_meta["frames"] == 12
    for meta in (action_meta, char_meta):
        assert meta["loop"] is False and meta["playback_range"] == [1, 3]
    for key in ("apng", "gif"):
        with Image.open(action[key]) as image:
            assert image.n_frames == 3 and image.info.get("duration") == 320
            assert image.info.get("loop") == (1 if key == "apng" else None)
            for i in range(image.n_frames):
                image.seek(i)
                with Image.open(directory / "frames" / f"{i + 1:03}.png") as expected:
                    actual, wanted = np.asarray(image.convert("RGBA")), np.asarray(expected)
                    if key == "gif":
                        assert np.array_equal(actual[..., 3], wanted[..., 3])
                        assert np.array_equal(actual[wanted[..., 3] != 0], wanted[wanted[..., 3] != 0])
                    else:
                        assert np.array_equal(actual, wanted)


def test_qa_reports_the_saved_range_endpoints_as_loop_seam_findings(clip):
    job, directory = clip
    profile = resolve(None)
    for i, x in enumerate([3, 2, 3, 4, 5, 6, 7, 8, 9, 8, 6, 3]):
        frame = Image.new("RGBA", (20, 16))
        frame.paste((70, 20, 180, 255), (x, 4, x + 8, 12))
        frame.save(directory / "frames" / f"{i:03}.png")
    assert stages.qa(job, profile)["12f"] == "pass"
    assert not any(issue["code"] == "loop-seam" for frame in stages.qa_review(job)["12f"]["frame_findings"] for issue in frame["issues"])
    timeline.update(job.root, directory, None, "playback", {"mode": "loop", "start_frame": "001.png", "end_frame": "006.png"})
    assert stages.qa(job, profile)["12f"] == "pass"
    findings = stages.qa_review(job)["12f"]["frame_findings"]
    assert [(frame["frame"], frame["file"]) for frame in findings if any(i["code"] == "loop-seam" for i in frame["issues"])] == [(1, "001.png"), (6, "006.png")]


def test_playback_range_follows_ids_and_refuses_missing_or_crossed_endpoints(clip):
    job, directory = clip
    profile = resolve(None)
    playback = {"mode": "loop", "start_frame": "copy-1", "end_frame": "004.png"}
    timeline.update(job.root, directory, "001.png", "duplicate")
    timeline.update(job.root, directory, None, "playback", playback)
    timeline.update(job.root, directory, "000.png", "move", 3)
    result = timeline.describe(job.root, directory, profile.fps("walk"))["playback"]
    assert result["start"] == 1 and result["end"] == 5
    timeline.update(job.root, directory, "copy-1", "move", 8)
    assert "before" in timeline.describe(job.root, directory, profile.fps("walk"))["playback"]["error"]
    with pytest.raises(ValueError, match="before"):
        stages.export(job, profile)
    with pytest.raises(ValueError, match="before"):
        stages.qa(job, profile)
    timeline.update(job.root, directory, None, "undo")
    timeline.update(job.root, directory, None, "undo")
    timeline.update(job.root, directory, None, "undo")
    assert "missing" in timeline.describe(job.root, directory, profile.fps("walk"))["playback"]["error"]
    with pytest.raises(RuntimeError, match="missing"):
        character.export(job.root, job.root / "06_export/character", "hero", profile.fps, require_pass=False)
    timeline.update(job.root, directory, None, "redo")
    view = timeline.describe(job.root, directory, profile.fps("walk"))["playback"]
    assert view["start"] == 2 and view["error"] is None
    for args in ({"mode": "bogus"}, {"mode": "loop", "start_frame": "000.png"},
                 {"mode": "loop", "start_frame": "004.png", "end_frame": "001.png"},
                 {"mode": "once", "start_frame": "999.png", "end_frame": "001.png"}):
        with pytest.raises(ValueError, match="Playback|playback"):
            timeline.update(job.root, directory, None, "playback", args)
    assert timeline.describe(job.root, directory, profile.fps("walk"))["playback"] == view
    timeline.update(job.root, directory, None, "playback", {"mode": "source"})
    assert timeline.describe(job.root, directory, profile.fps("walk"))["playback"]["start"] == 0


def test_playback_is_shared_by_http_cli_and_mcp(clip, tmp_path, monkeypatch, capsys):
    job, _ = clip
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    route = "/api/jobs/hero/j/timeline?facing=S&action=walk"
    args = ["timeline", "--job", "hero/j", "--facing", "S", "--action", "walk"]
    assert cli.main([*args, "--playback", "once", "--range-start", "000.png", "--range-end", "001.png"]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["playback"]["end"] == 1 and view["loop"] is False
    with TestClient(create_app(worker=False)) as client:
        assert client.get(route).json()["playback"] == view["playback"]
        response = client.post(route, json={"operation": "playback", "playback": {"mode": "loop"}})
        assert response.status_code == 200 and response.json()["playback"]["end"] == 11
        assert response.json()["loop"] is True
        assert client.post(route, json={"operation": "playback", "playback": {"mode": [], "start_frame": 0}}).status_code == 400
    mcp, _ = build(tmp_path)
    result = text(call(mcp, "edit_timeline_frame", character="hero", job_id="j", facing="S", action="walk",
                       operation="playback", playback={"mode": "source"}))
    assert result["playback"]["mode"] == "source" and result["loop"] is True


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
