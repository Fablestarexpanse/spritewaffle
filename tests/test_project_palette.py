import json

import pytest
from fastapi.testclient import TestClient

from spritewaffle import cli
from spritewaffle.core import camera, job_palette, manifest, project
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.mcp_server import build
from spritewaffle.ui.server import create_app
from test_mcp import call, text


COLORS = ["#22102E", "#542073", "#FFCB42", "#FFF1D0"]
NORMALIZED = [c.lower() for c in COLORS]


def test_new_jobs_keep_project_palette_and_can_override_it(tmp_path):
    base = tmp_path / "jobs"
    default = GameProfile(name="default")
    old = Job.create("hero", "old", base=base)
    project.set_palette(base, COLORS + ["#22102e"])
    job = Job.create("hero", "new", base=base)
    assert "project_palette" not in old.read_meta()["inputs"]
    assert job.read_meta()["inputs"]["project_palette"] == NORMALIZED
    assert job_palette.resolve(job, default) == (NORMALIZED, False)
    assert job_palette.current(job, default)["origin"] == "project"
    assert manifest.read(job)["project_palette"] == NORMALIZED

    local = ["#010203", "#101112"]
    job_palette.save(job, local, "hand picked")
    assert job_palette.resolve(job, default) == (local, False)
    locked = GameProfile(name="game", palette=["#000000", "#ffffff"])
    assert job_palette.resolve(job, locked) == (locked.palette, False)
    job_palette.clear(job)
    project.set_palette(base, local)
    assert job_palette.resolve(job, default) == (NORMALIZED, False)
    project.set_palette(base, None)
    assert job_palette.resolve(job, default) == (NORMALIZED, False)
    assert "project_palette" not in Job.create("hero", "later", base=base).read_meta()["inputs"]


def test_palette_validation_and_camera_coexist(tmp_path):
    base = tmp_path / "jobs"
    camera.set_project(base, {"light_yaw": 81})
    project.set_style(base, {"target_engine": "Godot"})
    project.set_palette(base, COLORS)
    for invalid in ([], "red", ["#889"], [None], [f"#{n:06x}" for n in range(257)]):
        with pytest.raises(ValueError):
            project.set_palette(base, invalid)
    assert project.palette(base) == NORMALIZED
    assert project.style(base)["style"]["target_engine"] == "Godot"
    assert camera.project(base)["camera"]["light_yaw"] == 81


def test_palette_integration_through_http_cli_mcp(tmp_path, monkeypatch, capsys):
    base = tmp_path / "jobs"
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(base))
    with TestClient(create_app(base, worker=False)) as client:
        assert client.get("/api/project/palette").json() == {"colours": None}
        assert client.post("/api/project/palette", json={}).status_code == 400
        assert client.post("/api/project/palette", json={"colours": COLORS}).json() == {"colours": NORMALIZED}
        assert client.post("/api/jobs", json={"character": "hero", "job_id": "one"}).status_code == 200
        job = "/api/jobs/hero/one"
        assert client.get(job).json()["palette"]["colours"] == NORMALIZED
        palette = ["#000000", "#ffffff"]
        edited = client.post(job + "/palette", json={"op": "set", "colours": palette})
        assert edited.status_code == 200 and edited.json()["origin"] == "job"
        assert client.post(job + "/palette", json={"op": "unlock"}).json()["origin"] == "project"
        override_file = tmp_path / "override.hex"
        override_file.write_text("#010203\n#abcdef\n", encoding="utf-8")
        changed = client.post(job + "/palette", json={"op": "file", "file": str(override_file)})
        assert changed.json()["colours"] == ["#010203", "#abcdef"]
        assert client.post(job + "/palette", json={"op": "unlock"}).json()["colours"] == NORMALIZED

    file = tmp_path / "new.hex"
    file.write_text("#121212\n#eeeeee\n", encoding="utf-8")
    assert cli.main(["project-palette", "--import", str(file)]) == 0
    assert json.loads(capsys.readouterr().out)["colours"] == ["#121212", "#eeeeee"]
    mcp, _ = build(base)
    assert text(call(mcp, "project_palette", action="set", colours=COLORS))["colours"] == NORMALIZED
    override = text(call(mcp, "palette", character="hero", job_id="one", action="set", colours=["#123456"]))
    assert override["colours"] == ["#123456"]
    fallback = text(call(mcp, "palette", character="hero", job_id="one", action="unlock"))
    assert fallback["colours"] == NORMALIZED and fallback["origin"] == "project"
