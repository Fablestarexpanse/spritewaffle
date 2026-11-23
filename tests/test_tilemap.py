import asyncio
import json
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from PIL import Image

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
    resource = {"id": "ore", "name": "Ore", "kind": "resource", "cell": 0, "state": "normal",
                "states": [{"name": "normal", "tile": 0}, {"name": "depleted", "tile": 1}]}
    args_mcp = params | {"operation": "save", "name": "North meadow", "objects": [resource],
                         "vertices": saved["vertices"], "revision": saved["revision"], "overrides": {"0": 1}}
    changed = text(asyncio.run(mcp.call_tool("tilemap", args_mcp)))
    assert changed["name"] == "North meadow" and changed["overrides"] == {"0": 1}
    assert changed["objects"][0]["state"] == "normal"
    resource = changed["objects"][0] | {"state": "depleted"}
    vertices.write_text(json.dumps({"vertices": changed["vertices"], "overrides": {"0": None},
                                   "objects": [resource]}), encoding="utf-8")
    assert cli.main(["tilemap", "save", *args, "--name", "North meadow", "--map-id", saved["id"],
                     "--revision", changed["revision"], "--file", str(vertices)]) == 0
    updated = json.loads(capsys.readouterr().out)
    assert updated["overrides"] == {"0": None} and updated["objects"] == [resource]
    assert cli.main(["tilemap", "export", *args, "--map-id", saved["id"]]) == 0
    result = json.loads(capsys.readouterr().out)
    with ZipFile(job.root / result["file"]) as package:
        native = json.loads(package.read("map.json"))
        assert native["name"] == "North meadow" and native["tiles"] == [[None]] and native["objects"] == [resource]


def test_manual_tile_and_empty_cell_override_terrain_without_changing_corners(tmp_path):
    job = meadow(tmp_path)
    route = "/api/jobs/meadow/one/tileset"
    vertices = [["Grass", "Water", "Grass", "Grass"]] * 2
    overrides = {"0": 0, "1": None}
    with TestClient(create_app(tmp_path, worker=False)) as client:
        preview = client.post(route + "/preview", json={"vertices": vertices, "overrides": overrides})
        assert preview.raise_for_status().json()["tiles"] == [[0, None, 0]]
        assert preview.json()["missing"] == []
        for bad in ({"3": 0}, {"01": 0}, {"0": 2}, {"0": True}, [{"0": 0}]):
            preview = client.post(route + "/preview", json={"vertices": vertices, "overrides": bad})
            assert preview.status_code == 400
        draft = {"name": "Manual meadow", "vertices": vertices, "overrides": overrides}
        saved = client.post(route + "/maps", json=draft).raise_for_status().json()
        path = route + "/maps/" + saved["id"]
        assert client.get(path).json() == saved
        assert saved["vertices"] == vertices and saved["overrides"] == overrides
        assert len(saved["override_atlas"]) == 64
        update = {"id": saved["id"], "name": draft["name"], "vertices": vertices, "revision": saved["revision"]}
        assert client.post(route + "/maps", json=update).json() == saved
        result = client.post(path + "/export").raise_for_status().json()
        with ZipFile(BytesIO(client.get(result["download"]).content)) as package:
            assert json.loads(package.read("map.tmj"))["layers"][0]["data"] == [1, 0, 1]
            native = json.loads(package.read("map.json"))
            assert native["overrides"] == overrides and native["vertices"] == vertices
        changed = Image.new("RGBA", (19, 11), "#f00")
        stream = BytesIO()
        changed.save(stream, "PNG")
        tileset.import_bytes(job, stream.getvalue(), "new.png",
                             {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1})
        assert client.get(path).json() == saved
        assert client.post(path + "/export").status_code == 400
        stale = client.post(route + "/preview", json=draft | {
            "override_atlas": saved["override_atlas"], "allow_unknown": True}).raise_for_status().json()
        assert stale["invalid_overrides"] == [[0, 0]]


def test_stateful_door_preserves_ground_and_exports_active_object_tile(tmp_path):
    job = meadow(tmp_path)
    route = "/api/jobs/meadow/one/tileset"
    door = {"id": "front-door", "name": "Front door", "kind": "door", "cell": 1, "state": "closed",
            "states": [{"name": "closed", "tile": 0}, {"name": "open", "tile": 1}]}
    vertices = [["Grass"] * 4] * 3
    body = {"name": "Workshop", "vertices": vertices}
    with TestClient(create_app(tmp_path, worker=False)) as client:
        for bad in (door | {"state": "locked"}, door | {"cell": 6}, door | {"cell": False},
                    door | {"states": [{"name": "closed", "tile": 1}, {"name": "Closed", "tile": 0}]},
                    door | {"states": [{"name": "closed", "tile": True}, {"name": "open", "tile": 1}]}):
            assert client.post(route + "/maps", json=body | {"objects": [bad]}).status_code == 400
        assert client.post(route + "/maps", json=body | {"objects": [door, door | {"id": "side-door"}]}).status_code == 400
        saved = client.post(route + "/maps", json=body | {"objects": [door]}).raise_for_status().json()
        atlas = saved["objects"][0]["atlas"]
        assert saved["objects"] == [door | {"atlas": atlas}]
        resource = route + "/maps/" + saved["id"]
        assert client.get(resource).json() == saved

        def export_object(state, solid, gid):
            exported = client.post(resource + "/export").raise_for_status().json()
            with ZipFile(BytesIO(client.get(exported["download"]).content)) as package:
                native = json.loads(package.read("map.json"))
                assert native["objects"] == [door | {"state": state, "atlas": atlas}]
                tiled = json.loads(package.read("map.tmj"))
                ground, objects = tiled["layers"]
                assert ground["data"] == [1] * 6
                tile_object, = objects["objects"]
                assert tile_object["gid"] == gid and [tile_object["x"], tile_object["y"]] == [8, 9]
                props = {prop["name"]: prop["value"] for prop in tile_object["properties"]}
                assert props["spritewaffle_id"] == "front-door"
                assert props["state"] == state and props["solid"] is solid
                assert json.loads(props["states"]) == door["states"]
            return job.root / exported["file"]

        export_object("closed", True, 1)
        updated = client.post(route + "/maps", json=body | {"id": saved["id"], "revision": saved["revision"],
                              "objects": [door | {"state": "open", "atlas": atlas}]}).raise_for_status().json()
        assert updated["revision"] != saved["revision"]
        package = export_object("open", False, 2)
        assert client.post(route + "/maps", json=body | {"id": saved["id"], "revision": updated["revision"]}).json() == updated
        prior = package.read_bytes()
        image = BytesIO()
        Image.new("RGBA", (19, 11), "#ffa600").save(image, "PNG")
        tileset.import_bytes(job, image.getvalue(), "replacement.png",
                             {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1})
        refused = client.post(resource + "/export")
        assert refused.status_code == 400 and "Front door" in refused.json()["detail"]
        assert package.read_bytes() == prior
