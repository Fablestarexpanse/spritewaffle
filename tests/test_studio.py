import asyncio
import json
from pathlib import Path

import pytest

from spritewaffle import cli
from spritewaffle.mcp_server import build
from spritewaffle.ui.server import create_app
from test_mcp import call, text


def test_studio_registry_matches_http_routes(tmp_path):
    from spritewaffle.studio import OPERATIONS

    app = create_app(tmp_path, worker=False)
    routes = {(method, route.path) for route in app.routes for method in getattr(route, "methods", ())}
    assert set(OPERATIONS.values()) <= routes
    assert all("/api/" in path for _, path in OPERATIONS.values())


def test_studio_cli_mcp_and_http_share_job_and_queue_operations(tmp_path, monkeypatch, capsys):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SPRITEWAFFLE_JOBS", str(tmp_path))
    request = tmp_path / "job.json"
    request.write_text(json.dumps({"character": "hero", "job_id": "one", "asset_type": "character"}),
                       encoding="utf-8")
    assert cli.main(["studio", "create-job", "--file", str(request)]) == 0
    assert json.loads(capsys.readouterr().out) == {"character": "hero", "job_id": "one"}

    mcp, _ = build(tmp_path)
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert {"studio", "tileset", "tilemap", "generate", "animation_timeline", "project_references"} <= names
    params = {"character": "hero", "job_id": "one"}
    assert text(call(mcp, "studio", operation="update-job", **params,
                     body={"prompt_writer": "ai"}))["result"] == {"ok": True}
    task = text(call(mcp, "studio", operation="run-stage", **params, body={"stage": "anchor"}))
    task_id, = task["result"]
    assert cli.main(["studio", "cancel-task", "--param", "tid=" + task_id]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "cancelled"
    with TestClient(create_app(tmp_path, worker=False)) as client:
        assert client.get("/api/jobs/hero/one").json()["inputs"]["prompt_writer"] == "ai"
        assert client.get("/api/queue").json()[0]["id"] == task_id


def test_cli_and_mcp_reference_covers_the_studio_catalog(tmp_path):
    from spritewaffle.studio import OPERATIONS

    doc = Path(__file__).resolve().parents[1] / "docs" / "wiki" / "Interfaces.md"
    content = doc.read_text(encoding="utf-8")
    mcp, _ = build(tmp_path)
    registered = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert all(f"`{name}`" in content for name in set(OPERATIONS) | registered)


def test_studio_requires_registered_operation_and_valid_path_parameters(tmp_path):
    from spritewaffle.studio import invoke

    for operation, kwargs in (
        ("unregistered", {}),
        ("job", {"parameters": {"char": "hero"}}),
        ("job", {"parameters": {"char": "..", "jid": "one"}}),
        ("jobs", {"parameters": {"extra": "yes"}}),
        ("jobs", {"body": {}}),
    ):
        with pytest.raises(ValueError):
            asyncio.run(invoke(tmp_path, operation, **kwargs))
