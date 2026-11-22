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
