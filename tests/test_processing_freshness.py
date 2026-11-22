from pathlib import Path

import pytest
from PIL import Image

from spritewaffle.core import job_palette, stages
from spritewaffle.core.job import Job
from spritewaffle.core.profile import resolve
from spritewaffle.core.queue import Queue, Worker
from spritewaffle.export import character
from spritewaffle.frames import video
from synth import write_clip


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
