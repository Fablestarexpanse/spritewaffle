import asyncio
import json
from pathlib import Path

import pytest
from PIL import Image

from spritewaffle.core import generate
from spritewaffle.core.job import Job
from spritewaffle.core.profile import GameProfile
from spritewaffle.mcp_server import build
from spritewaffle.prompts import builder
from synth import draw_sprite, render
from test_generate import StubClient


def call(m, name, **args):
    return asyncio.run(m.call_tool(name, args))


def text(res) -> dict:
    blocks = res[0] if isinstance(res, tuple) else res
    return json.loads(blocks[0].text)


@pytest.fixture
def srv(tmp_path):
    m, q = build(tmp_path)
    return m, q, tmp_path


def test_generate_anchor_creates_job_and_queues(srv):
    m, q, base = srv
    out = text(call(m, "generate", character="elf", description="a forest elf", asset_type="creature"))
    t = q.list()[0]
    assert t["stage"] == "anchor" and t["args"]["asset_type"] == "creature"
    assert (base / "elf" / out["job_id"] / "job.json").exists() and out["tasks"] == [t["id"]]


def test_bad_inputs_are_refused(srv):
    m, q, base = srv
    for args in ({"character": "elf", "description": "x", "asset_type": "vehicle"},
                 {"character": "elf", "stage": "sprites"},
                 {"character": "elf", "stage": "facings"}):
        with pytest.raises(Exception):
            call(m, "generate", **args)
    assert q.list() == []


def test_animate_needs_approved_facings_and_status_reports(srv):
    m, q, base = srv
    job = Job.create("hero", "j", base=base)
    Image.fromarray(render(draw_sprite(), canvas=(256, 256))).save(job.root / "01_anchor" / "anchor.png")
    job.set_stage("anchor", "review")
    with pytest.raises(Exception, match="not approved"):
        call(m, "animate", character="hero", job_id="j", facing="S", action="walk")
    call(m, "approve", character="hero", job_id="j", stage="anchor")
    job.set_stage("facings", "approved")
    out = text(call(m, "animate", character="hero", job_id="j", facing="E", action="walk", seconds=3))
    assert len(out["tasks"]) == 5 and q.get(out["tasks"][0])["args"]["seconds"] == 3
    with pytest.raises(Exception):
        call(m, "animate", character="hero", job_id="j", facing="UP", action="walk")
    res = call(m, "status", character="hero", job_id="j", include_images=True)
    blocks = res[0] if isinstance(res, tuple) else res
    st = json.loads(blocks[0].text)
    assert st["stages"]["anchor"] == "approved" and len(st["open_tasks"]) == 5
    assert any(getattr(b, "type", "") == "image" for b in blocks[1:])
    assert "hero" in [j["character"] for j in text(call(m, "status"))["jobs"]]


def test_unknown_job_refused(srv):
    m, q, base = srv
    with pytest.raises(Exception):
        call(m, "status", character="..", job_id="..")


def test_hero_style_ref_uses_edit_template_and_requires_approval(tmp_path):
    hero = Job.create("hero", "h", base=tmp_path)
    Image.fromarray(render(draw_sprite(), canvas=(256, 256))).save(hero.root / "01_anchor" / "anchor.png")
    hero.set_stage("anchor", "review")
    new = Job.create("orc", "o", base=tmp_path)
    with pytest.raises(RuntimeError, match="approve"):
        generate.anchor(new, GameProfile(name="p"), client=StubClient(), description="an orc", style_ref=hero.root)
    generate.approve(hero, "anchor")
    c = StubClient()
    generate.anchor(new, GameProfile(name="p"), client=c, description="an orc", style_ref=hero.root)
    slot, v = c.calls[0]
    assert slot == "facing_multiref" and Path(v["ref_images"][0]).name == "anchor.png"
    assert "same art style as <Picture 1>" in v["prompt"] and "an orc" in v["prompt"]
    assert new.read_meta()["inputs"]["style_ref"] == str(hero.root)


def test_asset_presets():
    p = GameProfile(name="p")
    assert builder.anchor("a lamp", p, asset_type="prop").startswith("Single video game prop sprite: a lamp.")
    assert builder.asset("prop")["actions"] == ["idle"]
    with pytest.raises(ValueError):
        builder.asset("vehicle")


def test_stack_tool_needs_approved_anchor(srv):
    m, q, base = srv
    job = Job.create("chest", "c", base=base)
    job.set_stage("anchor", "review")
    with pytest.raises(Exception, match="not approved"):
        call(m, "stack", character="chest", job_id="c")
    out = text(call(m, "stack", character="chest", job_id="c", regenerate_views=False, height=20))
    assert [q.get(t)["stage"] for t in out["tasks"]] == ["stack"]
