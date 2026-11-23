import json
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.core import tileset
from spritewaffle.ui.server import create_app


def source(base):
    atlas = Image.new("RGBA", (24, 16))
    for tile in (0, 1, 2, 3, 5):
        x, y = tile % 3 * 8, tile // 3 * 8
        atlas.paste((50 * tile, 80, 120, 255), (x, y, x + 8, y + 8))
    png = BytesIO()
    atlas.save(png, "PNG")
    data = png.getvalue()
    grid = {"tile_width": 8, "tile_height": 8}
    job = tileset.create(base, "building", "v1")
    tileset.import_bytes(job, data, "building.png", grid)
    tileset.collision(job, 0, True)
    return job, data, grid


def test_assemble_and_export_a_module_with_a_transparent_doorway(tmp_path):
    job, data, grid = source(tmp_path)
    route = "/api/jobs/building/v1/tileset"
    vertices = [[None] * 5 for _ in range(4)]
    with TestClient(create_app(tmp_path, worker=False)) as client:
        initial = client.post(route + "/export").raise_for_status().json()
        draft = {"name": "Doorway", "start": 5, "end": 0, "revision": initial["revision"]}
        for change in ({"start": True}, {"end": 6}, {"name": ""}, {"start": 4, "end": 4}):
            assert client.post(route + "/modules", json=draft | change).status_code == 400
        saved = client.post(route + "/modules", json=draft).raise_for_status().json()
        module, = saved["tileset"]["modules"]
        assert module == {"name": "Doorway", "width": 3, "height": 2, "tiles": [[0, 1, 2], [3, None, 5]]}
        assert saved["export"]["status"] == "stale"
        assert client.post(route + "/modules", json=draft | {"revision": saved["revision"], "name": "doorway"}).status_code == 400
        stamp = {"name": "Doorway", "cell": 1, "vertices": vertices, "overrides": {"6": 0},
                 "revision": saved["revision"], "override_atlas": saved["atlas_revision"]}
        for change in ({"cell": 2}, {"cell": True}, {"revision": initial["revision"]}, {"override_atlas": "0" * 64}):
            assert client.post(route + "/stamp", json=stamp | change).status_code == 400
        placed = client.post(route + "/stamp", json=stamp).raise_for_status().json()
        assert placed["overrides"] == {"1": 0, "2": 1, "3": 2, "5": 3, "6": 0, "7": 5}
        assert placed["override_atlas"] == saved["atlas_revision"]
        map_record = client.post(route + "/maps", json={"name": "Workshop", "vertices": vertices, **placed}).raise_for_status().json()
        result = client.post(route + "/maps/" + map_record["id"] + "/export").raise_for_status().json()
    with ZipFile(job.root / result["file"]) as output:
        assert output.read("tiles.png") == data
        assert json.loads(output.read("tileset.json"))["modules"] == [module]
        tiled = json.loads(output.read("map.tmj"))
        assert tiled["layers"][0]["data"] == [0, 1, 2, 3, 0, 4, 1, 6, 0, 0, 0, 0]
        assert json.loads(output.read("tileset.tsj"))["tiles"][0]["objectgroup"]["objects"][0]["height"] == 8
    same = tileset.import_bytes(job, data, "building-copy.png", grid)
    assert same["tileset"]["modules"] == [module]
    replacement = tileset.import_bytes(job, data, "retiled.png", {"tile_width": 4, "tile_height": 8})
    assert "modules" not in replacement["tileset"]
    history = job.root / tileset.DIRECTORY / "history" / (same["revision"] + ".json")
    assert json.loads(history.read_text(encoding="utf-8"))["modules"] == [module]


def test_module_cli_and_mcp_share_draft_placement(tmp_path, monkeypatch, capsys):
    from spritewaffle import cli
    from spritewaffle.mcp_server import build
    from test_mcp import call, text

    source(tmp_path)
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    path = tmp_path / "module.json"
    path.write_text(json.dumps({"name": "Lintel", "start": 0, "end": 2}), encoding="utf-8")
    args = ["--job", "building/v1", "--file", str(path)]
    assert cli.main(["tileset", "module", *args]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["tileset"]["modules"][0]["tiles"] == [[0, 1, 2]]
    stamp = {"name": "Lintel", "cell": 0, "vertices": [[None] * 4] * 2}
    path.write_text(json.dumps(stamp), encoding="utf-8")
    assert cli.main(["tileset", "stamp", *args]) == 0
    placed = json.loads(capsys.readouterr().out)
    mcp, _ = build(tmp_path)
    actual = text(call(mcp, "tileset", character="building", job_id="v1", operation="stamp", module=stamp))
    assert placed == actual and actual["overrides"] == {"0": 0, "1": 1, "2": 2}
