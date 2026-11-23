import json
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import tileset
from spritewaffle.ui.server import create_app


def packed_atlas(base):
    image = Image.new("RGBA", (30, 16), (255, 255, 0, 255))
    for tile in range(6):
        x, y = 1 + tile % 3 * 10, 1 + tile // 3 * 8
        rgba = (0, 0, 0, 0) if tile == 4 else (45 * tile, 90, 130, 128 if tile == 1 else 255)
        image.paste(rgba, (x, y, x + 8, y + 6))
    png = BytesIO()
    image.save(png, "PNG")
    job = tileset.create(base, "workshop", "one")
    imported = tileset.import_bytes(job, png.getvalue(), "walls.png",
                                    {"tile_width": 8, "tile_height": 6, "margin": 1, "spacing": 2})
    for tile in (0, 3, 4, 5):
        tileset.collision(job, tile, True)
    tileset.update_animation(job, 0, [{"tile": 1, "duration_ms": 130}, {"tile": 2, "duration_ms": 230}])
    state = tileset.save_module(job, "Arch / stone", 0, 5)
    return job, png.getvalue(), imported["preview"], state["revision"]


def test_module_zip_preserves_pixels_holes_pivot_and_collision(tmp_path):
    job, atlas, source, revision = packed_atlas(tmp_path)
    path = "/api/jobs/workshop/one/tileset/modules/export"
    with TestClient(create_app(tmp_path, worker=False)) as client:
        response = client.post(path, json={"name": "Arch / stone", "revision": revision}).raise_for_status().json()
        original = client.get(response["download"]).raise_for_status().content
        with ZipFile(BytesIO(original)) as archive:
            assert set(archive.namelist()) == {"module.png", "module.json"}
            spec = json.loads(archive.read("module.json"))
            assert spec["schema_version"] == 1 and spec["image"] == "module.png"
            assert spec["name"] == "Arch / stone" and spec["size"] == [24, 12]
            assert spec["pivot"] == [12, 12]
            assert spec["collision"] == [
                {"x": 0, "y": 0, "width": 8, "height": 6},
                {"x": 0, "y": 6, "width": 8, "height": 6},
                {"x": 16, "y": 6, "width": 8, "height": 6},
            ]
            with Image.open(BytesIO(archive.read("module.png"))) as sprite:
                assert sprite.mode == "RGBA" and sprite.size == (24, 12)
                assert sprite.getpixel((0, 0)) == (0, 90, 130, 255)
                assert sprite.getpixel((8, 0)) == (45, 90, 130, 128)
                assert sprite.getpixel((8, 6)) == (0, 0, 0, 0)
        for invalid in ({"pivot": [25, 12]}, {"pivot": [False, 1]}, {"pivot": [1, 1.5]},
                        {"pivot": [1]}, {"name": "../missing"}, {"revision": "stale"}):
            result = client.post(path, json={"name": "Arch / stone"} | invalid)
            assert result.status_code == 400
        custom = client.post(path, json={"name": "Arch / stone", "pivot": [8, 6]}).raise_for_status().json()
        assert custom["file"] != response["file"] and custom["pivot"] == [8, 6]
        with ZipFile(job.root / custom["file"]) as archive:
            assert json.loads(archive.read("module.json"))["pivot"] == [8, 6]
        assert (job.root / response["file"]).read_bytes() == original
        assert (job.root / source).read_bytes() == atlas
        (job.root / source).write_bytes(b"changed")
        assert client.post(path, json={"name": "Arch / stone"}).status_code == 400
        assert (job.root / response["file"]).read_bytes() == original


def test_module_export_uses_same_metadata_in_cli_and_mcp(tmp_path, monkeypatch, capsys):
    from spritewaffle import cli
    from spritewaffle.mcp_server import build
    from test_mcp import call, text

    job, _, _, _ = packed_atlas(tmp_path)
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    draft = {"name": "Arch / stone", "pivot": [4, 7]}
    request = tmp_path / "export.json"
    request.write_text(json.dumps(draft), encoding="utf-8")
    assert cli.main(["tileset", "export-module", "--job", "workshop/one", "--file", str(request)]) == 0
    expected = json.loads(capsys.readouterr().out)
    mcp, _ = build(tmp_path)
    actual = text(call(mcp, "tileset", character="workshop", job_id="one", operation="export-module", module=draft))
    assert expected == actual
    with ZipFile(job.root / actual["file"]) as archive:
        assert json.loads(archive.read("module.json"))["pivot"] == [4, 7]
