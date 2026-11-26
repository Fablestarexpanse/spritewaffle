"""Edit the prompt behind one generated view, then re-roll it (core/prompt_edit.py)."""
from fastapi.testclient import TestClient

from spritewaffle.core import generate, prompt_edit, variant
from spritewaffle.core.profile import GameProfile
from spritewaffle.ui.server import create_app
from test_variant import FakeComfy, _base

import pytest


def _variant(tmp_path):
    b = _base(tmp_path)
    b.set_stage("facings", "approved")
    v = variant.create(b, "add a long green cape")
    c = FakeComfy()
    variant.anchor(v, GameProfile(name="p"), client=c)
    v.set_stage("anchor", "approved")
    generate.facings(v, GameProfile(name="p"), client=c)
    return v, c


def test_saved_prompt_replaces_the_built_one_for_that_view_only(tmp_path):
    v, c = _variant(tmp_path)
    built = prompt_edit.used(v, "02_facings/NE.png")
    assert built and "cape" in built
    prompt_edit.set_prompt(v, r"02_facings\NE.png", "  the knight from behind, plain cape, no buckle  ")  # Windows separator
    assert prompt_edit.get(v, "02_facings/NE.png")["custom"] == "the knight from behind, plain cape, no buckle"
    c.calls.clear()
    generate.facings(v, GameProfile(name="p"), client=c, only=["NE", "E"])
    prompts = [vals["prompt"] for _, vals in c.calls]
    assert prompts[0] != "the knight from behind, plain cape, no buckle"            # E: built prompt
    assert prompts[1] == "the knight from behind, plain cape, no buckle"            # NE: the edit
    assert prompt_edit.used(v, "02_facings/NE.png") == prompts[1]
    assert v.read_meta()["provenance"][-1]["prompt_edited"] is True
    prompt_edit.set_prompt(v, "02_facings/NE.png", "")
    assert "prompt_overrides" not in v.read_meta()["inputs"]


def test_prompt_paths_are_checked_and_http_round_trips(tmp_path):
    v, _ = _variant(tmp_path)
    for bad in ("../x.png", "02_facings/NE.txt", ""):
        with pytest.raises(ValueError):
            prompt_edit.get(v, bad)
    with TestClient(create_app(tmp_path, worker=False)) as client:
        route = f"/api/jobs/knight/{v.root.name}/prompt"
        got = client.get(route, params={"file": "02_facings/NE.png"}).raise_for_status().json()
        assert got["used"] and got["custom"] is None
        saved = client.post(route, json={"file": "02_facings/NE.png", "prompt": "new words"}).raise_for_status().json()
        assert saved["custom"] == "new words"
        assert client.get(route, params={"file": "../x.png"}).status_code == 400
