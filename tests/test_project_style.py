import json

import pytest
from fastapi.testclient import TestClient

from spritewaffle import cli
from spritewaffle.core import camera, manifest, project
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.mcp_server import build
from spritewaffle.ui.server import create_app
from test_mcp import call, text


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv("SPRITEWAFFLE_HOME", str(tmp_path))
    jobs = tmp_path / "jobs"
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(jobs))
    GameProfile(name="game-look", projection="iso_2to1", cell_size=80, sprite_height_px=60).save(tmp_path / "profiles/game-look.json")
    return jobs


GUIDE = {"default_style": "painted", "default_profile": "game-look", "target_engine": "Godot 4",
         "art_direction": "Soft edges and clear silhouettes.\nUse muted blue shadows."}


def test_style_and_camera_preserve_legacy_and_unknown_project_fields(studio):
    studio.mkdir()
    path = studio / "project.json"
    legacy = {"schema_version": 1, "id": "inkwood", "camera": {"camera_elevation_degrees": 31},
              "extension": {"preserve": True}}
    path.write_text(json.dumps(legacy), encoding="utf-8")
    assert project.style(studio)["style"]["default_style"] is None
    assert project.set_style(studio, GUIDE)["style"] == GUIDE
    assert camera.project(studio)["camera"] == legacy["camera"]
    camera.set_project(studio, {"light_yaw": 70}, "inkwood-2")
    assert project.style(studio) == {"project_id": "inkwood-2", "style": GUIDE}
    assert json.loads(path.read_text(encoding="utf-8"))["extension"] == legacy["extension"]
    camera.set_project(studio, None)
    assert project.style(studio)["style"] == GUIDE
    project.set_style(studio, {"target_engine": "Custom"})
    assert project.style(studio)["style"] == GUIDE | {"target_engine": "Custom"}
    project.set_style(studio, None)
    assert camera.project(studio)["camera"] is None
    assert "style" not in json.loads(path.read_text(encoding="utf-8"))


def test_new_job_inherits_defaults_and_manifest_keeps_its_saved_guide(studio):
    old = Job.create("old", "one", base=studio)
    old.set_stage("anchor", "approved")
    old_meta = old.meta_path.read_bytes()
    project.set_style(studio, GUIDE)
    inherited = Job.create("hero", "one", base=studio)
    meta = inherited.read_meta()["inputs"]
    assert meta["style"] == "painted" and meta["profile"] == "game-look" and meta["style_guide"] == GUIDE
    m = manifest.read(inherited)
    assert m["style"] == "painted" and m["profile"] == "game-look" and m["canvas"] == [80, 80]
    assert m["style_guide"] == GUIDE
    override = Job.create("hero", "two", base=studio, style="anime", profile=None).read_meta()["inputs"]
    assert override["style"] == "anime" and override["profile"] is None
    variant = Job.create("old", "two", base=studio, base_job=str(old.root)).read_meta()["inputs"]
    assert not {"style", "profile", "style_guide"}.intersection(variant)
    project.set_style(studio, {"art_direction": "Heavy ink and bright colours.", "default_style": "comic"})
    assert manifest.read(inherited)["style_guide"] == GUIDE
    assert old.meta_path.read_bytes() == old_meta and "style_guide" not in manifest.read(old)


def test_rejects_bad_defaults_and_newer_project_without_writing(studio):
    project.set_style(studio, GUIDE)
    path = studio / "project.json"
    saved = path.read_bytes()
    for fields in ({"typo": "pixel"}, {"default_style": "unknown"}, {"default_profile": "../../bad"},
                   {"default_profile": "missing"}, {"target_engine": 5}):
        with pytest.raises((ValueError, FileNotFoundError)):
            project.set_style(studio, fields)
        assert path.read_bytes() == saved
    record = json.loads(saved) | {"schema_version": 99}
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="newer"):
        camera.set_project(studio, None)
    with pytest.raises(ValueError, match="newer"):
        project.set_style(studio, None)
    assert json.loads(path.read_text(encoding="utf-8")) == record


def test_missing_profile_can_be_overridden_without_leaving_an_empty_job(studio):
    project.set_style(studio, GUIDE)
    (studio.parent / "profiles/game-look.json").unlink()
    with pytest.raises(ValueError, match="'game-look' is unavailable"):
        Job.create("character", "take", base=studio)
    assert not (studio / "character").exists()
    Job.create("character", "take", base=studio, profile=None)
    assert Job.create("character", "take", base=studio).read_meta()["inputs"]["profile"] is None


def test_style_settings_and_creation_across_http_cli_and_mcp(studio, tmp_path, capsys):
    with TestClient(create_app(studio, worker=False)) as client:
        route = "/api/project/style"
        assert client.post(route, json={"style": GUIDE}).status_code == 200
        assert client.get(route).json()["style"] == GUIDE
        assert client.post(route, json={}).status_code == 400
        assert client.post("/api/jobs", json={"character": "web", "job_id": "one"}).status_code == 200
        explicit = {"character": "web", "job_id": "two", "style": "pixel", "profile": None}
        assert client.post("/api/jobs", json=explicit).status_code == 200
        inputs = Job.open(studio / "web/one").read_meta()["inputs"]
        assert inputs["style"] == "painted" and inputs["profile"] == "game-look"
        assert Job.open(studio / "web/two").read_meta()["inputs"]["profile"] is None
        assert client.get("/api/jobs/web/one/manifest").json()["style_guide"] == GUIDE

    edit = tmp_path / "style.json"
    edit.write_text('{"target_engine":"Unity"}', encoding="utf-8")
    assert cli.main(["project-style", "--set", str(edit)]) == 0
    assert json.loads(capsys.readouterr().out)["style"]["target_engine"] == "Unity"
    mcp, queue = build(studio)
    result = text(call(mcp, "project_style", action="set", style={"default_style": "comic"}))
    assert result["style"]["default_style"] == "comic"
    queued = text(call(mcp, "generate", character="agent", description="a sprite"))
    inputs = Job.open(studio / "agent" / queued["job_id"]).read_meta()["inputs"]
    assert inputs["style"] == "comic" and inputs["profile"] == "game-look"
    assert inputs["style_guide"]["target_engine"] == "Unity"
    assert queue.get(queued["tasks"][0])["profile"] == "game-look"
    override = text(call(mcp, "generate", character="other", description="a sprite", style="pixel", profile=""))
    other = Job.open(studio / "other" / override["job_id"]).read_meta()["inputs"]
    assert other["style"] == "pixel" and other["profile"] is None
    assert queue.get(override["tasks"][0])["profile"] is None
