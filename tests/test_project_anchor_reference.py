from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import generate, manifest, project_references
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.core.queue import Queue, Worker
from spritewaffle.mcp_server import build
from spritewaffle.ui.server import create_app
from test_generate import StubClient
from test_mcp import call, text


@pytest.fixture
def library(tmp_path):
    base = tmp_path / "jobs"
    path = tmp_path / "hero.png"
    Image.new("RGBA", (72, 72), (170, 65, 88, 255)).save(path)
    entry = project_references.import_file(base, path, collection="Characters")
    return base, entry["id"], path


def test_reference_anchor_records_its_source_and_requires_review(library):
    base, ref_id, source = library
    source_bytes = source.read_bytes()
    new = Job.create("scout", "one", base=base)
    client = StubClient()
    prof = GameProfile(name="default")
    generate.anchor(new, prof, client, description="a teal scout", seed=7, project_reference_id=ref_id)
    [(slot, values)] = client.calls
    assert slot == "facing_multiref" and values["seed"] == 7
    [image] = values["ref_images"]
    assert image == project_references.image(base, ref_id) and image.read_bytes() == source_bytes
    assert "art style reference" in values["prompt"] and "a teal scout" in values["prompt"]
    meta = new.read_meta()
    assert meta["inputs"]["project_reference_id"] == ref_id
    assert meta["provenance"][-1]["project_reference_id"] == ref_id
    assert meta["stages"]["anchor"]["status"] == "review"
    assert manifest.read(new)["project_reference_id"] == ref_id
    assert source.read_bytes() == source_bytes
    generate.anchor(new, prof, client, description="an independent anchor")
    assert "project_reference_id" not in new.read_meta()["inputs"]


def test_queue_rejects_incompatible_selection_and_rechecks_archiving(library, monkeypatch):
    base, ref_id, source = library
    job = Job.create("scout", "one", base=base)
    queue = Queue(base)
    args = {"describe": "a teal scout", "project_reference_id": ref_id}
    for patch in ({"image": str(source)}, {"style_ref": str(source)}, {"describe": None}):
        with pytest.raises(ValueError):
            queue.submit(job.root, "anchor", args | patch)
    with pytest.raises(ValueError, match="anchor"):
        queue.submit(job.root, "facings", args)
    with pytest.raises(ValueError, match="turnaround"):
        queue.submit(job.root, "anchor", args | {"asset_type": "base_body"})
    assert queue.list() == []

    first = queue.submit(job.root, "anchor", args)
    project_references.update(base, ref_id, {"archived": True})
    with pytest.raises(ValueError, match="archived"):
        queue.submit(job.root, "anchor", args)
    monkeypatch.setattr(generate, "ComfyClient", lambda: pytest.fail("archived reference reached the renderer"))
    Worker(queue)._execute(first)
    failed = queue.get(first["id"])
    assert failed["status"] == "failed" and "archived" in failed["error"]
    assert not (job.root / "01_anchor" / "anchor.png").exists()


def test_http_and_mcp_submit_the_project_reference_id(library):
    base, ref_id, _ = library
    job = Job.create("scout", "one", base=base)
    with TestClient(create_app(base, worker=False)) as client:
        assert 'id="projectReferenceOptions"' in client.get("/").text
        route = "/api/jobs/scout/one/run"
        args = {"describe": "a teal scout", "project_reference_id": ref_id}
        response = client.post(route, json={"stage": "anchor", "args": args})
        assert response.status_code == 200
        assert Queue(base).get(response.json()[0])["args"] == args
        bad = client.post(route, json={"stage": "anchor", "args": args | {"project_reference_id": "0" * 32}})
        assert bad.status_code == 400

    mcp, queue = build(base)
    response = text(call(mcp, "generate", character="scout", job_id="one", description="a teal scout",
                         project_reference_id=ref_id))
    assert queue.get(response["tasks"][0])["args"]["project_reference_id"] == ref_id
    assert Job.open(job.root).read_meta()["inputs"].get("project_reference_id") is None


def test_cli_accepts_project_references(library, monkeypatch):
    from spritewaffle import cli
    base, ref_id, _ = library
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(base))
    client = StubClient()
    monkeypatch.setattr(generate, "ComfyClient", lambda: client)
    job = Job.create("scout", "one", base=base)
    manifest.write(job)
    assert cli.main(["anchor", "--job", "scout/one", "--describe", "a teal scout", "--project-reference", ref_id]) == 0
    assert Path(client.calls[0][1]["ref_images"][0]) == project_references.image(base, ref_id)
    assert manifest.read(job)["project_reference_id"] == ref_id
    assert cli.main(["anchor", "--job", "scout/one", "--describe", "a new anchor"]) == 0
    assert "project_reference_id" not in manifest.read(job)
