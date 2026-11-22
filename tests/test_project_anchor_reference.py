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


def test_item_anchor_uses_only_colours_from_the_project_reference(library, monkeypatch):
    base, _, _ = library
    image = base.parent / "keyed.png"
    art = Image.new("RGB", (72, 72), "#00ff00")
    art.paste("#753761", (16, 16, 56, 56))
    art.paste("#008855", (24, 24, 32, 32))
    art.save(image)
    ref_id = project_references.import_file(base, image, collection="Characters")["id"]
    job = Job.create("raygun", "one", base=base, asset_type="item")
    client = StubClient()
    monkeypatch.setattr(generate, "ComfyClient", lambda: client)
    queue = Queue(base)
    task = queue.submit(job.root, "anchor", {"describe": "a fictional turquoise ray gun",
                                             "project_reference_id": ref_id, "seed": 7})
    Worker(queue)._execute(task)
    assert queue.get(task["id"])["status"] == "done"
    [(slot, values)] = client.calls
    assert slot == "anchor_still"
    assert set(values) == {"prompt", "seed"}
    assert values["seed"] == 7
    assert "a fictional turquoise ray gun" in values["prompt"]
    assert "shown on its own" in values["prompt"]
    assert "#753761" in values["prompt"] and "#008855" in values["prompt"]
    meta = job.read_meta()
    assert meta["inputs"]["asset_type"] == "item"
    assert meta["provenance"][-1]["style_palette"] == ["#753761", "#008855"]
    assert meta["stages"]["anchor"]["status"] == "review"
    assert manifest.read(job)["project_reference_id"] == ref_id


def test_item_anchor_requires_a_visible_reference(tmp_path):
    ref = tmp_path / "transparent.png"
    Image.new("RGBA", (16, 16), (24, 75, 92, 0)).save(ref)
    job = Job.create("item", "one", base=tmp_path, asset_type="item")
    client = StubClient()
    with pytest.raises(ValueError, match="visible colours"):
        generate.anchor(job, GameProfile(name="default"), client, description="a scarf", style_ref=ref)
    assert client.calls == []


def test_item_anchor_from_approved_hero_uses_only_visible_colours(tmp_path):
    job = Job.create("item", "one", base=tmp_path, asset_type="item")
    hero = Job.create("hero", "one", base=tmp_path)
    ref = hero.stage_dir("01_anchor") / "anchor.png"
    image = Image.new("RGBA", (16, 16), (34, 90, 124, 0))
    image.paste("#882a30", (3, 3, 10, 12))
    image.save(ref)
    hero.set_stage("anchor", "approved")
    client = StubClient()
    generate.anchor(job, GameProfile(name="default"), client, description="a scarf", style_ref=hero.root)
    [(slot, values)] = client.calls
    assert slot == "anchor_still" and "ref_images" not in values
    assert job.read_meta()["provenance"][-1]["style_palette"] == ["#882a30"]


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


def test_cli_and_mcp_preserve_saved_item_type(library, monkeypatch):
    from spritewaffle import cli
    base, ref_id, _ = library
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(base))
    client = StubClient()
    monkeypatch.setattr(generate, "ComfyClient", lambda: client)
    args = ["anchor", "--job", "item/one", "--describe", "a scarf", "--project-reference", ref_id]
    assert cli.main([*args, "--asset-type", "item"]) == 0
    assert cli.main(args) == 0
    assert [slot for slot, _ in client.calls] == ["anchor_still", "anchor_still"]

    mcp, queue = build(base)
    response = text(call(mcp, "generate", character="item", job_id="one", description="a scarf",
                         project_reference_id=ref_id))
    task = queue.get(response["tasks"][0])
    Worker(queue)._execute(task)
    assert queue.get(task["id"])["status"] == "done"
    assert client.calls[-1][0] == "anchor_still"
