import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from spritewaffle.ui.server import create_app


def atlas_bytes():
    image = Image.new("RGBA", (19, 11))
    image.paste("#67b652", (1, 1, 9, 10))
    image.paste("#f0a43d", (10, 2, 16, 8))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def test_tileset_http_import_collision_and_portable_export(tmp_path):
    from base64 import b64encode

    original = atlas_bytes()
    grid = {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1}
    root = "/api/jobs/ground/one"
    with TestClient(create_app(tmp_path, worker=False)) as client:
        assert client.post("/api/jobs", json={"character": "ground", "job_id": "one", "asset_type": "tileset"}).status_code == 200
        assert client.get(root).json()["asset_type"] == "tileset"
        payload = {"data": b64encode(original).decode("ascii"), "filename": "ground.png", "grid": grid}
        malformed = client.post(root + "/tileset/import", json=payload | {"grid": grid | {"tile_width": 7}})
        assert malformed.status_code == 400
        assert "fit" in malformed.json()["detail"]
        assert client.get(root + "/tileset").json()["tileset"] is None
        result = client.post(root + "/tileset/import", json=payload).json()
        state = result["tileset"]
        assert client.get(result["preview"]).content == original
        assert state["grid"]["columns"] == 2 and state["grid"]["rows"] == 1
        assert state["empty_tiles"] == []
        params = {"tile": 1, "solid": True, "revision": result["revision"]}
        result = client.post(root + "/tileset/collision", json=params).json()
        assert result["tileset"]["solid_tiles"] == [1]
        assert client.post(root + "/tileset/collision", json=params | {"tile": 0}).status_code == 400
        result = client.post(root + "/tileset/export", json={}).json()
        assert result["export"]["status"] == "current"
        files = result["files"]
        generic = client.get(files["tileset.json"]).json()
        tiled = client.get(files["tileset.tsj"]).json()
        assert client.get(files["tiles.png"]).content == original
        assert generic["tiles"][1] == {"id": 1, "rect": [10, 1, 8, 9], "empty": False, "solid": True}
        assert tiled["image"] == "tiles.png" and tiled["tilecount"] == 2 and tiled["spacing"] == 1
        assert tiled["tiles"][0]["id"] == 1
        collision = tiled["tiles"][0]["objectgroup"]["objects"][0]
        assert [collision[key] for key in ("x", "y", "width", "height")] == [0, 0, 8, 9]
        final = client.post(root + "/tileset/collision", json={"tile": 1, "solid": False, "revision": result["revision"]}).json()
        assert final["export"]["status"] == "stale"
        assert client.get(files["tileset.tsj"]).json() == tiled


def test_tileset_cli_mcp_preserve_empty_ids_and_import_history(tmp_path, monkeypatch, capsys):
    from spritewaffle import cli
    from spritewaffle.core import manifest, tileset
    from spritewaffle.core.job import Job
    from spritewaffle.mcp_server import build
    from test_mcp import call, text

    base = tmp_path / "jobs"
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(base))
    file = tmp_path / "terrain.png"
    image = Image.new("RGBA", (32, 16))
    image.paste("#4987b9", (16, 0, 32, 16))
    image.save(file)
    args = ["--job", "terrain/imported"]
    assert cli.main(["tileset", "import", *args, "--file", str(file)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["tileset"]["empty_tiles"] == [0]
    job = Job.open(base / "terrain/imported")
    assert manifest.read(job)["tileset"] == "01_tileset/tileset.json"
    source = job.root / result["preview"]
    assert cli.main(["tileset", "collision", *args, "--tile", "1"]) == 0
    first = json.loads(capsys.readouterr().out)
    mcp, _ = build(base)
    params = {"character": "terrain", "job_id": "imported"}
    assert text(call(mcp, "tileset", **params)) == first
    package = text(call(mcp, "tileset", **params, operation="export"))
    metadata = json.loads((job.root / package["files"]["tileset.json"]).read_text(encoding="utf-8"))
    assert metadata["tiles"][0] == {"id": 0, "rect": [0, 0, 16, 16], "empty": True, "solid": False}
    replacement = text(call(mcp, "tileset", **params, operation="import", path=str(file),
                            grid={"tile_width": 8, "tile_height": 8}))
    assert replacement["tileset"]["solid_tiles"] == []
    history = job.root / "01_tileset/history" / (first["revision"] + ".json")
    assert json.loads(history.read_text(encoding="utf-8"))["solid_tiles"] == [1]
    assert source.read_bytes() == file.read_bytes()
    assert replacement["export"]["status"] == "stale"
    assert tileset.inspect(job)["tileset"]["grid"]["columns"] == 4


def test_terrain_preview_matches_shared_corners_and_exports_wang_ids(tmp_path):
    from base64 import b64encode

    route = "/api/jobs/ground/one/tileset"
    grid = {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1}
    ground = {"colors": ["Grass", "Water"], "tiles": {"0": ["Grass"] * 4,
              "1": ["Grass", "Water", "Water", "Grass"]}}
    with TestClient(create_app(tmp_path, worker=False)) as client:
        assert client.post("/api/jobs", json={"character": "ground", "job_id": "one", "asset_type": "tileset"}).is_success
        first = client.post(route + "/import", json={"data": b64encode(atlas_bytes()).decode("ascii"),
                            "filename": "ground.png", "grid": grid}).json()
        assert client.post(route + "/export").json()["export"]["status"] == "current"
        saved = client.post(route + "/terrain", json={"terrain": ground, "revision": first["revision"]})
        assert saved.status_code == 200
        assert saved.json()["tileset"]["terrain"] == ground and saved.json()["export"]["status"] == "stale"
        assert client.post(route + "/terrain", json={"terrain": ground, "revision": "old"}).status_code == 400
        bad = client.post(route + "/terrain", json={"terrain": ground | {"colors": ["Grass"]}})
        assert bad.status_code == 400 and "Water" in bad.json()["detail"]
        assert client.get(route).json()["tileset"]["terrain"] == ground

        vertices = [["Grass", "Grass", "Water", "Water"], ["Grass", "Grass", "Water", "Water"]]
        preview = client.post(route + "/preview", json={"vertices": vertices}).json()
        assert preview == {"width": 3, "height": 1, "tiles": [[0, 1, None]], "missing": [[2, 0]]}
        blank = client.post(route + "/preview", json={"vertices": [[None, None], [None, None]]}).json()
        assert blank["tiles"] == [[None]] and not blank["missing"]
        assert client.post(route + "/preview", json={"vertices": [["Grass", "Grass"], ["Grass"]]}).status_code == 400

        exported = client.post(route + "/export").json()
        native, tiled = (client.get(exported["files"][f"tileset.{ext}"]).json() for ext in ("json", "tsj"))
        assert native["terrain"] == ground
        rules, = tiled["wangsets"]
        assert rules["type"] == "corner" and [color["name"] for color in rules["colors"]] == ["Grass", "Water"]
        assert rules["wangtiles"] == [{"tileid": 0, "wangid": [0, 1, 0, 1, 0, 1, 0, 1]},
                                      {"tileid": 1, "wangid": [0, 2, 0, 2, 0, 1, 0, 1]}]


def test_terrain_cli_mcp_and_reimport_share_tile_assignments(tmp_path, monkeypatch, capsys):
    from spritewaffle import cli
    from spritewaffle.core import tileset
    from spritewaffle.mcp_server import build
    from test_mcp import call, text

    base = tmp_path / "jobs"
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(base))
    job = tileset.create(base, "terrain", "one")
    grid = {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1}
    atlas = atlas_bytes()
    tileset.import_bytes(job, atlas, "atlas.png", grid)
    rules = tmp_path / "terrain.json"
    terrain = {"colors": ["Grass"], "tiles": {"1": ["Grass"] * 4, "0": ["Grass"] * 4}}
    rules.write_text(json.dumps(terrain), encoding="utf-8")
    args = ["--job", "terrain/one"]
    assert cli.main(["tileset", "terrain", *args, "--file", str(rules)]) == 0
    assert json.loads(capsys.readouterr().out)["tileset"]["terrain"] == terrain
    assert tileset.import_bytes(job, atlas, "atlas.png", grid)["tileset"]["terrain"] == terrain

    mcp, _ = build(base)
    params = {"character": "terrain", "job_id": "one"}
    actual = text(call(mcp, "tileset", **params, operation="preview", vertices=[["Grass"] * 2] * 2))
    assert actual["tiles"] == [[0]] and actual["missing"] == []


def test_tile_animation_retains_collision_and_exports_frame_order(tmp_path):
    from base64 import b64encode

    route = "/api/jobs/water/one/tileset"
    image = atlas_bytes()
    payload = {"data": b64encode(image).decode("ascii"), "filename": "water.png",
               "grid": {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1}}
    frames = [{"tile": 1, "duration_ms": 70}, {"tile": 0, "duration_ms": 230}]
    with TestClient(create_app(tmp_path, worker=False)) as client:
        assert client.post("/api/jobs", json={"character": "water", "job_id": "one", "asset_type": "tileset"}).is_success
        assert client.post(route + "/import", json=payload).is_success
        first = client.post(route + "/collision", json={"tile": 1, "solid": True}).json()
        client.post(route + "/export").raise_for_status()
        saved = client.post(route + "/animation", json={"tile": 1, "frames": frames, "revision": first["revision"]})
        assert saved.status_code == 200
        assert saved.json()["tileset"]["animations"] == {"1": frames}
        assert saved.json()["export"]["status"] == "stale"
        for bad in ([frames[0]], [frames[0], {"tile": 2, "duration_ms": 70}],
                    [frames[0], {"tile": 0, "duration_ms": 0}],
                    [frames[0], {"tile": 0, "duration_ms": 60001}],
                    [frames[0], {"tile": False, "duration_ms": 70}]):
            assert client.post(route + "/animation", json={"tile": 1, "frames": bad}).status_code == 400
        assert client.post(route + "/animation", json={"tile": 1, "frames": [], "revision": first["revision"]}).status_code == 400
        assert client.post(route + "/import", json=payload).json()["tileset"]["animations"] == {"1": frames}
        exported = client.post(route + "/export").json()
        native, tiled = (client.get(exported["files"][f"tileset.{ext}"]).json() for ext in ("json", "tsj"))
        assert native["tiles"][1]["animation"] == frames and native["tiles"][1]["solid"]
        tile, = tiled["tiles"]
        assert tile["id"] == 1 and tile["objectgroup"]["objects"][0]["width"] == 8
        assert tile["animation"] == [{"tileid": 1, "duration": 70}, {"tileid": 0, "duration": 230}]
        state = client.post(route + "/animation", json={"tile": 1, "frames": []}).json()
        assert "animations" not in state["tileset"] and state["export"]["status"] == "stale"


def test_tile_animation_cli_and_mcp_share_durations(tmp_path, monkeypatch, capsys):
    from spritewaffle import cli
    from spritewaffle.core import tileset
    from spritewaffle.mcp_server import build
    from test_mcp import call, text

    base = tmp_path / "jobs"
    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(base))
    job = tileset.create(base, "terrain", "anim")
    tileset.import_bytes(job, atlas_bytes(), "atlas.png", {"tile_width": 8, "tile_height": 9, "margin": 1, "spacing": 1})
    file = tmp_path / "animation.json"
    frames = [{"tile": 0, "duration_ms": 200}, {"tile": 1, "duration_ms": 120}]
    file.write_text(json.dumps(frames), encoding="utf-8")
    args = ["--job", "terrain/anim", "--tile", "0"]
    assert cli.main(["tileset", "animation", *args, "--file", str(file)]) == 0
    expected = json.loads(capsys.readouterr().out)
    mcp, _ = build(base)
    params = {"character": "terrain", "job_id": "anim"}
    assert text(call(mcp, "tileset", **params)) == expected
    changed = text(call(mcp, "tileset", **params, operation="animation", tile=0, frames=list(reversed(frames))))
    assert changed["tileset"]["animations"] == {"0": list(reversed(frames))}
    assert cli.main(["tileset", "animation", *args, "--clear"]) == 0
    assert "animations" not in json.loads(capsys.readouterr().out)["tileset"]
