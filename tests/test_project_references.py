import base64
import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle import cli
from spritewaffle.core import camera, fsutil, project, project_references as refs
from spritewaffle.mcp_server import build
from spritewaffle.ui.server import create_app
from test_mcp import call, text


def image_bytes(fmt="PNG", size=(240, 120)):
    buf = BytesIO()
    Image.new("RGB", size, (120, 65, 185)).save(buf, fmt)
    return buf.getvalue()


def test_reference_keeps_original_and_identity_through_edits_and_move(tmp_path):
    base = tmp_path / "jobs"
    source = tmp_path / "Héro.png"
    data = image_bytes()
    source.write_bytes(data)
    camera.set_project(base, {"light_yaw": 64}, "story")
    project.set_style(base, {"default_style": "painted"})

    added = refs.import_file(base, source, collection="Characters", notes="Warm highlights")
    ref_id = added["id"]
    assert added["name"] == "Héro" and added["filename"] == source.name
    assert (added["width"], added["height"]) == (240, 120)
    assert refs.image(base, ref_id).read_bytes() == data
    with Image.open(refs.image(base, ref_id, thumbnail=True)) as thumbnail:
        assert thumbnail.size == (192, 96)
    assert refs.update(base, ref_id, {"name": "Approved hero", "collection": "Approved"})["id"] == ref_id
    camera.set_project(base, {"light_yaw": 70})
    project.set_style(base, {"target_engine": "Godot"})

    moved = base.rename(tmp_path / "new-project")
    assert camera.project(moved)["camera"]["light_yaw"] == 70
    assert project.style(moved)["style"]["target_engine"] == "Godot"
    assert refs.list_all(moved)[0]["collection"] == "Approved"
    assert refs.list_all(moved)[0]["notes"] == "Warm highlights"
    assert refs.image(moved, ref_id).read_bytes() == source.read_bytes() == data

    refs.update(moved, ref_id, {"archived": True})
    assert refs.list_all(moved) == []
    assert refs.list_all(moved, include_archived=True)[0]["archived"]
    assert refs.image(moved, ref_id).read_bytes() == data
    assert refs.update(moved, ref_id, {"archived": False})["name"] == "Approved hero"


def test_import_cleans_up_its_copies_if_project_save_fails(tmp_path, monkeypatch):
    base = tmp_path / "jobs"
    camera.set_project(base, {"light_yaw": 64}, "story")
    project_before = (base / "project.json").read_bytes()

    def save_error(*_):
        raise OSError("project disk is full")

    monkeypatch.setattr(fsutil, "write_text", save_error)
    with pytest.raises(OSError, match="disk is full"):
        refs.add(base, image_bytes(), "sketch.png")
    assert list((base / "_references").iterdir()) == []
    assert refs.list_all(base) == []
    assert (base / "project.json").read_bytes() == project_before


def test_refuses_bad_images_and_metadata_without_writes_and_reports_missing_files(tmp_path, monkeypatch):
    base = tmp_path / "jobs"
    assert refs.list_all(base) == []
    for data in (b"<svg></svg>", image_bytes("GIF"), image_bytes()[:-20]):
        with pytest.raises(ValueError, match="image"):
            refs.add(base, data, "not-a-valid.png")
    assert not base.exists()
    original_max = refs.MAX_IMAGE_PIXELS
    monkeypatch.setattr(refs, "MAX_IMAGE_PIXELS", 10)
    with pytest.raises(ValueError, match="pixels"):
        refs.add(base, image_bytes(), "large.png")
    monkeypatch.setattr(refs, "MAX_IMAGE_PIXELS", original_max)
    added = refs.add(base, image_bytes("JPEG"), r"C:\Users\Test\sketch.png")
    assert added["name"] == "sketch" and added["filename"] == "sketch.png" and added["format"] == "JPEG"
    ref_id = added["id"]
    saved = (base / "project.json").read_bytes()
    for fields in ({"filename": "other.png"}, {"archived": "true"}, {"name": " "}):
        with pytest.raises(ValueError):
            refs.update(base, ref_id, fields)
        assert (base / "project.json").read_bytes() == saved
    with pytest.raises(ValueError):
        refs.image(base, "../sketch")

    refs.image(base, ref_id).unlink()
    assert refs.list_all(base)[0]["available"] is False
    with pytest.raises(FileNotFoundError):
        refs.image(base, ref_id)
    (base / "project.json").write_text(json.dumps(json.loads(saved) | {"schema_version": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="newer"):
        refs.update(base, ref_id, {"archived": True})
    with pytest.raises(ValueError, match="newer"):
        refs.add(base, image_bytes(), "another.png")


def test_reference_library_http_cli_and_mcp(tmp_path, monkeypatch, capsys):
    base = tmp_path / "jobs"
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(base))
    route = "/api/project/references"
    data = image_bytes()
    payload = {"data": base64.b64encode(data).decode("ascii"), "filename": "hero.png",
               "name": "Hero", "collection": "Characters"}
    with TestClient(create_app(base, worker=False)) as client:
        assert client.get(route).json() == []
        assert client.post(route, json=payload | {"data": "%%%"}).status_code == 400
        assert client.post(route, json=payload | {"name": False}).status_code == 400
        response = client.post(route, json=payload)
        assert response.status_code == 200, response.text
        ref_id = response.json()["id"]
        file_url = f"{route}/{ref_id}/image"
        assert client.get(file_url).content == data
        assert client.get(file_url + "?thumbnail=true").headers["content-type"] == "image/png"
        assert client.get(f"{route}/{'0' * 32}/image").status_code == 404
        assert client.post(f"{route}/{ref_id}", json={"archived": True}).status_code == 200
        assert client.get(route).json() == []
        assert client.get(route + "?include_archived=true").json()[0]["id"] == ref_id

    assert cli.main(["project-references", "restore", ref_id]) == 0
    assert json.loads(capsys.readouterr().out)["archived"] is False
    mcp, _ = build(base)
    listed = text(call(mcp, "project_references", action="list"))
    assert listed["references"][0]["id"] == ref_id
    edited = text(call(mcp, "project_references", action="update", reference_id=ref_id, fields={"notes": "Use scarf"}))
    assert edited["notes"] == "Use scarf"
    preview = call(mcp, "project_reference_image", reference_id=ref_id)
    assert preview[0].type == "image" and preview[0].mimeType == "image/png"
    assert cli.main(["project-references", "path", ref_id]) == 0
    assert capsys.readouterr().out.strip() == str(refs.image(base, ref_id))
