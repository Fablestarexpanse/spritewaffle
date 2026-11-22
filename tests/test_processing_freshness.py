from pathlib import Path

import pytest
from PIL import Image

from spritewaffle.core import job_palette, motion, stages
from spritewaffle.core.job import Job
from spritewaffle.core.profile import resolve
from spritewaffle.core.queue import Queue, Worker
from spritewaffle.export import character
from spritewaffle.frames import video
from synth import draw_sprite, render, write_clip


@pytest.fixture
def processed(tmp_path):
    job = Job.create("hero", "one", base=tmp_path)
    prof = resolve(None)
    job_palette.save(job, ["#13131c", "#584088", "#eec051"], "first palette")
    clip = tmp_path / "walk.mp4"
    write_clip(clip, frames=24)
    stages.extract(job, clip, "E", "walk")
    stages.select(job, "E", "walk")
    stages.pixel(job, prof, "E", "walk")
    stages.export(job, prof, "E", "walk")
    return job, prof


def test_palette_refresh_requires_processing_for_both_exports(processed, tmp_path):
    job, prof = processed
    out = tmp_path / "character"
    package = character.export(job.root, out, "hero", prof.fps, require_pass=False)
    original_package = Path(package["aseprite"]).read_bytes()
    original_action = (job.root / "06_export/E/walk/12f/walk_E_12f.aseprite").read_bytes()
    job_palette.save(job, ["#13131c", "#584088", "#eec051"], "renamed palette")
    assert stages.export_status(job, prof)["processing"]["status"] == "current"
    first = job.root / "03_actions/E/walk/raw.mp4"
    raw = first.read_bytes()
    job_palette.save(job, ["#151517", "#2d6472", "#dd7622"], "same size, new colours")
    status = stages.export_status(job, prof)
    assert status["processing"]["settings_changed"] == ["palette"]
    assert {entry["status"] for entry in status["formats"].values()} == {"stale"}
    assert character.export_status(job.root, out, prof.fps)["processing"]["E/walk"]["step"] == "pixelize"
    with pytest.raises(RuntimeError, match="Re-process"):
        stages.export(job, prof)
    with pytest.raises(RuntimeError, match="Re-process"):
        character.export(job.root, out, "hero", prof.fps, require_pass=False)
    assert Path(package["aseprite"]).read_bytes() == original_package
    assert (job.root / "06_export/E/walk/12f/walk_E_12f.aseprite").read_bytes() == original_action
    stages.pixel(job, prof, "E", "walk")
    assert stages.export_status(job, prof)["processing"]["status"] == "current"
    stages.export(job, prof)
    character.export(job.root, out, "hero", prof.fps, require_pass=False)
    assert character.export_status(job.root, out, prof.fps)["status"] == "current"
    assert first.read_bytes() == raw


def test_replaced_raw_clip_is_decoded_again_without_rendering(processed, tmp_path):
    job, prof = processed
    root = job.root / "03_actions/E/walk"
    selection = root / "selection_report.json"
    before = selection.read_bytes()
    (root / "raw.mp4").unlink()
    with pytest.raises(RuntimeError, match="Re-process"):
        stages.select(job, "E", "walk")
    assert selection.read_bytes() == before
    write_clip(root / "raw.mp4", frames=18, scale=7)
    check = stages.export_status(job, prof)["processing"]
    assert check["step"] == "extract"
    assert check["changed_inputs"] == ["03_actions/E/walk/raw.mp4"]
    with pytest.raises(RuntimeError, match="Re-process"):
        stages.pixel(job, prof, "E", "walk")
    q = Queue(tmp_path)
    tasks = q.submit_action_pipeline(job.root, "E", "walk", generate=False)
    assert [t["stage"] for t in tasks] == ["extract", "select", "pixelize", "qa", "export"]
    for t in tasks:
        Worker(q)._execute(t)
        assert q.get(t["id"])["status"] == "done", q.get(t["id"])["error"]
    assert len(video.list_frames(root / "extracted")) == 18
    assert stages.export_status(job, prof)["processing"]["status"] == "current"


def test_changed_selected_frame_requires_local_reprocessing(processed):
    job, prof = processed
    selection = job.root / "03_actions/E/walk/extracted"
    for frame in video.list_frames(selection):
        with Image.open(frame) as image:
            updated = image.copy()
        updated.putpixel((0, 0), (1, 255, 0))
        updated.save(frame)
    check = stages.export_status(job, prof)["processing"]
    assert check["step"] == "pixelize"
    assert check["changed_inputs"]
    assert all(name.startswith("03_actions/E/walk/extracted/") for name in check["changed_inputs"])


def test_explicit_per_clip_palette_and_interrupted_extraction(processed, monkeypatch):
    job, prof = processed
    stages.pixel(job, prof, "E", "walk", palette=4)
    stages.export(job, prof)
    job_palette.save(job, ["#151517", "#2d6472", "#dd7622"], "replacement")
    assert stages.export_status(job, prof)["processing"] == {"status": "current"}

    raw = job.root / "03_actions/E/walk/raw.mp4"
    before = raw.read_bytes()

    def interrupted(*args, **kwargs):
        raise OSError("the decoder stopped")

    with monkeypatch.context() as patch:
        patch.setattr(video, "extract", interrupted)
        with pytest.raises(OSError, match="decoder stopped"):
            stages.extract(job, raw, "E", "walk")
    assert stages.export_status(job, prof)["processing"]["step"] == "extract"
    with pytest.raises(RuntimeError, match="Re-process"):
        stages.export(job, prof)
    assert raw.read_bytes() == before
    stages.extract(job, raw, "E", "walk")
    stages.select(job, "E", "walk")
    stages.pixel(job, prof, "E", "walk", palette=4)
    assert stages.export_status(job, prof)["processing"] == {"status": "current"}


def test_mirror_tracks_source_processing_and_source_frames(processed, tmp_path):
    job, prof = processed
    stages.mirror_action(job, prof, "W", "walk", source="E")
    stages.mirror_action(job, prof, "NW", "walk", source="W")
    stages.export(job, prof, "NW", "walk")
    assert stages.export_status(job, prof, "NW", "walk")["processing"] == {"status": "current"}
    job_palette.save(job, ["#151517", "#2d6472", "#dd7622"], "replacement")
    result = stages.export_status(job, prof, "NW", "walk")["processing"]
    assert result["step"] == "mirror" and result["source_facing"] == "W"
    with pytest.raises(RuntimeError, match="W/walk"):
        stages.export(job, prof, "NW", "walk")
    with pytest.raises(ValueError, match="cycle"):
        stages.mirror_action(job, prof, "E", "walk", source="NW")

    q = Queue(tmp_path)
    tasks = q.submit_reprocess(job.root)
    mirrors = [t for t in tasks if t["stage"] == "mirror"]
    assert [t["args"]["facing"] for t in mirrors] == ["W", "NW"]
    assert mirrors[1]["after"] == [mirrors[0]["id"]]
    for task in tasks:
        Worker(q)._execute(task)
        assert q.get(task["id"])["status"] == "done", q.get(task["id"])["error"]

    frame = job.root / "04_pixel/W/walk/12f/frames/000.png"
    with Image.open(frame) as image:
        updated = image.copy()
    updated.putpixel((0, 0), (10, 20, 30, 255))
    updated.save(frame)
    result = stages.export_status(job, prof, "NW", "walk")["processing"]
    assert result["changed_inputs"] == ["04_pixel/W/walk/12f/frames/000.png"]


def test_optical_flow_tracks_guide_and_facing_and_queues_local_recovery(processed, tmp_path):
    job, prof = processed
    motion.add("guide", job, "E", "walk", tmp_path)
    motion.approve("guide", tmp_path)
    job.set_stage("facings", "approved")
    face = job.root / "02_facings/S.png"
    Image.fromarray(render(draw_sprite())).save(face)
    stages.flow_transfer(job, prof, "S", "idle", "guide", counts=(12,), loop=False)
    stages.export(job, prof, "S", "idle")
    assert stages.export_status(job, prof, "S", "idle")["processing"] == {"status": "current"}
    guide = Path(motion.get("guide", tmp_path)["clip"])
    write_clip(guide, frames=20, scale=7)
    Image.fromarray(render(draw_sprite(1))).save(face)
    result = stages.export_status(job, prof, "S", "idle")["processing"]
    assert result["step"] == "flow"
    assert "02_facings/S.png" in result["changed_inputs"]
    assert any(path.endswith("_library/motions/guide/clip.mp4") for path in result["changed_inputs"])
    q = Queue(tmp_path)
    tasks = q.submit_action_pipeline(job.root, "S", "idle", generate=False)
    assert [t["stage"] for t in tasks] == ["flow", "qa", "export"]
    assert tasks[0]["args"]["counts"] == [12] and tasks[0]["args"]["loop"] is False
    for task in tasks:
        Worker(q)._execute(task)
        assert q.get(task["id"])["status"] == "done", q.get(task["id"])["error"]
    assert stages.export_status(job, prof, "S", "idle")["processing"] == {"status": "current"}


def test_palette_only_rebuild_keeps_manual_selection_bytes(processed, tmp_path):
    job, prof = processed
    stages.select(job, "E", "walk", indices="0,2,4,6,8,10,12,14,16,18,20,22", loop=False)
    stages.pixel(job, prof, "E", "walk")
    report = job.root / "03_actions/E/walk/selection_report.json"
    before = report.read_bytes()
    job_palette.save(job, ["#151517", "#2d6472", "#dd7622"], "replacement")
    q = Queue(tmp_path)
    tasks = q.submit_action_pipeline(job.root, "E", "walk", generate=False)
    assert [t["stage"] for t in tasks] == ["pixelize", "qa", "export"]
    for task in tasks:
        Worker(q)._execute(task)
        assert q.get(task["id"])["status"] == "done", q.get(task["id"])["error"]
    assert report.read_bytes() == before
    assert set(q.get(tasks[-1]["id"])["result"]) == {"12f"}
    assert (job.root / "04_pixel/E/walk/24f/frames/000.png").exists()
    with pytest.raises(RuntimeError, match="no pixelized animations"):
        character.export(job.root, tmp_path / "old-set", "hero", prof.fps, "24f", require_pass=False)
