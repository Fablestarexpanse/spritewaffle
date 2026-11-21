import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core.job import Job
from spritewaffle.ui.server import create_app
from synth import draw_sprite, render


@pytest.fixture
def client(tmp_path):
    job = Job.create("hero", "j1", base=tmp_path)
    Image.fromarray(render(draw_sprite(), canvas=(256, 256))).save(job.root / "01_anchor" / "anchor.png")
    job.set_stage("anchor", "review")
    with TestClient(create_app(tmp_path, worker=False)) as c:
        yield c, tmp_path


def test_page_and_job_listing(client):
    c, _ = client
    assert "SpriteWaffle" in c.get("/").text
    jobs = c.get("/api/jobs").json()
    assert [(x["character"], x["job_id"], x["stages"], x["asset_type"]) for x in jobs] == [("hero", "j1", {"anchor": "review"}, "character")]
    assert jobs[0]["thumb"].startswith("/files/hero/j1/01_anchor/.anchor.crop128.png")
    j = c.get("/api/jobs/hero/j1").json()
    assert j["anchor_full"].startswith("/files/hero/j1/01_anchor/anchor.png?t=") and j["anchor"]
    assert [f["facing"] for f in j["facings"]] == ["S", "E", "N", "W", "SE", "NE", "NW", "SW"]
    assert c.get(j["anchor"]).status_code == 200


def test_appearance_assets_are_served_by_the_app(client):
    c, _ = client
    page = c.get("/").text
    assert 'id="appearanceSettings"' in page
    assert 'src="/static/appearance.js"' in page
    script = c.get("/static/appearance.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert "sw.appearance.v1" in script.text
    assert c.get("/static/..%2Fserver.py").status_code == 404


def test_export_freshness_agrees_across_http_cli_and_mcp(tmp_path, monkeypatch, capsys):
    from spritewaffle.cli import main
    from spritewaffle.mcp_server import build
    from test_character_export import _anim
    from test_mcp import call, text

    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    job = Job.create("hero", "j", base=tmp_path)
    _anim(job, "S", "walk", [(100, 20, 30)])
    route = "/api/jobs/hero/j/export_character"
    with TestClient(create_app(tmp_path, worker=False)) as c:
        assert c.get(route).json()["status"] == "missing"
        assert c.post(route, json={"set": "../12f"}).status_code == 400
        result = c.post(route, json={})
        assert result.status_code == 200
        assert c.get(route).json()["status"] == "current"
        (job.root / "04_pixel/S/walk/12f/frames/000.png").unlink()
        changed = c.get(route).json()
        assert changed["status"] == "stale"
        assert changed["changed_inputs"] == ["04_pixel/S/walk/12f/frames/000.png"]

    assert main(["export-character-status", "--job", "hero/j"]) == 0
    import json
    assert json.loads(capsys.readouterr().out) == changed
    mcp, _ = build(tmp_path)
    assert text(call(mcp, "character_export_status", character="hero", job_id="j")) == changed


def test_files_refuse_paths_outside_jobs(client):
    c, base = client
    (base.parent / "secret.txt").write_text("nope")
    assert c.get("/files/../secret.txt").status_code == 404
    assert c.get("/files/..%2Fsecret.txt").status_code == 404
    assert c.get("/api/jobs/..%2F..%2F/x").status_code == 404


def test_approve_and_queue_runs(client):
    c, base = client
    assert c.post("/api/jobs/hero/j1/approve", json={"stage": "anchor"}).json() == {"ok": True}
    assert c.get("/api/jobs/hero/j1").json()["stages"]["anchor"]["status"] == "approved"
    assert c.post("/api/jobs/hero/j1/approve", json={"stage": "facings"}).status_code == 400
    ids = c.post("/api/jobs/hero/j1/run", json={"stage": "pipeline", "args": {"facing": "S", "action": "walk"}}).json()
    assert len(ids) == 5
    q = c.get("/api/queue").json()
    assert [t["stage"] for t in q][::-1] == ["action", "select", "pixelize", "qa", "export"]
    assert c.post(f"/api/queue/{ids[0]}/cancel").json()["status"] == "cancelled"
    assert c.post("/api/jobs/hero/j1/run", json={"stage": "nope"}).status_code == 400


def test_create_job_validates_names(client):
    c, base = client
    assert c.post("/api/jobs", json={"character": "elf"}).status_code == 200
    assert c.post("/api/jobs", json={"character": "../evil"}).status_code == 400
    assert (base / "elf").is_dir()


def test_stack_fields_and_pipeline(client):
    c, base = client
    j = c.get("/api/jobs/hero/j1").json()
    assert set(j["stack"]["views"]) == {"front", "back", "right", "top"} and j["stack"]["turntable"] is None
    ids = c.post("/api/jobs/hero/j1/run", json={"stage": "stack_pipeline", "args": {"views": False, "height": 12}}).json()
    assert len(ids) == 1 and c.get("/api/queue").json()[0]["stage"] == "stack"


def test_sources_are_valid_utf8():
    """Patch scripts on Windows default to cp1252; a stray byte once broke the page's badges."""
    from pathlib import Path
    root = Path(__file__).parent.parent
    for p in list((root / "spritewaffle").rglob("*")) + list((root / "skill").rglob("*.md")):
        if p.is_file() and p.suffix in (".py", ".html", ".md", ".json"):
            p.read_bytes().decode("utf-8")


def test_status_settings_animate_export_and_queue_controls(client):
    c, base = client
    st = c.get("/api/status").json()
    assert st["version"] and "walk" in st["actions"] and "prop" in st["asset_types"] and "comfy" in st
    assert c.post("/api/jobs/hero/j1/settings", json={"profile": "nope"}).status_code == 400
    assert c.post("/api/jobs/hero/j1/settings", json={"asset_type": "prop"}).json() == {"ok": True}
    assert c.get("/api/jobs/hero/j1").json()["asset_type"] == "prop"
    assert c.post("/api/jobs/hero/j1/run", json={"stage": "animate", "args": {"facings": [], "actions": ["walk"]}}).status_code == 400
    ids = c.post("/api/jobs/hero/j1/run", json={"stage": "animate", "args": {"facings": ["E", "W"], "actions": ["walk"]}}).json()
    stages = [t["stage"] for t in c.get("/api/queue").json()]
    assert "mirror" in stages and len(ids) == 8
    r = c.post("/api/jobs/hero/j1/export_character", json={})
    assert r.status_code == 400 and "nothing to export" in r.json()["detail"]
    c.post(f"/api/queue/{ids[0]}/cancel")
    assert c.post(f"/api/queue/{ids[0]}/retry").json()["stage"] == "action"
    assert c.post("/api/queue/clear", json={}).json()["removed"] == 1


def test_downloads_listed_and_archive(client):
    c, base = client
    out = base / "hero" / "j1" / "06_export" / "character"
    out.mkdir(parents=True)
    (out / "hero.aseprite").write_bytes(b"x" * 10)
    (out / "frames").mkdir()
    (out / "frames" / "f.png").write_bytes(b"x")
    ex = c.get("/api/jobs/hero/j1").json()["exports"]
    assert [(e["group"], e["name"]) for e in ex] == [("character", "hero.aseprite")]
    r = c.get(ex[0]["url"])
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert c.post("/api/jobs/hero/j1/archive").status_code == 200
    assert c.get("/api/jobs").json() == [] and (base / "_archive" / "hero" / "j1" / "job.json").exists()
