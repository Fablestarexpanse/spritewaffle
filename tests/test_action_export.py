import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle import cli
from spritewaffle.core import stages
from spritewaffle.core.job import Job
from spritewaffle.core.profile import resolve
from spritewaffle.export import aseprite, sheet
from spritewaffle.frames.video import colour_frames
from spritewaffle.mcp_server import build
from spritewaffle.qa import checks
from spritewaffle.ui.server import create_app
from test_character_export import _anim
from test_mcp import call, text


@pytest.fixture
def action_job(tmp_path):
    job = Job.create("hero", "j", base=tmp_path, facing="S", action="walk")
    _anim(job, "S", "walk", [(70, 20, 180)])
    pixel = job.root / "04_pixel" / "S" / "walk"
    (pixel / "pixel_report.json").write_text('{"palette": []}', encoding="utf-8")
    (pixel / "12f" / "placements.json").write_text("[]", encoding="utf-8")
    return job


def test_action_exports_track_each_format_and_all_png_outputs(action_job):
    prof = resolve(None)
    root = action_job.root / "06_export" / "S" / "walk"

    def status():
        return stages.export_status(action_job, prof)["formats"]

    assert {value["status"] for value in status().values()} == {"missing"}
    legacy = root / "12f" / "walk_S_12f.png"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"old file")
    assert status()["png"]["status"] == "untracked"
    assert status()["aseprite"]["status"] == "missing"
    out = stages.export(action_job, prof)
    assert set(out["12f"]) == {"strip", "json", "gif", "apng", "aseprite"}
    assert {value["status"] for value in status().values()} == {"current"}
    frame = root / "12f" / "frames" / "walk_S_12f_000.png"
    frame.unlink()
    assert status()["png"]["changed_outputs"] == ["12f/frames/walk_S_12f_000.png"]
    assert status()["aseprite"]["status"] == "current"
    stages.export(action_job, prof, fmt="aseprite")
    assert status()["png"]["status"] == "stale"
    stages.export(action_job, prof, fmt="png")
    assert {value["status"] for value in status().values()} == {"current"}
    selection = action_job.root / "03_actions" / "S" / "walk" / "selection_report.json"
    selection.write_text('{"loop": false}', encoding="utf-8")
    assert {value["status"] for value in status().values()} == {"stale"}


def test_action_export_status_matches_http_cli_and_mcp(action_job, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    mcp, _ = build(tmp_path)
    out = text(call(mcp, "export_action", character="hero", job_id="j", facing="S", action="walk", format="aseprite"))
    Path(out["12f"]["aseprite"]).unlink()
    with TestClient(create_app(tmp_path, worker=False)) as client:
        route = "/api/jobs/hero/j/action_export_status"
        assert client.get(route, params={"facing": "..", "action": "walk"}).status_code == 400
        result = client.get(route, params={"facing": "S", "action": "walk"}).json()
    assert result["formats"]["aseprite"]["status"] == "stale"
    assert result["formats"]["png"]["status"] == "missing"
    assert cli.main(["export-action-status", "--job", "hero/j"]) == 0
    assert json.loads(capsys.readouterr().out) == result
    assert text(call(mcp, "action_export_status", character="hero", job_id="j", facing="S", action="walk")) == result


def test_action_export_rejects_index_disagreement_and_can_retry(action_job, monkeypatch):
    prof = resolve(None)
    pixel = action_job.root / "04_pixel" / "S" / "walk"
    (pixel / "pixel_report.json").write_text('{"palette": ["#4614b4"]}', encoding="utf-8")
    indices = []
    for path in colour_frames(pixel / "12f" / "frames"):
        with Image.open(path) as image:
            indices.append(np.where(np.asarray(image)[..., 3] > 0, 0, -1))
    source = pixel / "12f" / "indices.npy"
    np.save(source, indices)
    exported = stages.export(action_job, prof)
    aset = Path(exported["12f"]["aseprite"])
    original = aset.read_bytes()
    indices[0][4, 4] = -1
    np.save(source, indices)
    with pytest.raises(ValueError, match="indexed pixels disagree"):
        stages.export(action_job, prof, fmt="aseprite")
    assert aset.read_bytes() == original
    status = stages.export_status(action_job, prof)["formats"]
    assert status["png"]["status"] == "current"
    assert status["aseprite"]["status"] == "stale"
    indices[0][4, 4] = 0
    np.save(source, indices)

    def interrupted(*args, **kwargs):
        raise OSError("write interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(aseprite, "write", interrupted)
        with pytest.raises(OSError, match="write interrupted"):
            stages.export(action_job, prof, fmt="aseprite")
    status = stages.export_status(action_job, prof)["formats"]
    assert status["png"]["status"] == "current"
    assert status["aseprite"]["status"] == "incomplete"
    stages.export(action_job, prof, fmt="aseprite")
    assert stages.export_status(action_job, prof)["formats"]["aseprite"]["status"] == "current"


def test_action_export_stays_incomplete_when_inputs_change_mid_write(action_job, monkeypatch):
    prof = resolve(None)
    stages.export(action_job, prof)
    write_png = sheet.export_png

    def write_and_change(*args, **kwargs):
        result = write_png(*args, **kwargs)
        (action_job.root / "04_pixel" / "S" / "walk" / "24f").mkdir()
        return result

    monkeypatch.setattr(sheet, "export_png", write_and_change)
    with pytest.raises(RuntimeError, match="inputs changed"):
        stages.export(action_job, prof, fmt="png")
    status = stages.export_status(action_job, prof)["formats"]
    assert status["png"]["status"] == "incomplete"
    assert status["aseprite"]["status"] == "stale"


def test_saved_frame_qa_findings_match_http_cli_and_mcp(action_job, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    report = {"status": "fail", "errors": ["border contact"], "frame_count": 12, "edge_contact_frames": [2]}
    checks.write(report, action_job.root / "05_qa" / "S" / "walk" / "12f" / "report.json")
    (action_job.root / "04_pixel" / "S" / "walk" / "12f" / "frames" / "001.png").unlink()
    with TestClient(create_app(tmp_path, worker=False)) as client:
        qa = client.get("/api/jobs/hero/j").json()["actions"][0]["sets"]["12f"]["qa"]
        preview = qa["frame_findings"][0].pop("preview")
        assert preview.split("?")[0].endswith("/002.png") and client.get(preview).status_code == 200
    assert qa["frame_findings"][0]["frame"] == 2
    assert cli.main(["qa-review", "--job", "hero/j"]) == 0
    assert json.loads(capsys.readouterr().out)["12f"] == qa
    mcp, _ = build(tmp_path)
    result = text(call(mcp, "status", character="hero", job_id="j"))
    assert result["actions"]["S/walk"]["qa"]["12f"] == qa


def test_qa_finding_keeps_the_source_filename_in_a_sparse_sequence(action_job):
    processed = action_job.root / "04_pixel" / "S" / "walk" / "12f" / "frames"
    (processed / "001.png").unlink()
    with Image.open(processed / "002.png") as original:
        image = original.copy()
    image.putpixel((0, 0), (70, 20, 180, 255))
    image.save(processed / "002.png")
    stages.qa(action_job, resolve(None))
    review = stages.qa_review(action_job)["12f"]
    border = next(f for f in review["frame_findings"] if any(i["code"] == "border" for i in f["issues"]))
    assert (border["frame"], border["file"]) == (1, "002.png")


def test_action_export_accepts_legacy_rgb_frames(action_job):
    processed = action_job.root / "04_pixel" / "S" / "walk" / "12f" / "frames"
    for path in colour_frames(processed):
        with Image.open(path) as source:
            rgb = source.convert("RGB")
        rgb.save(path)
    outputs = stages.export(action_job, resolve(None))
    with Image.open(outputs["12f"]["strip"]) as strip:
        assert strip.mode == "RGBA"
        assert strip.getchannel("A").getextrema() == (255, 255)
    assert stages.export_status(action_job, resolve(None))["formats"]["png"]["status"] == "current"
