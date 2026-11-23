import asyncio
import json
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient

from spritewaffle.core import tileset
from spritewaffle.ui.server import create_app
from test_tileset import atlas_bytes


def meadow(base):
    job = tileset.create(base, "meadow", "one")
    tileset.import_bytes(job, atlas_bytes(), "meadow.png",
                         {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1})
    tileset.update_terrain(job, {"colors": ["Grass", "Water"],
                                 "tiles": {"0": ["Grass"] * 4, "1": ["Water"] * 4}})
    tileset.collision(job, 0, True)
    tileset.update_animation(job, 0, [{"tile": 0, "duration_ms": 100}, {"tile": 1, "duration_ms": 200}])
    return job


def test_saved_map_round_trip_and_portable_export(tmp_path):
    job = meadow(tmp_path)
    route = "/api/jobs/meadow/one/tileset"
    vertices = [["Grass", "Grass", None, None]] * 2
    with TestClient(create_app(tmp_path, worker=False)) as client:
        assert client.get(route + "/maps").json() == []
        revision = client.get(route).json()["revision"]
        saved = client.post(route + "/maps", json={"name": "South meadow", "vertices": vertices,
                                                  "tileset_revision": revision}).raise_for_status().json()
        assert saved["vertices"] == vertices
        path = route + "/maps/" + saved["id"]
        refused = client.post(path + "/export")
        assert refused.status_code == 400 and "1 unresolved" in refused.json()["detail"]
        assert not (job.root / "06_export" / "maps").exists()

    with TestClient(create_app(tmp_path, worker=False)) as client:
        assert client.get(path).json() == saved
        entries = client.get(route + "/maps").json()
        assert entries == [{"id": saved["id"], "name": saved["name"]}]
        clean = [["Grass", "Grass"]] * 2 + [[None, None]] * 2
        tileset.update_terrain(job, {"colors": ["Grass", "Water"],
                                     "tiles": {"0": ["Grass"] * 4, "1": ["Grass", "Grass", None, None]}})
        body = {"id": saved["id"], "name": "South meadow", "vertices": clean, "revision": saved["revision"]}
        assert client.post(route + "/maps", json=body | {"tileset_revision": revision}).status_code == 400
        updated = client.post(route + "/maps", json=body).raise_for_status().json()
        assert updated["revision"] != saved["revision"]
        assert client.post(route + "/maps", json=body).status_code == 400
        assert client.post(route + "/maps", json=body | {"id": "../bad"}).status_code == 400
        assert client.post(route + "/maps", json={"name": "Invalid", "vertices": [["Unknown"] * 2] * 2}).status_code == 400
        result = client.post(path + "/export").raise_for_status().json()
        download = client.get(result["download"]).raise_for_status()

    with ZipFile(BytesIO(download.content)) as package:
        assert set(package.namelist()) == {"map.tmj", "map.json", "tileset.tsj", "tileset.json", "tiles.png"}
        assert package.read("tiles.png") == atlas_bytes()
        tiled = json.loads(package.read("map.tmj"))
        assert tiled["tilesets"] == [{"firstgid": 1, "source": "tileset.tsj"}]
        assert tiled["orientation"] == "orthogonal" and [tiled["width"], tiled["height"]] == [1, 3]
        assert tiled["layers"][0]["data"] == [1, 2, 0]
        tsj = json.loads(package.read(tiled["tilesets"][0]["source"]))
        assert tsj["image"] == "tiles.png" and "wangsets" in tsj
        assert tsj["tiles"][0]["animation"] == [{"tileid": 0, "duration": 100}, {"tileid": 1, "duration": 200}]
        assert tsj["tiles"][0]["objectgroup"]["objects"][0]["width"] == 8
        native = json.loads(package.read("map.json"))
        assert native["vertices"] == clean and native["tiles"] == [[0], [1], [None]]
        assert native["tileset"] == "tileset.json"

    prior = (job.root / result["file"]).read_bytes()
    tileset.update_terrain(job, {"colors": [], "tiles": {}})
    with TestClient(create_app(tmp_path, worker=False)) as client:
        assert client.get(path).json() == updated
        preview = client.post(route + "/preview", json={"vertices": clean, "allow_unknown": True})
        assert preview.raise_for_status().json()["missing"] == [[0, 0], [0, 1]]
        assert client.post(path + "/export").status_code == 400
    assert (job.root / result["file"]).read_bytes() == prior


def test_saved_map_cli_and_mcp_share_files(tmp_path, monkeypatch, capsys):
    from spritewaffle import cli
    from spritewaffle.mcp_server import build
    from test_mcp import call, text

    base = tmp_path / "jobs"
    job = meadow(base)
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(base))
    vertices = tmp_path / "map.json"
    vertices.write_text(json.dumps([["Grass"] * 2] * 2), encoding="utf-8")
    args = ["--job", "meadow/one"]
    assert cli.main(["tilemap", "save", *args, "--name", "Meadow", "--file", str(vertices)]) == 0
    saved = json.loads(capsys.readouterr().out)
    mcp, _ = build(base)
    params = {"character": "meadow", "job_id": "one", "map_id": saved["id"]}
    assert text(call(mcp, "tilemap", **params, operation="load")) == saved
    args_mcp = params | {"operation": "save", "name": "North meadow",
                         "vertices": saved["vertices"], "revision": saved["revision"]}
    changed = text(asyncio.run(mcp.call_tool("tilemap", args_mcp)))
    assert changed["name"] == "North meadow"
    assert cli.main(["tilemap", "export", *args, "--map-id", saved["id"]]) == 0
    result = json.loads(capsys.readouterr().out)
    with ZipFile(job.root / result["file"]) as package:
        assert json.loads(package.read("map.json"))["name"] == "North meadow"
