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
    assert c.get("/api/jobs").json() == [{"character": "hero", "job_id": "j1", "stages": {"anchor": "review"}}]
    j = c.get("/api/jobs/hero/j1").json()
    assert j["anchor"].startswith("/files/hero/j1/01_anchor/anchor.png?t=")
    assert [f["facing"] for f in j["facings"]] == ["S", "E", "N", "W", "SE", "NE", "NW", "SW"]
    assert c.get(j["anchor"]).status_code == 200


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
